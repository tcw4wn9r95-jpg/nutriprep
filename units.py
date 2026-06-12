"""
NutriPrep — quantity parsing & normalisation.
Parses human ingredient quantities ("200 g", "1.2 kg", "2 cloves", "1/2 cup")
into a normalised (amount, kind, unit) so inventory can add/subtract them.

kinds:
  - "mass"   → base unit grams (g)
  - "volume" → base unit millilitres (ml)
  - "count"  → base unit is the count word itself (e.g. "clove"); only
               subtractable against the same count word
  - "unknown"→ unparseable; carried through as-is, never auto-subtracted
"""
import re

_MASS = {"g": 1, "gram": 1, "grams": 1, "gr": 1, "kg": 1000, "kgs": 1000, "kilo": 1000, "kilos": 1000, "kilogram": 1000, "kilograms": 1000}
_VOLUME = {"ml": 1, "milliliter": 1, "millilitre": 1, "cl": 10, "dl": 100, "l": 1000, "litre": 1000, "liter": 1000, "litres": 1000, "liters": 1000}
# Count words we recognise (kept as their own unit for subtraction)
_COUNT = {
    "pcs", "pc", "piece", "pieces", "unit", "units", "x",
    "clove", "cloves", "can", "cans", "tin", "tins", "jar", "jars",
    "slice", "slices", "fillet", "fillets", "egg", "eggs", "head", "heads",
    "bunch", "bunches", "sprig", "sprigs", "stalk", "stalks", "stick", "sticks",
    "handful", "handfuls", "pinch", "pinches", "dash", "dashes",
    "tbsp", "tablespoon", "tablespoons", "tsp", "teaspoon", "teaspoons",
    "cup", "cups", "scoop", "scoops", "pack", "packs", "packet", "packets",
    "bottle", "bottles", "punnet", "punnets", "bag", "bags",
}


def _parse_number(token: str) -> float | None:
    token = token.strip().replace(",", ".")
    # range "2-3" → take the upper bound (so we don't under-buy)
    if "-" in token:
        parts = [p for p in token.split("-") if p]
        try:
            return max(float(p) for p in parts)
        except ValueError:
            return None
    # fraction "1/2"
    if "/" in token:
        try:
            num, den = token.split("/")
            return float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(token)
    except ValueError:
        return None


def parse_qty(qty: str) -> dict:
    """Return {amount, kind, unit, raw} for a quantity string."""
    raw = str(qty).strip()
    low = raw.lower()
    m = re.match(r"^([\d.,/\-\s]+)?\s*([a-zµ]*)", low)
    if not m:
        return {"amount": None, "kind": "unknown", "unit": "", "raw": raw}

    num_str, unit = m.group(1), (m.group(2) or "").strip()
    amount = _parse_number(num_str) if num_str and num_str.strip() else 1.0
    if amount is None:
        amount = 1.0

    if unit in _MASS:
        return {"amount": amount * _MASS[unit], "kind": "mass", "unit": "g", "raw": raw}
    if unit in _VOLUME:
        return {"amount": amount * _VOLUME[unit], "kind": "volume", "unit": "ml", "raw": raw}
    # singularise simple plurals for count words
    singular = unit[:-1] if unit.endswith("s") and unit[:-1] in _COUNT else unit
    if unit in _COUNT or singular in _COUNT:
        return {"amount": amount, "kind": "count", "unit": singular if singular in _COUNT else unit, "raw": raw}
    # bare number, no unit → treat as count of "unit"
    if not unit and num_str and num_str.strip():
        return {"amount": amount, "kind": "count", "unit": "unit", "raw": raw}
    return {"amount": None, "kind": "unknown", "unit": unit, "raw": raw}


def format_qty(amount: float, kind: str, unit: str) -> str:
    """Render a normalised amount back into a friendly string."""
    if amount is None:
        return ""
    if kind == "mass":
        if amount >= 1000:
            return f"{round(amount / 1000, 2)} kg".replace(".0 ", " ")
        return f"{int(round(amount))} g"
    if kind == "volume":
        if amount >= 1000:
            return f"{round(amount / 1000, 2)} L".replace(".0 ", " ")
        return f"{int(round(amount))} ml"
    if kind == "count":
        n = round(amount, 1)
        n = int(n) if n == int(n) else n
        u = unit + ("s" if n != 1 and not unit.endswith("s") else "")
        return f"{n} {u}".strip()
    return ""


def add_qty(a: dict, b: dict) -> dict:
    """Add two parsed quantities of the same kind/unit. Returns parsed dict."""
    if a["kind"] == b["kind"] and a["kind"] != "unknown" and a.get("unit") == b.get("unit"):
        return {"amount": (a["amount"] or 0) + (b["amount"] or 0), "kind": a["kind"], "unit": a["unit"], "raw": ""}
    # fall back to whichever is parseable
    return a if a["kind"] != "unknown" else b


def subtract_qty(have: dict, used: dict) -> dict:
    """Subtract `used` from `have`. Returns parsed dict, clamped at 0."""
    if have["kind"] == used["kind"] and have["kind"] != "unknown" and have.get("unit") == used.get("unit"):
        remaining = max(0.0, (have["amount"] or 0) - (used["amount"] or 0))
        return {"amount": remaining, "kind": have["kind"], "unit": have["unit"], "raw": ""}
    return have  # incompatible units → leave untouched
