#!/usr/bin/env python3
"""
AI plugin - Claude-backed assistant for Hamr via `claude -p`.

Modes:
  - Direct Q&A:     ask anything
  - App suggestion: "find me a video editor" -> ranked installed app list
"""

import json
import os
import select
import signal
import subprocess
import sys
from configparser import ConfigParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin

CONFIG_PATH = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    / "hamr" / "plugins" / "ai" / "config.json"
)

APP_DIRS = [
    Path.home() / ".local/share/applications",
    Path.home() / ".local/share/flatpak/exports/share/applications",
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
]

APP_SUGGESTION_KEYWORDS = [
    "find", "open", "launch", "suggest", "what app", "which app",
    "tool for", "app for", "software for", "program for",
    "how do i", "how can i",
]


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def emit(data: dict) -> None:
    print(json.dumps(data), flush=True)


def query_claude(prompt: str) -> str:
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.stdout.strip() or result.stderr.strip() or "No response"
    except subprocess.TimeoutExpired:
        return "Request timed out"
    except FileNotFoundError:
        return "claude not found — is Claude Code installed?"
    except Exception as e:
        return f"Error: {e}"


def get_installed_apps() -> list[dict]:
    apps = {}
    for app_dir in APP_DIRS:
        if not app_dir.exists():
            continue
        for desktop_file in app_dir.glob("*.desktop"):
            try:
                config = ConfigParser(interpolation=None)
                config.read(desktop_file, encoding="utf-8")
                if not config.has_section("Desktop Entry"):
                    continue
                entry = config["Desktop Entry"]
                if entry.get("Type", "") != "Application":
                    continue
                name = entry.get("Name", "")
                if not name:
                    continue
                app_id = str(desktop_file)
                if app_id not in apps:
                    apps[app_id] = {
                        "id": app_id,
                        "name": name,
                        "icon": entry.get("Icon", "application-x-executable"),
                        "comment": entry.get("Comment", ""),
                        "generic_name": entry.get("GenericName", ""),
                        "categories": [c for c in entry.get("Categories", "").split(";") if c],
                    }
            except Exception:
                continue
    return list(apps.values())


def is_app_suggestion_query(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in APP_SUGGESTION_KEYWORDS)


def suggest_apps(query: str, apps: list[dict]) -> list[dict]:
    app_list = "\n".join(
        f"- {a['name']} ({a.get('generic_name') or ', '.join(a['categories'][:2]) or a.get('comment', '')})"
        for a in apps[:300]
    )
    prompt = (
        f"The user wants to: {query}\n\n"
        f"From this list of installed apps, suggest the 3-5 most relevant ones. "
        f"Reply with ONLY a JSON array of app names, e.g. [\"GIMP\", \"Inkscape\"]. "
        f"No explanation, no markdown, just the JSON array.\n\nInstalled apps:\n{app_list}"
    )

    raw = query_claude(prompt)

    try:
        start = raw.index("[")
        end = raw.rindex("]") + 1
        suggested_names = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return []

    suggested_names_lower = [n.lower() for n in suggested_names]
    results = []
    for app in apps:
        if app["name"].lower() in suggested_names_lower:
            results.append({
                "id": app["id"],
                "name": app["name"],
                "description": app.get("generic_name") or app.get("comment", ""),
                "icon": app["icon"],
                "iconType": "system",
            })

    order = {n.lower(): i for i, n in enumerate(suggested_names)}
    results.sort(key=lambda a: order.get(a["name"].lower(), 99))
    return results


def handle_request(request: dict, apps: list[dict]) -> None:
    step = request.get("step", "search")
    query = request.get("query", "").strip()
    selected_id = request.get("id", "")

    if step == "search":
        if not query:
            emit(HamrPlugin.results(
                [{"id": "__placeholder__", "name": "Ask Claude anything...", "icon": "neurology",
                  "description": "Type a question or 'find me a [tool]'"}],
                input_mode="realtime",
                placeholder="Ask Claude or describe what you need...",
            ))
            return

        emit(HamrPlugin.results(
            [{"id": "__thinking__", "name": f"Thinking: {query}", "icon": "sync",
              "description": "Asking Claude..."}],
            input_mode="realtime",
            placeholder="Ask Claude or describe what you need...",
        ))

        if is_app_suggestion_query(query):
            suggested = suggest_apps(query, apps)
            if suggested:
                results = [
                    {"id": "__header__", "name": f"Claude suggests for: {query}",
                     "icon": "neurology", "description": "via claude -p"},
                    *suggested,
                ]
            else:
                results = [{"id": "__noresult__", "name": "No matching apps found",
                            "icon": "search_off", "description": query}]
        else:
            answer = query_claude(query)
            lines = []
            for para in answer.split("\n"):
                para = para.strip()
                if not para:
                    continue
                while len(para) > 90:
                    lines.append(para[:90])
                    para = para[90:]
                if para:
                    lines.append(para)

            results = [
                {"id": "__answer__", "name": query, "icon": "neurology",
                 "description": "via claude -p"},
                *[{"id": f"__line__{i}", "name": line, "icon": ""}
                  for i, line in enumerate(lines[:20])],
            ]

        emit(HamrPlugin.results(
            results,
            input_mode="realtime",
            placeholder="Ask Claude or describe what you need...",
        ))
        return

    if step == "action":
        if selected_id.startswith("__"):
            return
        for app in apps:
            if app["id"] == selected_id:
                response = HamrPlugin.execute(launch=selected_id, close=True)
                response["name"] = f"Launch {app['name']}"
                response["icon"] = app["icon"]
                response["iconType"] = "system"
                emit(response)
                return
        emit(HamrPlugin.error(f"App not found: {selected_id}"))


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    apps = get_installed_apps()

    while True:
        readable, _, _ = select.select([sys.stdin], [], [], 1.0)
        if readable:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                request = json.loads(line.strip())
                handle_request(request, apps)
            except (json.JSONDecodeError, ValueError):
                continue


if __name__ == "__main__":
    main()
