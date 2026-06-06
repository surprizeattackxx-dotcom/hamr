#!/usr/bin/env python3
"""
Kill plugin - find a running process and terminate it.

Activate the plugin, then type part of a process name to filter. Enter sends
SIGTERM. Prefix the filter with "!" (e.g. "!chrome") to send SIGKILL instead.
"""

import json
import os
import select
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin

SELF = os.getpid()


def list_processes(needle, force):
    out = subprocess.run(
        ["ps", "-eo", "pid=,rss=,comm=,args="],
        capture_output=True, text=True,
    ).stdout
    procs = []
    needle = needle.lower()
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 3:
            continue
        pid = int(parts[0])
        if pid == SELF or pid <= 1:
            continue
        rss_kb = int(parts[1])
        comm = parts[2]
        args = parts[3] if len(parts) > 3 else comm
        hay = (comm + " " + args).lower()
        if needle and needle not in hay:
            continue
        procs.append({"pid": pid, "name": comm, "args": args, "rss": rss_kb})
    procs.sort(key=lambda p: p["rss"], reverse=True)
    return procs[:30], force


def human_mem(kb):
    if kb >= 1024 * 1024:
        return f"{kb / 1024 / 1024:.1f} GB"
    if kb >= 1024:
        return f"{kb / 1024:.0f} MB"
    return f"{kb} KB"


def emit(data):
    print(json.dumps(data), flush=True)


def items_for(query):
    force = query.startswith("!")
    needle = query[1:].strip() if force else query.strip()
    procs, force = list_processes(needle, force)
    verb = "SIGKILL" if force else "SIGTERM"
    sig = "9" if force else "15"
    if not procs:
        return [{"id": "__none__", "name": "No matching processes", "icon": "search_off",
                 "description": "type part of a process name · prefix ! to force-kill"}]
    items = []
    for p in procs:
        cmd = p["args"] if len(p["args"]) <= 80 else p["args"][:80] + "…"
        items.append({
            "id": f"{sig}:{p['pid']}:{p['name']}",
            "name": f"{p['name']}  ·  {human_mem(p['rss'])}",
            "description": f"pid {p['pid']} · {cmd} · Enter sends {verb}",
            "icon": "cancel",
        })
    return items


def handle_request(request):
    step = request.get("step", "initial")
    query = request.get("query", "")

    if step in ("initial", "search"):
        emit(HamrPlugin.results(items_for(query), input_mode="realtime",
                                placeholder="filter processes · ! to force-kill"))
        return

    if step == "action":
        sel = (request.get("selected", {}) or {}).get("id", "")
        if sel.startswith("__"):
            emit(HamrPlugin.noop())
            return
        try:
            sig_s, pid_s, name = sel.split(":", 2)
            pid, sig = int(pid_s), int(sig_s)
            os.kill(pid, sig)
            verb = "killed" if sig == 9 else "terminated"
            emit(HamrPlugin.execute(notify=f"{verb} {name} (pid {pid})", close=True))
        except (ValueError, ProcessLookupError) as e:
            emit(HamrPlugin.execute(notify=f"Failed: {e}", close=True))
        except PermissionError:
            emit(HamrPlugin.execute(notify=f"Permission denied for pid {pid_s}", close=True))


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    while True:
        readable, _, _ = select.select([sys.stdin], [], [], 1.0)
        if readable:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                handle_request(json.loads(line.strip()))
            except (json.JSONDecodeError, ValueError):
                continue


if __name__ == "__main__":
    main()
