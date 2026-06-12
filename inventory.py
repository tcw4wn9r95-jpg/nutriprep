"""
NutriPrep — daily fridge/pantry inventory update.
Runs at ~21:00 Luxembourg (19:00 UTC) via cron. For every confirmed meal
(meal_logs entry with ate=true that hasn't been applied to inventory yet),
subtract that person's portion ingredients from inventory.json.

Inventory is (re)seeded weekly by generate.py to the full week's required
quantities. This job only depletes it based on what was actually eaten.
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
    for member in MEMBERS:
        logs_path = BASE / "users" / member / "meal_logs.json"
        logs = load(logs_path, [])
        changed = False

        for entry in logs:
            if not entry.get("ate") or entry.get("inv_applied"):
                continue
            meal = find_meal(menu, entry.get("date"), entry.get("slot"))
            if not meal:
                # Can't map to a meal (e.g. plan rotated) — mark applied to avoid retry
                entry["inv_applied"] = True
                changed = True
                continue

            portion = (meal.get("portions") or {}).get(member, {})
            for ing in portion.get("ingredients", []):
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

            entry["inv_applied"] = True
            entry["inv_applied_on"] = date.today().isoformat()
            changed = True
            total_applied += 1

        if changed:
            with open(logs_path, "w") as f:
                json.dump(logs, f, indent=2)

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

    print(f"Inventory updated: applied {total_applied} confirmed meal(s); {len(kept)} items remain.")


if __name__ == "__main__":
    main()
