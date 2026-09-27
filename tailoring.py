"""
NutriPrep — household food preferences and per-person menu tailoring.

The household eats ONE shared menu, cooked by one person. Each member can still
have their own restrictions (intolerances, foods they won't eat, a diet style)
and their own loves. This module is the single source of truth for:

  * loading preferences.json (migrating the older household.json +
    learned_preferences.json fields on the fly until the app has saved once),
  * turning a member's restrictions into matchable terms,
  * checking every portion of the generated menu against them, and
  * annotating each meal with WHO gets a different plate and WHY, so the app
    can say so clearly.

Pure functions only — no network, no file writes — so it is unit-testable.

preferences.json shape
----------------------
{
  "migrated_legacy": true,
  "household": {"allergies": [], "intolerances": [], "avoid": [], "love": [], "notes": []},
  "people": {
    "diego": {"allergies": [], "intolerances": [], "avoid": [], "love": [], "notes": [], "diet_style": "omnivore"},
    "diana": {...}
  },
  "history": [{"at": "2026-09-27", "who": "diana", "kind": "avoid", "item": "mushrooms",
               "action": "added", "source": "app"}]
}

"household" entries apply to everyone. ALLERGIES — whoever they belong to — are
kept out of the whole kitchen (shared pans, cross-contact); everything else only
changes that person's plate.
"""
from __future__ import annotations

import re

LIST_KINDS = ("allergies", "intolerances", "avoid", "love", "notes")
DIET_STYLES = ("omnivore", "flexitarian", "pescatarian", "vegetarian", "vegan")

# ── Keyword expansions ────────────────────────────────────────────────────────
# A restriction like "lactose" or "vegetarian" has to be matched against concrete
# ingredient names. These lists cover the common cases; anything else is matched
# as the literal word the household typed.
_MEAT = ["chicken", "turkey", "beef", "pork", "lamb", "veal", "duck", "bacon", "ham",
         "sausage", "chorizo", "salami", "prosciutto", "mince", "steak", "meatball",
         "poulet", "dinde", "boeuf", "bœuf", "porc", "agneau", "jambon", "lardons"]
_FISH = ["fish", "salmon", "tuna", "cod", "hake", "mackerel", "sardine", "anchovy", "trout",
         "tilapia", "sea bass", "seabass", "haddock", "pollock", "herring", "saumon", "thon",
         "cabillaud", "poisson"]
_SHELLFISH = ["shrimp", "prawn", "crab", "lobster", "mussel", "clam", "oyster", "scallop",
              "squid", "calamari", "octopus", "crevette", "moule", "langoustine"]
_DAIRY = ["milk", "cheese", "yogurt", "yoghurt", "cream", "butter", "kefir", "feta",
          "mozzarella", "parmesan", "ricotta", "cottage cheese", "skyr", "quark", "ghee", "halloumi", "buttermilk",
          "lait", "fromage", "yaourt", "crème", "beurre"]
_EGG = ["egg", "oeuf", "œuf", "mayonnaise", "mayo"]
_GLUTEN = ["wheat", "bread", "pasta", "spaghetti", "penne", "couscous", "barley", "rye",
           "flour", "bulgur", "seitan", "farro", "spelt", "semolina", "tortilla", "wrap",
           "pita", "noodle", "baguette", "croissant", "cracker", "breadcrumb", "blé", "pain",
           "pâtes", "farine"]
_NUTS = ["almond", "walnut", "cashew", "hazelnut", "pecan", "pistachio", "macadamia",
         "brazil nut", "pine nut", "amande", "noix", "noisette", "pistache"]

