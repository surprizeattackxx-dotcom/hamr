#!/usr/bin/env python3
"""
Color plugin - convert between hex, rgb and hsl (offline).

Type in the main search: "color #ff5733", "color rgb(255,87,51)",
"color tomato", "hsl 9 100 60". Shows every format; Enter copies the hex.
"""

import colorsys
import json
import re
import select
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin

NAMED = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000", "green": "#008000",
    "lime": "#00ff00", "blue": "#0000ff", "yellow": "#ffff00", "cyan": "#00ffff",
    "magenta": "#ff00ff", "gray": "#808080", "grey": "#808080", "silver": "#c0c0c0",
    "maroon": "#800000", "olive": "#808000", "teal": "#008080", "navy": "#000080",
    "purple": "#800080", "orange": "#ffa500", "pink": "#ffc0cb", "brown": "#a52a2a",
    "gold": "#ffd700", "tomato": "#ff6347", "coral": "#ff7f50", "salmon": "#fa8072",
    "indigo": "#4b0082", "violet": "#ee82ee", "crimson": "#dc143c", "khaki": "#f0e68c",
    "turquoise": "#40e0d0", "lavender": "#e6e6fa", "beige": "#f5f5dc",
}


def to_rgb(text):
    t = text.strip().lower()
    if t in NAMED:
        t = NAMED[t]
    m = re.fullmatch(r"#?([0-9a-f]{3})", t)
    if m:
        h = m.group(1)
        return tuple(int(c * 2, 16) for c in h)
    m = re.fullmatch(r"#?([0-9a-f]{6})", t)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r"rgba?\(?\s*(\d{1,3})[ ,]+(\d{1,3})[ ,]+(\d{1,3})\s*\)?", t)
    if m:
        vals = tuple(int(x) for x in m.groups())
        if all(v <= 255 for v in vals):
            return vals
    m = re.fullmatch(r"hsla?\(?\s*(\d{1,3})[ ,]+(\d{1,3})%?[ ,]+(\d{1,3})%?\s*\)?", t)
    if m:
        h, s, light = (int(x) for x in m.groups())
        r, g, b = colorsys.hls_to_rgb((h % 360) / 360, light / 100, s / 100)
        return (round(r * 255), round(g * 255), round(b * 255))
    return None


def formats(rgb):
    r, g, b = rgb
    hex_s = f"#{r:02x}{g:02x}{b:02x}"
    h, light, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    hsl = f"hsl({round(h * 360)}, {round(s * 100)}%, {round(light * 100)}%)"
    return hex_s, f"rgb({r}, {g}, {b})", hsl


def strip_kw(query):
    parts = query.split(maxsplit=1)
    if parts and parts[0].lower() in ("color", "colour", "hex", "rgb", "hsl"):
        head = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""
        if head in ("rgb", "hsl") and rest and not rest.startswith(("rgb", "hsl")):
            return f"{head} {rest}"
        return rest
    return query.strip()


def emit(d):
    print(json.dumps(d), flush=True)


def items_for(query):
    rgb = to_rgb(strip_kw(query))
    if not rgb:
        return None
    hex_s, rgb_s, hsl_s = formats(rgb)
    return [
        {"id": hex_s, "name": hex_s, "description": "hex · Enter to copy", "icon": "palette"},
        {"id": rgb_s, "name": rgb_s, "description": "rgb · Enter to copy", "icon": "palette"},
        {"id": hsl_s, "name": hsl_s, "description": "hsl · Enter to copy", "icon": "palette"},
    ]


def handle_request(request):
    step = request.get("step", "initial")
    query = request.get("query", "").strip()

    if step == "match":
        try:
            items = items_for(query)
        except Exception:
            items = None
        if not items:
            emit({"type": "match", "result": None})
            return
        first = items[0]
        emit({"type": "match", "result": {**first, "copy": first["id"],
              "description": items[1]["name"] + " · " + items[2]["name"]}})
        return

    if step in ("initial", "search"):
        try:
            items = items_for(query)
        except Exception:
            items = None
        if not items:
            items = [{"id": "__hint__", "name": "Convert a color", "icon": "palette",
                      "description": "color #ff5733 · color tomato · color rgb(255,87,51)"}]
        emit(HamrPlugin.results(items, input_mode="realtime",
                                placeholder="color #ff5733 · color tomato · color hsl(9,100,60)"))
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
