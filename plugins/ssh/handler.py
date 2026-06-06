#!/usr/bin/env python3
"""
SSH plugin - connect to hosts from ~/.ssh/config.

Activate the plugin (or type "ssh"), optionally filtering by name. Enter
opens your terminal and runs `ssh <host>`.
"""

import json
import os
import re
import select
import shutil
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin

SSH_CONFIG = Path.home() / ".ssh" / "config"
TERMINALS = ["ghostty", "kitty", "alacritty", "foot", "wezterm", "konsole", "xterm"]


def parse_hosts():
    hosts = []
    try:
        lines = SSH_CONFIG.read_text().splitlines()
    except OSError:
        return hosts
    current = None
    for line in lines:
        m = re.match(r"\s*Host\s+(.+)", line, re.IGNORECASE)
        if m:
            for name in m.group(1).split():
                if "*" in name or "?" in name:
                    continue
                current = {"host": name, "hostname": "", "user": ""}
                hosts.append(current)
            continue
        if current is None:
            continue
        hm = re.match(r"\s*HostName\s+(\S+)", line, re.IGNORECASE)
        if hm:
            current["hostname"] = hm.group(1)
        um = re.match(r"\s*User\s+(\S+)", line, re.IGNORECASE)
        if um:
            current["user"] = um.group(1)
    # de-dupe by host name, keep first
    seen, out = set(), []
    for h in hosts:
        if h["host"] not in seen:
            seen.add(h["host"])
            out.append(h)
    return out


def terminal_cmd():
    term = os.environ.get("TERMINAL")
    if term and shutil.which(term):
        return term
    for t in TERMINALS:
        if shutil.which(t):
            return t
    return None


def connect(host):
    term = terminal_cmd()
    if not term:
        return False
    try:
        subprocess.Popen(
            [term, "-e", "ssh", host],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
        return True
    except OSError:
        return False


def emit(d):
    print(json.dumps(d), flush=True)


def items_for(query):
    hosts = parse_hosts()
    q = query.strip().lower()
    if q:
        hosts = [h for h in hosts if q in h["host"].lower()
                 or q in h["hostname"].lower() or q in h["user"].lower()]
    if not hosts:
        return [{"id": "__none__", "name": "No SSH hosts" if not query else f"No host matching: {query}",
                 "icon": "dns", "description": "add entries to ~/.ssh/config"}]
    items = []
    for h in hosts:
        target = h["hostname"] or h["host"]
        desc = f"{h['user'] + '@' if h['user'] else ''}{target} · Enter to connect"
        items.append({"id": f"ssh:{h['host']}", "name": h["host"], "description": desc, "icon": "dns"})
    return items


def handle_request(request):
    step = request.get("step", "initial")
    query = request.get("query", "")

    if step in ("initial", "search"):
        emit(HamrPlugin.results(items_for(query), input_mode="realtime",
                                placeholder="filter ssh hosts…"))
        return

    if step == "action":
        sel = (request.get("selected", {}) or {}).get("id", "")
        if not sel.startswith("ssh:"):
            emit(HamrPlugin.noop())
            return
        host = sel[4:]
        if connect(host):
            emit(HamrPlugin.execute(notify=f"Connecting to {host}…", close=True))
        else:
            emit(HamrPlugin.execute(notify="No terminal found (set $TERMINAL)", close=True))


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
