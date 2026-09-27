"""Run with: python -m unittest discover -s tests"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import training_link as tl  # noqa: E402


class FuelTests(unittest.TestCase):
    def test_fuel_from_tss_then_calories(self):
        self.assertEqual(tl.workout_fuel({"tss": 60}), 420)
        self.assertEqual(tl.workout_fuel({"tss": 200}), 700)          # capped
        self.assertEqual(tl.workout_fuel({"tss": 0, "calories": 500}), 350)
        self.assertEqual(tl.workout_fuel({}), 0)

    def test_only_completed_workouts_count(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "workouts.json").write_text(json.dumps([
                {"date": "2026-10-05", "sport": "cycling", "duration_min": 90, "tss": 80, "calories": 900},
                {"date": "2026-10-05", "sport": "running", "duration_min": 30, "tss": 0, "calories": 300},
                {"date": "2026-09-20", "sport": "running", "tss": 50}]))
            Path(d, "weekly_plan.json").write_text(json.dumps([
                {"date": "2026-10-06", "name": "Intervals", "sport": "cycling", "planned_tss": 90}]))
            base = Path(d).as_uri()
            done = tl.load_completed(["2026-10-05", "2026-10-06"], base=base)
            self.assertEqual(list(done), ["2026-10-05"])               # planned day adds nothing
            self.assertEqual(done["2026-10-05"]["extra_kcal"], 560 + 210)
            planned = tl.load_training_week({"Tuesday": "2026-10-06"}, base=base)
            self.assertEqual(planned["2026-10-06"]["name"], "Intervals")


if __name__ == "__main__":
    unittest.main()
