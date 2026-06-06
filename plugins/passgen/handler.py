#!/usr/bin/env python3
"""
Password Generator plugin.

  pass            - 20-char strong password
  pass 32         - 32 chars
  pass simple     - letters + digits only (no symbols)
  passphrase      - 5-word diceware-style phrase
  passphrase 7    - 7 words
"""

import json
import secrets
import select
import signal
import string
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin

SYMBOLS = "!@#$%^&*()-_=+[]{};:,.?"
WORDS = (
    "able acid aged also area army away baby back ball band bank base bath bear beat "
    "bell belt bird blue boat body bone book boot born boss both bowl bulk burn bush "
    "calm card care cash cell chip city clay club coal coat code cold cope cord core "
    "corn cost crew crop dark data dawn deal dean dear debt deep desk dial diet disk "
    "dock dose dust duty east edge exit face fact fair fall farm fast fear feed feel "
    "feet fell file fill film find fine fire fish five flag flat flow folk food foot "
    "ford form fort four free frog fuel full fund gain game gate gear gift girl glad "
    "goal goat gold golf good gray grew grid grip grow gulf hall hand hard harm hawk "
    "head heat held hero high hill hint hire hold hole holy home hook hope horn host "
    "hour huge hunt idea inch iron item jack jade jane jazz join jump jury keen keep "
    "kick kind king knee knew knot lace lack lake lamp land lane last late lawn lead "
    "leaf lean left lend lens less life lift like line link lion list live load loan "
    "lock loft long look loop lord lose loss loud love luck lung made mail main make "
    "male mall many maps mark mask mass mate math meal mean meat meet melt menu mere "
    "mesh mile milk mill mind mine mint miss mode mood moon more moss most moth move "
    "much mule muse name navy near neat neck need nest news next nice nick node nose "
    "note noun null oath obey odds onto oval oven over pace pack page paid pain pair "
    "palm park part pass past path peak pear peer pile pine pink pipe plan play plot "
    "plug plus poem poet pole poll pond pool poor pope port pose post pour pull pump "
    "pure push race rack rail rain rank rare rate read real reef rely rent rest rice "
    "rich ride ring rise risk road rock role roll roof room root rope rose rule rush "
    "safe sage said sail salt same sand save scan seal seat seed seek self sell semi "
    "send sent ship shoe shop shot show shut sick side sign silk site size skin slip "
    "slot slow snap snow soap sock soft soil sold sole some song sort soul soup spin "
    "spot star stay stem step stir stop sure surf swim tale talk tall tank tape task "
    "team tear tech tell tend tent term test text than that them then they thin this "
    "tide tidy tile till time tiny toll tone tool tour town trap tree trim trip true "
    "tube tune turn twin type unit vary vast verb very vest view vial vibe vine visa "
    "void volt vote wage wait wake walk wall want ward warm wash wave weak wear weed "
    "week well went were west what when whip wide wife wild will wind wine wing wins "
    "wire wise wish with wolf wood wool word wore work worm yard yarn yeah year yoga "
    "your zero zone zoom"
).split()


def emit(data: dict) -> None:
    print(json.dumps(data), flush=True)


def gen_password(length: int, symbols: bool) -> str:
    alphabet = string.ascii_letters + string.digits + (SYMBOLS if symbols else "")
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and (not symbols or any(c in SYMBOLS for c in pw))):
            return pw


def gen_passphrase(words: int) -> str:
    chosen = [secrets.choice(WORDS).capitalize() for _ in range(words)]
    return "-".join(chosen) + str(secrets.randbelow(100))


def parse(query: str):
    parts = query.lower().split()
    op = parts[0] if parts else "pass"
    rest = parts[1:]
    if op in ("passphrase",) or "words" in rest or "phrase" in rest:
        n = next((int(t) for t in rest if t.isdigit()), 5)
        return "phrase", max(3, min(n, 12)), False
    length = next((int(t) for t in rest if t.isdigit()), 20)
    symbols = "simple" not in rest and "nosym" not in rest
    return "pw", max(6, min(length, 128)), symbols


def make_results(query: str):
    kind, n, symbols = parse(query)
    if kind == "phrase":
        cands = [gen_passphrase(n) for _ in range(5)]
        desc = f"{n}-word passphrase · Enter to copy"
        icon = "key"
    else:
        cands = [gen_password(n, symbols) for _ in range(5)]
        desc = f"{n} chars{'' if symbols else ' · no symbols'} · Enter to copy"
        icon = "password"
    return [{"id": c, "name": c, "description": desc, "icon": icon} for c in cands]


def handle_request(request: dict) -> None:
    step = request.get("step", "initial")
    query = request.get("query", "").strip()

    if step == "match":
        kind, n, symbols = parse(query)
        pw = gen_passphrase(n) if kind == "phrase" else gen_password(n, symbols)
        emit({"type": "match", "result": {
            "id": pw, "name": pw, "icon": "password",
            "description": f"Generated {'passphrase' if kind == 'phrase' else 'password'} · Enter to copy",
            "copy": pw,
        }})
        return

    if step in ("initial", "search"):
        emit(HamrPlugin.results(make_results(query), input_mode="realtime",
                                placeholder="pass [length] [simple] · passphrase [words]"))
        return

    if step == "action":
        pw = (request.get("selected", {}) or {}).get("id", "")
        emit(HamrPlugin.copy_and_close(pw) if pw and not pw.startswith("__") else HamrPlugin.noop())


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
