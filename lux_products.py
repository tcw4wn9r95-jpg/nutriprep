"""
Luxembourg product localisation: English → French translations + supermarket availability.

Stores covered: Cactus, Auchan, Delhaize, Aldi, Lidl, Match, Grand Frais.
If an item is not in the curated dict, the LLM-provided French name is kept
and all major stores are listed as available.
"""

# fmt: off
_PRODUCTS = {
    # ── Proteins ──────────────────────────────────────────────────────────────
    "chicken breast":         {"fr": "Blanc de poulet",        "aisle": "Meat / Boucherie",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "chicken thigh":          {"fr": "Cuisse de poulet",       "aisle": "Meat / Boucherie",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "whole chicken":          {"fr": "Poulet entier",          "aisle": "Meat / Boucherie",    "stores": ["Cactus", "Auchan", "Delhaize"]},
    "ground beef":            {"fr": "Bœuf haché",             "aisle": "Meat / Boucherie",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "beef steak":             {"fr": "Steak de bœuf",          "aisle": "Meat / Boucherie",    "stores": ["Cactus", "Auchan", "Delhaize"]},
    "pork tenderloin":        {"fr": "Filet de porc",          "aisle": "Meat / Boucherie",    "stores": ["Cactus", "Auchan", "Delhaize"]},
    "pork chop":              {"fr": "Côtelette de porc",      "aisle": "Meat / Boucherie",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi"]},
    "lamb":                   {"fr": "Agneau",                 "aisle": "Meat / Boucherie",    "stores": ["Cactus", "Auchan", "Delhaize"]},
    "salmon fillet":          {"fr": "Filet de saumon",        "aisle": "Fish / Poissonnerie", "stores": ["Cactus", "Auchan", "Delhaize"]},
    "tuna (canned)":          {"fr": "Thon (en conserve)",     "aisle": "Canned Goods / Épicerie", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "cod":                    {"fr": "Cabillaud",              "aisle": "Fish / Poissonnerie", "stores": ["Cactus", "Auchan", "Delhaize"]},
    "shrimp":                 {"fr": "Crevettes",              "aisle": "Fish / Poissonnerie", "stores": ["Cactus", "Auchan", "Delhaize"]},
    "eggs":                   {"fr": "Œufs",                   "aisle": "Dairy / Œufs",        "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "tofu":                   {"fr": "Tofu",                   "aisle": "Organic / Bio",       "stores": ["Cactus", "Auchan", "Delhaize"]},
    "tempeh":                 {"fr": "Tempeh",                 "aisle": "Organic / Bio",       "stores": ["Cactus", "Auchan"]},
    # ── Dairy ─────────────────────────────────────────────────────────────────
    "greek yogurt":           {"fr": "Yaourt grec",            "aisle": "Dairy / Laiterie",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "natural yogurt":         {"fr": "Yaourt nature",          "aisle": "Dairy / Laiterie",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "milk":                   {"fr": "Lait",                   "aisle": "Dairy / Laiterie",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "semi-skimmed milk":      {"fr": "Lait demi-écrémé",       "aisle": "Dairy / Laiterie",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "feta cheese":            {"fr": "Fromage feta",           "aisle": "Dairy / Fromagerie",  "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "cottage cheese":         {"fr": "Fromage cottage",        "aisle": "Dairy / Laiterie",    "stores": ["Cactus", "Auchan", "Delhaize"]},
    "mozzarella":             {"fr": "Mozzarella",             "aisle": "Dairy / Fromagerie",  "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "parmesan":               {"fr": "Parmesan",               "aisle": "Dairy / Fromagerie",  "stores": ["Cactus", "Auchan", "Delhaize"]},
    "butter":                 {"fr": "Beurre",                 "aisle": "Dairy / Laiterie",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "cream cheese":           {"fr": "Fromage à la crème",     "aisle": "Dairy / Laiterie",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi"]},
    "heavy cream":            {"fr": "Crème entière",          "aisle": "Dairy / Laiterie",    "stores": ["Cactus", "Auchan", "Delhaize"]},
    "sour cream":             {"fr": "Crème fraîche",          "aisle": "Dairy / Laiterie",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    # ── Grains & carbs ────────────────────────────────────────────────────────
    "brown rice":             {"fr": "Riz complet",            "aisle": "Grains / Céréales",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "white rice":             {"fr": "Riz blanc",              "aisle": "Grains / Céréales",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "quinoa":                 {"fr": "Quinoa",                 "aisle": "Grains / Céréales",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi"]},
    "oats":                   {"fr": "Flocons d'avoine",       "aisle": "Grains / Céréales",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "pasta":                  {"fr": "Pâtes",                  "aisle": "Grains / Pâtes",      "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "whole wheat pasta":      {"fr": "Pâtes complètes",        "aisle": "Grains / Pâtes",      "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "couscous":               {"fr": "Couscous",               "aisle": "Grains / Céréales",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "lentils":                {"fr": "Lentilles",              "aisle": "Legumes / Légumineuses", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "red lentils":            {"fr": "Lentilles rouges",       "aisle": "Legumes / Légumineuses", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi"]},
    "chickpeas":              {"fr": "Pois chiches",           "aisle": "Legumes / Légumineuses", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "black beans":            {"fr": "Haricots noirs",         "aisle": "Legumes / Légumineuses", "stores": ["Cactus", "Auchan", "Delhaize"]},
    "kidney beans":           {"fr": "Haricots rouges",        "aisle": "Legumes / Légumineuses", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "bread":                  {"fr": "Pain",                   "aisle": "Bakery / Boulangerie", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "whole wheat bread":      {"fr": "Pain complet",           "aisle": "Bakery / Boulangerie", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "wraps":                  {"fr": "Wraps / Tortillas",      "aisle": "Bakery / Boulangerie", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi"]},
    "rice cakes":             {"fr": "Galettes de riz",        "aisle": "Snacks / Snacks",     "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    # ── Vegetables ────────────────────────────────────────────────────────────
    "spinach":                {"fr": "Épinards",               "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "broccoli":               {"fr": "Brocoli",                "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "zucchini":               {"fr": "Courgette",              "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "courgette":              {"fr": "Courgette",              "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "bell pepper":            {"fr": "Poivron",                "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "red bell pepper":        {"fr": "Poivron rouge",          "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "onion":                  {"fr": "Oignon",                 "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "red onion":              {"fr": "Oignon rouge",           "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "garlic":                 {"fr": "Ail",                    "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "tomato":                 {"fr": "Tomate",                 "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "cherry tomatoes":        {"fr": "Tomates cerises",        "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "cucumber":               {"fr": "Concombre",              "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "carrot":                 {"fr": "Carotte",                "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "sweet potato":           {"fr": "Patate douce",           "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "potato":                 {"fr": "Pomme de terre",         "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "cauliflower":            {"fr": "Chou-fleur",             "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "kale":                   {"fr": "Chou kale",              "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize"]},
    "lettuce":                {"fr": "Laitue",                 "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "mixed salad leaves":     {"fr": "Mesclun / Salade mélangée", "aisle": "Produce / Légumes", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "mushrooms":              {"fr": "Champignons",            "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "asparagus":              {"fr": "Asperges",               "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize"]},
    "green beans":            {"fr": "Haricots verts",         "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "peas":                   {"fr": "Petits pois",            "aisle": "Frozen / Surgelés",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "corn":                   {"fr": "Maïs",                   "aisle": "Canned Goods / Épicerie", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "eggplant":               {"fr": "Aubergine",              "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "leek":                   {"fr": "Poireau",                "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "celery":                 {"fr": "Céleri",                 "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize"]},
    # ── Fruit ─────────────────────────────────────────────────────────────────
    "apple":                  {"fr": "Pomme",                  "aisle": "Produce / Fruits",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "banana":                 {"fr": "Banane",                 "aisle": "Produce / Fruits",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "orange":                 {"fr": "Orange",                 "aisle": "Produce / Fruits",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "lemon":                  {"fr": "Citron",                 "aisle": "Produce / Fruits",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "lime":                   {"fr": "Citron vert",            "aisle": "Produce / Fruits",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "strawberries":           {"fr": "Fraises",                "aisle": "Produce / Fruits",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "blueberries":            {"fr": "Myrtilles",              "aisle": "Produce / Fruits",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "mixed berries":          {"fr": "Fruits rouges mélangés", "aisle": "Frozen / Surgelés",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "mango":                  {"fr": "Mangue",                 "aisle": "Produce / Fruits",    "stores": ["Cactus", "Auchan", "Delhaize"]},
    "avocado":                {"fr": "Avocat",                 "aisle": "Produce / Fruits",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "grapes":                 {"fr": "Raisins",                "aisle": "Produce / Fruits",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    # ── Nuts & seeds ──────────────────────────────────────────────────────────
    "almonds":                {"fr": "Amandes",                "aisle": "Snacks / Noix",       "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "walnuts":                {"fr": "Noix",                   "aisle": "Snacks / Noix",       "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "cashews":                {"fr": "Noix de cajou",          "aisle": "Snacks / Noix",       "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "chia seeds":             {"fr": "Graines de chia",        "aisle": "Health / Bio",        "stores": ["Cactus", "Auchan", "Delhaize"]},
    "flaxseeds":              {"fr": "Graines de lin",         "aisle": "Health / Bio",        "stores": ["Cactus", "Auchan", "Delhaize"]},
    "sunflower seeds":        {"fr": "Graines de tournesol",   "aisle": "Snacks / Noix",       "stores": ["Cactus", "Auchan", "Delhaize", "Aldi"]},
    "pumpkin seeds":          {"fr": "Graines de courge",      "aisle": "Snacks / Noix",       "stores": ["Cactus", "Auchan", "Delhaize", "Aldi"]},
    "peanut butter":          {"fr": "Beurre de cacahuète",    "aisle": "Spreads / Pâtes à tartiner", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi"]},
    "almond butter":          {"fr": "Beurre d'amande",        "aisle": "Health / Bio",        "stores": ["Cactus", "Auchan", "Delhaize"]},
    # ── Oils & condiments ─────────────────────────────────────────────────────
    "olive oil":              {"fr": "Huile d'olive",          "aisle": "Oils / Huiles",       "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "extra virgin olive oil": {"fr": "Huile d'olive vierge extra", "aisle": "Oils / Huiles",  "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "coconut oil":            {"fr": "Huile de coco",          "aisle": "Oils / Huiles",       "stores": ["Cactus", "Auchan", "Delhaize"]},
    "soy sauce":              {"fr": "Sauce soja",             "aisle": "International / Asie","stores": ["Cactus", "Auchan", "Delhaize", "Aldi"]},
    "honey":                  {"fr": "Miel",                   "aisle": "Spreads / Pâtes à tartiner", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "tomato passata":         {"fr": "Coulis de tomates",      "aisle": "Canned Goods / Épicerie", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "tinned tomatoes":        {"fr": "Tomates pelées en boîte","aisle": "Canned Goods / Épicerie", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl", "Match"]},
    "tomato paste":           {"fr": "Concentré de tomates",   "aisle": "Canned Goods / Épicerie", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "balsamic vinegar":       {"fr": "Vinaigre balsamique",    "aisle": "Oils / Vinaigrettes", "stores": ["Cactus", "Auchan", "Delhaize"]},
    "dijon mustard":          {"fr": "Moutarde de Dijon",      "aisle": "Condiments / Sauces", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "tahini":                 {"fr": "Tahini / Purée de sésame","aisle": "International / Moyen-Orient", "stores": ["Cactus", "Auchan", "Delhaize"]},
    "hummus":                 {"fr": "Houmous",                "aisle": "Deli / Charcuterie",  "stores": ["Cactus", "Auchan", "Delhaize", "Aldi"]},
    # ── Herbs & spices ────────────────────────────────────────────────────────
    "cumin":                  {"fr": "Cumin",                  "aisle": "Spices / Épices",     "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "paprika":                {"fr": "Paprika",                "aisle": "Spices / Épices",     "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "turmeric":               {"fr": "Curcuma",                "aisle": "Spices / Épices",     "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "cinnamon":               {"fr": "Cannelle",               "aisle": "Spices / Épices",     "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "dried oregano":          {"fr": "Origan séché",           "aisle": "Spices / Épices",     "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "fresh basil":            {"fr": "Basilic frais",          "aisle": "Produce / Herbes",    "stores": ["Cactus", "Auchan", "Delhaize"]},
    "fresh parsley":          {"fr": "Persil frais",           "aisle": "Produce / Herbes",    "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "fresh coriander":        {"fr": "Coriandre fraîche",      "aisle": "Produce / Herbes",    "stores": ["Cactus", "Auchan", "Delhaize"]},
    "ginger":                 {"fr": "Gingembre",              "aisle": "Produce / Légumes",   "stores": ["Cactus", "Auchan", "Delhaize", "Aldi"]},
    "chili flakes":           {"fr": "Piment en flocons",      "aisle": "Spices / Épices",     "stores": ["Cactus", "Auchan", "Delhaize", "Aldi"]},
    # ── Pantry staples ────────────────────────────────────────────────────────
    "vegetable stock":        {"fr": "Bouillon de légumes",    "aisle": "Canned Goods / Épicerie", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "chicken stock":          {"fr": "Bouillon de poulet",     "aisle": "Canned Goods / Épicerie", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
    "coconut milk":           {"fr": "Lait de coco",           "aisle": "International / Asie","stores": ["Cactus", "Auchan", "Delhaize", "Aldi"]},
    "protein powder":         {"fr": "Protéine en poudre",     "aisle": "Health / Santé",      "stores": ["Cactus", "Auchan", "Delhaize", "Grand Frais"]},
    "dark chocolate":         {"fr": "Chocolat noir",          "aisle": "Confectionery / Confiserie", "stores": ["Cactus", "Auchan", "Delhaize", "Aldi", "Lidl"]},
}
# fmt: on


def enrich_item(item: dict) -> dict:
    """
    Add French name, aisle and LU stores to a shopping list item in-place.
    Looks up by English name (case-insensitive). Falls back to item's existing
    name_fr (provided by Claude) if not in the dict.
    """
    name_en = item.get("name_en", "").strip().lower()
    match = _PRODUCTS.get(name_en)
    if match:
        item["name_fr"] = match["fr"]
        item["aisle"] = match["aisle"]
        item["stores"] = match["stores"]
        item["available_in_lux"] = True
    else:
        # Fall back: keep LLM-provided French name or mark as needing review
        if not item.get("name_fr"):
            item["name_fr"] = item.get("name_en", "")  # last resort
        if not item.get("aisle"):
            item["aisle"] = "General / Général"
        if not item.get("stores"):
            item["stores"] = ["Cactus", "Auchan", "Delhaize"]
        item["available_in_lux"] = True
    return item


def get_french_name(name_en: str) -> str:
    """Return French name for an ingredient, or the original if not found."""
    match = _PRODUCTS.get(name_en.strip().lower())
    return match["fr"] if match else name_en
