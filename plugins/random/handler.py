#!/usr/bin/env python3
"""
Random plugin - dice, coins, ranges, picks and lorem ipsum.

Type in the main search: "roll 2d6", "rand 1-100", "coin", "pick a, b, c",
"flip 3", "lorem 30". Enter copies the result.
"""

import json
import random
import re
import select
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin

EIGHTBALL = [
    "It is certain.", "Without a doubt.", "Yes, definitely.", "You may rely on it.",
    "Most likely.", "Outlook good.", "Signs point to yes.", "Yes.",
    "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
    "Cannot predict now.", "Concentrate and ask again.",
    "Don't count on it.", "My reply is no.", "My sources say no.",
    "Outlook not so good.", "Very doubtful.",
]

LOREM = (
    "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod "
    "tempor incididunt ut labore et dolore magna aliqua ut enim ad minim veniam "
    "quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo "
    "consequat duis aute irure dolor in reprehenderit in voluptate velit esse "
    "cillum dolore eu fugiat nulla pariatur excepteur sint occaecat cupidatat non "
    "proident sunt in culpa qui officia deserunt mollit anim id est laborum"
).split()


def roll_dice(spec):
    m = re.fullmatch(r"(\d*)d(\d+)([+-]\d+)?", spec.replace(" ", ""), re.IGNORECASE)
    if not m:
        return None
    n = int(m.group(1) or 1)
    sides = int(m.group(2))
    mod = int(m.group(3) or 0)
    if not (1 <= n <= 100 and 2 <= sides <= 1000):
        return None
    rolls = [random.randint(1, sides) for _ in range(n)]
    total = sum(rolls) + mod
    if n == 1 and not mod:
        return str(total), f"d{sides}"
    detail = " + ".join(map(str, rolls)) + (f" {m.group(3)}" if mod else "")
    return str(total), f"{spec}: {detail}"


def rand_range(arg):
    m = re.fullmatch(r"\s*(-?\d+)\s*(?:-|to|\.\.)\s*(-?\d+)\s*", arg)
    if not m:
        return None
    lo, hi = int(m.group(1)), int(m.group(2))
    if lo > hi:
        lo, hi = hi, lo
    return str(random.randint(lo, hi)), f"random {lo}–{hi}"


def handle(query):
    """Return (result, label) or None."""
    parts = query.split(maxsplit=1)
    cmd = parts[0].lower() if parts else ""
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("coin", "flip"):
        n = int(arg) if arg.isdigit() and int(arg) > 0 else 1
        n = min(n, 100)
        if n == 1:
            return random.choice(["Heads", "Tails"]), "coin flip"
        flips = [random.choice(["H", "T"]) for _ in range(n)]
        return " ".join(flips), f"{n} flips · {flips.count('H')}H {flips.count('T')}T"

    if cmd in ("8ball", "8", "eightball"):
        return random.choice(EIGHTBALL), "magic 8-ball"

    if cmd in ("roll", "dice"):
        spec = arg or "1d6"
        return roll_dice(spec)

    if cmd in ("rand", "random"):
        r = rand_range(arg)
        if r:
            return r
        if arg.isdigit():
            n = int(arg)
            return str(random.randint(1, n)), f"random 1–{n}"
        if not arg:
            return str(random.randint(1, 100)), "random 1–100"
        return None

    if cmd in ("pick", "choose"):
        opts = [o.strip() for o in re.split(r"[,/]| or ", arg) if o.strip()]
        if len(opts) < 2:
            return None
        return random.choice(opts), f"picked from {len(opts)} options"

    if cmd == "lorem":
        n = int(arg) if arg.isdigit() else 25
        n = max(1, min(n, 500))
        words = (LOREM * (n // len(LOREM) + 1))[:n]
        text = " ".join(words)
        return text[0].upper() + text[1:] + ".", f"{n} words"

    return None


def emit(data):
    print(json.dumps(data), flush=True)


def handle_request(request):
    step = request.get("step", "initial")
    query = request.get("query", "").strip()

    if step == "match":
        try:
            res = handle(query)
        except Exception:
            res = None
        if not res:
            emit({"type": "match", "result": None})
            return
        result, label = res
        shown = result if len(result) <= 200 else result[:200] + "…"
        emit({"type": "match", "result": {
            "id": result, "name": shown, "description": label,
            "icon": "casino", "copy": result,
        }})
        return

    if step in ("initial", "search"):
        try:
            res = handle(query)
        except Exception:
            res = None
        if res:
            result, label = res
            shown = result if len(result) <= 200 else result[:200] + "…"
            items = [{"id": result, "name": shown, "description": f"{label} · Enter to copy",
                      "icon": "casino"}]
        else:
            items = [{"id": "__hint__", "name": "Roll, flip, pick or generate", "icon": "casino",
                      "description": "roll 2d6 · rand 1-100 · coin · pick a, b, c · lorem 30"}]
        emit(HamrPlugin.results(items, input_mode="realtime",
                                placeholder="roll 2d6 · rand 1-100 · coin · pick a,b,c"))
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
