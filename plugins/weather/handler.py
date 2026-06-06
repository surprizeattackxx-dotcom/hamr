#!/usr/bin/env python3
"""
Weather plugin - current conditions and a short forecast.

Activate the plugin (or type "weather"), optionally followed by a city:
"weather", "weather tokyo", "forecast berlin". Data from wttr.in, cached
15 minutes per location so repeat lookups are instant.
"""

import json
import select
import signal
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin

CACHE_DIR = Path.home() / ".cache" / "hamr"
CACHE_TTL = 15 * 60

ICONS = {
    "sunny": "☀️", "clear": "🌙", "partly": "⛅", "cloudy": "☁️", "overcast": "☁️",
    "mist": "🌫️", "fog": "🌫️", "rain": "🌧️", "drizzle": "🌦️", "shower": "🌦️",
    "snow": "❄️", "sleet": "🌨️", "thunder": "⛈️", "blizzard": "🌨️",
}


def pick_icon(desc):
    d = desc.lower()
    for key, icon in ICONS.items():
        if key in d:
            return icon
    return "🌡️"


def cache_file(location):
    safe = "".join(c if c.isalnum() else "_" for c in location.lower()) or "here"
    return CACHE_DIR / f"weather_{safe}.json"


def fetch(location):
    cf = cache_file(location)
    try:
        cached = json.loads(cf.read_text())
        if time.time() - cached["ts"] < CACHE_TTL:
            return cached["data"]
    except (OSError, ValueError, KeyError):
        cached = None
    url = f"https://wttr.in/{urllib.parse.quote(location)}?format=j1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps({"ts": time.time(), "data": data}))
        return data
    except Exception:
        return cached["data"] if cached else None


def render(data, location):
    cur = data["current_condition"][0]
    area = data.get("nearest_area", [{}])[0]
    name = " ".join(
        v[0]["value"] for k in ("areaName", "country") if (v := area.get(k))
    ) or (location or "here")
    desc = cur["weatherDesc"][0]["value"].strip()
    icon = pick_icon(desc)
    lines = [
        f"## {icon}  {cur['temp_C']}°C  ·  {name}",
        f"**{desc}** · feels like {cur['FeelsLikeC']}°C",
        "",
        f"💧 {cur['humidity']}%   🌬️ {cur['windspeedKmph']} km/h "
        f"{cur.get('winddir16Point', '')}   👁️ {cur['visibility']} km",
        "",
        "| Day | Min | Max | Conditions |",
        "|-----|-----|-----|------------|",
    ]
    days = ["Today", "Tomorrow"]
    for i, day in enumerate(data.get("weather", [])[:3]):
        label = days[i] if i < len(days) else day["date"][5:]
        cond = day["hourly"][len(day["hourly"]) // 2]["weatherDesc"][0]["value"].strip()
        lines.append(
            f"| {label} | {day['mintempC']}° | {day['maxtempC']}° | {pick_icon(cond)} {cond} |"
        )
    return "\n".join(lines)


def plain(data, location):
    cur = data["current_condition"][0]
    return f"{cur['temp_C']}C, {cur['weatherDesc'][0]['value'].strip()} ({location or 'here'})"


STATE = {"plain": ""}


def emit(d):
    print(json.dumps(d), flush=True)


def strip_kw(query):
    parts = query.split(maxsplit=1)
    if parts and parts[0].lower() in ("weather", "forecast", "wttr"):
        return parts[1].strip() if len(parts) > 1 else ""
    return query.strip()


def card_for(location):
    data = fetch(location)
    if not data:
        return HamrPlugin.card("Weather", markdown="Couldn't reach the weather service.")
    STATE["plain"] = plain(data, location)
    return HamrPlugin.card(
        "Weather",
        markdown=render(data, location),
        actions=[
            {"id": "refresh", "name": "Refresh", "icon": "refresh"},
            {"id": "copy", "name": "Copy", "icon": "content_copy"},
        ],
    )


def handle_request(request):
    step = request.get("step", "initial")
    query = request.get("query", "").strip()

    if step in ("initial", "search"):
        emit(card_for(strip_kw(query)))
        return

    if step == "action":
        action = request.get("action", "")
        if action == "copy":
            emit(HamrPlugin.copy_and_close(STATE["plain"]))
            return
        cache_file(strip_kw(query)).unlink(missing_ok=True)
        emit(card_for(strip_kw(query)))


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
