"""Run with: python -m unittest discover -s tests"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import inventory  # noqa: E402


class MadeThisTests(unittest.TestCase):
    def test_made_meal_depletes_every_portion_once(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "inventory.json").write_text(json.dumps({"items": [
                {"name_en": "Chicken breast", "kind": "mass", "unit": "g", "amount": 1000},
                {"name_en": "Tofu", "kind": "mass", "unit": "g", "amount": 400}]}))
            (base / "weekly_menu.json").write_text(json.dumps([{"date": "2026-10-05", "meals": [{"slot": "dinner", "portions": {
                "diego": {"ingredients": [{"item": "Chicken breast", "qty": "200 g"}]},
                "diana": {"ingredients": [{"item": "Tofu", "qty": "150 g"}]}}}]}]))
            (base / "cooked_log.json").write_text(json.dumps([{"date": "2026-10-05", "slot": "dinner"}]))
            old = inventory.BASE
            inventory.BASE = base
            try:
                inventory.main()
                inventory.main()   # second run must not deplete again
            finally:
                inventory.BASE = old
            items = {i["name_en"]: i["amount"] for i in json.loads((base / "inventory.json").read_text())["items"]}
            self.assertEqual(items, {"Chicken breast": 800, "Tofu": 250})
            self.assertTrue(json.loads((base / "cooked_log.json").read_text())[0]["inv_applied"])


if __name__ == "__main__":
    unittest.main()
