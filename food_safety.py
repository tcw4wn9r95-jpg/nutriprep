"""
Deterministic food safety rules for the NutriPrep meal prep planner.

Sources: USDA FoodKeeper (foodsafety.gov), FDA Food Code, EFSA guidance,
ANSES (France/Luxembourg food safety), European Food Safety Authority.
These rules are NOT LLM-generated — they are looked up from this module
and overwrite any LLM suggestions in the prep plan.

Key principles enforced:
- Refrigerate cooked food within 2 hours (1 h if ambient > 32 °C)
- Fridge temperature ≤ 4 °C (40 °F)
- Reheat to internal temperature ≥ 74 °C (165 °F)
- Do not refreeze thawed raw items
- Cooked rice is high-risk (Bacillus cereus): use within 1 day
"""

_RULES = {
    # ── Proteins ──────────────────────────────────────────────────────────────
    "poultry": {
        "method": "refrigerate",
        "container": "airtight container",
        "fridge_c": "≤ 4",
        "cool_within_hours": 2,
        "use_within_days": 3,
        "freeze_option_days": 60,
        "reheat_c": 74,
        "safety_note": "Cool quickly; never leave poultry at room temp > 2 h. Reheat to 74 °C through.",
    },
    "red_meat": {
        "method": "refrigerate",
        "container": "airtight container",
        "fridge_c": "≤ 4",
        "cool_within_hours": 2,
        "use_within_days": 3,
        "freeze_option_days": 90,
        "reheat_c": 74,
        "safety_note": "Store in coldest part of fridge. Reheat to 74 °C before serving.",
    },
    "fish_seafood": {
        "method": "refrigerate",
        "container": "airtight container on ice or coldest shelf",
        "fridge_c": "≤ 4",
        "cool_within_hours": 1,
        "use_within_days": 2,
        "freeze_option_days": 30,
        "reheat_c": 74,
        "safety_note": "Fish spoils fast. Use within 2 days; 1 day is safer. Reheat to 74 °C.",
    },
    "eggs_cooked": {
        "method": "refrigerate",
        "container": "covered container",
        "fridge_c": "≤ 4",
        "cool_within_hours": 2,
        "use_within_days": 4,
        "freeze_option_days": None,
        "reheat_c": 74,
        "safety_note": "Hard-boiled eggs: 1 week in shell, 5 days peeled in water. Scrambled/cooked dishes: 3–4 days.",
    },
    # ── Grains & legumes ──────────────────────────────────────────────────────
    "rice": {
        "method": "refrigerate",
        "container": "airtight container — cool within 1 hour",
        "fridge_c": "≤ 4",
        "cool_within_hours": 1,
        "use_within_days": 1,
        "freeze_option_days": 30,
        "reheat_c": 74,
        "safety_note": "⚠ HIGH RISK: Bacillus cereus spores survive cooking. Cool rice within 1 h, refrigerate, use within 1 day. Never reheat more than once.",
    },
    "grains_pasta": {
        "method": "refrigerate",
        "container": "airtight container",
        "fridge_c": "≤ 4",
        "cool_within_hours": 2,
        "use_within_days": 3,
        "freeze_option_days": 60,
        "reheat_c": 74,
        "safety_note": "Add a splash of water before reheating to restore moisture. Use within 3 days.",
    },
    "legumes": {
        "method": "refrigerate",
        "container": "airtight container",
        "fridge_c": "≤ 4",
        "cool_within_hours": 2,
        "use_within_days": 5,
        "freeze_option_days": 90,
        "reheat_c": 74,
        "safety_note": "Cooked beans and lentils keep well. Freeze in portions for quick meals.",
    },
    # ── Vegetables & fruit ────────────────────────────────────────────────────
    "vegetables_cooked": {
        "method": "refrigerate",
        "container": "airtight container",
        "fridge_c": "≤ 4",
        "cool_within_hours": 2,
        "use_within_days": 4,
        "freeze_option_days": 90,
        "reheat_c": 74,
        "safety_note": "Cooked vegetables store well. Roasted veg can be eaten cold in salads.",
    },
    "vegetables_raw_prepped": {
        "method": "refrigerate",
        "container": "airtight container or zip bag",
        "fridge_c": "≤ 4",
        "cool_within_hours": None,
        "use_within_days": 4,
        "freeze_option_days": None,
        "reheat_c": None,
        "safety_note": "Pre-cut vegetables: store dry, use within 3–4 days. Wash just before eating.",
    },
    # ── Soups, stews & sauces ─────────────────────────────────────────────────
    "soup_stew": {
        "method": "refrigerate",
        "container": "airtight container",
        "fridge_c": "≤ 4",
        "cool_within_hours": 2,
        "use_within_days": 4,
        "freeze_option_days": 90,
        "reheat_c": 74,
        "safety_note": "Bring to a rolling boil when reheating. Excellent for freezing in individual portions.",
    },
    "sauce_dairy": {
        "method": "refrigerate",
        "container": "airtight container",
        "fridge_c": "≤ 4",
        "cool_within_hours": 2,
        "use_within_days": 3,
        "freeze_option_days": None,
        "reheat_c": 74,
        "safety_note": "Cream-based sauces can separate when frozen; use within 3 days refrigerated.",
    },
    # ── Dairy ─────────────────────────────────────────────────────────────────
    "dairy": {
        "method": "refrigerate",
        "container": "sealed original packaging or airtight container",
        "fridge_c": "≤ 4",
        "cool_within_hours": None,
        "use_within_days": 5,
        "freeze_option_days": None,
        "reheat_c": None,
        "safety_note": "Check use-by date on packaging. Opened yogurt: 5–7 days.",
    },
    # ── Baked goods ───────────────────────────────────────────────────────────
    "baked_goods": {
        "method": "store at room temp or refrigerate",
        "container": "airtight container",
        "fridge_c": "≤ 4",
        "cool_within_hours": None,
        "use_within_days": 3,
        "freeze_option_days": 60,
        "reheat_c": None,
        "safety_note": "Most baked goods: 2–3 days at room temp, 1 week refrigerated. Freeze for longer.",
    },
    # ── Fallback ──────────────────────────────────────────────────────────────
    "generic": {
        "method": "refrigerate",
        "container": "airtight container",
        "fridge_c": "≤ 4",
        "cool_within_hours": 2,
        "use_within_days": 3,
        "freeze_option_days": 60,
        "reheat_c": 74,
        "safety_note": "Cool within 2 h of cooking, refrigerate, use within 3 days, reheat to 74 °C.",
    },
}

