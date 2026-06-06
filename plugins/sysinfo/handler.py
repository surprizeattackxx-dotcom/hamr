#!/usr/bin/env python3
"""
System info plugin - at-a-glance dashboard card.

Activate the plugin (or type "sys") to see CPU, memory, disk, temperature,
network and uptime in one card. Refresh re-samples; Copy yields plain text.
"""

import json
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin


def _read(path, default=""):
    try:
        return Path(path).read_text()
    except OSError:
        return default


def bar(pct, width=16):
    pct = max(0.0, min(100.0, pct))
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def cpu_percent():
    def snap():
        f = _read("/proc/stat").splitlines()[0].split()[1:]
        v = list(map(int, f))
        idle = v[3] + v[4]
        return sum(v), idle
    t1, i1 = snap()
    time.sleep(0.2)
    t2, i2 = snap()
    dt, di = t2 - t1, i2 - i1
    return 0.0 if dt <= 0 else (1 - di / dt) * 100


def cpu_model():
    for line in _read("/proc/cpuinfo").splitlines():
        if line.startswith("model name"):
            return line.split(":", 1)[1].strip()
    return "CPU"


def meminfo():
    d = {}
    for line in _read("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        d[k] = int(v.strip().split()[0]) if v.strip() else 0
    total = d.get("MemTotal", 0)
    avail = d.get("MemAvailable", 0)
    used = total - avail
    swap_t = d.get("SwapTotal", 0)
    swap_u = swap_t - d.get("SwapFree", 0)
    return total, used, swap_t, swap_u


def gib(kb):
    return kb / 1024 / 1024


def uptime_str():
    secs = float(_read("/proc/uptime", "0").split()[0] or 0)
    d, rem = divmod(int(secs), 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h or d:
        parts.append(f"{h}h")
    parts.append(f"{m}m")
    return " ".join(parts)


def temperatures():
    try:
        out = subprocess.run(["sensors", "-A", "-u"], capture_output=True,
                             text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    temps = []
    chip = None
    for line in out.splitlines():
        if line and not line.startswith(" ") and ":" not in line:
            chip = line.strip()
        m = re.search(r"(temp\d+|Tctl|Tccd\d+|Composite|edge|junction)_input:\s+([\d.]+)", line)
        if m:
            temps.append((chip or "", float(m.group(2))))
    out_t = []
    seen = set()
    for chip, val in temps:
        key = chip.split("-")[0]
        if key in seen:
            continue
        seen.add(key)
        out_t.append((key or "temp", val))
    return out_t[:4]


def network():
    try:
        route = subprocess.run(["ip", "route", "get", "1.1.1.1"], capture_output=True,
                               text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return None, None
    m_dev = re.search(r"dev (\S+)", route)
    m_src = re.search(r"src (\S+)", route)
    return (m_dev.group(1) if m_dev else None), (m_src.group(1) if m_src else None)


def gather():
    cpu = cpu_percent()
    mt, mu, st, su = meminfo()
    du = shutil.disk_usage("/")
    disk_pct = du.used / du.total * 100
    mem_pct = mu / mt * 100 if mt else 0
    iface, ip = network()
    uname = os.uname()
    return {
        "host": uname.nodename,
        "kernel": uname.release,
        "cpu_model": cpu_model(),
        "cores": os.cpu_count(),
        "load": _read("/proc/loadavg", "").split()[:3],
        "cpu": cpu,
        "mem_pct": mem_pct,
        "mem_used": gib(mu),
        "mem_total": gib(mt),
        "swap_used": gib(su),
        "swap_total": gib(st),
        "disk_pct": disk_pct,
        "disk_used": du.used / 1024**3,
        "disk_total": du.total / 1024**3,
        "temps": temperatures(),
        "iface": iface,
        "ip": ip,
        "uptime": uptime_str(),
    }


def render_markdown(s):
    lines = [
        f"**{s['host']}** · `{s['kernel']}` · up {s['uptime']}",
        "",
        f"`CPU  {bar(s['cpu'])} {s['cpu']:5.1f}%`  ",
        f"_{s['cpu_model']}_ · {s['cores']} cores · load {' '.join(s['load'])}",
        "",
        f"`RAM  {bar(s['mem_pct'])} {s['mem_pct']:5.1f}%`  {s['mem_used']:.1f}/{s['mem_total']:.1f} GiB",
        f"`DISK {bar(s['disk_pct'])} {s['disk_pct']:5.1f}%`  {s['disk_used']:.0f}/{s['disk_total']:.0f} GiB  (/)",
    ]
    if s["swap_total"] > 0.01:
        sp = s["swap_used"] / s["swap_total"] * 100
        lines.append(f"`SWAP {bar(sp)} {sp:5.1f}%`  {s['swap_used']:.1f}/{s['swap_total']:.1f} GiB")
    if s["temps"]:
        lines.append("")
        lines.append(" · ".join(f"{name} {val:.0f}°C" for name, val in s["temps"]))
    if s["iface"]:
        lines.append("")
        lines.append(f"🌐 {s['iface']} · {s['ip']}")
    return "\n".join(lines)


def render_plain(s):
    out = [
        f"{s['host']} | {s['kernel']} | up {s['uptime']}",
        f"CPU {s['cpu']:.1f}% ({s['cpu_model']}, {s['cores']} cores, load {' '.join(s['load'])})",
        f"RAM {s['mem_used']:.1f}/{s['mem_total']:.1f} GiB ({s['mem_pct']:.0f}%)",
        f"Disk {s['disk_used']:.0f}/{s['disk_total']:.0f} GiB ({s['disk_pct']:.0f}%)",
    ]
    if s["temps"]:
        out.append("Temp " + ", ".join(f"{n} {v:.0f}C" for n, v in s["temps"]))
    if s["iface"]:
        out.append(f"Net {s['iface']} {s['ip']}")
    return "\n".join(out)


STATE = {"plain": ""}


def emit(data):
    print(json.dumps(data), flush=True)


def make_card():
    s = gather()
    STATE["plain"] = render_plain(s)
    return HamrPlugin.card(
        "System",
        markdown=render_markdown(s),
        actions=[
            {"id": "refresh", "name": "Refresh", "icon": "refresh"},
            {"id": "copy", "name": "Copy", "icon": "content_copy"},
        ],
    )


def handle_request(request):
    step = request.get("step", "initial")

    if step in ("initial", "search"):
        emit(make_card())
        return

    if step == "action":
        action = request.get("action", "")
        if action == "copy":
            emit(HamrPlugin.copy_and_close(STATE["plain"] or render_plain(gather())))
            return
        emit(make_card())


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
