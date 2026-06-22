#!/usr/bin/env python3
"""
Kill Process plugin for hamr - find and terminate any running process.

Unlike the topcpu/topmem monitors (which only surface the busiest few
processes), this plugin is search-first:

  - Type a name fragment ("chrome", "node") to find matching processes.
  - Type a port (":3000", "port 8080") to find whatever is listening on it
    and kill it - the classic "address already in use" rescue.

Each result offers a graceful SIGTERM and a forceful SIGKILL.

Uses the socket SDK for daemon mode.
"""

import os
import re
import signal as signals
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path to import SDK
sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin

# Match a leading port query: ":3000" or "port 8080"
PORT_QUERY_RE = re.compile(r"^\s*(?::|port\s+)(\d{1,5})\s*$", re.IGNORECASE)
# Extract pid=NNN from `ss` output
SS_PID_RE = re.compile(r"pid=(\d+)")

MAX_RESULTS = 40


def _ps_field(pid: str, fmt: str) -> str:
    """Read a single ps field for one pid, empty string on failure."""
    try:
        out = subprocess.run(
            ["ps", "-p", pid, "-o", f"{fmt}="],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def get_proc_info(pid: str) -> Optional[dict]:
    """Return process details for a single pid, or None if it's gone."""
    try:
        out = subprocess.run(
            ["ps", "-p", pid, "-o", "pid=,comm=,%cpu=,%mem=,user=,args="],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    line = out.stdout.strip()
    if not line:
        return None
    return _parse_ps_line(line)


def _parse_ps_line(line: str) -> Optional[dict]:
    """Parse one `pid comm %cpu %mem user args...` line into a dict."""
    parts = line.split(None, 5)
    if len(parts) < 5:
        return None
    try:
        pid = parts[0]
        comm = parts[1]
        cpu = float(parts[2])
        mem = float(parts[3])
        user = parts[4]
        args = parts[5] if len(parts) > 5 else comm
    except (ValueError, IndexError):
        return None
    return {
        "pid": pid,
        "name": comm,
        "cpu": cpu,
        "mem": mem,
        "user": user,
        "args": args,
    }


def search_processes(query: str) -> list[dict]:
    """Return processes whose name/args/pid match the query, busiest first."""
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid=,comm=,%cpu=,%mem=,user=,args=", "--sort=-%cpu"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    own_pid = str(os.getpid())
    parent_pid = str(os.getppid())
    query_lower = query.lower()
    matches = []
    for line in out.stdout.splitlines():
        proc = _parse_ps_line(line)
        if not proc:
            continue
        # Never offer to kill ourselves or the daemon that launched us.
        if proc["pid"] in (own_pid, parent_pid):
            continue
        if query_lower and not (
            query_lower in proc["name"].lower()
            or query_lower in proc["args"].lower()
            or query_lower == proc["pid"]
        ):
            continue
        matches.append(proc)
        if len(matches) >= MAX_RESULTS:
            break
    return matches


def find_pids_on_port(port: str) -> list[str]:
    """Return pids listening on the given TCP or UDP port via `ss`."""
    pids: list[str] = []
    try:
        out = subprocess.run(
            ["ss", "-tulpnH"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return _find_pids_on_port_lsof(port)

    needle = f":{port}"
    for line in out.stdout.splitlines():
        # Local address is column 5 (tcp/udp state recv send local peer process)
        cols = line.split()
        if len(cols) < 5:
            continue
        local = cols[4]
        # Match the port at the end of the local address, not inside an IP.
        if not local.endswith(needle):
            continue
        for pid in SS_PID_RE.findall(line):
            if pid not in pids:
                pids.append(pid)
    if not pids:
        return _find_pids_on_port_lsof(port)
    return pids


def _find_pids_on_port_lsof(port: str) -> list[str]:
    """Fallback port lookup using lsof."""
    try:
        out = subprocess.run(
            ["lsof", "-t", "-i", f":{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return []
    pids = []
    for pid in out.stdout.split():
        if pid not in pids:
            pids.append(pid)
    return pids


def build_results(query: str) -> list[dict]:
    """Build result rows for the current query."""
    port_match = PORT_QUERY_RE.match(query) if query else None

    if port_match:
        port = port_match.group(1)
        pids = find_pids_on_port(port)
        procs = [info for pid in pids if (info := get_proc_info(pid))]
        if not procs:
            return [
                {
                    "id": "__empty__",
                    "name": f"Nothing is listening on port {port}",
                    "icon": "info",
                    "description": "Note: ports owned by other users may be hidden",
                }
            ]
        return [proc_result(p, port=port) for p in procs]

    procs = search_processes(query)
    if not procs:
        return [
            {
                "id": "__empty__",
                "name": "No matching processes" if query else "Type a name or :port",
                "icon": "search",
                "description": "e.g. \"chrome\", \"node\", or \":3000\"",
            }
        ]
    return [proc_result(p, query=query) for p in procs]


def _pango_escape(ch: str) -> str:
    """Escape a single char for Pango markup."""
    if ch == "&":
        return "&amp;"
    if ch == "<":
        return "&lt;"
    if ch == ">":
        return "&gt;"
    return ch


def highlight_markup(name: str, query: str) -> Optional[str]:
    """Wrap the matched query characters in <b> tags (Pango markup).

    Matches the query as a case-insensitive subsequence, left to right -
    the same feel as the launcher's fuzzy match. Returns None when nothing
    matches so the row falls back to plain text.
    """
    if not query:
        return None
    q = query.lower()
    qi = 0
    out: list[str] = []
    in_bold = False
    for ch in name:
        if qi < len(q) and ch.lower() == q[qi]:
            if not in_bold:
                out.append("<b>")
                in_bold = True
            out.append(_pango_escape(ch))
            qi += 1
        else:
            if in_bold:
                out.append("</b>")
                in_bold = False
            out.append(_pango_escape(ch))
    if in_bold:
        out.append("</b>")
    # Only worthwhile if we matched the whole query somewhere in the name.
    if qi < len(q):
        return None
    return "".join(out)


def proc_result(proc: dict, port: Optional[str] = None, query: str = "") -> dict:
    """Convert a process dict into a hamr result row."""
    desc = f"PID {proc['pid']}  •  CPU {proc['cpu']:.0f}%  •  Mem {proc['mem']:.1f}%  •  {proc['user']}"
    if port:
        desc = f"Listening on :{port}  •  " + desc

    badges = []
    if port:
        badges.append({"icon": "lan", "color": "#2196f3"})
    if proc["cpu"] > 50:
        badges.append({"icon": "warning", "color": "#f44336"})

    row = {
        "id": f"proc:{proc['pid']}",
        "name": proc["name"],
        "description": desc,
        "badges": badges,
        "verb": "Kill",
        "actions": [
            {"id": "kill", "name": "Kill (SIGTERM)", "icon": "cancel"},
            {"id": "kill9", "name": "Force Kill (SIGKILL)", "icon": "dangerous"},
        ],
    }

    # Highlight the typed letters in the process name (name searches only;
    # in port mode the query is the port number, not part of the name).
    if query and not port:
        markup = highlight_markup(proc["name"], query)
        if markup:
            row["nameMarkup"] = markup

    return row


def kill_process(pid: str, force: bool = False) -> tuple[bool, str]:
    """Send SIGTERM (or SIGKILL) to a pid."""
    name = _ps_field(pid, "comm") or pid
    sig = signals.SIGKILL if force else signals.SIGTERM
    try:
        os.kill(int(pid), sig)
    except ProcessLookupError:
        return False, f"{name} (PID {pid}) is already gone"
    except PermissionError:
        return False, f"Permission denied killing {name} (PID {pid})"
    except (ValueError, OSError) as exc:
        return False, f"Failed to kill PID {pid}: {exc}"
    verb = "force killed" if force else "terminated"
    return True, f"{name} (PID {pid}) {verb}"


plugin = HamrPlugin(
    id="killproc",
    name="Kill Process",
    description="Search and kill any process by name or by port (:3000)",
    icon="dangerous",
)

state = {"current_query": ""}


@plugin.on_initial
async def handle_initial(params=None):
    state["current_query"] = ""
    return HamrPlugin.results(
        build_results(""),
        placeholder="Search a process by name, or a :port to free it...",
    )


@plugin.on_search
async def handle_search(query: str, context: Optional[str]):
    query = (query or "").strip()
    state["current_query"] = query
    return HamrPlugin.results(build_results(query))


@plugin.on_action
async def handle_action(item_id: str, action: Optional[str], context: Optional[str]):
    if not item_id.startswith("proc:"):
        return HamrPlugin.results(build_results(state["current_query"]))

    pid = item_id.split(":", 1)[1]
    success, message = kill_process(pid, force=(action == "kill9"))

    response = HamrPlugin.results(build_results(state["current_query"]))
    response["status"] = {"notify": message}
    return response


if __name__ == "__main__":
    plugin.run()