EXPANSIONS: dict[str, list[str]] = {
    # intolerances / allergies
    "lactose": _DAIRY,
    "dairy": _DAIRY,
    "milk": _DAIRY,
    "gluten": _GLUTEN,
    "wheat": _GLUTEN,
    "coeliac": _GLUTEN,
    "celiac": _GLUTEN,
    "egg": _EGG,
    "eggs": _EGG,
    "shellfish": _SHELLFISH,
    "crustaceans": _SHELLFISH,
    "seafood": _FISH + _SHELLFISH,
    "fish": _FISH,
    "tree nuts": _NUTS,
    "nuts": _NUTS + ["peanut"],
    "peanut": ["peanut", "cacahuète", "arachide"],
    "peanuts": ["peanut", "cacahuète", "arachide"],
    "soy": ["soy", "soja", "tofu", "tempeh", "edamame", "miso"],
    "soya": ["soy", "soja", "tofu", "tempeh", "edamame", "miso"],
    "sesame": ["sesame", "sésame", "tahini", "tahina"],
    "red meat": ["beef", "pork", "lamb", "veal", "boeuf", "bœuf", "porc", "agneau"],
    "meat": _MEAT,
    "pork": ["pork", "bacon", "ham", "chorizo", "salami", "prosciutto", "porc", "jambon", "lardons"],
}

DIET_EXCLUDES: dict[str, list[str]] = {
    "omnivore": [],
    "flexitarian": [],
    "pescatarian": _MEAT,
    "vegetarian": _MEAT + _FISH + _SHELLFISH + ["gelatin", "gélatine"],
    "vegan": _MEAT + _FISH + _SHELLFISH + _DAIRY + _EGG + ["honey", "miel", "gelatin", "gélatine"],
}

# An ingredient that says it is free of the thing is fine ("lactose-free milk").
_FREE_OF = re.compile(r"\b(lactose|gluten|dairy|egg|nut|soy|sugar)[- ]free\b|\bsans (lactose|gluten)\b")
# Plant "milks"/"creams"/"butters" are not dairy.
_PLANT_DAIRY = re.compile(
    r"\b(oat|almond|soy|soya|rice|coconut|cashew|pea|plant|vegan|avoine|amande|soja|coco)[- ]"
    r"(milk|cream|yogh?urt|butter|drink|lait|crème|yaourt|boisson)\b"
    r"|\b(peanut|almond|cashew|nut|seed)[- ]butter\b|\bcocoa butter\b|\bbutter ?beans?\b"
    r"|\bcream of tartar\b|\bcoconut\b"
)


def _clean_list(v) -> list[str]:
    out, seen = [], set()
    for x in v or []:
        s = str(x).strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


def empty_person() -> dict:
    return {k: [] for k in LIST_KINDS} | {"diet_style": ""}


def normalize(prefs: dict | None, members: list[str]) -> dict:
    """Return a complete, de-duplicated preferences dict for these members."""
    prefs = prefs or {}
    hh_in = prefs.get("household") or {}
    household = {k: _clean_list(hh_in.get(k)) for k in LIST_KINDS}
    people = {}
    for m in members:
        p_in = (prefs.get("people") or {}).get(m) or {}
        p = {k: _clean_list(p_in.get(k)) for k in LIST_KINDS}
        style = str(p_in.get("diet_style") or "").strip().lower()
        p["diet_style"] = style if style in DIET_STYLES else ""
        people[m] = p
    return {
        "migrated_legacy": bool(prefs.get("migrated_legacy")),
        "household": household,
        "people": people,
        "history": list(prefs.get("history") or [])[-200:],
    }


def load_preferences(prefs_file: dict | None, household: dict | None, learned: dict | None,
                     members: list[str]) -> dict:
    """Merge preferences.json with the legacy sources it replaces.

    Until the app has saved preferences.json once (``migrated_legacy``), the older
    household-wide fields are folded into the "household" section so nothing the
    household already told the app is lost."""
    prefs = normalize(prefs_file, members)
    if prefs["migrated_legacy"]:
        return prefs
    household = household or {}
    learned = learned or {}
    hh = prefs["household"]
    hh["allergies"] = _clean_list(hh["allergies"] + list(household.get("allergies") or []))
    hh["intolerances"] = _clean_list(hh["intolerances"] + list(household.get("intolerances") or []))
    hh["avoid"] = _clean_list(hh["avoid"] + list(household.get("dislikes") or []) + list(learned.get("avoid") or []))
    hh["love"] = _clean_list(hh["love"] + list(learned.get("prefer") or []))
    hh["notes"] = _clean_list(hh["notes"] + list(learned.get("notes") or []))
    style = str(household.get("diet_style") or "").strip().lower()
    if style in DIET_STYLES:
        for p in prefs["people"].values():
            if not p["diet_style"]:
                p["diet_style"] = style
    return prefs


