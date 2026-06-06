#!/usr/bin/env python3
"""
AI plugin - Claude-backed assistant for Hamr via `claude -p`.

Modes (type a prefix to specialize):
  explain/eli5/code/cmd <x>        - explanation / simple explanation / code / shell command
  fix/grammar/proofread/rewrite <x>- text cleanup and rewriting
  shorter/longer/formal/casual <x> - tone and length
  translate/summarize/tldr <x>     - translate / bullet summary / one-line TL;DR
  see <question>                   - capture a screen region and ask about it
  opus/sonnet/haiku <x>            - pick the model for this query
  new <x>                          - fresh thread (otherwise follow-ups continue it)

Plain text is a direct Q&A. "find me a video editor" ranks installed apps.

Text source: with no subject (or `sel`/`clip`), text modes operate on the
current selection then clipboard, e.g. highlight text then type "rewrite".
Vision source: `see clip` uses an image from the clipboard instead of capturing.
"""

import json
import os
import select
import signal
import subprocess
import sys
import time
from configparser import ConfigParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin

CONFIG_PATH = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    / "hamr" / "plugins" / "ai" / "config.json"
)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_SYSTEM_PROMPT = (
    "You are a concise assistant inside a desktop launcher. "
    "Answer directly from your own knowledge without using any tools. "
    "Keep answers short and use markdown when it helps."
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
]

MODES = {
    "explain": "Explain this clearly and concisely for a knowledgeable reader.",
    "code": "Respond with only the code that does this, in a single fenced block. Minimal prose.",
    "cmd": "Give a single Linux shell command that does this. Output only the command in a fenced block, no explanation.",
    "fix": "Fix the spelling and grammar of the following text. Output only the corrected text.",
    "grammar": "Fix grammar and spelling. Output only the corrected text.",
    "translate": "Translate the following to English, or to the target language if one is named. Output only the translation.",
    "summarize": "Summarize the following concisely as a few markdown bullets.",
    "rewrite": "Rewrite the following to be clearer and well-written. Output only the rewritten text.",
    "improve": "Improve the wording of the following. Output only the improved text.",
    "shorter": "Make the following more concise while keeping the meaning. Output only the result.",
    "longer": "Expand the following with more useful detail. Output only the result.",
    "formal": "Rewrite the following in a formal, professional tone. Output only the result.",
    "casual": "Rewrite the following in a casual, friendly tone. Output only the result.",
    "eli5": "Explain the following simply, as if to a smart five-year-old. Use a short, friendly analogy.",
    "tldr": "Give a one or two sentence TL;DR of the following. Output only the summary.",
    "proofread": "Proofread the following: fix grammar, spelling and punctuation, keep the author's voice. Output only the corrected text.",
}

# Inline model overrides: prefix a query with one of these to pick the model.
MODEL_ALIASES = {
    "opus": "claude-opus-4-8",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
}

# Modes that operate on highlighted/clipboard text when no subject is typed.
TEXT_INPUT_MODES = {"fix", "grammar", "translate", "summarize", "rewrite",
                    "improve", "shorter", "longer", "formal", "casual",
                    "tldr", "proofread"}
VISION_MODES = {"see", "look", "screen", "shot"}

CLIP_WORDS = {"clip", "clipboard", "this", "that"}
SELECTION_WORDS = {"sel", "selection", "selected", "highlight", "primary"}
CACHE_MAX = 50
STATE = {"resume": None, "last_answer": "", "cache": {}}


def cache_get(key: str) -> str | None:
    return STATE["cache"].get(key)


def cache_put(key: str, answer: str) -> None:
    cache = STATE["cache"]
    cache[key] = answer
    if len(cache) > CACHE_MAX:
        cache.pop(next(iter(cache)))


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def emit(data: dict) -> None:
    print(json.dumps(data), flush=True)


