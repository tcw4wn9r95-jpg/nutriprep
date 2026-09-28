"""The dashboard's FOOD_SAFETY / FOOD_ALIASES must match food_safety.py (swapped dishes' Sunday prep)."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import food_safety as fs  # noqa: E402

HTML = (ROOT / "dashboard.html").read_text(encoding="utf-8")


def _js_block(start: str) -> str:
    i = HTML.index(start)
    return HTML[i:HTML.index("};", i)]


def _js_str(s: str):
    s = s.strip()
    if s == "null":
        return None
    if s.startswith('"'):
        return json.loads(s)
    return int(s)


class ParityTests(unittest.TestCase):
    def test_rules_match(self):
        rows = re.findall(r"^\s*(\w+):_FS\((.*)\),?\s*$", _js_block("const FOOD_SAFETY={"), re.M)
        js = {}
        for key, args in rows:
            parts = [_js_str(a) for a in re.findall(r'"(?:[^"\\]|\\.)*"|null|\d+', args)]
            method, container, cool, days, freeze, reheat, note = parts
            js[key] = {"method": method, "container": container, "fridge_c": "≤ 4", "cool_within_hours": cool,
                       "use_within_days": days, "freeze_option_days": freeze, "reheat_c": reheat, "safety_note": note}
        self.assertEqual(js, fs._RULES)

    def test_aliases_match(self):
        pairs = dict(re.findall(r"(\w+):\"(\w+)\"", _js_block("const FOOD_ALIASES={")))
        self.assertEqual(pairs, fs._ALIASES)


if __name__ == "__main__":
    unittest.main()
