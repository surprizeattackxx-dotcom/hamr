#!/usr/bin/env python3
"""
Translate plugin - instant text translation (no LLM).

Type in the main search: "tr hola mundo", "tr good morning to french",
"tr fr: how are you". Auto-detects the source; default target is English.
Enter copies the translation. Powered by Google's gtx endpoint, cached.
"""

import json
import select
import signal
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin

CACHE = {}
CACHE_MAX = 80

LANGS = {
    "english": "en", "spanish": "es", "french": "fr", "german": "de",
    "italian": "it", "portuguese": "pt", "dutch": "nl", "russian": "ru",
    "japanese": "ja", "chinese": "zh-CN", "korean": "ko", "arabic": "ar",
    "hindi": "hi", "turkish": "tr", "polish": "pl", "swedish": "sv",
    "greek": "el", "hebrew": "iw", "thai": "th", "vietnamese": "vi",
    "indonesian": "id", "ukrainian": "uk", "czech": "cs", "danish": "da",
    "finnish": "fi", "norwegian": "no", "romanian": "ro", "hungarian": "hu",
    "latin": "la", "esperanto": "eo",
}
CODES = set(LANGS.values()) | {"en", "es", "fr", "de", "zh", "pt"}


def resolve_lang(token):
    t = token.lower()
    if t in LANGS:
        return LANGS[t]
    if t in CODES or len(t) == 2:
        return t
    return None


def parse(query):
    """Return (text, target_code) or None."""
    parts = query.split(maxsplit=1)
    if not parts or parts[0].lower() not in ("tr", "translate"):
        return None
    body = parts[1].strip() if len(parts) > 1 else ""
    if not body:
        return None
    target = "en"
    # "<code>: text"
    if ":" in body.split(maxsplit=1)[0]:
        pre, rest = body.split(":", 1)
        code = resolve_lang(pre.strip())
        if code:
            return rest.strip(), code
    # "... to <lang>"
    low = body.lower()
    idx = low.rfind(" to ")
    if idx != -1:
        cand = body[idx + 4:].strip()
        code = resolve_lang(cand)
        if code:
            return body[:idx].strip(), code
    return body, target


def translate(text, target):
    key = f"{target}\x00{text}"
    cached = CACHE.get(key)
    if cached and time.time() - cached[0] < 3600:
        return cached[1]
    url = (
        "https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl=auto&tl={urllib.parse.quote(target)}&dt=t"
        f"&q={urllib.parse.quote(text)}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read())
        out = "".join(seg[0] for seg in data[0] if seg[0])
        src = data[2] if len(data) > 2 else "?"
        result = (out, src)
        CACHE[key] = (time.time(), result)
        if len(CACHE) > CACHE_MAX:
            CACHE.pop(next(iter(CACHE)))
        return result
    except Exception:
        return None


def emit(d):
    print(json.dumps(d), flush=True)


def result_item(query):
    parsed = parse(query)
    if not parsed:
        return None
    text, target = parsed
    res = translate(text, target)
    if not res:
        return None
    out, src = res
    return {
        "id": out, "name": out if len(out) <= 200 else out[:200] + "…",
        "description": f"{src} → {target} · Enter to copy", "icon": "translate", "copy": out,
    }


def handle_request(request):
    step = request.get("step", "initial")
    query = request.get("query", "").strip()

    if step == "match":
        try:
            item = result_item(query)
        except Exception:
            item = None
        emit({"type": "match", "result": item})
        return

    if step in ("initial", "search"):
        try:
            item = result_item(query)
        except Exception:
            item = None
        items = [item] if item else [{
            "id": "__hint__", "name": "Translate text", "icon": "translate",
            "description": "tr hola mundo · tr good morning to french · tr fr: how are you",
        }]
        emit(HamrPlugin.results(items, input_mode="realtime",
                                placeholder="tr <text> · tr <text> to <language>"))
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