# Aliases that map common Claude-returned category strings to our keys
_ALIASES = {
    "chicken": "poultry", "turkey": "poultry", "duck": "poultry",
    "beef": "red_meat", "lamb": "red_meat", "pork": "red_meat", "meat": "red_meat",
    "fish": "fish_seafood", "salmon": "fish_seafood", "tuna": "fish_seafood",
    "seafood": "fish_seafood", "shrimp": "fish_seafood",
    "eggs": "eggs_cooked", "egg": "eggs_cooked",
    "rice": "rice",
    "pasta": "grains_pasta", "grains": "grains_pasta", "quinoa": "grains_pasta",
    "couscous": "grains_pasta", "oats": "grains_pasta",
    "beans": "legumes", "lentils": "legumes", "chickpeas": "legumes",
    "legume": "legumes",
    "vegetables": "vegetables_cooked", "veggies": "vegetables_cooked",
    "roasted_veg": "vegetables_cooked",
    "raw_veg": "vegetables_raw_prepped",
    "soup": "soup_stew", "stew": "soup_stew", "curry": "soup_stew",
    "sauce": "sauce_dairy", "cream_sauce": "sauce_dairy",
    "dairy": "dairy", "yogurt": "dairy", "cheese": "dairy",
    "bread": "baked_goods", "muffin": "baked_goods", "cake": "baked_goods",
}


def get_storage(food_category: str) -> dict:
    """Return deterministic food-safety storage rules for a given food category."""
    key = food_category.lower().strip().replace(" ", "_")
    key = _ALIASES.get(key, key)
    return dict(_RULES.get(key, _RULES["generic"]))


def validate_prep_plan(prep_batches: list) -> list:
    """Overwrite every batch's storage block with evidence-based rules."""
    for batch in prep_batches:
        category = batch.get("food_category", "generic")
        batch["storage"] = get_storage(category)
    return prep_batches
