"""
NutriPrep — daily targets for every member, derived from ONE place.

Inputs, in order of authority:
  1. The nutritionist's plan (nutrition_plan.json, from parse_plan.py) — the
     clinical authority: stated numbers, the macro split its portions imply,
     sugar rules, hydration, foods to eat/avoid.
  2. Each member's goals + body (users/<m>/goals.json, latest weigh-in in
     users/<m>/weight_log.json) — energy need (Mifflin-St Jeor × activity,
     adjusted for the goal and its rate).

How they combine, per member:
  * Energy (kcal): the plan's number when the plan STATES it for that member.
    Otherwise (plan written for someone else, or its numbers were only
    estimated from portions) the member's goals decide the energy.
  * Protein / carbs / fat / fibre: the plan's split (its share of energy for
    each macro, fibre per 1000 kcal) applied to that energy; protein never below
    1.2 g/kg (ACSM/AND/DC) nor above 2.2 g/kg. No plan → reference split.
  * Free sugar ceiling: the plan's own limit if it states one; 5% of energy
    (WHO conditional) if the plan restricts sugar; otherwise 10% (WHO).
    Total sugar has no target (fruit, milk, yogurt are fine).
  * Water: the plan's hydration for its client; EFSA drinking-water amounts
    for everyone else.

Writes users/<m>/macro_targets.json for every member. Coach Claudio reads
Diego's file (see SHARED_DATA.md). Run directly (`python targets.py`), from
parse_plan.py after a new plan, and from generate.py every Friday.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent
MEMBERS = ["diego", "diana"]
MACROS = ("kcal", "protein_g", "carbs_g", "fat_g", "fiber_g")
ACTIVITY = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725, "very_active": 1.9}
SUGAR_WORDS = ("sugar", "azúcar", "azucar", "sweet", "dulce", "refined", "refinad", "pastr", "bollería",
               "bolleria", "soda", "soft drink", "refresco", "juice", "zumo", "candy", "chocolate", "dessert", "postre")


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) and x == x else None


def _load(path: Path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def body_of(goals: dict, weight_log: list) -> dict:
    """Body data for the energy maths; `missing` lists what had to be assumed."""
    goals = goals or {}
    logs = sorted([w for w in (weight_log or []) if _num(w.get("weight_kg"))], key=lambda w: w.get("date", ""))
    weight = logs[-1]["weight_kg"] if logs else _num(goals.get("start_weight_kg"))
    missing = []
    if not weight:
        missing.append("weight")
    for k in ("height_cm", "age", "sex", "activity_level"):
        if not goals.get(k):
            missing.append(k)
    sex = goals.get("sex") if goals.get("sex") in ("male", "female") else None
    return {
        "weight_kg": weight or 70,
        "height_cm": _num(goals.get("height_cm")) or (178 if sex == "male" else 165),
        "age": _num(goals.get("age")) or 40,
        "sex": sex,
        "activity": ACTIVITY.get(goals.get("activity_level") or "light", 1.375),
        "missing": missing,
    }


def goal_energy(goals: dict, body: dict) -> tuple[int, str]:
    """kcal/day for the goal, and a one-line explanation."""
    goals = goals or {}
    kg, h, age = body["weight_kg"], body["height_cm"], body["age"]
    sex_adj = 5 if body["sex"] == "male" else -161 if body["sex"] == "female" else -78
    bmr = 10 * kg + 6.25 * h - 5 * age + sex_adj
    tdee = bmr * body["activity"]
    goal = goals.get("goal_type") or "maintain"
    rate = _num(goals.get("target_rate_kg_per_week")) or 0.5
    if goal == "weight_loss":
        deficit = min(rate * 7700 / 7, tdee * 0.25)          # never more than a 25% deficit
        kcal, why = tdee - deficit, f"weight loss at ~{rate} kg/week"
    elif goal == "muscle_gain":
        kcal, why = tdee + 250, "lean muscle gain (+250 kcal)"
    elif goal == "recomp":
        kcal, why = tdee * 0.9, "recomposition (−10%)"
    else:
        kcal, why = tdee, "maintenance"
    floor = 1500 if body["sex"] == "male" else 1200
    kcal = max(kcal, floor, bmr * 1.05)
    return int(round(kcal / 10) * 10), why


def plan_split(plan: dict) -> dict | None:
    """The macro split the plan implies (share of energy, fibre per 1000 kcal)."""
    for t in ((plan or {}).get("per_member_targets") or {}).values():
        t = t or {}
        kcal = _num(t.get("kcal"))
        if kcal and all(_num(t.get(k)) for k in ("protein_g", "carbs_g", "fat_g")):
            return {"protein": t["protein_g"] * 4 / kcal, "carbs": t["carbs_g"] * 4 / kcal,
                    "fat": t["fat_g"] * 9 / kcal,
                    "fiber_per_1000": (_num(t.get("fiber_g")) or kcal * 0.014) / kcal * 1000}
    return None


def plan_restricts_sugar(plan: dict) -> bool:
    plan = plan or {}
    text = " ".join([*(plan.get("restricted_foods") or []), plan.get("methodology") or "",
                     plan.get("nutritionist_notes") or ""]).lower()
    return any(w in text for w in SUGAR_WORDS) or "glucose" in text


def free_sugar_ceiling(plan: dict, kcal: int) -> tuple[int, str]:
    sg = (plan or {}).get("sugar_guidance") or {}
    if _num(sg.get("free_sugar_max_g")):
        return int(round(sg["free_sugar_max_g"])), "nutritionist plan"
    if _num(sg.get("free_sugar_max_pct_energy")):
        return int(round(kcal * sg["free_sugar_max_pct_energy"] / 100 / 4)), "nutritionist plan"
    if plan_restricts_sugar(plan):
        return int(round(kcal * 0.05 / 4)), "plan limits sugar → WHO 5% of energy"
    return int(round(kcal * 0.10 / 4)), "WHO: under 10% of energy"


def derive(member: str, plan: dict, goals: dict, weight_log: list) -> dict:
    plan = plan or {}
    body = body_of(goals, weight_log)
    stated = ((plan.get("per_member_targets") or {}).get(member)) or {}
    stated = {k: v for k, v in stated.items() if _num(v)}
    estimated = bool(plan.get("targets_estimated"))
    has_plan = plan.get("source") == "nutritionist_upload"
    client = has_plan and bool(stated.get("kcal"))
    sources = {}

    goal_kcal, goal_why = goal_energy(goals, body)
    if client and not estimated:
        kcal, sources["kcal"] = int(round(stated["kcal"])), "nutritionist plan"
    elif client and estimated and body["missing"]:
        kcal, sources["kcal"] = int(round(stated["kcal"])), "nutritionist plan (estimated from portions)"
    else:
        kcal, sources["kcal"] = goal_kcal, f"goals: {goal_why}"

    split = plan_split(plan) if has_plan else None
    kg = body["weight_kg"]
    out = {"kcal": kcal}
    if client and not estimated and all(stated.get(k) for k in ("protein_g", "carbs_g", "fat_g")):
        for k in ("protein_g", "carbs_g", "fat_g", "fiber_g"):
            if stated.get(k):
                out[k], sources[k] = int(round(stated[k])), "nutritionist plan"
        if "fiber_g" not in out:
            out["fiber_g"], sources["fiber_g"] = kcal * 0.014, "reference (14 g / 1000 kcal)"
    elif split:
        out["protein_g"] = kcal * split["protein"] / 4
        out["fat_g"] = kcal * split["fat"] / 9
        out["fiber_g"] = kcal * split["fiber_per_1000"] / 1000
        for k in ("protein_g", "fat_g", "fiber_g"):
            sources[k] = "nutritionist plan's split"
    else:
        protein_per_kg = 1.8 if (goals or {}).get("goal_type") == "weight_loss" else 1.6
        out["protein_g"], out["fat_g"], out["fiber_g"] = kg * protein_per_kg, kcal * 0.30 / 9, kcal * 0.014
        sources.update({"protein_g": "reference (ACSM/AND/DC)", "fat_g": "reference (30% of energy)",
                        "fiber_g": "reference (14 g / 1000 kcal)"})
    # Protein inside the evidence band for active adults; carbs take what's left.
    p = min(max(out["protein_g"], kg * 1.2), kg * 2.2)
    if round(p) != round(out["protein_g"]):
        sources["protein_g"] += " (kept within 1.2–2.2 g/kg)"
    out["protein_g"] = p
    if "carbs_g" not in out:
        out["carbs_g"] = max(50, (kcal - out["protein_g"] * 4 - out["fat_g"] * 9) / 4)
        sources["carbs_g"] = sources["protein_g"].split(" (")[0] if split else "remaining energy"
    for k in ("protein_g", "carbs_g", "fat_g", "fiber_g"):
        out[k] = int(round(out[k]))

    out["free_sugar_g"], sources["free_sugar_g"] = free_sugar_ceiling(plan, kcal)
    if client and _num(plan.get("hydration_l")):
        out["water_ml"], sources["water_ml"] = int(plan["hydration_l"] * 1000), "nutritionist plan"
    else:
        out["water_ml"] = 1600 if body["sex"] == "female" else 2000
        sources["water_ml"] = "reference (EFSA, drinks)"

    kinds = {s.split(" (")[0].split(":")[0] for s in sources.values()}
    out.update({
        "source": ("nutritionist + goals" if has_plan and "goals" in kinds else
                   "nutritionist" if has_plan else "derived from goals"),
        "sources": sources,
        "basis": ("Energy from " + sources["kcal"] + ("; macro split from the nutritionist plan" if split else "")),
        "body": {k: body[k] for k in ("weight_kg", "height_cm", "age", "sex")} | {"activity_factor": body["activity"]},
        "missing_body": body["missing"],
        "goal": {k: (goals or {}).get(k) for k in ("goal_type", "target_weight_kg", "target_rate_kg_per_week", "target_date")},
        "sugar": {"free_sugar_max_g": out["free_sugar_g"], "rule": sources["free_sugar_g"],
                  "total_sugar": "no target — fruit, milk and plain yogurt sugars are fine"},
        "updated_on": date.today().isoformat(),
    })
    if has_plan:
        out.update({"methodology": plan.get("methodology", ""), "prescribed_foods": plan.get("prescribed_foods", []),
                    "restricted_foods": plan.get("restricted_foods", []), "client_name": plan.get("client_name", ""),
                    "nutritionist_notes": plan.get("nutritionist_notes", ""), "plan_client": client})
    return out


def derive_all(base: Path = BASE, members=MEMBERS, write: bool = True) -> dict:
    plan = _load(base / "nutrition_plan.json", {})
    out = {}
    for m in members:
        udir = base / "users" / m
        t = derive(m, plan, _load(udir / "goals.json", {}), _load(udir / "weight_log.json", []))
        out[m] = t
        if write:
            udir.mkdir(parents=True, exist_ok=True)
            with open(udir / "macro_targets.json", "w") as f:
                json.dump(t, f, indent=2)
    return out


if __name__ == "__main__":
    for m, t in derive_all().items():
        print(f"{m}: {t['kcal']} kcal · P{t['protein_g']} C{t['carbs_g']} F{t['fat_g']} · fibre {t['fiber_g']} · "
              f"free sugar ≤{t['free_sugar_g']} g · {t['basis']}"
              + (f" · missing: {', '.join(t['missing_body'])}" if t["missing_body"] else ""))
