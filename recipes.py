"""
NutriPrep — recipe library of REAL recipes.

The library is built from TheMealDB (themealdb.com, a free public recipe
database; each recipe keeps its original source link — BBC Good Food, Serious
Eats, blogs …). Claude never invents library entries: it only ADAPTS a chosen
recipe to the household (each person's macros, preferences, sugar ceiling).

  python recipes.py            # (re)build recipes.json from TheMealDB
  load() / shortlist(...)      # used by generate.py to suggest library dishes

recipes.json: {"source", "built", "count", "recipes": [
  {"id", "name", "cuisine", "category", "proteins": [...], "meal_types": [...],
   "ingredients": [{"item", "qty"}], "instructions": [...], "image", "source_url",
   "video_url", "tags": [...]}]}

dish_archive.json keeps every dish that has been on a weekly menu (name → the
last full meal, first/last seen) so dishes the household liked can be brought
back from the library's "Liked before" filter.
"""
from __future__ import annotations

import json
import re
import string
import urllib.request
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent
API = "https://www.themealdb.com/api/json/v1/1/search.php?f="
SKIP_CATEGORIES = {"Dessert"}   # not planned by NutriPrep

# Protein groups the library filters on. Order matters for display only.
PROTEINS = {
    "chicken": ["chicken", "poulet"],
    "turkey": ["turkey"],
    "beef": ["beef", "steak", "mince", "minced meat", "veal"],
    "pork": ["pork", "bacon", "ham", "chorizo", "sausage", "pancetta", "prosciutto"],
    "lamb": ["lamb", "mutton", "goat"],
    "fish": ["salmon", "tuna", "cod", "haddock", "mackerel", "sardine", "trout", "hake", "fish", "anchov",
             "tilapia", "sea bass", "monkfish", "halibut", "herring", "kipper"],
    "seafood": ["prawn", "shrimp", "king prawns", "mussel", "clam", "squid", "scallop", "crab", "lobster", "oyster"],
    "eggs": ["egg"],
    "legumes": ["chickpea", "lentil", "kidney bean", "black bean", "cannellini", "butter bean", "borlotti",
                "black-eyed", "pinto", "haricot", "split pea", "edamame", "fava", "broad bean", "refried beans"],
    "tofu": ["tofu", "tempeh", "seitan"],
}
# Condiments that name a protein without being one ("fish sauce" isn't fish).
NOT_PROTEIN = ("fish sauce", "oyster sauce", "fish stock", "anchovy paste", "chicken stock", "beef stock",
               "chicken broth", "beef broth", "chicken stock cube", "beef stock cube", "egg white", "egg yolk",
               "worcestershire")
EGG_DISH = ("egg", "omelette", "omelet", "frittata", "shakshuka", "quiche", "tortilla espa", "huevos", "benedict")
CUISINE_NAMES = {"France": "French", "India": "Indian", "United States": "American", "Norway": "Norwegian",
                 "Netherlands": "Dutch", "Argentina": "Argentinian", "Venezuela": "Venezuelan", "Unknown": "International"}
CATEGORY_PROTEIN = {"Chicken": "chicken", "Beef": "beef", "Pork": "pork", "Lamb": "lamb", "Goat": "lamb",
                    "Seafood": "fish"}


def _words(text: str) -> str:
    return " " + re.sub(r"[^a-z]+", " ", text.lower()) + " "


def proteins_of(category: str, ingredients: list[dict], name: str = "") -> list[str]:
    found = []
    raw = " | ".join(i["item"].lower() for i in ingredients)
    for phrase in NOT_PROTEIN:
        raw = raw.replace(phrase, " ")
    text = _words(raw)
    for group, words in PROTEINS.items():
        if any((" " + w) in text for w in words):
            found.append(group)
    # Egg as a glaze or binder isn't the protein of the dish.
    others = [g for g in found if g != "eggs"]
    if "eggs" in found and others and not any(w in name.lower() for w in EGG_DISH):
        found.remove("eggs")
    if CATEGORY_PROTEIN.get(category) and CATEGORY_PROTEIN[category] not in found:
        found.insert(0, CATEGORY_PROTEIN[category])
    if category == "Seafood" and "seafood" in found and "fish" in found and not any(
            (" " + w) in text for w in PROTEINS["fish"]):
        found.remove("fish")
    meaty = {"chicken", "turkey", "beef", "pork", "lamb", "fish", "seafood"}
    if not (set(found) & meaty):
        found.append("vegetarian")
    if category == "Vegan":
        found.append("vegan")
    return found


