"""
NutriPrep — daily fridge/pantry inventory update.
Runs at ~21:00 Luxembourg (19:00 UTC) via cron. For every meal the cook marked
"I made this" (cooked_log.json) that hasn't been applied yet, subtract EVERY
member's portion ingredients from inventory.json. Older per-person ticks
(users/<m>/meal_logs.json, ate=true) are still applied for that person's portion.

The pantry reflects only what the household has actually bought (added via
"Add bought to fridge" in the app). generate.py never seeds it. This job
only depletes it based on what was actually eaten.
"""
import json
from datetime import date
from pathlib import Path

import units

BASE = Path(__file__).parent
MEMBERS = ["diego", "diana"]


def load(path: Path, default):
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return default
    return default


def find_meal(menu: list, day_date: str, slot: str) -> dict | None:
    for day in menu:
        if day.get("date") == day_date:
            for meal in day.get("meals", []):
                if meal.get("slot") == slot:
                    return meal
    return None


def main():
    inventory = load(BASE / "inventory.json", {"items": []})
    menu = load(BASE / "weekly_menu.json", [])
    if not inventory.get("items"):
        print("Inventory empty — nothing to deplete. (Generate a plan first.)")
        return

    # Index inventory by lowercased English name for fast subtraction
    inv_index = {it["name_en"].strip().lower(): it for it in inventory["items"]}

    total_applied = 0

    def deplete(portion: dict) -> None:
        for ing in (portion or {}).get("ingredients", []):
            name = ing.get("item", "").strip().lower()
            inv_item = inv_index.get(name)
            if not inv_item:
                continue
            used = units.parse_qty(ing.get("qty", ""))
            have = {
                "amount": inv_item.get("amount"),
                "kind": inv_item.get("kind", "unknown"),
                "unit": inv_item.get("unit", ""),
            }
            if have["kind"] == "unknown" or used["kind"] == "unknown":
                continue
            remaining = units.subtract_qty(have, used)
            inv_item["amount"] = round(remaining["amount"], 2)
            inv_item["display_qty"] = units.format_qty(
                inv_item["amount"], inv_item["kind"], inv_item["unit"]
            )

    def apply(entries: list, members: list[str], path: Path, is_ready) -> None:
        nonlocal total_applied
        changed = False
        for entry in entries:
            if not is_ready(entry) or entry.get("inv_applied"):
                continue
            meal = find_meal(menu, entry.get("date"), entry.get("slot"))
            if meal:
                for member in members:
                    deplete((meal.get("portions") or {}).get(member, {}))
                total_applied += 1
            # Unmappable (plan rotated) entries are marked too, so they aren't retried.
            entry["inv_applied"] = True
            entry["inv_applied_on"] = date.today().isoformat()
            changed = True
        if changed:
            with open(path, "w") as f:
                json.dump(entries, f, indent=2)

    # Household "I made this" log — the cook made the meal for everyone.
    cooked_path = BASE / "cooked_log.json"
    apply(load(cooked_path, []), MEMBERS, cooked_path, lambda e: True)
    # Legacy per-person ticks from before household mode.
    for member in MEMBERS:
        logs_path = BASE / "users" / member / "meal_logs.json"
        if logs_path.exists():
            apply(load(logs_path, []), [member], logs_path, lambda e: e.get("ate"))

    # Drop items that are fully depleted (amount ~0) for parseable kinds
    kept = []
    for it in inventory["items"]:
        if it.get("kind") in ("mass", "volume", "count") and (it.get("amount") or 0) <= 0.001:
            continue
        kept.append(it)
    inventory["items"] = kept
    inventory["updated"] = date.today().isoformat()

    with open(BASE / "inventory.json", "w") as f:
        json.dump(inventory, f, indent=2)

    print(f"Inventory updated: applied {total_applied} made meal(s); {len(kept)} items remain.")


if __name__ == "__main__":
    main()
