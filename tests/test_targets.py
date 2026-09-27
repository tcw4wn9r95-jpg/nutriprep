"""Run with: python -m unittest discover -s tests"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import targets as T  # noqa: E402

PLAN = {"source": "nutritionist_upload", "client_name": "Diego C", "targets_estimated": False,
        "per_member_targets": {"diego": {"kcal": 2000, "protein_g": 150, "carbs_g": 200, "fat_g": 67, "fiber_g": 30},
                               "diana": {"kcal": None, "protein_g": None}},
        "restricted_foods": ["added sugar", "alcohol"], "methodology": "Glucose Goddess", "hydration_l": 2.5}
DIEGO = {"goal_type": "weight_loss", "start_weight_kg": 85, "target_rate_kg_per_week": 0.5, "age": 38,
         "height_cm": 180, "sex": "male", "activity_level": "moderate"}
DIANA = {"goal_type": "weight_loss", "start_weight_kg": 62, "target_rate_kg_per_week": 0.25, "age": 36,
         "height_cm": 165, "sex": "female", "activity_level": "light"}


class TargetTests(unittest.TestCase):
    def test_plan_client_keeps_stated_numbers(self):
        t = T.derive("diego", PLAN, DIEGO, [])
        self.assertEqual((t["kcal"], t["protein_g"], t["carbs_g"], t["fat_g"]), (2000, 150, 200, 67))
        self.assertEqual(t["sources"]["kcal"], "nutritionist plan")
        self.assertEqual(t["water_ml"], 2500)
        self.assertTrue(t["plan_client"])

    def test_other_member_gets_goal_energy_with_the_plans_split(self):
        t = T.derive("diana", PLAN, DIANA, [{"date": "2026-09-20", "weight_kg": 61.5}])
        self.assertTrue(t["sources"]["kcal"].startswith("goals: weight loss"))
        self.assertEqual(t["sources"]["fat_g"], "nutritionist plan's split")
        # the plan's 30% fat share applied to her energy
        self.assertAlmostEqual(t["fat_g"] * 9 / t["kcal"], 67 * 9 / 2000, delta=0.01)
        self.assertEqual(t["body"]["weight_kg"], 61.5)                    # latest weigh-in wins
        self.assertEqual(t["water_ml"], 1600)
        self.assertEqual(t["source"], "nutritionist + goals")
        self.assertGreaterEqual(t["kcal"], 1200)

    def test_sugar_ceiling_follows_the_plan(self):
        self.assertEqual(T.derive("diego", PLAN, DIEGO, [])["free_sugar_g"], 25)          # restricts sugar → 5%
        self.assertEqual(T.derive("diego", dict(PLAN, restricted_foods=[], methodology=""), DIEGO, [])["free_sugar_g"], 50)
        stated = dict(PLAN, sugar_guidance={"free_sugar_max_g": 20})
        t = T.derive("diego", stated, DIEGO, [])
        self.assertEqual((t["free_sugar_g"], t["sources"]["free_sugar_g"]), (20, "nutritionist plan"))

    def test_estimated_plan_uses_goal_energy_when_body_is_known(self):
        est = dict(PLAN, targets_estimated=True)
        t = T.derive("diego", est, DIEGO, [])
        self.assertTrue(t["sources"]["kcal"].startswith("goals"))
        self.assertEqual(t["sources"]["protein_g"], "nutritionist plan's split")

    def test_no_plan_and_missing_body(self):
        t = T.derive("diana", {}, {"goal_type": "maintain", "start_weight_kg": 60}, [])
        self.assertEqual(t["source"], "derived from goals")
        self.assertEqual(set(t["missing_body"]), {"height_cm", "age", "sex", "activity_level"})
        self.assertTrue(72 <= t["protein_g"] <= 132)                         # 1.2–2.2 g/kg
        self.assertNotIn("methodology", t)

    def test_stated_without_fibre(self):
        plan = dict(PLAN, per_member_targets={"diego": {"kcal": 2000, "protein_g": 150, "carbs_g": 200, "fat_g": 67}})
        self.assertEqual(T.derive("diego", plan, DIEGO, [])["fiber_g"], 28)

    def test_derive_all_writes_every_member(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "nutrition_plan.json").write_text(json.dumps(PLAN))
            for m, g in (("diego", DIEGO), ("diana", DIANA)):
                (base / "users" / m).mkdir(parents=True)
                (base / "users" / m / "goals.json").write_text(json.dumps(g))
            T.derive_all(base)
            for m in ("diego", "diana"):
                self.assertIn("free_sugar_g", json.loads((base / "users" / m / "macro_targets.json").read_text()))


if __name__ == "__main__":
    unittest.main()