def normalize(meal: dict) -> dict | None:
    category = meal.get("strCategory") or ""
    if category in SKIP_CATEGORIES:
        return None
    ingredients = []
    for i in range(1, 21):
        item = (meal.get(f"strIngredient{i}") or "").strip()
        if item:
            ingredients.append({"item": item, "qty": (meal.get(f"strMeasure{i}") or "").strip()})
    steps = [s.strip() for s in re.split(r"\r?\n+", meal.get("strInstructions") or "") if s.strip()]
    steps = [re.sub(r"^(step\s*\d+[:.]?|\d+[.)])\s*", "", s, flags=re.I) for s in steps]
    steps = [s for s in steps if s and not re.fullmatch(r"step\s*\d*", s, flags=re.I)]
    meal_types = ["breakfast"] if category == "Breakfast" else \
        ["snack", "lunch"] if category in ("Side", "Starter") else ["lunch", "dinner"]
    return {
        "id": "mdb-" + str(meal.get("idMeal")),
        "name": (meal.get("strMeal") or "").strip(),
        "cuisine": CUISINE_NAMES.get((meal.get("strArea") or "").strip(), (meal.get("strArea") or "").strip() or "International"),
        "category": category,
        "proteins": proteins_of(category, ingredients, meal.get("strMeal") or ""),
        "meal_types": meal_types,
        "ingredients": ingredients,
        "instructions": steps,
        "image": meal.get("strMealThumb") or "",
        "source_url": meal.get("strSource") or "",
        "video_url": meal.get("strYoutube") or "",
        "tags": [t.strip() for t in (meal.get("strTags") or "").split(",") if t.strip()],
    }


def build(path: Path = BASE / "recipes.json") -> dict:
    seen, recipes = set(), []
    for letter in string.ascii_lowercase:
        with urllib.request.urlopen(API + letter, timeout=30) as r:
            meals = (json.load(r) or {}).get("meals") or []
        for m in meals:
            rec = normalize(m)
            if rec and rec["id"] not in seen and rec["name"]:
                seen.add(rec["id"])
                recipes.append(rec)
    recipes.sort(key=lambda r: (r["cuisine"], r["name"]))
    out = {"source": "TheMealDB (themealdb.com) — real recipes; each keeps its original source link",
           "built": date.today().isoformat(), "count": len(recipes), "recipes": recipes}
    with open(path, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    return out


def load(path: Path = BASE / "recipes.json") -> list[dict]:
    try:
        with open(path) as f:
            return json.load(f).get("recipes", [])
    except Exception:
        return []


def shortlist(recipes: list[dict], prefs: dict, members: list[str], n: int = 30,
              avoid_names: set[str] | None = None) -> list[dict]:
    """Lunch/dinner recipes nobody's kitchen allergy rules out, ranked by what the
    household loves and away from personal won't-eats (those still need a variant)."""
    import tailoring
    allergens = [tailoring.terms_for(a) for a in tailoring.kitchen_allergens(prefs)]
    everyone_avoid = [tailoring.terms_for(a) for a in prefs["household"]["intolerances"] + prefs["household"]["avoid"]]
    loves = [l.lower() for l in prefs["household"]["love"] + [x for m in members for x in prefs["people"][m]["love"]]]
    personal = {m: tailoring.restrictions_for(prefs, m) for m in members}
    avoid_names = {a.lower() for a in (avoid_names or set())}
    scored = []
    for r in recipes:
        if "dinner" not in r.get("meal_types", []) or r["name"].lower() in avoid_names:
            continue
        items = [i["item"] for i in r.get("ingredients", [])]
        blob = " ".join(items + [r["name"], r["cuisine"]] + r.get("proteins", []))
        if any(tailoring.matches(i, t, tailoring._is_dairy_terms(t)) for t in allergens + everyone_avoid for i in items):
            continue
        score = sum(2 for l in loves if l and l in blob.lower())
        clashes = sum(1 for m in members for rule in personal[m]
                      if any(tailoring.matches(i, rule["terms"], tailoring._is_dairy_terms(rule["terms"])) for i in items))
        score -= clashes
        scored.append((score, r["name"], r))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [r for _, _, r in scored[:n]]


def archive_dishes(menu: list[dict], path: Path = BASE / "dish_archive.json", today: str | None = None) -> dict:
    """Remember every dish that appears on a menu (for the library's "Liked before")."""
    today = today or date.today().isoformat()
    try:
        with open(path) as f:
            arch = json.load(f)
    except Exception:
        arch = {"dishes": {}}
    dishes = arch.setdefault("dishes", {})
    for day in menu or []:
        for meal in day.get("meals", []):
            name = (meal.get("name") or "").strip()
            if not name or meal.get("slot") in ("am_snack", "pm_snack"):
                continue
            key = name.lower()
            entry = dishes.get(key) or {"first_seen": day.get("date") or today}
            entry.update({"name": name, "last_seen": day.get("date") or today, "slot": meal.get("slot"),
                          "meal": {k: meal.get(k) for k in ("name", "food_category", "prep_steps", "day_of_steps",
                                                            "image_prompt", "portions", "recipe_source")}})
            dishes[key] = entry
    arch["updated"] = today
    with open(path, "w") as f:
        json.dump(arch, f, indent=1, ensure_ascii=False)
    return arch


if __name__ == "__main__":
    out = build()
    print(f"Library: {out['count']} recipes from TheMealDB.")
