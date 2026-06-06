#!/usr/bin/env python3
"""
QR Code plugin - generate a QR code from text or a URL.

From the main search: "qr <text>" -> Enter opens the image.
Inside the plugin: type any text to see the QR inline, then open or copy.
"""

import json
import select
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from sdk.hamr_sdk import HamrPlugin

PNG_PATH = "/tmp/hamr-qr.png"
STATE = {"text": ""}


def emit(data: dict) -> None:
    print(json.dumps(data), flush=True)


def ascii_qr(text: str) -> str:
    try:
        return subprocess.run(["qrencode", "-t", "UTF8", "-m", "1", text],
                              capture_output=True, text=True, timeout=3).stdout.rstrip("\n")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def write_png(text: str) -> str | None:
    try:
        subprocess.run(["qrencode", "-o", PNG_PATH, "-s", "10", "-m", "2", text], timeout=3, check=True)
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return None
    return PNG_PATH


def strip_prefix(query: str) -> str:
    parts = query.split(maxsplit=1)
    if parts and parts[0].lower() == "qr":
        return parts[1] if len(parts) > 1 else ""
    return query


def card_for(text: str) -> dict:
    grid = ascii_qr(text)
    body = f"```\n{grid}\n```\n\n`{text}`" if grid else f"QR for: `{text}`"
    return HamrPlugin.card(
        "QR Code",
        markdown=body,
        actions=[
            {"id": "open", "name": "Open image", "icon": "image"},
            {"id": "copy", "name": "Copy text", "icon": "content_copy"},
        ],
    )


def handle_request(request: dict) -> None:
    step = request.get("step", "initial")
    query = request.get("query", "").strip()

    if step == "match":
        text = strip_prefix(query)
        if not text:
            emit({"type": "match", "result": None})
            return
        emit({"type": "match", "result": {
            "id": f"qr:{text}", "name": f"QR code for: {text[:60]}", "verb": "Show",
            "description": "Enter to open the QR image", "icon": "qr_code_2",
            "entryPoint": {"step": "action", "selected": {"id": f"qr:{text}"}},
            "priority": 70,
        }})
        return

    if step in ("initial", "search"):
        text = strip_prefix(query)
        if not text:
            emit(HamrPlugin.results(
                [{"id": "__hint__", "name": "Type text or a URL to encode", "icon": "qr_code_2"}],
                input_mode="realtime", placeholder="text or URL to encode…"))
            return
        STATE["text"] = text
        emit(card_for(text))
        return

    if step == "action":
        selected = (request.get("selected", {}) or {}).get("id", "")
        action = request.get("action", "")
        if selected.startswith("qr:"):
            STATE["text"] = selected[3:]
            action = "open"

        if action == "copy":
            emit(HamrPlugin.copy_and_close(STATE["text"]))
            return
        png = write_png(STATE["text"])
        emit(HamrPlugin.execute(open=png, close=True) if png
             else HamrPlugin.error("qrencode failed — is it installed?"))


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
