#!/usr/bin/env python3
"""
Web search plugin - bang-style search dispatcher.

Type a bang + query in the main search: "g rust async", "yt lofi beats",
"gh hamr launcher", "w mitochondria", "aur brave". Enter opens the browser.
With no recognised bang the query falls back to the default engine.
"""

import json
import select
import signal
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin

Q = "{q}"

# bang -> (label, icon, url-template)
BANGS = {
    "g": ("Google", "search", "https://www.google.com/search?q={q}"),
    "ddg": ("DuckDuckGo", "search", "https://duckduckgo.com/?q={q}"),
    "b": ("Brave Search", "search", "https://search.brave.com/search?q={q}"),
    "kagi": ("Kagi", "search", "https://kagi.com/search?q={q}"),
    "yt": ("YouTube", "smart_display", "https://www.youtube.com/results?search_query={q}"),
    "gh": ("GitHub", "code", "https://github.com/search?q={q}&type=repositories"),
    "ghc": ("GitHub code", "code", "https://github.com/search?q={q}&type=code"),
    "gl": ("GitLab", "code", "https://gitlab.com/search?search={q}"),
    "w": ("Wikipedia", "menu_book", "https://en.wikipedia.org/w/index.php?search={q}"),
    "so": ("Stack Overflow", "quiz", "https://stackoverflow.com/search?q={q}"),
    "r": ("Reddit", "forum", "https://www.reddit.com/search/?q={q}"),
    "aw": ("Arch Wiki", "menu_book", "https://wiki.archlinux.org/index.php?search={q}"),
    "aur": ("AUR", "deployed_code", "https://aur.archlinux.org/packages?K={q}"),
    "arch": ("Arch packages", "deployed_code", "https://archlinux.org/packages/?q={q}"),
    "npm": ("npm", "deployed_code", "https://www.npmjs.com/search?q={q}"),
    "crates": ("crates.io", "deployed_code", "https://crates.io/search?q={q}"),
    "pypi": ("PyPI", "deployed_code", "https://pypi.org/search/?q={q}"),
    "mdn": ("MDN", "menu_book", "https://developer.mozilla.org/en-US/search?q={q}"),
    "docs": ("docs.rs", "menu_book", "https://docs.rs/releases/search?query={q}"),
    "maps": ("Google Maps", "map", "https://www.google.com/maps/search/{q}"),
    "img": ("Google Images", "image", "https://www.google.com/search?tbm=isch&q={q}"),
    "tr": ("Translate", "translate", "https://translate.google.com/?sl=auto&tl=en&text={q}&op=translate"),
    "def": ("Dictionary", "menu_book", "https://www.merriam-webster.com/dictionary/{q}"),
    "ud": ("Urban Dictionary", "menu_book", "https://www.urbandictionary.com/define.php?term={q}"),
    "imdb": ("IMDb", "movie", "https://www.imdb.com/find/?q={q}"),
    "wa": ("Wolfram Alpha", "functions", "https://www.wolframalpha.com/input?i={q}"),
    "amazon": ("Amazon", "shopping_cart", "https://www.amazon.com/s?k={q}"),
    "wb": ("Wayback Machine", "history", "https://web.archive.org/web/*/{q}"),
    "std": ("Rust std", "menu_book", "https://doc.rust-lang.org/std/?search={q}"),
    "cpp": ("cppreference", "menu_book", "https://en.cppreference.com/mwiki/index.php?search={q}"),
    "protondb": ("ProtonDB", "sports_esports", "https://www.protondb.com/search?q={q}"),
    "yt-music": ("YouTube Music", "music_note", "https://music.youtube.com/search?q={q}"),
    "gpt": ("ChatGPT", "smart_toy", "https://chatgpt.com/?q={q}"),
    "perplexity": ("Perplexity", "smart_toy", "https://www.perplexity.ai/search?q={q}"),
    "phind": ("Phind", "smart_toy", "https://www.phind.com/search?q={q}"),
}

DEFAULT = "g"


def split_bang(query):
    parts = query.split(maxsplit=1)
    if not parts:
        return None, ""
    head = parts[0].lower()
    if head in BANGS and len(parts) > 1 and parts[1].strip():
        return head, parts[1].strip()
    return None, query.strip()


def build(bang, term):
    label, icon, tmpl = BANGS[bang]
    url = tmpl.replace(Q, urllib.parse.quote(term))
    return {
        "id": url, "name": f"{label}: {term}",
        "description": f"Open {label} · {url[:60]}", "icon": icon,
    }


def emit(data):
    print(json.dumps(data), flush=True)


def bang_list():
    items = []
    for key, (label, icon, _) in BANGS.items():
        items.append({"id": f"__bang__{key}", "name": f"{key}  —  {label}",
                      "description": f"e.g. {key} <query>", "icon": icon})
    return items


def handle_request(request):
    step = request.get("step", "initial")
    query = request.get("query", "").strip()

    if step == "match":
        bang, term = split_bang(query)
        if not bang:
            emit({"type": "match", "result": None})
            return
        item = build(bang, term)
        emit({"type": "match", "result": {**item, "openUrl": item["id"]}})
        return

    if step in ("initial", "search"):
        if not query:
            emit(HamrPlugin.results(bang_list(), input_mode="realtime",
                                    placeholder="g <query> · yt <query> · gh <query> …"))
            return
        bang, term = split_bang(query)
        if bang:
            item = build(bang, term)
        else:
            item = build(DEFAULT, term)
            item["description"] = f"Search Google · Enter to open"
        emit(HamrPlugin.results([item], input_mode="realtime",
                                placeholder="g <query> · yt <query> · gh <query> …"))
        return

    if step == "action":
        url = (request.get("selected", {}) or {}).get("id", "")
        if url.startswith("__"):
            emit(HamrPlugin.noop())
            return
        emit(HamrPlugin.open_url(url))


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