# ── Term matching ─────────────────────────────────────────────────────────────
_LEAD_NOISE = re.compile(r"^(no|not|never|avoid|without|hates?|dislikes?|less|any|all)\s+", re.I)


def terms_for(item: str) -> list[str]:
    """Concrete, lower-case ingredient words a restriction stands for."""
    s = _LEAD_NOISE.sub("", str(item).strip().lower()).strip(" .!")
    if not s:
        return []
    if s in EXPANSIONS:
        return sorted(set(EXPANSIONS[s] + [s]))
    # "lactose intolerance", "gluten (coeliac)" → the known key inside it
    for key, words in EXPANSIONS.items():
        if re.search(rf"\b{re.escape(key)}\b", s):
            return sorted(set(words + [key]))
    return [s]


_WORD = re.compile(r"[a-zà-ÿœæ]+")


def _sing(w: str) -> str:
    """Crude singular so 'mushrooms' matches 'mushroom' and 'anchovies' 'anchovy'."""
    if len(w) <= 3:
        return w
    if w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith(("oes", "ches", "shes", "xes", "sses")):
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us")):
        return w[:-1]
    return w


def _words(text: str) -> str:
    return " " + " ".join(_sing(w) for w in _WORD.findall(text.lower())) + " "


def matches(item_text: str, terms: list[str], dairy_like: bool = False) -> str | None:
    """Return the term that hits this ingredient text, or None.

    Whole-word matching on singularised words, so 'egg' hits 'eggs' but not
    'eggplant', and 'butter' does not hit 'butternut squash'."""
    text = str(item_text or "").lower()
    if not text:
        return None
    for fm in _FREE_OF.finditer(text):
        # "lactose-free milk" is fine for a lactose rule (but still milk for a dairy one)
        if (fm.group(1) or fm.group(2)) in terms:
            return None
    text = _FREE_OF.sub(" ", text)
    if dairy_like:
        text = _PLANT_DAIRY.sub(" ", text)
    hay = _words(text)
    for t in terms:
        needle = _words(t)
        if needle.strip() and needle in hay:
            return t
    return None


def _is_dairy_terms(terms: list[str]) -> bool:
    return any(t in _DAIRY for t in terms)


def kitchen_allergens(prefs: dict) -> list[str]:
    """Every allergy in the household — kept out of ALL dishes."""
    out = list(prefs["household"]["allergies"])
    for p in prefs["people"].values():
        out += p["allergies"]
    return _clean_list(out)


def restrictions_for(prefs: dict, member: str) -> list[dict]:
    """Things this member must not be served: [{label, kind, terms}]."""
    p = prefs["people"].get(member) or empty_person()
    hh = prefs["household"]
    rules = []
    for kind in ("intolerances", "avoid"):
        for item in _clean_list(hh[kind] + p[kind]):
            ts = terms_for(item)
            if ts:
                rules.append({"label": item, "kind": kind, "terms": ts})
    if p.get("diet_style") and DIET_EXCLUDES.get(p["diet_style"]):
        rules.append({"label": p["diet_style"], "kind": "diet", "terms": DIET_EXCLUDES[p["diet_style"]]})
    return rules


def _ingredient_names(portion: dict) -> list[str]:
    out = []
    for ing in (portion or {}).get("ingredients") or []:
        if isinstance(ing, dict):
            out.append(str(ing.get("item") or ""))
        else:
            out.append(str(ing))
    return [x for x in out if x.strip()]


def find_allergen_hits(menu: list[dict], prefs: dict, members: list[str]) -> list[str]:
    """Any kitchen allergen in any portion of any meal (fatal)."""
    hits = []
    for allergen in kitchen_allergens(prefs):
        terms = terms_for(allergen)
        dairy = _is_dairy_terms(terms)
        for day in menu:
            for meal in day.get("meals", []):
                for m in members:
                    for name in _ingredient_names((meal.get("portions") or {}).get(m)):
                        t = matches(name, terms, dairy)
                        if t:
                            hits.append(f"{day.get('day','?')} {meal.get('slot','?')} '{meal.get('name','')}': "
                                        f"{m}'s '{name}' contains allergen '{allergen}'")
    return hits


