#!/usr/bin/env python3
"""
World clock plugin - current time in any city or timezone.

Type in the main search: "time tokyo", "time in london", "tz utc",
"time new york". Bare "time" shows local. Enter copies the timestamp.
"""

import json
import select
import signal
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, available_timezones

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin

CITIES = {
    "utc": "UTC", "gmt": "UTC",
    "london": "Europe/London", "uk": "Europe/London",
    "paris": "Europe/Paris", "berlin": "Europe/Berlin", "madrid": "Europe/Madrid",
    "rome": "Europe/Rome", "amsterdam": "Europe/Amsterdam", "zurich": "Europe/Zurich",
    "moscow": "Europe/Moscow", "istanbul": "Europe/Istanbul", "athens": "Europe/Athens",
    "dublin": "Europe/Dublin", "lisbon": "Europe/Lisbon", "stockholm": "Europe/Stockholm",
    "tokyo": "Asia/Tokyo", "japan": "Asia/Tokyo",
    "beijing": "Asia/Shanghai", "shanghai": "Asia/Shanghai", "china": "Asia/Shanghai",
    "hongkong": "Asia/Hong_Kong", "hk": "Asia/Hong_Kong", "singapore": "Asia/Singapore",
    "seoul": "Asia/Seoul", "korea": "Asia/Seoul", "mumbai": "Asia/Kolkata",
    "delhi": "Asia/Kolkata", "india": "Asia/Kolkata", "bangkok": "Asia/Bangkok",
    "dubai": "Asia/Dubai", "uae": "Asia/Dubai", "jakarta": "Asia/Jakarta",
    "manila": "Asia/Manila", "karachi": "Asia/Karachi", "telaviv": "Asia/Jerusalem",
    "jerusalem": "Asia/Jerusalem",
    "sydney": "Australia/Sydney", "melbourne": "Australia/Melbourne",
    "perth": "Australia/Perth", "auckland": "Pacific/Auckland", "nz": "Pacific/Auckland",
    "newyork": "America/New_York", "nyc": "America/New_York", "ny": "America/New_York",
    "est": "America/New_York", "edt": "America/New_York", "eastern": "America/New_York",
    "chicago": "America/Chicago", "cst": "America/Chicago", "central": "America/Chicago",
    "denver": "America/Denver", "mst": "America/Denver", "mountain": "America/Denver",
    "losangeles": "America/Los_Angeles", "la": "America/Los_Angeles",
    "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles", "pacific": "America/Los_Angeles",
    "seattle": "America/Los_Angeles", "sf": "America/Los_Angeles",
    "detroit": "America/Detroit", "toronto": "America/Toronto", "vancouver": "America/Vancouver",
    "mexico": "America/Mexico_City", "saopaulo": "America/Sao_Paulo", "brazil": "America/Sao_Paulo",
    "buenosaires": "America/Argentina/Buenos_Aires", "lima": "America/Lima",
    "cairo": "Africa/Cairo", "lagos": "Africa/Lagos", "nairobi": "Africa/Nairobi",
    "johannesburg": "Africa/Johannesburg", "capetown": "Africa/Johannesburg",
    "honolulu": "Pacific/Honolulu", "hawaii": "Pacific/Honolulu", "anchorage": "America/Anchorage",
}

_ALL_TZ = None


def resolve(name):
    key = name.lower().replace(" ", "").replace("_", "")
    if key in CITIES:
        return CITIES[key]
    global _ALL_TZ
    if _ALL_TZ is None:
        _ALL_TZ = {z.lower().replace("/", "").replace("_", ""): z for z in available_timezones()}
    raw = name.strip().replace(" ", "_")
    try:
        ZoneInfo(raw)
        return raw
    except Exception:
        pass
    return _ALL_TZ.get(key)


def strip_kw(query):
    parts = query.split(maxsplit=1)
    rest = query.strip()
    if parts and parts[0].lower() in ("time", "clock", "tz"):
        rest = parts[1].strip() if len(parts) > 1 else ""
    low = rest.split(maxsplit=1)
    if low and low[0].lower() in ("in", "at"):
        rest = low[1].strip() if len(low) > 1 else ""
    return rest


def clock(name):
    """Return (display, label, copy) or None."""
    tz = resolve(name)
    if not tz:
        return None
    now = datetime.now(ZoneInfo(tz))
    disp = now.strftime("%-I:%M %p · %a %b %-d")
    off = now.strftime("%Z %z")
    return disp, f"{tz}  ({off})", now.strftime("%Y-%m-%d %H:%M:%S %Z%z")


def emit(data):
    print(json.dumps(data), flush=True)


def handle_request(request):
    step = request.get("step", "initial")
    query = request.get("query", "").strip()

    if step == "match":
        target = strip_kw(query)
        if not target:
            emit({"type": "match", "result": None})
            return
        res = clock(target)
        if not res:
            emit({"type": "match", "result": None})
            return
        disp, label, copy = res
        emit({"type": "match", "result": {
            "id": copy, "name": disp, "description": label,
            "icon": "schedule", "copy": copy,
        }})
        return

    if step in ("initial", "search"):
        target = strip_kw(query) or "local"
        if target == "local":
            now = datetime.now().astimezone()
            items = [{"id": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
                      "name": now.strftime("%-I:%M %p · %a %b %-d"),
                      "description": f"local · {now.strftime('%Z %z')}", "icon": "schedule"}]
        else:
            res = clock(target)
            if res:
                disp, label, copy = res
                items = [{"id": copy, "name": disp, "description": f"{label} · Enter to copy",
                          "icon": "schedule"}]
            else:
                items = [{"id": "__none__", "name": f"Unknown place: {target}", "icon": "help",
                          "description": "try a city (tokyo, london, nyc) or IANA zone (Asia/Tokyo)"}]
        emit(HamrPlugin.results(items, input_mode="realtime",
                                placeholder="time tokyo · time in london · tz utc"))
        return

    if step == "action":
        text = (request.get("selected", {}) or {}).get("id", "")
        if text.startswith("__"):
            emit(HamrPlugin.noop())
            return
        emit(HamrPlugin.copy_and_close(text))


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
