#!/usr/bin/env python3
"""
Kaomoji plugin - Japanese emoticons, searchable by mood.

Activate the plugin (or type "kao"), optionally with a keyword: "kao shrug",
"kao happy", "kao table". Enter copies the kaomoji.
"""

import json
import select
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin

# (kaomoji, keywords)
KAOMOJI = [
    ("¯\\_(ツ)_/¯", "shrug whatever dunno idk meh"),
    ("(╯°□°)╯︵ ┻━┻", "table flip rage angry mad"),
    ("┬─┬ノ( º _ ºノ)", "table unflip calm fix put back"),
    ("(ノ◕ヮ◕)ノ*:･ﾟ✧", "magic sparkle excited happy yay"),
    ("(づ｡◕‿‿◕｡)づ", "hug love cuddle"),
    ("(╥﹏╥)", "cry sad tears sobbing"),
    ("(◕‿◕)", "happy smile cute content"),
    ("(¬‿¬)", "smug sly suspicious"),
    ("(✿◠‿◠)", "happy flower cute pretty"),
    ("(ಠ_ಠ)", "disapproval stare look serious"),
    ("(ಥ﹏ಥ)", "crying sad sob"),
    ("ᕕ( ᐛ )ᕗ", "happy walk run go leave"),
    ("(•_•) ( •_•)>⌐■-■ (⌐■_■)", "deal with it cool sunglasses"),
    ("(☞ﾟヮﾟ)☞", "point you finger guns"),
    ("(ノ°益°)ノ", "rage angry yell scream"),
    ("(＾▽＾)", "happy joy smile"),
    ("(；一_一)", "unamused tired done annoyed"),
    ("(°ロ°)", "shock surprise wow"),
    ("ヽ(´▽`)/", "cheer happy excited yay"),
    ("(눈_눈)", "unimpressed side eye done"),
    ("( ͡° ͜ʖ ͡°)", "lenny smirk suggestive"),
    ("ʕ•ᴥ•ʔ", "bear cute animal"),
    ("(=^･ω･^=)", "cat cute animal meow"),
    ("(っ◔◡◔)っ ♥", "love heart give cute"),
    ("(•‿•)", "smile content sneaky"),
    ("\\(^o^)/", "celebrate hooray happy yay"),
    ("(＞﹏＜)", "frustrated cringe ugh"),
    ("(´･_･`)", "worried unsure concerned"),
    ("(ᵔ◡ᵔ)", "content cozy happy"),
    ("ᕦ(ò_óˇ)ᕤ", "flex strong gym muscle"),
]


def strip_kw(query):
    parts = query.split(maxsplit=1)
    if parts and parts[0].lower() in ("kao", "kaomoji"):
        return parts[1].strip() if len(parts) > 1 else ""
    return query.strip()


def search(query):
    q = query.lower().strip()
    if not q:
        return KAOMOJI
    return [k for k in KAOMOJI if q in k[1] or q in k[0].lower()]


def emit(d):
    print(json.dumps(d), flush=True)


def items_for(query):
    matches = search(strip_kw(query))
    if not matches:
        return [{"id": "__none__", "name": "No kaomoji found", "icon": "sentiment_satisfied",
                 "description": "try: shrug, happy, table, cat, love"}]
    return [{"id": k, "name": k, "description": kw.split()[0] if kw else "", "icon": "sentiment_satisfied"}
            for k, kw in matches]


def handle_request(request):
    step = request.get("step", "initial")
    query = request.get("query", "")

    if step in ("initial", "search"):
        emit(HamrPlugin.results(items_for(query), input_mode="realtime",
                                placeholder="kaomoji — search by mood (shrug, happy, table)"))
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