def check_portions(menu: list[dict], prefs: dict, members: list[str]) -> list[dict]:
    """Personal restriction violations (non-fatal). Annotates each offending meal
    with ``warnings`` so the cook sees it, and returns a flat list."""
    found = []
    rules = {m: restrictions_for(prefs, m) for m in members}
    for day in menu:
        for meal in day.get("meals", []):
            meal.pop("warnings", None)
            for m in members:
                names = _ingredient_names((meal.get("portions") or {}).get(m))
                for rule in rules[m]:
                    dairy = _is_dairy_terms(rule["terms"])
                    for name in names:
                        if matches(name, rule["terms"], dairy):
                            w = {"member": m, "ingredient": name, "rule": rule["label"], "kind": rule["kind"],
                                 "day": day.get("day"), "slot": meal.get("slot"), "meal": meal.get("name")}
                            found.append(w)
                            kind_label = {"diet": "diet", "intolerances": "intolerance", "avoid": "won't-eat list"}[rule["kind"]]
                            meal.setdefault("warnings", []).append(
                                {"member": m, "text": f"'{name}' conflicts with {m.capitalize()}'s {kind_label}: {rule['label']}"})
                            break
    return found


def _norm_item(name: str) -> str:
    s = re.sub(r"\(.*?\)", "", str(name).lower())
    s = re.sub(r"[^a-zà-ÿ ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"(es|s)$", "", s)


def _has_personal_rules(prefs: dict | None, member: str) -> bool:
    p = ((prefs or {}).get("people") or {}).get(member) or {}
    return bool(p.get("allergies") or p.get("intolerances") or p.get("avoid")
                or (p.get("diet_style") or "omnivore") not in ("", "omnivore", "flexitarian"))


def _attribute(diffs: dict, explicit: set, missing: dict, prefs: dict | None) -> dict:
    """A difference between two plates shows up from both sides ("without X" /
    "adds X"). Keep it only on the plate that was actually adapted."""
    if explicit:
        return {m: t for m, t in diffs.items() if m in explicit}
    if len(diffs) < 2:
        return diffs
    lacking = {m: t for m, t in diffs.items() if missing.get(m)}
    if len(lacking) == 1:
        return lacking
    pool = lacking or diffs
    restricted = {m: t for m, t in pool.items() if _has_personal_rules(prefs, m)}
    return restricted if len(restricted) == 1 else pool


def annotate_differences(menu: list[dict], members: list[str], prefs: dict | None = None) -> int:
    """Mark meals where a member's PLATE differs (not just the portion size).

    Sets ``meal["differs_for"]`` = [members] and ``meal["differences"]`` =
    {member: "what is different"}. A model-supplied ``portions.<m>.variant``
    wins; otherwise the difference is derived from the ingredient lists.
    Returns the number of meals that differ."""
    n = 0
    for day in menu:
        for meal in day.get("meals", []):
            portions = meal.get("portions") or {}
            present = [m for m in members if m in portions]
            item_sets = {m: {_norm_item(x) for x in _ingredient_names(portions[m])} for m in present}
            diffs, explicit, missing_by = {}, set(), {}
            for m in present:
                variant = (portions[m] or {}).get("variant") or {}
                if isinstance(variant, dict) and (variant.get("changes") or variant.get("name")):
                    txt = variant.get("changes") or f"Gets {variant.get('name')}"
                    if variant.get("reason"):
                        txt += f" ({variant['reason']})"
                    diffs[m] = txt
                    explicit.add(m)
                    continue
                others = [item_sets[o] for o in present if o != m]
                if not others or not item_sets[m]:
                    continue
                shared = set.intersection(*others) if others else set()
                union_others = set.union(*others)
                missing = sorted(x for x in shared if x not in item_sets[m])
                extra = sorted(x for x in item_sets[m] if x not in union_others)
                missing_by[m] = missing
                if missing or extra:
                    parts = []
                    if extra and missing:
                        parts.append(f"{', '.join(extra)} instead of {', '.join(missing)}")
                    elif missing:
                        parts.append(f"without {', '.join(missing)}")
                    else:
                        parts.append(f"adds {', '.join(extra)}")
                    diffs[m] = "; ".join(parts)
            diffs = _attribute(diffs, explicit, missing_by, prefs)
            if diffs:
                meal["differs_for"] = sorted(diffs)
                meal["differences"] = diffs
                n += 1
            else:
                meal.pop("differs_for", None)
                meal.pop("differences", None)
    return n


def prompt_block(prefs: dict, members: list[str]) -> str:
    """Human-readable summary of everyone's preferences for the generation prompt."""
    hh = prefs["household"]
    lines = []
    allergens = kitchen_allergens(prefs)
    lines.append("KITCHEN-WIDE ALLERGIES (ABSOLUTE — never in ANY dish or portion, not even for the other person, "
                 "to avoid cross-contact): " + (", ".join(allergens) if allergens else "none"))
    if hh["intolerances"] or hh["avoid"]:
        lines.append("Everyone avoids: " + ", ".join(_clean_list(hh["intolerances"] + hh["avoid"])))
    if hh["love"]:
        lines.append("Everyone loves (lean into these): " + ", ".join(hh["love"]))
    if hh["notes"]:
        lines.append("Household notes (respect the spirit; don't re-suggest dishes they swapped away): "
                     + "; ".join(hh["notes"][-12:]))
    for m in members:
        p = prefs["people"][m]
        bits = []
        if p["diet_style"] and p["diet_style"] != "omnivore":
            bits.append(f"diet: {p['diet_style']}")
        if p["allergies"]:
            bits.append("allergies: " + ", ".join(p["allergies"]))
        if p["intolerances"]:
            bits.append("intolerances (never on their plate): " + ", ".join(p["intolerances"]))
        if p["avoid"]:
            bits.append("won't eat (never on their plate): " + ", ".join(p["avoid"]))
        if p["love"]:
            bits.append("loves: " + ", ".join(p["love"]))
        if p["notes"]:
            bits.append("notes: " + "; ".join(p["notes"][-8:]))
        lines.append(f"{m.capitalize()} — " + (" · ".join(bits) if bits else "no personal restrictions"))
    return "\n".join(lines)


# ── Middle ground: one shared pot that fits as many plates as possible ─────────
_DIET_ORDER = ["", "omnivore", "flexitarian", "pescatarian", "vegetarian", "vegan"]
# Food groups each diet leaves out, in the order they're named to the cook.
_DIET_LEAVES_OUT = {
    "omnivore": [], "flexitarian": [], "": [],
    "pescatarian": ["meat"],
    "vegetarian": ["meat", "fish"],
    "vegan": ["meat", "fish", "dairy", "eggs"],
}


def middle_ground(prefs: dict, members: list[str]) -> dict:
    """Rules that maximise how often everyone can eat the SAME plate.

    * base_diet — the strictest diet in the house; shared dishes are built on it
      and the others get their extra protein as a separate add-on.
    * keep_out — personal intolerances / won't-eat items: left out of the shared
      pot (a person who loves one gets it on the side).
    * sides — someone's love that clashes with another person's rules: cooked or
      served on the side, only for them.
    * shared_loves — loved by everyone (or by the household): build dishes on them.
    * safe_loves — one person's love nobody objects to: fine in the shared dish.
    """
    styles = {m: prefs["people"][m]["diet_style"] or "omnivore" for m in members}
    base = max(styles.values(), key=_DIET_ORDER.index) if styles else "omnivore"
    addons = []
    for m in members:
        extra = [g for g in _DIET_LEAVES_OUT[base] if g not in _DIET_LEAVES_OUT[styles[m]]]
        if extra:
            groups = extra[0] if len(extra) == 1 else ", ".join(extra[:-1]) + " or " + extra[-1]
            addons.append({"member": m, "note": f"add {groups} as a separate component"})

    rules = {m: restrictions_for(prefs, m) for m in members}
    loves = {m: _clean_list(prefs["people"][m]["love"]) for m in members}
    hh_love = prefs["household"]["love"]

    keep_out, seen = [], {}
    for m in members:
        p = prefs["people"][m]
        for kind in ("intolerances", "avoid"):
            for item in p[kind]:
                key = item.lower()
                if key in seen:
                    if m not in seen[key]["who"]:
                        seen[key]["who"].append(m)
                    continue
                entry = {"item": item, "kind": kind, "who": [m], "side_for": []}
                seen[key] = entry
                keep_out.append(entry)
    sides, safe = [], []
    for m in members:
        for love in loves[m]:
            blockers = []
            for o in members:
                if o == m:
                    continue
                for r in rules[o]:
                    if matches(love, r["terms"], _is_dairy_terms(r["terms"])):
                        blockers.append({"member": o, "rule": r["label"]})
                        break
            if blockers:
                sides.append({"item": love, "member": m, "because": blockers})
                for e in keep_out:
                    if any(b["rule"] == e["item"] for b in blockers) and m not in e["side_for"]:
                        e["side_for"].append(m)
            elif not all(any(love.lower() == x.lower() for x in loves[o]) for o in members):
                safe.append({"item": love, "member": m})
    common = [x for x in loves[members[0]] if all(any(x.lower() == y.lower() for y in loves[o]) for o in members[1:])] \
        if members else []
    # A household-wide love still has to pass everyone's rules; if it doesn't, the
    # people who can eat it get it on the side.
    shared = []
    for love in _clean_list(hh_love + common):
        blocked = [{"member": o, "rule": r["label"]} for o in members
                   for r in rules[o][:] if matches(love, r["terms"], _is_dairy_terms(r["terms"]))]
        if not blocked:
            shared.append(love)
            continue
        blocked_members = {b["member"] for b in blocked}
        for m in members:
            if m not in blocked_members and not any(s["item"].lower() == love.lower() and s["member"] == m for s in sides):
                sides.append({"item": love, "member": m, "because": blocked})
    return {
        "base_diet": base,
        "addons": addons,
        "keep_out": keep_out,
        "sides": sides,
        "shared_loves": shared,
        "safe_loves": safe,
    }


def middle_ground_block(prefs: dict, members: list[str]) -> str:
    mg = middle_ground(prefs, members)
    name = lambda m: m.capitalize()  # noqa: E731
    lines = ["Goal: the SAME plate for everyone as often as possible (aim for ≥85% of meals identical apart from "
             "portion size). Build every shared dish on this common ground, then add per-person extras — don't swap "
             "whole recipes:"]
    if mg["base_diet"] not in ("", "omnivore", "flexitarian"):
        extra = "; ".join(f"{name(a['member'])}: {a['note']}" for a in mg["addons"])
        lines.append(f"- Shared base is {mg['base_diet']}" + (f" ({extra})." if extra else "."))
    if mg["keep_out"]:
        lines.append("- Keep OUT of the shared pot: " + "; ".join(
            f"{e['item']} ({', '.join(name(w) for w in e['who'])})"
            + (f" — serve on the side for {', '.join(name(s) for s in e['side_for'])}" if e["side_for"] else "")
            for e in mg["keep_out"]))
    if mg["sides"]:
        lines.append("- Loved by one, not OK for another → on the side / add-on only: " + "; ".join(
            f"{s['item']} for {name(s['member'])}" for s in mg["sides"]))
    if mg["shared_loves"]:
        lines.append("- Everyone loves — build shared dishes around: " + ", ".join(mg["shared_loves"]))
    if mg["safe_loves"]:
        lines.append("- One person's favourite that suits everyone — use in shared dishes: " + ", ".join(
            f"{s['item']} ({name(s['member'])})" for s in mg["safe_loves"]))
    return "\n".join(lines)


def overlap_stats(menu: list[dict]) -> dict:
    """How many meals are the same plate for everyone (after annotate_differences)."""
    total = sum(len(d.get("meals", [])) for d in menu)
    differ = sum(1 for d in menu for m in d.get("meals", []) if m.get("differs_for"))
    return {"meals": total, "same_plate": total - differ,
            "same_plate_pct": round((total - differ) / total * 100) if total else None}
