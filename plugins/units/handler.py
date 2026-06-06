#!/usr/bin/env python3
"""
Units plugin - instant offline unit and number-base conversion.

Type in the main search: "100 km to mi", "32 f to c", "5 gb in mb",
"255 to hex", "0xff to dec", "1h in s". Enter copies the result.
"""

import json
import re
import select
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin


# category -> { alias: factor-to-base-unit }
UNITS = {
    "length": {
        "m": 1, "meter": 1, "meters": 1, "metre": 1,
        "km": 1000, "kilometer": 1000, "kilometers": 1000,
        "cm": 0.01, "mm": 0.001, "um": 1e-6, "nm": 1e-9,
        "mi": 1609.344, "mile": 1609.344, "miles": 1609.344,
        "yd": 0.9144, "yard": 0.9144, "yards": 0.9144,
        "ft": 0.3048, "foot": 0.3048, "feet": 0.3048,
        "in": 0.0254, "inch": 0.0254, "inches": 0.0254,
        "nmi": 1852, "ly": 9.4607e15, "au": 1.495978707e11,
    },
    "mass": {
        "g": 1, "gram": 1, "grams": 1,
        "kg": 1000, "kilogram": 1000, "kilograms": 1000,
        "mg": 0.001, "ug": 1e-6, "t": 1e6, "tonne": 1e6, "ton": 1e6,
        "lb": 453.59237, "lbs": 453.59237, "pound": 453.59237, "pounds": 453.59237,
        "oz": 28.349523125, "ounce": 28.349523125, "ounces": 28.349523125,
        "st": 6350.29318, "stone": 6350.29318,
    },
    "data": {
        "b": 1, "byte": 1, "bytes": 1,
        "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12, "pb": 1e15,
        "kib": 1024, "mib": 1024**2, "gib": 1024**3, "tib": 1024**4, "pib": 1024**5,
        "bit": 0.125, "bits": 0.125, "kbit": 125, "mbit": 125000, "gbit": 1.25e8,
    },
    "time": {
        "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
        "ms": 0.001, "us": 1e-6, "ns": 1e-9,
        "min": 60, "mins": 60, "minute": 60, "minutes": 60,
        "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600,
        "d": 86400, "day": 86400, "days": 86400,
        "wk": 604800, "week": 604800, "weeks": 604800,
        "mo": 2629800, "month": 2629800, "months": 2629800,
        "yr": 31557600, "year": 31557600, "years": 31557600,
    },
    "speed": {
        "mps": 1, "kmh": 1 / 3.6, "kph": 1 / 3.6,
        "mph": 0.44704, "fps": 0.3048, "knot": 0.514444, "knots": 0.514444, "kn": 0.514444,
    },
    "area": {
        "m2": 1, "km2": 1e6, "cm2": 1e-4, "mm2": 1e-6,
        "ha": 1e4, "hectare": 1e4, "acre": 4046.8564224, "acres": 4046.8564224,
        "ft2": 0.09290304, "in2": 0.00064516, "mi2": 2589988.110336,
    },
    "volume": {
        "l": 1, "liter": 1, "liters": 1, "litre": 1,
        "ml": 0.001, "cl": 0.01, "dl": 0.1, "m3": 1000,
        "gal": 3.785411784, "gallon": 3.785411784, "gallons": 3.785411784,
        "qt": 0.946352946, "pt": 0.473176473, "cup": 0.2365882365,
        "floz": 0.0295735296, "tbsp": 0.01478676, "tsp": 0.00492892,
    },
    "pressure": {
        "pa": 1, "kpa": 1000, "hpa": 100, "bar": 1e5, "mbar": 100,
        "atm": 101325, "psi": 6894.757293, "mmhg": 133.322387, "torr": 133.322368,
    },
    "energy": {
        "j": 1, "joule": 1, "kj": 1000, "mj": 1e6,
        "cal": 4.184, "kcal": 4184, "wh": 3600, "kwh": 3.6e6,
        "ev": 1.602176634e-19, "btu": 1055.05585,
    },
    "power": {
        "w": 1, "watt": 1, "kw": 1000, "mw": 1e6, "hp": 745.699872,
    },
    "angle": {
        "deg": 1, "degree": 1, "degrees": 1,
        "rad": 57.29577951308232, "radian": 57.29577951308232,
        "grad": 0.9, "turn": 360, "arcmin": 1 / 60, "arcsec": 1 / 3600,
    },
}

