#!/usr/bin/env python3
"""
Unit tests for the pure logic of the offline plugins (no daemon, no network).
Run: python3 scripts/test-plugin-logic.py   (or via unittest discovery)

Complements smoke-test-plugins.sh, which only checks JSON output shape — these
assert the actual conversion/transform results so math regressions are caught.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

PLUGINS = Path(__file__).resolve().parent.parent / "plugins"


def load(name):
    """Import a plugin's handler.py as a module."""
    plugin_dir = PLUGINS / name
    sys.path.insert(0, str(PLUGINS))  # for `from sdk.hamr_sdk import ...`
    spec = importlib.util.spec_from_file_location(f"{name}_handler", plugin_dir / "handler.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestUnits(unittest.TestCase):
    h = load("units")

    def test_length(self):
        out, _ = self.h.convert("100 km to mi")
        self.assertTrue(out.startswith("62.137"))

    def test_temperature(self):
        self.assertEqual(self.h.convert("32 f to c")[0], "0 C")
        self.assertEqual(self.h.convert("100 c to f")[0], "212 F")

    def test_data(self):
        self.assertEqual(self.h.convert("5 gb in mb")[0], "5000 mb")

    def test_bases(self):
        self.assertEqual(self.h.convert("255 to hex")[0], "0xff")
        self.assertEqual(self.h.convert("0xff to dec")[0], "255")
        self.assertEqual(self.h.convert("0b1010 to dec")[0], "10")

    def test_rejects_garbage(self):
        self.assertIsNone(self.h.convert("hello world"))


class TestColor(unittest.TestCase):
    h = load("color")

    def test_hex_to_formats(self):
        items = self.h.items_for("color #ff5733")
        names = [i["name"] for i in items]
        self.assertIn("#ff5733", names)
        self.assertIn("rgb(255, 87, 51)", names)

    def test_named(self):
        self.assertEqual(self.h.items_for("color tomato")[0]["name"], "#ff6347")

    def test_shorthand(self):
        self.assertEqual(self.h.items_for("#abc")[0]["name"], "#aabbcc")

    def test_invalid(self):
        self.assertIsNone(self.h.items_for("color notacolor"))


class TestDevtools(unittest.TestCase):
    h = load("devtools")

    def test_base64(self):
        self.assertEqual(self.h.compute("base64 hi")[1], "aGk=")
        self.assertEqual(self.h.compute("b64d aGk=")[1], "hi")

    def test_hash(self):
        self.assertEqual(self.h.compute("sha256 abc")[1],
                         "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_slug(self):
        self.assertEqual(self.h.compute("slug Hello World!")[1], "hello-world")

    def test_json(self):
        self.assertEqual(self.h.compute('jsonmin {"a": 1}')[1], '{"a":1}')


class TestWebsearch(unittest.TestCase):
    h = load("websearch")

    def test_bang(self):
        bang, term = self.h.split_bang("gh hamr")
        self.assertEqual(bang, "gh")
        self.assertEqual(term, "hamr")

    def test_url_encoding(self):
        item = self.h.build("g", "a b")
        self.assertIn("a%20b", item["id"])

    def test_no_bang(self):
        self.assertIsNone(self.h.split_bang("just text")[0])


class TestUnicode(unittest.TestCase):
    h = load("unicode")

    def test_char(self):
        self.assertEqual(self.h.item_for("char A")["copy"], "A")

    def test_codepoint(self):
        self.assertEqual(self.h.item_for("u+1f600")["copy"], "😀")

    def test_name_lookup(self):
        self.assertEqual(self.h.item_for("unicode snowman")["copy"], "☃")


class TestWorldclock(unittest.TestCase):
    h = load("worldclock")

    def test_resolve_city(self):
        self.assertEqual(self.h.resolve("tokyo"), "Asia/Tokyo")
        self.assertEqual(self.h.resolve("nyc"), "America/New_York")

    def test_strip_connectors(self):
        self.assertEqual(self.h.strip_kw("time in london"), "london")

    def test_unknown(self):
        self.assertIsNone(self.h.resolve("atlantis"))


class TestRandom(unittest.TestCase):
    h = load("random")

    def test_dice_range(self):
        for _ in range(50):
            val = int(self.h.handle("roll 1d6")[0])
            self.assertTrue(1 <= val <= 6)

    def test_range(self):
        for _ in range(50):
            val = int(self.h.handle("rand 1-10")[0])
            self.assertTrue(1 <= val <= 10)

    def test_pick(self):
        self.assertIn(self.h.handle("pick a, b, c")[0], ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
