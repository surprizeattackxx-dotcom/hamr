#!/usr/bin/env python3
"""
Roman plugin - convert between Roman numerals and Arabic numbers.

Type in the main search: "roman 2024" -> MMXXIV, "roman MMXXIV" -> 2024.
Range 1–3999. Enter copies the result.
"""

import json
import re
import select
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin

NUMERALS = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
    (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]
VALID = re.compile(r"^M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")


def to_roman(n):
    if not (1 <= n <= 3999):
        raise ValueError("range is 1–3999")
    out = []
    for val, sym in NUMERALS:
        while n >= val:
            out.append(sym)
            n -= val
    return "".join(out)


def from_roman(s):
    s = s.upper()
    if not s or not VALID.fullmatch(s):
        raise ValueError("not a valid Roman numeral")
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    prev = 0
    for ch in reversed(s):
        v = vals[ch]
        total += -v if v < prev else v
        prev = v
    return total


def compute(arg):
    """Return (label, result) or None."""
    arg = arg.strip()
    if not arg:
        return None
    if arg.isdigit():
        return "Roman numeral", to_roman(int(arg))
    if re.fullmatch(r"[ivxlcdmIVXLCDM]+", arg):
        return "Arabic number", str(from_roman(arg))
    return None


def strip_kw(query):
    parts = query.split(maxsplit=1)
    if parts and parts[0].lower() == "roman":
        return parts[1].strip() if len(parts) > 1 else ""
    return query.strip()


def emit(data):
    print(json.dumps(data), flush=True)


def handle_request(request):
    step = request.get("step", "initial")
    arg = strip_kw(request.get("query", "").strip())

    if step == "match":
        try:
            computed = compute(arg)
        except Exception:
            computed = None
        if not computed:
            emit({"type": "match", "result": None})
            return
        label, result = computed
        emit({"type": "match", "result": {
            "id": result, "name": result, "description": label,
            "icon": "looks_one", "copy": result,
        }})
        return

    if step in ("initial", "search"):
        if not arg:
            emit(HamrPlugin.results(
                [{"id": "__hint__", "name": "Convert Roman numerals", "icon": "looks_one",
                  "description": "roman 2024 · roman MMXXIV"}],
                input_mode="realtime", placeholder="roman 2024 · roman MMXXIV"))
            return
        try:
            computed = compute(arg)
        except Exception as e:
            emit(HamrPlugin.results(
                [{"id": "__err__", "name": "Cannot convert", "icon": "error",
                  "description": str(e)}], input_mode="realtime"))
            return
        if not computed:
            emit(HamrPlugin.results(
                [{"id": "__none__", "name": "Enter a number or Roman numeral", "icon": "help",
                  "description": "roman 2024 · roman MMXXIV"}], input_mode="realtime"))
            return
        label, result = computed
        items = [{"id": result, "name": result, "description": f"{label} · Enter to copy",
                  "icon": "looks_one"}]
        emit(HamrPlugin.results(items, input_mode="realtime",
                                placeholder="roman 2024 · roman MMXXIV"))
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
