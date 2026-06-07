#!/usr/bin/env python3
"""
Dev Tools plugin - instant offline text transforms.

Type `<op> <input>` in the main search, e.g. "base64 hello", "sha256 secret",
"jwt <token>", "urld %20", "uuid", "epoch", "epoch 1700000000". Enter copies.
"""

import base64
import codecs
import hashlib
import json
import re
import select
import signal
import sys
import time
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin


def _hash(algo):
    return lambda s: hashlib.new(algo, s.encode()).hexdigest()


def _jwt(token: str) -> str:
    parts = token.strip().split(".")
    if len(parts) < 2:
        raise ValueError("not a JWT")
    out = {}
    for name, seg in (("header", parts[0]), ("payload", parts[1])):
        pad = seg + "=" * (-len(seg) % 4)
        out[name] = json.loads(base64.urlsafe_b64decode(pad))
    return json.dumps(out, indent=2)


def _epoch(s: str) -> str:
    s = s.strip()
    if not s:
        return f"{int(time.time())}  ({datetime.now(timezone.utc).isoformat()})"
    ts = float(s)
    if ts > 1e12:
        ts /= 1000.0
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _uuid(s: str) -> str:
    n = int(s) if s.strip().isdigit() else 1
    return "\n".join(str(uuid.uuid4()) for _ in range(max(1, min(n, 20))))


def _slug(s: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", s.strip().lower())
    return out.strip("-")


def _words(s: str):
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s.strip())
    return [w for w in re.split(r"[^A-Za-z0-9]+", s) if w]


def _camel(s: str) -> str:
    w = _words(s)
    return (w[0].lower() + "".join(p.capitalize() for p in w[1:])) if w else ""


def _pascal(s: str) -> str:
    return "".join(p.capitalize() for p in _words(s))


def _snake(s: str) -> str:
    return "_".join(w.lower() for w in _words(s))


def _kebab(s: str) -> str:
    return "-".join(w.lower() for w in _words(s))


def _const(s: str) -> str:
    return "_".join(w.upper() for w in _words(s))


def _title(s: str) -> str:
    return " ".join(w.capitalize() for w in _words(s))


OPS = {
    "base64": ("Base64 encode", lambda s: base64.b64encode(s.encode()).decode()),
    "b64": ("Base64 encode", lambda s: base64.b64encode(s.encode()).decode()),
    "unbase64": ("Base64 decode", lambda s: base64.b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "replace")),
    "b64d": ("Base64 decode", lambda s: base64.b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "replace")),
    "url": ("URL encode", urllib.parse.quote),
    "urld": ("URL decode", urllib.parse.unquote),
    "hex": ("To hex", lambda s: s.encode().hex()),
    "unhex": ("From hex", lambda s: bytes.fromhex(s.strip()).decode("utf-8", "replace")),
    "md5": ("MD5", _hash("md5")),
    "sha1": ("SHA1", _hash("sha1")),
    "sha256": ("SHA256", _hash("sha256")),
    "sha512": ("SHA512", _hash("sha512")),
    "jwt": ("JWT decode", _jwt),
    "rot13": ("ROT13", lambda s: codecs.encode(s, "rot_13")),
    "upper": ("Uppercase", str.upper),
    "lower": ("Lowercase", str.lower),
    "reverse": ("Reverse", lambda s: s[::-1]),
    "uuid": ("UUID v4", _uuid),
    "epoch": ("Unix time", _epoch),
    "now": ("Unix time", _epoch),
    "len": ("Length", lambda s: f"{len(s)} chars, {len(s.encode())} bytes, {len(s.split())} words"),
    "json": ("JSON pretty-print", lambda s: json.dumps(json.loads(s), indent=2, ensure_ascii=False)),
    "jsonmin": ("JSON minify", lambda s: json.dumps(json.loads(s), separators=(",", ":"), ensure_ascii=False)),
    "slug": ("Slugify", _slug),
    "camel": ("camelCase", _camel),
    "pascal": ("PascalCase", _pascal),
    "snake": ("snake_case", _snake),
    "kebab": ("kebab-case", _kebab),
    "const": ("CONSTANT_CASE", _const),
    "title": ("Title Case", _title),
}

STANDALONE = {"uuid", "epoch", "now"}


def emit(data: dict) -> None:
    print(json.dumps(data), flush=True)


def compute(query: str):
    """Return (label, result) or None if not a valid op invocation."""
    parts = query.split(maxsplit=1)
    op = parts[0].lower() if parts else ""
    arg = parts[1] if len(parts) > 1 else ""
    if op not in OPS:
        return None
    if not arg and op not in STANDALONE:
        return None
    label, fn = OPS[op]
    return label, fn(arg)


def op_list_results():
    items, seen = [], set()
    for key, (label, _) in OPS.items():
        if label in seen:
            continue
        seen.add(label)
        items.append({"id": f"__op__{key}", "name": key, "description": label, "icon": "data_object"})
    return items


def result_items(label: str, result: str):
    lines = result.split("\n")
    items = [{"id": lines[0], "name": lines[0] if len(lines[0]) <= 200 else lines[0][:200] + "…",
              "description": f"{label} · Enter to copy", "icon": "content_copy"}]
    for line in lines[1:]:
        items.append({"id": line, "name": line, "description": "Enter to copy",
                      "icon": "subdirectory_arrow_right"})
    return items


def handle_request(request: dict) -> None:
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
        first = result.split("\n")[0]
        emit({"type": "match", "result": {
            "id": first, "name": first if len(first) <= 200 else first[:200] + "…",
            "description": label, "icon": "data_object", "copy": first,
        }})
        return

    if step in ("initial", "search"):
        if not query:
            emit(HamrPlugin.results(op_list_results(), input_mode="realtime",
                                    placeholder="op input — e.g. base64 hello"))
            return
        parts = query.split(maxsplit=1)
        op = parts[0].lower()
        if op not in OPS:
            matches = [{"id": f"__op__{k}", "name": k, "description": label, "icon": "data_object"}
                       for k, (label, _) in OPS.items() if k.startswith(op)]
            emit(HamrPlugin.results(
                matches or [{"id": "__none__", "name": f"Unknown op: {op}", "icon": "help",
                             "description": "Try: " + ", ".join(list(OPS)[:8])}],
                input_mode="realtime", placeholder="op input — e.g. base64 hello"))
            return
        try:
            label, result = compute(query) or (OPS[op][0], "")
        except Exception as e:
            emit(HamrPlugin.results(
                [{"id": "__err__", "name": f"{OPS[op][0]}: error", "icon": "error", "description": str(e)}],
                input_mode="realtime"))
            return
        emit(HamrPlugin.results(result_items(label, result), input_mode="realtime",
                                placeholder="op input — e.g. base64 hello"))
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