def get_clipboard() -> str:
    for cmd in (["wl-paste", "-n"], ["xclip", "-selection", "clipboard", "-o"]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if r.returncode == 0:
                return r.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return ""


def get_selection() -> str:
    try:
        r = subprocess.run(["wl-paste", "-p", "-n"], capture_output=True, text=True, timeout=2)
        if r.returncode == 0:
            return r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ""


def resolve_source(text: str) -> str:
    low = text.lower()
    if low in SELECTION_WORDS:
        return get_selection() or get_clipboard()
    if low in CLIP_WORDS:
        return get_clipboard()
    return text


def clipboard_image() -> str | None:
    try:
        types = subprocess.run(["wl-paste", "-l"], capture_output=True, text=True, timeout=2).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    mime = next((t for t in ("image/png", "image/jpeg") if t in types), None)
    if not mime:
        return None
    path = f"/tmp/hamr-ai-clip.{mime.split('/')[1]}"
    with open(path, "wb") as f:
        subprocess.run(["wl-paste", "-t", mime], stdout=f, timeout=3)
    return path if os.path.getsize(path) else None


def capture_region() -> str | None:
    path = "/tmp/hamr-ai-shot.png"
    try:
        geo = subprocess.run(["slurp"], capture_output=True, text=True, timeout=30).stdout.strip()
        if not geo:
            return None
        subprocess.run(["grim", "-g", geo, path], timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return path if os.path.exists(path) and os.path.getsize(path) else None


def build_cmd(prompt: str, config: dict, system_prompt: str, resume: str | None,
              stream: bool, read_files: bool = False) -> list[str]:
    cmd = ["claude", "-p", prompt, "--model", config.get("model", DEFAULT_MODEL)]
    cmd += ["--system-prompt", system_prompt or config.get("system_prompt") or DEFAULT_SYSTEM_PROMPT]
    if config.get("slim", True):
        cmd += ["--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--setting-sources", ""]
    if read_files:
        cmd += ["--allowedTools", "Read"]
    if resume:
        cmd += ["--resume", resume]
    if stream:
        cmd += ["--output-format", "stream-json", "--include-partial-messages", "--verbose"]
    else:
        cmd += ["--output-format", "json"]
    return cmd


def query_json(prompt: str, config: dict, system_prompt: str | None = None, read_files: bool = False) -> str:
    cmd = build_cmd(prompt, config, system_prompt or "", None, stream=False, read_files=read_files)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=config.get("timeout", 60))
        out = r.stdout.strip()
        try:
            return json.loads(out).get("result", "").strip() or "No response"
        except json.JSONDecodeError:
            return out or r.stderr.strip() or "No response"
    except subprocess.TimeoutExpired:
        return "Request timed out"
    except FileNotFoundError:
        return "claude not found — is Claude Code installed?"
    except Exception as e:
        return f"Error: {e}"


def stream_claude(prompt: str, config: dict, system_prompt: str, resume: str | None, on_text,
                  read_files: bool = False) -> tuple[str, str | None]:
    cmd = build_cmd(prompt, config, system_prompt, resume, stream=True, read_files=read_files)
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    except FileNotFoundError:
        return "claude not found — is Claude Code installed?", None

    session_id = None
    acc: list[str] = []
    deadline = time.time() + config.get("timeout", 60)
    try:
        for line in proc.stdout:
            if time.time() > deadline:
                proc.kill()
                acc.append("\n\n_(timed out)_")
                break
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = d.get("type")
            if d.get("session_id"):
                session_id = d["session_id"]
            if t == "stream_event":
                ev = d.get("event", {})
                if ev.get("type") == "content_block_delta":
                    delta = ev.get("delta", {})
                    if delta.get("type") == "text_delta":
                        acc.append(delta.get("text", ""))
                        on_text("".join(acc))
            elif t == "result" and not acc and d.get("result"):
                acc.append(d["result"])
                on_text(d["result"])
    finally:
        proc.wait()
    return "".join(acc).strip() or "No response", session_id


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


def suggest_apps(query: str, apps: list[dict], config: dict) -> list[dict]:
    app_list = "\n".join(
        f"- {a['name']} ({a.get('generic_name') or ', '.join(a['categories'][:2]) or a.get('comment', '')})"
        for a in apps[:300]
    )
    prompt = (
        f"The user wants to: {query}\n\n"
        f"From this list of installed apps, suggest the 3-5 most relevant ones. "
        f'Reply with ONLY a JSON array of app names, e.g. ["GIMP", "Inkscape"]. '
        f"No explanation, no markdown, just the JSON array.\n\nInstalled apps:\n{app_list}"
    )
    raw = query_json(prompt, config, "Reply with only a JSON array of strings.")
    try:
        start = raw.index("[")
        end = raw.rindex("]") + 1
        suggested_names = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return []

    suggested_lower = [n.lower() for n in suggested_names]
    results = []
    for app in apps:
        if app["name"].lower() in suggested_lower:
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


def parse_query(query: str) -> tuple[str, str, str | None, str, str | None]:
    """Return (effective_prompt, system_prompt, resume_session, kind, model).

    kind is "vision", "mode" (explicit text mode), or "" (plain Q&A).
    model is an inline model override (e.g. "opus …") or None.
    """
    def split(q):
        w = q.split(maxsplit=1)
        return (w[0].lower() if w else ""), (w[1] if len(w) > 1 else "")

    head, rest = split(query)

    resume = STATE.get("resume")
    if head == "new":
        resume = None
        query = rest
        head, rest = split(query)

    model = None
    if head in MODEL_ALIASES and rest.strip():
        model = MODEL_ALIASES[head]
        query = rest
        head, rest = split(query)

    if head in VISION_MODES:
        return rest.strip(), DEFAULT_SYSTEM_PROMPT, resume, "vision", model

    system_prompt, kind = DEFAULT_SYSTEM_PROMPT, ""
    if head in MODES:
        system_prompt, kind, query = MODES[head], "mode", rest

    subject = query.strip()
    if subject.lower() in CLIP_WORDS | SELECTION_WORDS:
        subject = resolve_source(subject)
    elif not subject and head in TEXT_INPUT_MODES:
        subject = get_selection() or get_clipboard()

    return subject, system_prompt, resume, kind, model


def answer_card(title: str, markdown: str, session_id: str | None, streaming: bool) -> dict:
    actions = None
    if not streaming:
        actions = [
            {"id": "copy", "name": "Copy", "icon": "content_copy"},
            {"id": "type", "name": "Type into window", "icon": "keyboard"},
            {"id": "new", "name": "New chat", "icon": "add_comment"},
        ]
    return HamrPlugin.card(
        title,
        markdown=markdown or "…",
        actions=actions,
        context=f"resume:{session_id}" if session_id else None,
    )


def handle_vision(subject: str, config: dict) -> None:
    words = subject.split(maxsplit=1)
    src = words[0].lower() if words else ""
    if src in CLIP_WORDS:
        question = words[1] if len(words) > 1 else "Describe what's shown."
        img = clipboard_image()
        if not img:
            emit(HamrPlugin.card("No image found", markdown="_Clipboard has no image. Copy a screenshot first._"))
            return
    else:
        question = subject or "Describe what's shown."
        emit(HamrPlugin.card("Select a region…", markdown="_Drag to select the area to ask about._"))
        img = capture_region()
        if not img:
            emit(HamrPlugin.card("Capture cancelled", markdown="_No region captured._"))
            return

    title = question if len(question) <= 60 else question[:57] + "…"
    prompt = f"@{img} {question}"

    if config.get("stream", True):
        last = [0.0]

        def on_text(text: str) -> None:
            now = time.time()
            if now - last[0] < 0.12:
                return
            last[0] = now
            emit(answer_card(title, text + " ▌", None, streaming=True))

        answer, _ = stream_claude(prompt, config, DEFAULT_SYSTEM_PROMPT, None, on_text, read_files=True)
    else:
        emit(HamrPlugin.card(f"Looking: {title}", markdown="_Asking Claude…_"))
        answer = query_json(prompt, config, read_files=True)

    STATE["last_answer"] = answer
    emit(answer_card(title, answer, None, streaming=False))


def handle_search(query: str, apps: list[dict], config: dict) -> None:
    if not query:
        emit(HamrPlugin.results(
            [{"id": "__placeholder__", "name": "Ask Claude anything…", "icon": "neurology",
              "description": "Ask · find a [tool] · explain/eli5/code/cmd/tldr · opus|sonnet [q] · see [q]"}],
            input_mode="submit",
            placeholder="Ask Claude or describe what you need…",
        ))
        return

    prompt, system_prompt, resume, kind, model = parse_query(query)
    if model:
        config = {**config, "model": model}

    if kind == "vision":
        handle_vision(prompt, config)
        return

    if kind != "mode" and is_app_suggestion_query(query):
        emit(HamrPlugin.card("Finding apps…", markdown=f"_Searching for: {query}_", context=None))
        suggested = suggest_apps(query, apps, config)
        if suggested:
            emit(HamrPlugin.results(
                [{"id": "__header__", "name": f"Claude suggests for: {query}",
                  "icon": "neurology", "description": "via claude -p"}, *suggested],
                input_mode="submit",
                placeholder="Ask Claude or describe what you need…",
            ))
        else:
            emit(HamrPlugin.results(
                [{"id": "__noresult__", "name": "No matching apps found",
                  "icon": "search_off", "description": query}],
                input_mode="submit",
            ))
        return

    title = query if len(query) <= 60 else query[:57] + "…"

    cache_key = f"{config.get('model', DEFAULT_MODEL)}\x00{system_prompt}\x00{prompt}"
    if not resume and (cached := cache_get(cache_key)) is not None:
        STATE["last_answer"] = cached
        emit(answer_card(title, cached, None, streaming=False))
        return

    if config.get("stream", True):
        last = [0.0]

        def on_text(text: str) -> None:
            now = time.time()
            if now - last[0] < 0.12:
                return
            last[0] = now
            emit(answer_card(title, text + " ▌", None, streaming=True))

        answer, session_id = stream_claude(prompt, config, system_prompt, resume, on_text)
    else:
        emit(HamrPlugin.card(f"Thinking: {title}", markdown="_Asking Claude…_"))
        answer, session_id = query_json(prompt, config, system_prompt), None

    STATE["last_answer"] = answer
    if not resume and answer not in ("No response", "Request timed out"):
        cache_put(cache_key, answer)
    emit(answer_card(title, answer, session_id, streaming=False))


def handle_action(request: dict, apps: list[dict]) -> None:
    selected = request.get("selected", {}) or {}
    selected_id = selected.get("id", "")
    action = request.get("action", "") or selected_id

    if action == "copy":
        emit(HamrPlugin.copy_and_close(STATE["last_answer"]))
        return
    if action == "type":
        emit(HamrPlugin.execute(type_text=STATE["last_answer"], hide=True))
        return
    if action == "new":
        STATE["resume"] = None
        STATE["last_answer"] = ""
        emit(HamrPlugin.results(
            [{"id": "__placeholder__", "name": "New chat — ask Claude anything…", "icon": "neurology"}],
            input_mode="submit",
            placeholder="Ask Claude or describe what you need…",
        ))
        return
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


def handle_request(request: dict, apps: list[dict], config: dict) -> None:
    step = request.get("step", "search")
    context = request.get("context", "") or ""
    STATE["resume"] = context.split(":", 1)[1] if context.startswith("resume:") else None

    if step == "search":
        handle_search(request.get("query", "").strip(), apps, config)
    elif step == "action":
        handle_action(request, apps)


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    apps = get_installed_apps()
    config = load_config()

    while True:
        readable, _, _ = select.select([sys.stdin], [], [], 1.0)
        if readable:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                request = json.loads(line.strip())
                handle_request(request, apps, config)
            except (json.JSONDecodeError, ValueError):
                continue


if __name__ == "__main__":
    main()
