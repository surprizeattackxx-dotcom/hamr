#!/usr/bin/env python3
"""
Unicode plugin - inspect characters, codepoints and names (offline).

Type in the main search:
  char <text>      - codepoint + name for each character
  u+1f600          - the character for a codepoint
  unicode <name>   - look up a character by its Unicode name (e.g. "heart")
Enter copies the character(s) or the looked-up glyph.
"""

import json
import re
import select
import signal
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin

CODEPOINT_RE = re.compile(r"^(?:u\+|0x|\\u)?([0-9a-fA-F]{2,6})$", re.IGNORECASE)


def describe(ch):
    cp = ord(ch)
    try:
        name = unicodedata.name(ch)
    except ValueError:
        name = unicodedata.category(ch)
    return f"U+{cp:04X}", name


def lookup(query):
    """Return (display, copy, label) or None."""
    q = query.strip()
    if not q:
        return None

    # codepoint -> char
    m = CODEPOINT_RE.match(q.replace(" ", ""))
    if m:
        try:
            ch = chr(int(m.group(1), 16))
        except (ValueError, OverflowError):
            return None
        code, name = describe(ch)
        return f"{ch}   {code}  {name}", ch, "codepoint"

    # name lookup (exact, case-insensitive)
    try:
        ch = unicodedata.lookup(q.upper())
        code, name = describe(ch)
        return f"{ch}   {code}  {name}", ch, "by name"
    except KeyError:
        pass

    # otherwise: describe each character in the input
    chars = list(q)
    if len(chars) == 1:
        code, name = describe(chars[0])
        return f"{chars[0]}   {code}  {name}", chars[0], "character"
    parts = [f"{c} {describe(c)[0]}" for c in chars[:12]]
    return "  ".join(parts), q, f"{len(chars)} characters"


def strip_kw(query):
    parts = query.split(maxsplit=1)
    if parts and parts[0].lower() in ("char", "unicode", "uni"):
        return parts[1].strip() if len(parts) > 1 else ""
    return query.strip()


def emit(d):
    print(json.dumps(d), flush=True)


def item_for(query):
    res = lookup(strip_kw(query))
    if not res:
        return None
    display, copy, label = res
    return {
        "id": copy, "name": display if len(display) <= 200 else display[:200] + "…",
        "description": f"{label} · Enter to copy", "icon": "tag", "copy": copy,
    }


def handle_request(request):
    step = request.get("step", "initial")
    query = request.get("query", "").strip()

    if step == "match":
        try:
            item = item_for(query)
        except Exception:
            item = None
        emit({"type": "match", "result": item})
        return

    if step in ("initial", "search"):
        try:
            item = item_for(query)
        except Exception:
            item = None
        items = [item] if item else [{
            "id": "__hint__", "name": "Inspect Unicode", "icon": "tag",
            "description": "char ★ · u+1f600 · unicode snowman",
        }]
        emit(HamrPlugin.results(items, input_mode="realtime",
                                placeholder="char <text> · u+1f600 · unicode <name>"))
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
