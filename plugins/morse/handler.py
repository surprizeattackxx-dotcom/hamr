#!/usr/bin/env python3
"""
Morse plugin - encode text to Morse and decode it back.

Type in the main search: "morse hello world" -> dots/dashes,
"unmorse .... ..." -> text. Words separate with " / ". Enter copies.
"""

import json
import select
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin

CODE = {
    "a": ".-", "b": "-...", "c": "-.-.", "d": "-..", "e": ".", "f": "..-.",
    "g": "--.", "h": "....", "i": "..", "j": ".---", "k": "-.-", "l": ".-..",
    "m": "--", "n": "-.", "o": "---", "p": ".--.", "q": "--.-", "r": ".-.",
    "s": "...", "t": "-", "u": "..-", "v": "...-", "w": ".--", "x": "-..-",
    "y": "-.--", "z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
    ".": ".-.-.-", ",": "--..--", "?": "..--..", "'": ".----.", "!": "-.-.--",
    "/": "-..-.", "(": "-.--.", ")": "-.--.-", "&": ".-...", ":": "---...",
    ";": "-.-.-.", "=": "-...-", "+": ".-.-.", "-": "-....-", "_": "..--.-",
    '"': ".-..-.", "$": "...-..-", "@": ".--.-.",
}
DECODE = {v: k for k, v in CODE.items()}


def encode(text):
    out = []
    for word in text.split():
        letters = [CODE[c] for c in word.lower() if c in CODE]
        if letters:
            out.append(" ".join(letters))
    return " / ".join(out)


def decode(text):
    words = []
    for chunk in text.replace("|", "/").split("/"):
        letters = [DECODE.get(sym, "?") for sym in chunk.split()]
        if letters:
            words.append("".join(letters))
    return " ".join(words)


def compute(query):
    """Return (label, result) or None."""
    parts = query.split(maxsplit=1)
    cmd = parts[0].lower() if parts else ""
    arg = parts[1].strip() if len(parts) > 1 else ""
    if not arg:
        return None
    if cmd == "morse":
        res = encode(arg)
        return ("To Morse", res) if res else None
    if cmd in ("unmorse", "demorse"):
        res = decode(arg)
        return ("From Morse", res) if res.strip() else None
    return None


def emit(data):
    print(json.dumps(data), flush=True)


def handle_request(request):
    step = request.get("step", "initial")
    query = request.get("query", "").strip()

    if step == "match":
        try:
            computed = compute(query)
        except Exception:
            computed = None
        if not computed:
            emit({"type": "match", "result": None})
            return
        label, result = computed
        shown = result if len(result) <= 200 else result[:200] + "…"
        emit({"type": "match", "result": {
            "id": result, "name": shown, "description": label,
            "icon": "graphic_eq", "copy": result,
        }})
        return

    if step in ("initial", "search"):
        try:
            computed = compute(query)
        except Exception:
            computed = None
        if computed:
            label, result = computed
            shown = result if len(result) <= 300 else result[:300] + "…"
            items = [{"id": result, "name": shown, "description": f"{label} · Enter to copy",
                      "icon": "graphic_eq"}]
        else:
            items = [{"id": "__hint__", "name": "Encode or decode Morse code", "icon": "graphic_eq",
                      "description": "morse hello world · unmorse .... . .-.. .-.. ---"}]
        emit(HamrPlugin.results(items, input_mode="realtime",
                                placeholder="morse hello · unmorse .... ."))
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
