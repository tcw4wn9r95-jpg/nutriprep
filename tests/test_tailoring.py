"""Run with: python -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tailoring as t  # noqa: E402

M = ["diego", "diana"]


def meal(name, diego, diana, **extra):
    p = {"diego": {"ingredients": [{"item": i, "qty": "1"} for i in diego]},
         "diana": {"ingredients": [{"item": i, "qty": "1"} for i in diana]}}
    for m, v in extra.pop("variants", {}).items():
        p[m]["variant"] = v
    return {"slot": "lunch", "name": name, "portions": p, **extra}


class LoadTests(unittest.TestCase):
    def test_legacy_sources_fold_into_household_until_migrated(self):
        prefs = t.load_preferences(
            None,
            {"allergies": ["peanuts"], "intolerances": ["lactose"], "dislikes": ["liver"], "diet_style": "omnivore"},
            {"avoid": ["no salmon"], "prefer": ["beef"], "notes": ["swapped X"]},
            M)
        hh = prefs["household"]
        self.assertEqual(hh["allergies"], ["peanuts"])
        self.assertEqual(hh["intolerances"], ["lactose"])
        self.assertEqual(hh["avoid"], ["liver", "no salmon"])
        self.assertEqual(hh["love"], ["beef"])
        self.assertEqual(prefs["people"]["diana"]["diet_style"], "omnivore")

    def test_migrated_file_ignores_legacy(self):
        prefs = t.load_preferences({"migrated_legacy": True, "people": {"diana": {"avoid": ["olives"]}}},
                                   {"allergies": ["peanuts"]}, {"avoid": ["salmon"]}, M)
        self.assertEqual(prefs["household"]["allergies"], [])
        self.assertEqual(prefs["people"]["diana"]["avoid"], ["olives"])
        self.assertEqual(prefs["people"]["diego"]["avoid"], [])

    def test_normalize_dedupes_and_rejects_unknown_diet(self):
        p = t.normalize({"people": {"diego": {"love": ["Beef", "beef", " "], "diet_style": "keto"}}}, M)
        self.assertEqual(p["people"]["diego"]["love"], ["Beef"])
        self.assertEqual(p["people"]["diego"]["diet_style"], "")


class MatchTests(unittest.TestCase):
    def test_plurals_and_whole_words(self):
        self.assertTrue(t.matches("Chestnut mushrooms", t.terms_for("mushroom")))
        self.assertTrue(t.matches("Mushroom", t.terms_for("no mushrooms")))
        self.assertTrue(t.matches("Free-range eggs", t.terms_for("eggs")))
        self.assertIsNone(t.matches("Eggplant", t.terms_for("eggs")))
        self.assertIsNone(t.matches("Butternut squash", t.terms_for("lactose"), True))

    def test_lactose_spares_free_and_plant_versions(self):
        terms = t.terms_for("lactose intolerance")
        self.assertTrue(t.matches("Greek yogurt", terms, True))
        self.assertIsNone(t.matches("Lactose-free milk", terms, True))
        self.assertIsNone(t.matches("Oat milk", terms, True))
        self.assertIsNone(t.matches("Peanut butter", terms, True))

    def test_french_lettuce_is_not_milk(self):
        self.assertIsNone(t.matches("Laitue", t.terms_for("dairy"), True))


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.prefs = t.normalize({"people": {
            "diana": {"avoid": ["mushrooms"], "intolerances": ["lactose"], "allergies": ["shellfish"]},
            "diego": {"diet_style": "omnivore"}}}, M)

    def test_personal_restriction_flags_only_that_person(self):
        menu = [{"day": "Monday", "meals": [meal("Risotto", ["Rice", "Mushrooms", "Parmesan"], ["Rice", "Courgette"])]}]
        self.assertEqual(t.check_portions(menu, self.prefs, M), [])
        menu[0]["meals"][0]["portions"]["diana"]["ingredients"].append({"item": "Parmesan", "qty": "10 g"})
        found = t.check_portions(menu, self.prefs, M)
        self.assertEqual([(w["member"], w["rule"]) for w in found], [("diana", "lactose")])
        self.assertEqual(menu[0]["meals"][0]["warnings"][0]["member"], "diana")

    def test_allergy_anywhere_in_the_kitchen_is_fatal(self):
        menu = [{"day": "Monday", "meals": [meal("Paella", ["Rice", "Prawns"], ["Rice", "Chicken"])]}]
        hits = t.find_allergen_hits(menu, self.prefs, M)
        self.assertEqual(len(hits), 1)
        self.assertIn("diego", hits[0])

    def test_vegetarian_diet(self):
        prefs = t.normalize({"people": {"diana": {"diet_style": "vegetarian"}}}, M)
        menu = [{"day": "Tue", "meals": [meal("Bowl", ["Chicken breast"], ["Salmon fillet"])]}]
        found = t.check_portions(menu, prefs, M)
        self.assertEqual([(w["member"], w["kind"]) for w in found], [("diana", "diet")])


class DifferenceTests(unittest.TestCase):
    def test_same_dish_different_sizes_is_not_a_difference(self):
        menu = [{"meals": [meal("Bowl", ["Chicken", "Rice"], ["Chicken", "Rice"])]}]
        menu[0]["meals"][0]["portions"]["diego"]["ingredients"][0]["qty"] = "200 g"
        self.assertEqual(t.annotate_differences(menu, M), 0)
        self.assertNotIn("differs_for", menu[0]["meals"][0])

    def test_swap_is_described_on_the_restricted_plate(self):
        prefs = t.normalize({"people": {"diana": {"diet_style": "vegetarian"}}}, M)
        menu = [{"meals": [meal("Stir-fry", ["Chicken breast", "Rice"], ["Tofu", "Rice"])]}]
        self.assertEqual(t.annotate_differences(menu, M, prefs), 1)
        m = menu[0]["meals"][0]
        self.assertEqual(m["differs_for"], ["diana"])
        self.assertEqual(m["differences"]["diana"], "tofu instead of chicken breast")

    def test_swap_without_known_reason_shows_both_sides(self):
        menu = [{"meals": [meal("Stir-fry", ["Chicken breast", "Rice"], ["Tofu", "Rice"])]}]
        t.annotate_differences(menu, M)
        self.assertEqual(menu[0]["meals"][0]["differs_for"], ["diana", "diego"])

    def test_left_out_ingredient_is_not_reported_twice(self):
        menu = [{"meals": [meal("Risotto", ["Rice", "Mushrooms", "Parmesan"], ["Rice", "Mushrooms"])]}]
        t.annotate_differences(menu, M)
        self.assertEqual(menu[0]["meals"][0]["differences"], {"diana": "without parmesan"})

    def test_model_variant_wins(self):
        menu = [{"meals": [meal("Risotto", ["Rice", "Mushrooms"], ["Rice", "Peas"],
                                variants={"diana": {"changes": "Peas instead of mushrooms", "reason": "doesn't eat mushrooms"}})]}]
        t.annotate_differences(menu, M)
        self.assertEqual(menu[0]["meals"][0]["differences"], {"diana": "Peas instead of mushrooms (doesn't eat mushrooms)"})

    def test_prompt_block_names_each_person(self):
        prefs = t.normalize({"household": {"love": ["beef"]}, "people": {"diana": {"avoid": ["olives"]}}}, M)
        block = t.prompt_block(prefs, M)
        self.assertIn("Diana — won't eat (never on their plate): olives", block)
        self.assertIn("Diego — no personal restrictions", block)
        self.assertIn("Everyone loves (lean into these): beef", block)


if __name__ == "__main__":
    unittest.main()