# alias -> (category, factor)
ALIAS = {}
for cat, table in UNITS.items():
    for name, factor in table.items():
        ALIAS[name] = (cat, factor)

TEMP = {"c", "celsius", "f", "fahrenheit", "k", "kelvin"}
BASES = {"hex": 16, "dec": 10, "bin": 2, "oct": 8, "decimal": 10,
         "hexadecimal": 16, "binary": 2, "octal": 8}


def to_celsius(v, unit):
    u = unit[0]
    if u == "c":
        return v
    if u == "f":
        return (v - 32) * 5 / 9
    return v - 273.15  # kelvin


def from_celsius(c, unit):
    u = unit[0]
    if u == "c":
        return c
    if u == "f":
        return c * 9 / 5 + 32
    return c + 273.15


def fmt(n):
    if isinstance(n, int):
        return str(n)
    if n == int(n) and abs(n) < 1e15:
        return str(int(n))
    r = f"{n:.6g}"
    return r


def parse_int(token):
    t = token.lower()
    if t.startswith("0x"):
        return int(t, 16)
    if t.startswith("0b"):
        return int(t, 2)
    if t.startswith("0o"):
        return int(t, 8)
    return int(t, 10)


def base_convert(value_token, target):
    n = parse_int(value_token)
    base = BASES[target]
    if base == 16:
        return f"0x{n:x}", f"{n} → hex"
    if base == 2:
        return f"0b{n:b}", f"{n} → binary"
    if base == 8:
        return f"0o{n:o}", f"{n} → octal"
    return str(n), "→ decimal"


NUM = r"[-+]?[\d.,]+(?:e[-+]?\d+)?"
# "<num><unit> [to|in|as|>] <unit>"  unit may hug the number
PATTERN = re.compile(
    rf"^\s*({NUM})\s*([a-zA-Z°µ/0-9]+)?\s*(?:to|in|as|>|->)\s*([a-zA-Z°µ/0-9]+)\s*$",
    re.IGNORECASE,
)


def norm_unit(u):
    if not u:
        return u
    return u.lower().replace("°", "").replace("µ", "u").replace("/", "p").strip()


def convert(query):
    """Return (result_str, label) or None."""
    m = PATTERN.match(query)
    if not m:
        return None
    num_s, from_u, to_u = m.group(1), m.group(2), m.group(3)
    value_s = num_s.replace(",", "")
    to_n = norm_unit(to_u)

    # number-base conversion: "255 to hex", "0xff to dec" (prefix hugs the digits)
    if to_n in BASES:
        token = (num_s + (from_u or "")).replace(",", "").strip()
        try:
            out, label = base_convert(token, to_n)
            return out, label
        except ValueError:
            pass

    try:
        value = float(value_s)
    except ValueError:
        return None

    from_n = norm_unit(from_u)
    if not from_n:
        return None

    # temperature
    if from_n in TEMP and to_n in TEMP:
        c = to_celsius(value, from_n)
        out = from_celsius(c, to_n)
        return f"{fmt(round(out, 4))} {to_u.upper()}", f"{num_s.strip()} {from_u.upper()} → {to_u.upper()}"

    if from_n in ALIAS and to_n in ALIAS:
        fc, ff = ALIAS[from_n]
        tc, tf = ALIAS[to_n]
        if fc != tc:
            return None
        out = value * ff / tf
        return f"{fmt(round(out, 6))} {to_u}", f"{num_s.strip()} {from_u} → {to_u}"

    return None


def emit(data):
    print(json.dumps(data), flush=True)


def handle_request(request):
    step = request.get("step", "initial")
    query = request.get("query", "").strip()

    if step == "match":
        try:
            res = convert(query)
        except Exception:
            res = None
        if not res:
            emit({"type": "match", "result": None})
            return
        result, label = res
        emit({"type": "match", "result": {
            "id": result, "name": result, "description": label,
            "icon": "swap_horiz", "copy": result,
        }})
        return

    if step in ("initial", "search"):
        try:
            res = convert(query)
        except Exception:
            res = None
        if res:
            result, label = res
            items = [{"id": result, "name": result, "description": f"{label} · Enter to copy",
                      "icon": "swap_horiz"}]
        else:
            items = [{"id": "__hint__", "name": "Convert units or bases", "icon": "swap_horiz",
                      "description": "e.g. 100 km to mi · 32 f to c · 255 to hex · 5 gb in mb"}]
        emit(HamrPlugin.results(items, input_mode="realtime",
                                placeholder="100 km to mi  ·  255 to hex"))
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
