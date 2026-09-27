"""Run with: python -m unittest discover -s tests"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import training_link as tl  # noqa: E402


class FuelTests(unittest.TestCase):
    def test_reads_claudios_fuel_for_completed_days_only(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "fuel.json").write_text(json.dumps({"version": 1, "days": {
                "2026-10-05": {"session_kcal": 880, "src": "measured", "sessions": ["cycling"],
                               "add": {"kcal": 590, "carbs_g": 132, "protein_g": 10, "fat_g": 1, "water_ml": 900}}}}))
            Path(d, "weekly_plan.json").write_text(json.dumps([
                {"date": "2026-10-06", "name": "Intervals", "sport": "cycling", "planned_tss": 90}]))
            base = Path(d).as_uri()
            fuel = tl.load_fuel(["2026-10-05", "2026-10-06"], base=base)
            self.assertEqual(list(fuel), ["2026-10-05"])               # planned day adds nothing
            self.assertEqual(fuel["2026-10-05"]["add"]["kcal"], 590)
            planned = tl.load_training_week({"Tuesday": "2026-10-06"}, base=base)
            self.assertEqual(planned["2026-10-06"]["name"], "Intervals")

    def test_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(tl.load_fuel(base=Path(d).as_uri()), {})


if __name__ == "__main__":
    unittest.main()
