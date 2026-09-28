"""Run with: python -m unittest discover -s tests"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import recipes as R  # noqa: E402
import tailoring  # noqa: E402

M = ["diego", "diana"]


def mdb(id_, name, cat, area, ings, instr="Step 1\nChop.\n2. Cook it."):
    m = {"idMeal": id_, "strMeal": name, "strCategory": cat, "strArea": area, "strInstructions": instr,
         "strMealThumb": "https://x/img.jpg", "strSource": "https://bbcgoodfood.com/x", "strYoutube": "", "strTags": "Spicy,Easy"}
    for i, (item, qty) in enumerate(ings, 1):
        m[f"strIngredient{i}"], m[f"strMeasure{i}"] = item, qty
    return m


class NormalizeTests(unittest.TestCase):
    def test_real_recipe_fields(self):
        r = R.normalize(mdb("1", "Chicken Fajitas", "Chicken", "Mexican", [("Chicken breast", "2"), ("Peppers", "3"), ("Fish sauce", "1 tbsp")]))
        self.assertEqual((r["id"], r["cuisine"], r["proteins"], r["meal_types"]), ("mdb-1", "Mexican", ["chicken"], ["lunch", "dinner"]))
        self.assertEqual(r["instructions"], ["Chop.", "Cook it."])
        self.assertEqual(r["source_url"], "https://bbcgoodfood.com/x")
        self.assertEqual(r["ingredients"][0], {"item": "Chicken breast", "qty": "2"})

    def test_protein_rules(self):
        self.assertEqual(R.proteins_of("Beef", [{"item": "Beef mince"}, {"item": "Egg"}], "Meatballs"), ["beef"])   # egg as binder
        self.assertIn("eggs", R.proteins_of("Vegetarian", [{"item": "Eggs"}, {"item": "Spinach"}], "Spinach frittata"))
        self.assertEqual(R.proteins_of("Vegetarian", [{"item": "Green beans"}, {"item": "Rice"}], "Stir fry"), ["vegetarian"])
        self.assertEqual(R.proteins_of("Vegetarian", [{"item": "Chickpeas"}], "Chana"), ["legumes", "vegetarian"])

    def test_desserts_skipped_and_cuisines_normalised(self):
        self.assertIsNone(R.normalize(mdb("2", "Cake", "Dessert", "British", [("Flour", "200g")])))
        self.assertEqual(R.normalize(mdb("3", "Ratatouille", "Vegetarian", "France", [("Courgette", "2")]))["cuisine"], "French")


class ShortlistTests(unittest.TestCase):
    def test_allergens_out_loves_first(self):
        lib = [R.normalize(mdb(str(i), n, c, "X", ings)) for i, (n, c, ings) in enumerate([
            ("Peanut chicken", "Chicken", [("Chicken", "1"), ("Peanut butter", "2 tbsp")]),
            ("Beef tacos", "Beef", [("Beef mince", "500g"), ("Tortillas", "8")]),
            ("Salmon bowl", "Seafood", [("Salmon", "2"), ("Rice", "1 cup")]),
            ("Mushroom risotto", "Vegetarian", [("Mushrooms", "300g"), ("Rice", "1 cup")])])]
        prefs = tailoring.normalize({"household": {"allergies": ["peanuts"], "love": ["salmon"]},
                                     "people": {"diana": {"avoid": ["mushrooms"]}}}, M)
        names = [r["name"] for r in R.shortlist(lib, prefs, M, n=10)]
        self.assertNotIn("Peanut chicken", names)
        self.assertEqual(names[0], "Salmon bowl")
        self.assertEqual(names[-1], "Mushroom risotto")            # a personal clash ranks last, still allowed
        self.assertNotIn("Beef tacos", [r["name"] for r in R.shortlist(lib, prefs, M, avoid_names={"beef tacos"})])


class ArchiveTests(unittest.TestCase):
    def test_archive_keeps_dishes_and_dates(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "dish_archive.json"
            R.archive_dishes([{"date": "2026-10-05", "meals": [{"slot": "lunch", "name": "Chicken fajitas", "portions": {}},
                                                               {"slot": "am_snack", "name": "Apple", "portions": {}}]}], path)
            a = R.archive_dishes([{"date": "2026-10-12", "meals": [{"slot": "dinner", "name": "Chicken Fajitas", "portions": {}}]}], path)
            e = a["dishes"]["chicken fajitas"]
            self.assertEqual((e["first_seen"], e["last_seen"]), ("2026-10-05", "2026-10-12"))
            self.assertNotIn("apple", a["dishes"])


if __name__ == "__main__":
    unittest.main()
