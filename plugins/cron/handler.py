#!/usr/bin/env python3
"""
Cron plugin - explain a cron expression and preview its next run times.

Type in the main search: "cron 0 9 * * 1-5", "cron */15 * * * *",
"cron @daily". Shows a plain-English description plus the next 5 firings.
"""

import json
import select
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin

ALIASES = {
    "@yearly": "0 0 1 1 *", "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *", "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *", "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}

DOW = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
MONTH = ["", "January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"]
FIELD_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
NAME_MAPS = [
    {}, {},
    {},
    {m.lower()[:3]: i for i, m in enumerate(MONTH) if m},
    {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6},
]


def _parse_field(spec, lo, hi, names):
    spec = spec.strip().lower()
    if spec in ("*", "?"):
        return set(range(lo, hi + 1))
    values = set()
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            step = int(step_s)
            if step <= 0:
                raise ValueError("bad step")
        if part in ("*", "?", ""):
            start, end = lo, hi
        elif "-" in part.lstrip("-") and not part.lstrip().startswith("-"):
            a, b = part.split("-", 1)
            start, end = _name(a, names), _name(b, names)
        else:
            start = end = _name(part, names)
        if start > end:
            raise ValueError("range reversed")
        values.update(range(start, end + 1, step))
    if not values or min(values) < lo or max(values) > hi:
        raise ValueError("out of range")
    return values


def _name(tok, names):
    tok = tok.strip()
    if tok in names:
        return names[tok]
    return int(tok)


def parse(expr):
    """Return list of 5 value-sets (min, hour, dom, month, dow) or raise."""
    expr = expr.strip()
    expr = ALIASES.get(expr.lower(), expr)
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f"need 5 fields, got {len(fields)}")
    sets = []
    for spec, (lo, hi), names in zip(fields, FIELD_RANGES, NAME_MAPS):
        s = _parse_field(spec, lo, hi, names)
        sets.append(s)
    if 7 in sets[4]:
        sets[4] = (sets[4] - {7}) | {0}
    return sets


def matches(dt, sets):
    mins, hours, doms, months, dows = sets
    if dt.minute not in mins or dt.hour not in hours or dt.month not in months:
        return False
    dom_restricted = len(doms) < 31
    dow_restricted = len(dows) < 7
    dom_ok = dt.day in doms
    dow_ok = (dt.weekday() + 1) % 7 in dows
    if dom_restricted and dow_restricted:
        return dom_ok or dow_ok
    return dom_ok and dow_ok


def next_runs(sets, start, count=5):
    runs = []
    dt = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = 366 * 24 * 60 * 5
    for _ in range(limit):
        if matches(dt, sets):
            runs.append(dt)
            if len(runs) >= count:
                break
        dt += timedelta(minutes=1)
    return runs


def _step_of(s, lo, hi):
    """Return n if s is a `*/n` pattern (evenly spaced from lo), else None."""
    vals = sorted(s)
    if len(vals) < 2 or vals[0] != lo:
        return None
    diffs = {vals[i + 1] - vals[i] for i in range(len(vals) - 1)}
    step = vals[1] - vals[0]
    if diffs == {step} and step > 1 and vals[-1] + step > hi:
        return step
    return None


def _fmt_set(s, lo, hi):
    step = _step_of(s, lo, hi)
    if step:
        return f"every {step}"
    vals = sorted(s)
    if len(vals) > 2 and vals == list(range(vals[0], vals[-1] + 1)):
        return f"{vals[0]}–{vals[-1]}"
    return ", ".join(str(v) for v in vals)


def describe(sets):
    mins, hours, doms, months, dows = sets
    parts = []
    full_min = mins == set(range(60))
    full_hour = hours == set(range(24))
    min_step = _step_of(mins, 0, 59)
    if full_min and full_hour:
        parts.append("every minute")
    elif min_step and full_hour:
        parts.append(f"every {min_step} minutes")
    elif len(mins) == 1 and len(hours) == 1:
        parts.append(f"at {next(iter(hours)):02d}:{next(iter(mins)):02d}")
    elif len(mins) == 1 and full_hour:
        parts.append(f"at minute {next(iter(mins))} of every hour")
    else:
        md = "every minute" if full_min else f"minute {_fmt_set(mins, 0, 59)}"
        hd = "every hour" if full_hour else f"hour {_fmt_set(hours, 0, 23)}"
        parts.append(f"{md}, {hd}")
    if dows != set(range(7)):
        parts.append("on " + ", ".join(DOW[d] for d in sorted(dows)))
    if doms != set(range(1, 32)):
        parts.append("on day " + ", ".join(str(d) for d in sorted(doms)) + " of the month")
    if months != set(range(1, 13)):
        parts.append("in " + ", ".join(MONTH[m] for m in sorted(months)))
    return ", ".join(parts)


def emit(data):
    print(json.dumps(data), flush=True)


def strip_kw(query):
    parts = query.split(maxsplit=1)
    if parts and parts[0].lower() == "cron":
        return parts[1].strip() if len(parts) > 1 else ""
    return query.strip()


def build_card(expr):
    sets = parse(expr)
    desc = describe(sets)
    runs = next_runs(sets, datetime.now())
    lines = [f"**`{expr}`**", "", desc, "", "**Next runs:**"]
    for r in runs:
        lines.append(f"- {r.strftime('%a %Y-%m-%d %H:%M')}")
    return desc, runs, "\n".join(lines)


def handle_request(request):
    step = request.get("step", "initial")
    query = strip_kw(request.get("query", "").strip())

    if step == "match":
        try:
            desc, runs, _ = build_card(query)
        except Exception:
            emit({"type": "match", "result": None})
            return
        nxt = runs[0].strftime("%a %H:%M") if runs else "never"
        emit({"type": "match", "result": {
            "id": query, "name": desc, "description": f"next: {nxt}",
            "icon": "schedule", "copy": query,
        }})
        return

    if step in ("initial", "search"):
        if not query:
            emit(HamrPlugin.results(
                [{"id": "__hint__", "name": "Explain a cron expression", "icon": "schedule",
                  "description": "cron 0 9 * * 1-5 · cron */15 * * * * · cron @daily"}],
                input_mode="realtime", placeholder="cron 0 9 * * 1-5"))
            return
        try:
            _, _, markdown = build_card(query)
        except Exception as e:
            emit(HamrPlugin.results(
                [{"id": "__err__", "name": "Invalid cron expression", "icon": "error",
                  "description": str(e)}], input_mode="realtime"))
            return
        emit(HamrPlugin.card("Cron", markdown=markdown, status={"text": query}))
        return

    if step == "action":
        emit(HamrPlugin.copy_and_close(query))


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
