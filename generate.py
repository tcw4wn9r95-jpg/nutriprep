"""
NutriPrep — Sunday weekly meal plan generator.
Reads household + user profiles, calls Claude Sonnet, parses three JSON blocks
(menu / shopping / prep), post-processes with food_safety + lux_products, writes
all output files and computes the notification schedule for the week.
"""
import os, json, sys, re, traceback
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import anthropic

BASE = Path(__file__).parent
LUX = ZoneInfo("Europe/Luxembourg")
MEMBERS = ["diego", "diana"]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# ── Self-reporting diagnostics ────────────────────────────────────────────────
# On ANY failure, write a readable log (traceback + raw Claude response) that the
# workflow commits, so the exact cause is visible without CI-log access.
ERROR_LOG = BASE / "_generation_error.txt"
_DEBUG = {"response": None, "stop_reason": None, "phase": "startup"}


def _write_error(header: str, body: str) -> None:
    try:
        with open(ERROR_LOG, "w") as f:
            f.write(f"{header}\nWhen: {datetime.now().isoformat()}\nPhase: {_DEBUG['phase']}\n\n{body}")
            if _DEBUG.get("stop_reason"):
                f.write(f"\n\nstop_reason: {_DEBUG['stop_reason']}")
            if _DEBUG.get("response"):
                f.write("\n\n=== RAW CLAUDE RESPONSE (first 20k chars) ===\n" + _DEBUG["response"][:20000])
    except Exception:
        pass


def _excepthook(exc_type, exc, tb):
    _write_error("NutriPrep plan generation FAILED (uncaught exception).",
                 "".join(traceback.format_exception(exc_type, exc, tb)))
    sys.__excepthook__(exc_type, exc, tb)


sys.excepthook = _excepthook

# ── Load shared files ─────────────────────────────────────────────────────────
with open(BASE / "household.json") as f:
    household = json.load(f)
with open(BASE / "schedule.json") as f:
    schedule = json.load(f)

nutrition_plan: dict = {}
if (BASE / "nutrition_plan.json").exists():
    with open(BASE / "nutrition_plan.json") as f:
        nutrition_plan = json.load(f)

menu_history: list = []
if (BASE / "menu_history.json").exists():
    with open(BASE / "menu_history.json") as f:
        menu_history = json.load(f)

# Preferences the household taught Coach Léa through chat (manual swaps, likes, dislikes).
learned_prefs: dict = {}
if (BASE / "learned_preferences.json").exists():
    with open(BASE / "learned_preferences.json") as f:
        try:
            learned_prefs = json.load(f) or {}
        except Exception:
            learned_prefs = {}

# ── Load per-user data ────────────────────────────────────────────────────────
users: dict = {}
for member in MEMBERS:
    udir = BASE / "users" / member
    u: dict = {}
    for fname in ["goals", "macro_targets", "weight_log", "checkins"]:
        p = udir / f"{fname}.json"
        if p.exists():
            with open(p) as f:
                u[fname] = json.load(f)
        else:
            u[fname] = [] if fname in ("weight_log", "checkins") else {}
    users[member] = u

# ── Compute next Monday ───────────────────────────────────────────────────────
today = date.today()
days_until_mon = (7 - today.weekday()) % 7 or 7
next_monday = today + timedelta(days=days_until_mon)
week_dates = {name: (next_monday + timedelta(days=i)).isoformat() for i, name in enumerate(DAY_NAMES)}

# ── Cross-app link to the training app (AthleteIQ) over the shared channel ─────
# training_link reads AthleteIQ's public JSON from the training-ai repo via HTTP.
import training_link
training_week = training_link.load_training_week(week_dates)   # {date: {...}}
sleep_block = training_link.sleep_summary()
athlete = training_link.shared_profile()
# Training fuelling applies to the athlete (Diego) only; Diana isn't on AthleteIQ.
ATHLETE_MEMBER = "diego"

# ── Skip if plan already exists (unless forced) ───────────────────────────────
_force = os.environ.get("FORCE_GENERATE", "").strip().lower() in ("1", "true")
if not _force and (BASE / "plan_status.json").exists():
    with open(BASE / "plan_status.json") as f:
        existing = json.load(f)
    if existing.get("week_of") == next_monday.isoformat() and existing.get("status") == "published":
        print(f"Plan already exists for {next_monday}. Use FORCE_GENERATE=1 to override.")
        sys.exit(0)

# ── Build member context ──────────────────────────────────────────────────────
member_blocks = []
for member in MEMBERS:
    u = users[member]
    mt = u.get("macro_targets") or {}
    goals = u.get("goals") or {}
    wlog = u.get("weight_log") or []
    recent_w = sorted(wlog, key=lambda x: x["date"])[-4:] if wlog else []

    # Weight trend summary
    if len(recent_w) >= 2:
        delta = recent_w[-1]["weight_kg"] - recent_w[0]["weight_kg"]
        trend = f"{recent_w[-1]['weight_kg']} kg (last 4 weeks: {delta:+.1f} kg)"
    elif recent_w:
        trend = f"{recent_w[-1]['weight_kg']} kg (starting)"
    else:
        trend = f"Start: {goals.get('start_weight_kg', '?')} kg (no weigh-ins yet)"

    target_w = goals.get("target_weight_kg", "?")
    rate = goals.get("target_rate_kg_per_week", 0.5)
    goal_type = goals.get("goal_type", "maintain")

    # Recent check-ins (last 14 days)
    cutoff = (today - timedelta(days=14)).isoformat()
    recent_ci = [c for c in (u.get("checkins") or []) if c.get("date", "") >= cutoff]
    ci_text = ""
    if recent_ci:
        ci_text = "\n  Recent check-ins:\n" + "\n".join(
            f"    {c['date']}: {c.get('note', '')} (mood:{c.get('mood','?')} energy:{c.get('energy','?')})"
            for c in recent_ci[-5:]
        )

    # Get macro targets from nutrition plan if available
    plan_targets = (nutrition_plan.get("per_member_targets") or {}).get(member) or {}
    if plan_targets and plan_targets.get("kcal"):
        macro_src = "nutritionist plan"
        mt = {**mt, **{k: v for k, v in plan_targets.items() if v is not None}}
    else:
        macro_src = mt.get("source", "estimate")

    member_blocks.append(f"""
### {member.capitalize()}
Goal: {goal_type.replace('_', ' ').title()} · Target: {target_w} kg at −{rate} kg/wk
Weight: {trend}
Daily targets ({macro_src}): {mt.get('kcal','?')} kcal · {mt.get('protein_g','?')}g protein · {mt.get('carbs_g','?')}g carbs · {mt.get('fat_g','?')}g fat · {mt.get('fiber_g','?')}g fibre{ci_text}""")

# ── Nutritionist guidelines ───────────────────────────────────────────────────
plan_notes = []
if nutrition_plan.get("client_name"):
    plan_notes.append(f"A nutritionist's plan is on file for {nutrition_plan['client_name']}. Treat the MACRO TARGETS, "
                      "the meal structure/times, and the AVOID list below as authority. The nutritionist's specific "
                      "example foods are INSPIRATION, not a fixed menu — prioritise variety.")
if nutrition_plan.get("methodology"):
    plan_notes.append("Methodology to respect: " + nutrition_plan["methodology"])
if nutrition_plan.get("prescribed_foods"):
    plan_notes.append("Encouraged regularly (lean on these, but you are not limited to them): " + ", ".join(nutrition_plan["prescribed_foods"]))
if nutrition_plan.get("restricted_foods"):
    plan_notes.append("AVOID — never serve these (hard rule): " + ", ".join(nutrition_plan["restricted_foods"]))
# Meal-by-meal exchange structure — used as a REFERENCE for shape & portion sizes, not a mandatory list.
if nutrition_plan.get("meals"):
    struct = ["The nutritionist's example daily structure is below. Use it ONLY as a reference for each meal's "
              "shape, the methodology, and typical portion SIZES per slot. It is NOT a required ingredient list: "
              "design fresh, varied, interesting dishes — you may use ANY healthy, in-season Luxembourg ingredient "
              "and any preferred cuisine, as long as you hit each member's macro targets and never use an avoided "
              "food. Do not simply repeat these exact items day to day:"]
    for m in nutrition_plan["meals"]:
        label = m.get("label") or m.get("slot", "")
        t = m.get("time", "")
        water = f" · {m['water_ml']} ml water" if m.get("water_ml") else ""
        struct.append(f"  {label} ({t}){water}:")
        for c in m.get("components", []):
            opts = c.get("portion") or " / ".join(c.get("options", []))
            struct.append(f"    - {c.get('category', '')} (e.g. {opts})")
    plan_notes.append("\n".join(struct))
if nutrition_plan.get("nutritionist_notes"):
    plan_notes.append("Notes: " + nutrition_plan["nutritionist_notes"])
nutrition_block = "\n".join(plan_notes) if plan_notes else "No nutritionist plan uploaded yet — use individual macro targets as authority."

# ── History (variety) ─────────────────────────────────────────────────────────
if menu_history:
    hist_lines = []
    for h in menu_history[-3:]:
        meals = h.get("meal_names", [])
        hist_lines.append(f"  Week of {h.get('week_of','?')}: {', '.join(meals[:6])}" + (" …" if len(meals) > 6 else ""))
    history_block = "\n".join(hist_lines)
else:
    history_block = "  No history yet — first week, prioritise variety and simplicity."

# ── Allergens & preferences ───────────────────────────────────────────────────
allergens = household.get("allergies", []) + household.get("intolerances", [])
dislikes = list(household.get("dislikes", [])) + list(learned_prefs.get("avoid", []))
cuisines = household.get("cuisines_loved", [])

# Free-form things learned from chat: foods they love, manual swaps, general notes.
_pref_lines = []
if learned_prefs.get("prefer"):
    _pref_lines.append("Foods/styles they have told Coach Léa they LOVE — lean into these: " + ", ".join(learned_prefs["prefer"]))
if learned_prefs.get("notes"):
    _pref_lines.append("Notes from past manual changes (respect the spirit — don't re-suggest dishes they swapped away): " + "; ".join(learned_prefs["notes"]))
learned_block = "\n".join(f"  {l}" for l in _pref_lines) if _pref_lines else "  Nothing learned from chat yet."

# Fridge-safety windows, sourced from food_safety.py so the prompt never drifts from
# the deterministic enforcement that runs afterwards.
from food_safety import use_within_days as _uwd
_safety_cats = [
    ("poultry", "chicken / turkey"), ("red_meat", "beef / pork / lamb"),
    ("fish_seafood", "fish / seafood"), ("rice", "cooked rice"),
    ("grains_pasta", "quinoa / pasta / cooked grains"), ("legumes", "beans / lentils / chickpeas"),
    ("vegetables_cooked", "roasted / cooked veg"), ("eggs_cooked", "cooked eggs"),
    ("soup_stew", "soup / stew / curry"), ("sauce_dairy", "cream / dairy sauce"),
]
safety_windows_block = "\n".join(f"  {label}: safe ~{_uwd(key)} day(s) in the fridge after cooking" for key, label in _safety_cats)

budget = household.get("budget_eur_per_week", 130)
max_prep = household.get("max_prep_minutes_sunday", 150)
max_cook = household.get("max_cook_minutes_weekday", 25)

# ── Schedule context ──────────────────────────────────────────────────────────
meal_times = schedule.get("meal_times", {})
eat_out_days = schedule.get("eat_out_days", [])
schedule_block = "\n".join(f"  {slot.replace('_', ' ').title()}: {t}" for slot, t in meal_times.items())
if eat_out_days:
    schedule_block += f"\n  Eat out: {', '.join(eat_out_days)} (still include a light home meal for those days)"

# ── Training fuelling (Diego only) — per-day adjusted calorie targets ──────────
diego_base_kcal = (users["diego"].get("macro_targets") or {}).get("kcal", 0) or 0
training_lines = []
diego_day_targets = {}  # iso_date -> adjusted kcal
for name in DAY_NAMES:
    d = week_dates[name]
    t = training_week.get(d)
    if t and t["extra_kcal"] > 0:
        adj = diego_base_kcal + t["extra_kcal"]
        diego_day_targets[d] = adj
        training_lines.append(
            f"  {name} {d}: 🚴 {t['name']} ({t['sport']}, {t['tss']} TSS, {t['duration_min']} min) "
            f"→ fuel +{t['extra_kcal']} kcal → Diego target ≈ {adj} kcal (add carbs)"
        )
    else:
        training_lines.append(f"  {name} {d}: rest / no logged session → Diego base {diego_base_kcal} kcal")
training_block = "\n".join(training_lines) if diego_base_kcal else "  (no athlete calorie base available)"
if not training_week:
    training_block = "  No training sessions found for this week (AthleteIQ plan not generated yet) — use base targets."

athlete_block = ""
if athlete.get("name") or athlete.get("training_goal"):
    athlete_block = (
        f"Athlete: {athlete.get('name','Diego')} | Training goal: {athlete.get('training_goal','-')}"
        + (f" | Injuries: {athlete['injuries']}" if athlete.get("injuries") else "")
    )

# ── Build the prompt ──────────────────────────────────────────────────────────
diego_kcal = (users["diego"].get("macro_targets") or {}).get("kcal", "?")
diana_kcal = (users["diana"].get("macro_targets") or {}).get("kcal", "?")

# ── Stage 1: lock a lean FRESH palette ────────────────────────────────────────
# The model won't obey a fresh-item cap inside the big menu prompt, so we first ask
# for ONLY a small shared palette of fresh proteins/vegetables, then force Stage 2 to
# build the entire week from exactly that list. Staples (carbs/spices/sauces) stay free,
# so variety comes from them — keeping the weekly FRESH shop small.
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

_palette_prompt = f"""You are a dietitian planning ONE week of meals for a Luxembourg household (Diego + Diana — same dishes, different portions).
Your ONLY job right now is to choose a SMALL shared FRESH-INGREDIENT PALETTE that the whole week's dishes will be built from. Day-to-day variety will come from carbs, spices and sauces (cheap pantry staples) — NOT from many different fresh items.

Hard constraints:
- Allergies (NEVER include): {', '.join(allergens) if allergens else 'none'}
- Dislikes / avoid (never include): {', '.join(dislikes) if dislikes else 'none'}
- Preferred cuisines: {', '.join(cuisines) if cuisines else 'varied'}
- The palette must be able to deliver: oily fish twice/week, legumes on ≥3 days, ≥5 veg portions/day each, and hit ~{diego_kcal} kcal (Diego) / ~{diana_kcal} kcal (Diana).
{('- Nutritionist guidance to respect: ' + nutrition_block) if nutrition_block and nutrition_block.strip() else ''}

Rules for the palette (STRICT):
- AT MOST 4 fresh proteins (e.g. one poultry, one white fish, one oily fish, one red meat or eggs). Pantry legumes (canned/dried beans, lentils, chickpeas) are STAPLES — list them under carbs_staples, not proteins.
- AT MOST 10 fresh vegetables and AT MOST 5 fruits — pick versatile ones you can reuse across many cuisines.
- ONE bread and ONE leafy green only.
- Then list the STAPLES you will lean on for VARIETY (as many as you like): grains/carbs, and spices/seasonings/sauces/oils.

Output ONLY this JSON block — no prose:
```json-palette
{{
  "proteins": ["..."],
  "vegetables": ["..."],
  "fruits": ["..."],
  "breads_greens": ["one bread", "one leafy green"],
  "carbs_staples": ["brown rice", "wholewheat pasta", "couscous", "canned chickpeas", "..."],
  "spices_sauces_staples": ["olive oil", "soy sauce", "cumin", "paprika", "..."]
}}
```"""

print("Stage 1: locking the fresh palette...")
_DEBUG["phase"] = "calling Claude API (palette)"
palette: dict = {}
try:
    _pal_msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{"role": "user", "content": _palette_prompt}],
    )
    _pal_text = "".join(b.text for b in _pal_msg.content if getattr(b, "type", None) == "text")
    _start, _end = _pal_text.find("{"), _pal_text.rfind("}")
    if _start >= 0 and _end > _start:
        palette = json.loads(_pal_text[_start:_end + 1])
except Exception as e:  # never let palette selection block the whole run
    print(f"  ! Stage 1 failed ({e}); falling back to soft caps in the menu prompt.")
    palette = {}


def _plist(key):
    return ", ".join(str(x) for x in (palette.get(key) or []))


if palette.get("proteins") or palette.get("vegetables"):
    palette_block = (
        "These fresh ingredients were LOCKED FIRST and are NON-NEGOTIABLE. Build EVERY dish using ONLY them:\n"
        f"  FRESH PROTEINS — use only these: {_plist('proteins')}\n"
        f"  FRESH VEGETABLES — use only these: {_plist('vegetables')}\n"
        f"  FRUITS — use only these: {_plist('fruits')}\n"
        f"  BREAD & LEAFY GREEN: {_plist('breads_greens')}\n"
        f"  CARBS / STAPLES — rotate these freely for variety: {_plist('carbs_staples')}\n"
        f"  SPICES / SAUCES / OILS — rotate these freely for variety: {_plist('spices_sauces_staples')}\n"
        "You MAY also use common cheap aromatics/finishers as needed even if not listed: garlic, onion, shallot, "
        "lemon, lime, fresh ginger, fresh chilli, fresh herbs — plus basic pantry items (salt, pepper, water, stock, "
        "vinegar, a little cheese/yogurt/egg). But DO NOT introduce any new fresh PROTEIN or new fresh VEGETABLE "
        "beyond the locked lists. If a dish idea needs something off-list, redesign it to use the palette instead."
    )
    print(f"  Palette locked: {len(palette.get('proteins', []))} proteins, {len(palette.get('vegetables', []))} vegetables.")
else:
    palette_block = ("No locked palette available — keep the FRESH shop lean yourself: AT MOST 4 fresh proteins and "
                     "AT MOST 10 fresh vegetables for the whole week, reused across dishes.")

prompt = f"""You are Coach Léa, a registered dietitian coach for a household in Luxembourg.
Generate a complete, evidence-based weekly meal plan for the week of {next_monday.strftime('%d %B %Y')} (Monday–Sunday).

## HOUSEHOLD
Two people: Diego and Diana. They eat the SAME dishes, just different portion sizes.
Allergies (ABSOLUTE — never include): {', '.join(allergens) if allergens else 'none'}
Dislikes (avoid): {', '.join(dislikes) if dislikes else 'none'}
Preferred cuisines: {', '.join(cuisines) if cuisines else 'varied'}
Weekly food budget: €{budget} (shopping for both)
Max Sunday batch-prep time: {max_prep} min active
Max weekday cooking time: {max_cook} min

## MEMBER PROFILES
{"".join(member_blocks)}

## NUTRITIONIST GUIDELINES (macros, meal structure & the AVOID list are authority; the specific example foods are inspiration — favour variety)
{nutrition_block}

## TRAINING FUELLING — DIEGO ONLY (shared from his AthleteIQ training plan)
{athlete_block}
Diego's calorie need changes day to day with training. On training days, raise his portions/snacks to hit the adjusted target below (carbs especially — pre/post workout fuel). Diana's targets do NOT change. Same dish for both; just bigger or an extra component for Diego on hard days.
{training_block}

## SLEEP & RECOVERY (shared from AthleteIQ / Garmin)
{sleep_block or "  No sleep data available."}

## MEAL SCHEDULE (Luxembourg time)
{schedule_block}

## PAST WEEKS (avoid repeating the same dishes)
{history_block}

## LEARNED FROM CHAT (the household corrected the plan — honour this)
{learned_block}

## LOCKED FRESH PALETTE (chosen first — the whole week MUST be built from this)
{palette_block}

## YOUR RULES
1. **One menu for the household, two sets of portions.** Each meal has a `portions.diego` and `portions.diana` with their own ingredient quantities and macros. The dish is the same; only amounts differ.
2. **All 5 slots every day**: breakfast, am_snack, lunch, pm_snack, dinner — no exceptions.
3. **Snacks must be genuinely healthy**: whole foods (fruit, veg, nuts, yogurt, hummus), never ultra-processed.
4. **Maximise Sunday batch-prep**: set `prep_ahead: true` for anything that can be cooked Sunday. Keep `cook_minutes_day_of` ≤ {max_cook} for all main meals (assembly/reheating only on weekdays).
5. **Luxembourg ingredients only**: all items must be available in Luxembourg supermarkets (Cactus, Auchan, Delhaize, Aldi, Lidl). Provide French name in parentheses on first mention.
6. **Evidence-based**: align with EFSA Dietary Reference Values and WHO guidelines. Sustainable weight loss ≈ 0.25–0.75 kg/week; no crash diets, detoxes, or unproven supplements.
7. **Hit each member's daily macro targets** (±10% tolerance). Use `day_totals` to verify.
8. Each week: include oily fish at least twice; legumes on at least 3 days; ≥ 5 portions of veg per day per person.
9. **BUILD EVERY DISH FROM THE LOCKED FRESH PALETTE ABOVE. This is a HARD limit, not a guideline.**
   - Use ONLY the fresh proteins and fresh vegetables/fruits listed in the LOCKED FRESH PALETTE section. Do NOT introduce any fresh protein or fresh vegetable that isn't on those lists. If a dish idea needs something off-list, redesign it to use the palette.
   - Variety comes from the PANTRY, not more fresh items: rotate the CARB (rice, pasta, couscous, potato, tortilla), the SPICE/SEASONING blend, the SAUCE/marinade, and the cooking method/format (bowl, wrap, traybake, stir-fry, soup, salad). The same chicken + courgette becomes a Mexican bowl, a Mediterranean traybake, or an Asian stir-fry just by changing carb + spices. Use as many different spices/sauces/carbs from the palette as you like — they're cheap staples.
   - Aim for ~16–20 distinct dishes across the week. Lunches/dinners should feel different most days; light spaced repetition (a dish at most twice, NEVER on consecutive days) is fine.
   - **Breakfasts and snacks may repeat freely** (e.g. the same two breakfasts alternating all week). Convenience wins.
   - Give each distinct dish its own `name` and `image_prompt`; a deliberate repeat keeps the same name/ingredients.
10. Assign each prep batch a `food_category` from: poultry, red_meat, fish_seafood, eggs_cooked, rice, grains_pasta, legumes, vegetables_cooked, vegetables_raw_prepped, soup_stew, sauce_dairy, dairy, baked_goods, generic.
11. **Recipe split**: every meal MUST have `prep_steps` (what to batch-cook/pre-portion on Sunday — empty list `[]` if nothing) AND `day_of_steps` (detailed, numbered, beginner-friendly actions performed on the day, including reheating instructions and quantities). Keep `video_url` as an empty string "" (the user attaches videos later).
12. **Image prompt**: every meal MUST have an `image_prompt` — a short, vivid description of a finished plate of that meal for an AI image generator (mention key ingredients, plating, natural light; no text/words in image).
13. **Fuel Diego's training days**: match Diego's `day_totals` to the per-day adjusted target in the TRAINING FUELLING table (extra mostly as carbohydrate around the session). On rest days use his base target. Diana's `day_totals` always track her own base target.
14. **Adapt to sleep**: after poor-sleep nights, favour easy-to-digest, blood-sugar-stable meals, adequate protein, and avoid heavy late dinners.
15. **CONSOLIDATE FRESH ITEMS ONLY — pantry staples are cheap, last for weeks, and DON'T count against you.**
   - Minimise DISTINCT FRESH / PERISHABLE products only: meat, fish, fresh vegetables, fresh herbs, dairy, bread. This is the weekly shop — keep it tight (~**12–16 fresh items**) by reusing the same proteins and vegetables across many dishes.
   - Do NOT minimise pantry staples: rice, pasta, couscous, other grains, dried/canned legumes, flour, spices, dried herbs, oils, vinegars, jarred sauces, canned goods, nuts/seeds, honey. The household buys these occasionally in standard packs and uses them across MANY weeks — so use as many different spices, seasonings, sauces and carbs as you like for variety. They are NOT a weekly burden; lean on them as the cheap source of variety.
   - One variant per FRESH staple where it matters (one bread, one fresh leafy green). Several different spices/condiments/carbs is encouraged, not discouraged.
   - Use ingredients sold in standard Luxembourg supermarket pack sizes.
16. **SHOPPING AISLES**: give every shopping item a real `aisle` (e.g. "Produce / Fruits & Légumes", "Meat / Boucherie", "Fish / Poissonnerie", "Dairy / Crèmerie", "Bakery / Boulangerie", "Grains & Pasta / Épicerie", "Frozen / Surgelés", "Oils & Condiments", "Spices / Épices") so the list groups sensibly for one efficient trip. Do not dump everything into "General".
## FOOD SAFETY — FRIDGE WINDOWS FROM SUNDAY PREP (HARD RULES, NON-NEGOTIABLE)
Prep is done on Sunday. Counting Monday = day 1, Tuesday = day 2 … Sunday = day 7, a Sunday-cooked
batch must be EATEN within its safe window:
{safety_windows_block}
Therefore, for every meal you must respect these rules:
  - NEVER set `prep_ahead: true` on a perishable protein/grain that is eaten past its window.
    (e.g. Sunday-cooked chicken eaten Thursday = day 4 > 3-day poultry limit is FORBIDDEN; salmon
    past day 2 is FORBIDDEN; cooked rice past day 1 is FORBIDDEN.)
  - For a perishable dish scheduled LATER than its window, COOK IT FRESH that day: set
    `prep_ahead: false`, put the real cooking in `day_of_steps`, and give a realistic
    `cook_minutes_day_of`. The Sunday batch must not be its source.
  - Alternatively, schedule a SECOND fresh mid-week cook (e.g. a Wednesday batch) as its own prep
    batch to safely cover the back half of the week.
  - Cooked RICE is day-1 only (Bacillus cereus) — cook fresh per serving (or none batched).
  - Only long-keeping items (legumes, cooked veg, cooked eggs, soups: 4–5 days) may bridge most of
    the week from a single Sunday batch.
A deterministic checker runs after you and will force-convert any violation to cook-fresh, so plan
it correctly yourself to keep weekday cooking times realistic.

## WEEK DATES
Monday: {week_dates['Monday']} | Tuesday: {week_dates['Tuesday']} | Wednesday: {week_dates['Wednesday']}
Thursday: {week_dates['Thursday']} | Friday: {week_dates['Friday']}
Saturday: {week_dates['Saturday']} | Sunday: {week_dates['Sunday']}

## OUTPUT — THREE JSON BLOCKS ONLY, IN ORDER
Output ONLY the three fenced code blocks below — no prose, no Markdown summary, no commentary before, between, or after them. Start your reply immediately with ```json-menu. Keep `day_of_steps` and `prep_steps` concise (short imperative phrases) so the whole response fits.

### SECTION 1: MENU JSON
Output a ```json-menu block. Schema (FOLLOW EXACTLY):

```json-menu
[
  {{
    "day": "Monday",
    "date": "{week_dates['Monday']}",
    "meals": [
      {{
        "slot": "breakfast",
        "name": "Meal name",
        "time": "07:30",
        "prep_ahead": true,
        "cook_minutes_day_of": 3,
        "image_prompt": "overhead food photo of greek yogurt bowl with mixed berries and granola, natural light, on a wooden table, appetising",
        "video_url": "",
        "prep_steps": ["What to batch-cook or pre-portion on Sunday for this meal (empty list if nothing)"],
        "day_of_steps": ["Detailed step-by-step done on the day, e.g. 'Spoon 200g yogurt into a bowl', 'Top with 100g berries', 'Sprinkle granola'"],
        "storage_ref": "prep_batch_1",
        "food_category": "dairy",
        "portions": {{
          "diego": {{
            "ingredients": [{{"item": "Greek yogurt", "qty": "200 g"}}, {{"item": "Mixed berries", "qty": "100 g"}}],
            "macros": {{"kcal": 380, "protein_g": 28, "carbs_g": 40, "fat_g": 12, "fiber_g": 4}}
          }},
          "diana": {{
            "ingredients": [{{"item": "Greek yogurt", "qty": "150 g"}}, {{"item": "Mixed berries", "qty": "80 g"}}],
            "macros": {{"kcal": 300, "protein_g": 22, "carbs_g": 32, "fat_g": 9, "fiber_g": 3}}
          }}
        }}
      }}
    ],
    "day_totals": {{
      "diego": {{"kcal": {diego_kcal}, "protein_g": 0, "carbs_g": 0, "fat_g": 0}},
      "diana": {{"kcal": {diana_kcal}, "protein_g": 0, "carbs_g": 0, "fat_g": 0}}
    }}
  }}
]
```

### SECTION 2: SHOPPING JSON
Output a ```json-shopping block. Pre-aggregate ALL ingredients for BOTH members across ALL 7 days. Each item = total household quantity needed for the week. Include French name.

```json-shopping
[
  {{"name_en": "Chicken breast", "name_fr": "Blanc de poulet", "qty": "2.0 kg", "food_category": "poultry"}}
]
```

### SECTION 3: PREP JSON
Output a ```json-prep block. List Sunday batch steps in logical cooking order (grains first, then proteins, then veg).
`day_of_assembly` rules (IMPORTANT — this is shown to the user as a daily checklist, so it must not look repetitive):
  - Only include the days on which this batch is ACTUALLY used. Do NOT list a day if the batch isn't part of that day's meals.
  - Each day's text MUST describe assembling that day's SPECIFIC named dish from the menu above (start with the slot + dish name, e.g. "Lunch — Mediterranean Chicken Bowl: …"). NEVER write the same instruction for two different days; identical "reheat X, reheat Y" lines repeated daily are forbidden.
  - If a batch component is reused on multiple days, each day must recombine it differently (different sauce, veg, format) to match that day's distinct dish name.

```json-prep
[
  {{
    "id": "prep_batch_1",
    "title": "Batch title",
    "order": 1,
    "active_minutes": 20,
    "steps": ["Detailed numbered step 1", "Step 2", "Step 3"],
    "yields": ["What is produced — quantity"],
    "food_category": "poultry",
    "video_url": "",
    "day_of_assembly": {{
      "Monday": "Lunch — Lemon Chicken Quinoa Bowl: reheat 150g chicken + quinoa, add roasted veg & lemon",
      "Wednesday": "Lunch — Chicken Caesar Wrap: slice cold chicken into a wholegrain wrap with romaine & yogurt dressing"
    }}
  }}
]
```
Keep each prep batch's `video_url` as "" (empty). Make `steps` detailed and beginner-friendly.

Generate all 7 days. Be specific and realistic. Verify that each person's `day_totals` sum to within ±10% of their kcal target.
"""

print("Stage 2: building the week from the locked palette...")
# (client created in Stage 1 above is reused here)
# A full week (35 meals × 2 portions + shopping + prep) is a large structured
# output — give it plenty of room and stream so the request can't time out.
_DEBUG["phase"] = "calling Claude API"
stop_reason = None
with client.messages.stream(
    # TEMPORARY (testing): cheapest model to keep token spend low while we iterate.
    # Switch back to "claude-sonnet-4-6" for launch — it produces richer menus.
    model="claude-haiku-4-5-20251001",
    max_tokens=32000,
    messages=[{"role": "user", "content": prompt}],
) as stream:
    for _ in stream.text_stream:
        pass
    final = stream.get_final_message()
# Join every text block (don't assume content[0])
response = "".join(b.text for b in final.content if getattr(b, "type", None) == "text")
stop_reason = final.stop_reason
_DEBUG["response"] = response
_DEBUG["stop_reason"] = stop_reason
_DEBUG["phase"] = "parsing response"
print(f"Plan received from Claude (stop_reason={stop_reason}, {len(response)} chars).")
if stop_reason == "max_tokens":
    print("WARNING: response hit the max_tokens limit and may be truncated — "
          "parsing what arrived and salvaging incomplete blocks.")

# ── Parse the three JSON blocks ───────────────────────────────────────────────
def extract_block(text: str, label: str) -> str | None:
    """Extract a ```{label} … ``` block. Tolerates a missing closing fence
    (truncated output) by taking everything up to the next ``` or end-of-text."""
    closed = re.search(rf"```{re.escape(label)}\s*(.*?)```", text, re.DOTALL)
    if closed:
        return closed.group(1).strip()
    # No closing fence — block was cut off mid-stream. Grab to next fence / EOF.
    open_m = re.search(rf"```{re.escape(label)}\s*(.*)", text, re.DOTALL)
    if open_m:
        tail = open_m.group(1)
        tail = re.split(r"```", tail)[0]
        return tail.strip()
    return None


def salvage_json_array(raw: str):
    """Parse a JSON array, repairing a truncated tail by trimming back to the
    last complete top-level element and closing the array."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    s = raw.strip()
    if not s.startswith("["):
        return None
    depth = 0; in_str = False; esc = False; last_good = None
    for i, ch in enumerate(s):
        if esc:
            esc = False; continue
        if ch == "\\":
            esc = True; continue
        if ch == '"':
            in_str = not in_str; continue
        if in_str:
            continue
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 1 and ch == "}":   # just closed a top-level element
                last_good = i
    if last_good is None:
        return None
    try:
        return json.loads(s[:last_good + 1] + "]")
    except json.JSONDecodeError:
        return None


menu_json: list = []
shopping_json: list = []
prep_json: list = []
errors = []

for label, name in [
    ("json-menu", "menu"),
    ("json-shopping", "shopping"),
    ("json-prep", "prep"),
]:
    raw_block = extract_block(response, label)
    if not raw_block:
        errors.append(f"Missing ```{label} block in response.")
        continue
    parsed = salvage_json_array(raw_block)
    if parsed is None:
        errors.append(f"JSON parse error in {label} (unrecoverable).")
        continue
    if label == "json-menu":
        menu_json = parsed
    elif label == "json-shopping":
        shopping_json = parsed
    else:
        prep_json = parsed
    print(f"Parsed {name}: {len(parsed)} items.")

if not menu_json:
    print("=" * 70)
    print("ERROR: No menu generated.")
    for e in errors:
        print("  " + e)
    print("RESPONSE (first 3000 chars):")
    print(response[:3000])
    _write_error("NutriPrep plan generation FAILED: no usable menu JSON parsed.",
                 "Parse errors:\n" + "\n".join(errors))
    sys.exit("Plan generation failed.")

# Enforce correct dates (LLM drifts: wrong/missing dates, day-name casing, extra days)
_week_by_lc = {name.lower(): iso for name, iso in week_dates.items()}
for i, day_data in enumerate(menu_json):
    day_label = str(day_data.get("day", "")).strip()
    iso = _week_by_lc.get(day_label.lower())
    if iso is None and i < len(DAY_NAMES):
        # Fall back to position in the week and normalise the day name too.
        iso = week_dates[DAY_NAMES[i]]
        day_data["day"] = DAY_NAMES[i]
    if iso:
        day_data["date"] = iso
    # Attach the day's training session (for Diego) so the app can show fuelling
    t = training_week.get(day_data.get("date"))
    if t:
        day_data["training"] = {"member": ATHLETE_MEMBER, **t}

# ── Allergen safety check ─────────────────────────────────────────────────────
allergen_list = [a.lower() for a in allergens]
for item in shopping_json:
    name_en_lower = item.get("name_en", "").lower()
    for allergen in allergen_list:
        if allergen in name_en_lower:
            msg = f"SAFETY VIOLATION: allergen '{allergen}' found in shopping list item '{item['name_en']}'! Aborting."
            _write_error("NutriPrep plan generation FAILED: allergen safety check.", msg)
            sys.exit(msg)

print("Allergen check passed.")

# ── Post-process shopping list (enrich + inventory-aware) ────────────────────
from lux_products import enrich_item
import units

for item in shopping_json:
    enrich_item(item)

# Load current fridge/pantry inventory to avoid buying what we already have.
inventory = {"items": []}
if (BASE / "inventory.json").exists():
    with open(BASE / "inventory.json") as f:
        inventory = json.load(f)
inv_index = {it["name_en"].strip().lower(): it for it in inventory.get("items", [])}

# ── Price book (load early: needed for net-weight packaging + pricing) ─────────
# generate.py both READS the price book (net weight, store, price) and TOPS IT UP
# with a stub for any new product, without clobbering values the household set.
import math
price_book = {"products": {}}
if (BASE / "price_book.json").exists():
    try:
        with open(BASE / "price_book.json") as f:
            price_book = json.load(f)
    except Exception:
        price_book = {"products": {}}
products = price_book.setdefault("products", {})


def _default_price_unit(kind):
    return {"mass": "kg", "volume": "L"}.get(kind, "item")


def _net_of(name_key):
    """Parsed package size for a product, or None. Only valid if it has a usable amount."""
    nw = (products.get(name_key) or {}).get("net_weight")
    if not nw:
        return None
    q = units.parse_qty(nw)
    return q if (q.get("kind") != "unknown" and q.get("amount")) else None


def _package_price(price_eur, price_unit, net):
    """Price of ONE package, from the unit price + package size."""
    if price_eur is None or not net:
        return None
    if net["kind"] == "mass" and price_unit == "kg":
        return price_eur * net["amount"] / 1000.0
    if net["kind"] == "volume" and price_unit == "L":
        return price_eur * net["amount"] / 1000.0
    if net["kind"] == "count" and price_unit == "item":
        return price_eur * net["amount"]
    if price_unit == "item":
        return price_eur  # price entered as per-package/jar
    return None


def _line_cost(qty_str, price_eur, price_unit, have_at_home=False):
    """Cost of buying qty_str at price_eur per price_unit. None if not computable."""
    if have_at_home:
        return 0.0
    if price_eur is None:
        return None
    q = units.parse_qty(qty_str or "")
    kind, amt = q.get("kind"), q.get("amount")
    if kind == "mass" and price_unit == "kg":
        return round(price_eur * (amt or 0) / 1000.0, 2)      # parse_qty mass → grams
    if kind == "volume" and price_unit == "L":
        return round(price_eur * (amt or 0) / 1000.0, 2)      # parse_qty volume → ml
    if kind == "count" and price_unit == "item":
        return round(price_eur * (amt or 0), 2)
    if kind == "unknown" and price_unit == "item":
        return round(price_eur * (amt or 1), 2)
    return None  # unit/kind mismatch — leave unpriced

# For each item: required = what the week needs; have = pantry. Packaged staples
# (with a net_weight) are bought in WHOLE packages and the fridge is depleted by
# the week's consumption, so we only re-buy when a pack runs out. Everything else
# keeps the simple top-up-to-required behaviour.
new_inventory_items = []
for item in shopping_json:
    name_key = item.get("name_en", "").strip().lower()
    required = units.parse_qty(item.get("qty", ""))
    have_item = inv_index.get(name_key)
    have = None
    if have_item:
        have = {"amount": have_item.get("amount"), "kind": have_item.get("kind", "unknown"), "unit": have_item.get("unit", "")}
    have_amt = have["amount"] if (have and have.get("kind") == required["kind"] and have.get("amount") is not None) else 0.0
    net = _net_of(name_key)

    if net and required["kind"] != "unknown" and net["kind"] == required["kind"]:
        # Packaged staple: buy whole packs to cover the shortfall, then deplete the
        # fridge by this week's consumption so we re-buy only when a pack runs out.
        shortfall = max(0.0, (required["amount"] or 0) - have_amt)
        packs = 0 if shortfall <= 0.001 else math.ceil(shortfall / net["amount"])
        bought = packs * net["amount"]
        new_balance = max(0.0, have_amt + bought - (required["amount"] or 0))
        item["packages"] = packs
        item["net_weight"] = units.format_qty(net["amount"], net["kind"], net["unit"])
        if packs == 0:
            item["have_at_home"] = True
            item["qty"] = "✓ in pantry"
        else:
            item["have_at_home"] = False
            item["qty"] = f"{packs} × {item['net_weight']}"
        kind, unit = required["kind"], required["unit"]
    elif required["kind"] != "unknown" and have and have["kind"] == required["kind"] and have.get("unit") == required.get("unit"):
        to_buy_amt = max(0.0, (required["amount"] or 0) - (have["amount"] or 0))
        new_balance = max(required["amount"] or 0, have["amount"] or 0)
        if to_buy_amt <= 0.001:
            item["have_at_home"] = True
            item["qty"] = "✓ in pantry"
        else:
            item["have_at_home"] = False
            item["qty"] = units.format_qty(to_buy_amt, required["kind"], required["unit"])
        kind, unit = required["kind"], required["unit"]
    else:
        # No usable pantry match — buy the full required amount.
        item["have_at_home"] = False
        if required["kind"] != "unknown":
            new_balance = required["amount"] or 0
            kind, unit = required["kind"], required["unit"]
        else:
            new_balance, kind, unit = None, "unknown", required.get("unit", "")

    new_inventory_items.append({
        "name_en": item.get("name_en", ""),
        "name_fr": item.get("name_fr", ""),
        "aisle": item.get("aisle", ""),
        "stores": item.get("stores", []),
        "food_category": item.get("food_category", "generic"),
        "kind": kind,
        "unit": unit,
        "amount": round(new_balance, 2) if isinstance(new_balance, (int, float)) else None,
        "display_qty": units.format_qty(new_balance, kind, unit) if isinstance(new_balance, (int, float)) else item.get("qty", ""),
    })

# Tag long-shelf-life pantry staples (rice, pasta, spices, oils, sauces, canned, nuts…)
# so the app can separate them from the weekly-fresh shop. Classification is NAME-driven
# (the model's food_category tags proved unreliable): a clearly shelf-stable form wins,
# then a clearly perishable name forces fresh, then keyword/aisle fallbacks.
_HARD_STAPLE_KW = ("canned", "tinned", "jarred", "dried", "passata", "tomato paste",
                   "stock cube", "bouillon", "powder", "flour", "cornflour", "cornstarch",
                   "baking soda", "baking powder", "breadcrumb", "frozen", "oil", "huile",
                   "vinegar", "vinaigre", "soy sauce", "honey", "miel", "maple", "tahini")
_STAPLE_NAME_KW = ("rice", "riz", "pasta", "pâtes", "pates", "spaghetti", "penne", "couscous",
                   "quinoa", "barley", "orge", "farro", "bulgur", "noodle", "nouille", "oat",
                   "avoine", "cumin", "paprika", "oregano", "origan", "cinnamon", "cannelle",
                   "turmeric", "curcuma", "curry", "chilli", "chili", "coriander seed", "thyme",
                   "thym", "rosemary", "romarin", "bay leaf", "laurier", "sesame", "sésame",
                   "mustard", "moutarde", "soy", "soja", "coconut milk", "lait de coco",
                   "peanut butter", "walnut", "almond", "amande", "cashew", "pecan", "hazelnut",
                   "pistachio", "pistache", "noisette", "seeds", "graines", "lentil", "lentille",
                   "chickpea", "pois chiche",
                   "stock", "herbes de provence", "nut")
_STAPLE_AISLE_KW = ("spice", "épice", "epice", "condiment", "grain", "pasta", "épicerie",
                    "epicerie", "baking", "international", "asie", "moyen", "pantry", "dry good")
# Clearly perishable names → always the weekly-fresh shop (unless a HARD staple form above).
_PERISHABLE_NAME_KW = ("cheese", "fromage", "yogurt", "yaourt", "yoghurt", "milk", "lait frais",
                       "cream", "crème", "butter", "beurre", "egg", "oeuf", "œuf", "fillet",
                       "filet", "steak", "breast", "thigh", "mince", "ground beef",
                       "ground turkey", "ground chicken", "salmon", "tuna", "cod", "hake",
                       "chicken", "beef", "pork", "turkey", "prawn", "shrimp", "bread",
                       "baguette", "lettuce", "spinach", "fresh ", "frais", "fraîche")


def _is_staple(it):
    name = ((it.get("name_en") or "") + " " + (it.get("name_fr") or "")).lower()
    if any(k in name for k in _HARD_STAPLE_KW):
        return True               # canned/dried/oil/vinegar… shelf-stable regardless of category
    if any(k in name for k in _PERISHABLE_NAME_KW):
        return False              # fresh meat/fish/dairy/bread/leafy → weekly-fresh
    if (it.get("food_category") or "").lower() in _STAPLE_CATS:
        return True
    if any(k in name for k in _STAPLE_NAME_KW):
        return True
    aisle = (it.get("aisle") or "").lower()
    return any(k in aisle for k in _STAPLE_AISLE_KW)


_STAPLE_CATS = {"rice", "grains_pasta", "legumes"}


for _it in shopping_json:
    _it["staple"] = _is_staple(_it)

shopping_sorted = sorted(shopping_json, key=lambda x: x.get("aisle", "zzz"))

est_by_supermarket = {}
total_known = 0.0
unpriced = 0
for item in shopping_sorted:
    key = item.get("name_en", "").strip().lower()
    q = units.parse_qty(item.get("qty", ""))
    entry = products.get(key)
    if entry is None:
        entry = {
            "name_en": item.get("name_en", ""),
            "name_fr": item.get("name_fr", ""),
            "aisle": item.get("aisle", ""),
            "supermarket": (item.get("stores") or [None])[0],
            "price_eur": None,
            "price_unit": _default_price_unit(q.get("kind")),
            "net_weight": None,
            "updated": today.isoformat(),
        }
        products[key] = entry
    else:
        # Refresh metadata only; never overwrite a user-set price/supermarket/net weight.
        if item.get("name_fr"):
            entry["name_fr"] = item.get("name_fr")
        if item.get("aisle"):
            entry["aisle"] = item.get("aisle")
        entry.setdefault("price_unit", _default_price_unit(q.get("kind")))
        entry.setdefault("supermarket", (item.get("stores") or [None])[0])
        entry.setdefault("price_eur", None)
        entry.setdefault("net_weight", None)

    sm = entry.get("supermarket")
    price = entry.get("price_eur")
    punit = entry.get("price_unit") or _default_price_unit(q.get("kind"))
    if "packages" in item:
        # Packaged staple: cost = whole packs bought × price of one pack.
        pp = _package_price(price, punit, _net_of(key))
        if item.get("have_at_home"):
            cost = 0.0
        elif pp is not None:
            cost = round(item["packages"] * pp, 2)
        else:
            cost = None
    else:
        cost = _line_cost(item.get("qty", ""), price, punit, item.get("have_at_home"))
    item["supermarket"] = sm
    item["unit_price_eur"] = price
    item["price_unit"] = punit
    item["line_cost_eur"] = cost

    if item.get("have_at_home"):
        continue
    if cost is None:
        unpriced += 1
    else:
        total_known += cost
        if sm:
            est_by_supermarket[sm] = round(est_by_supermarket.get(sm, 0.0) + cost, 2)

priced_total = round(total_known)
# Fall back to the old heuristic only while nothing has been priced yet.
est_total_eur = priced_total if priced_total > 0 else round(budget * 0.85)
price_book["updated"] = today.isoformat()

shopping_out = {
    "week_of": next_monday.isoformat(),
    "currency": "EUR",
    "est_total_eur": est_total_eur,
    "est_by_supermarket": est_by_supermarket,
    "unpriced_count": unpriced,
    "budget_eur": budget,
    "items": shopping_sorted,
}

# The pantry/fridge reflects what the household has ACTUALLY bought — it is never
# auto-seeded from the plan. Generation leaves inventory.json untouched; the pantry
# only changes when the user marks shopping items as bought, deletes items by hand,
# or the daily depletion cron runs. (`new_inventory_items` above is unused now but the
# shopping loop still uses the real pantry to avoid re-buying what's genuinely on hand.)

# ── Post-process prep plan (food safety) ─────────────────────────────────────
from food_safety import validate_prep_plan, enforce_food_safety

prep_json = validate_prep_plan(prep_json)

# Deterministic safety net: flip any Sunday-batched perishable eaten past its fridge
# window to "cook fresh on the day". Prep happens the Sunday before the Mon–Sun week.
prep_date = next_monday - timedelta(days=1)
_safety = enforce_food_safety(menu_json, prep_json, prep_date, week_dates)
if _safety["meals_fixed"] or _safety["assembly_fixed"]:
    print(f"⚠ Food safety: flipped {_safety['meals_fixed']} meal(s) to cook-fresh, "
          f"fixed {_safety['assembly_fixed']} assembly note(s).")
    for d in _safety["details"]:
        print(f"    • {d}")

prep_total_min = sum(b.get("active_minutes", 0) for b in prep_json)

prep_out = {
    "week_of": next_monday.isoformat(),
    "prep_day": schedule.get("prep_day", "Sunday"),
    "prep_start_time": schedule.get("prep_start_time", "15:00"),
    "total_active_minutes": prep_total_min,
    "batches": prep_json,
}

# ── Compute notification schedule ─────────────────────────────────────────────
def to_lux_dt(day_date: date, time_str: str) -> str:
    h, m = map(int, time_str.split(":"))
    return datetime(day_date.year, day_date.month, day_date.day, h, m, tzinfo=LUX).isoformat()


events: list[dict] = []
for day_data in menu_json:
    try:
        day_date = date.fromisoformat(str(day_data.get("date", "")))
    except ValueError:
        print(f"  ! Skipping notifications for a day with an invalid date: {day_data.get('date')!r}")
        continue
    day_name = day_data.get("day", "")

    # Sunday: weigh-in + prep reminders
    if day_name == "Sunday":
        events.append({
            "id": f"weighin-{day_date.isoformat()}",
            "type": "weigh_in",
            "audience": MEMBERS,
            "at": to_lux_dt(day_date, "08:00"),
            "title": "Sunday weigh-in ⚖️",
            "body": "Log your weight to track your progress this week.",
            "sent": False,
        })
        prep_start = schedule.get("prep_start_time", "15:00")
        events.append({
            "id": f"prep-{day_date.isoformat()}",
            "type": "prep",
            "audience": MEMBERS,
            "at": to_lux_dt(day_date, prep_start),
            "title": "Meal prep time 🥗",
            "body": f"~{prep_total_min // 60}h{prep_total_min % 60:02d} of prep sets up your whole week. Tap for the steps.",
            "sent": False,
        })

    for meal in day_data.get("meals", []):
        slot = meal.get("slot")
        if not slot:
            continue
        meal_name = meal.get("name", "Your meal")
        meal_time = meal.get("time") or meal_times.get(slot)
        if not meal_time:
            continue

        if slot in ("am_snack", "pm_snack"):
            emoji = "🍎" if slot == "am_snack" else "🥜"
            events.append({
                "id": f"snack-{day_date.isoformat()}-{slot}",
                "type": "snack",
                "audience": MEMBERS,
                "at": to_lux_dt(day_date, meal_time),
                "title": f"Snack time {emoji}",
                "body": f"{meal_name} — keeps you on track toward your goal.",
                "sent": False,
            })
        elif slot in ("lunch", "dinner") and meal.get("cook_minutes_day_of", 0) > 0:
            cook_min = meal["cook_minutes_day_of"]
            meal_dt = datetime.fromisoformat(to_lux_dt(day_date, meal_time))
            reminder_dt = meal_dt - timedelta(minutes=cook_min + 5)
            events.append({
                "id": f"cook-{day_date.isoformat()}-{slot}",
                "type": "cook",
                "audience": MEMBERS,
                "at": reminder_dt.isoformat(),
                "title": f"Start {'dinner' if slot == 'dinner' else 'lunch'} soon 🍳",
                "body": f"{meal_name} — {cook_min} min. Tap for recipe.",
                "sent": False,
            })

# Sort events chronologically
events.sort(key=lambda e: e["at"])
notif_out = {"tz": "Europe/Luxembourg", "events": events}

# ── Build the Markdown menu deterministically from the parsed JSON ────────────
SLOT_EMOJI = {"breakfast": "☀️", "am_snack": "🍎", "lunch": "🥗", "pm_snack": "🥜", "dinner": "🍽️"}


def build_menu_md() -> str:
    lines = []
    for day in menu_json:
        lines.append(f"## {day.get('day','')} — {day.get('date','')}")
        for meal in day.get("meals", []):
            em = SLOT_EMOJI.get(meal.get("slot", ""), "•")
            dg = ((meal.get("portions") or {}).get("diego") or {}).get("macros", {})
            dn = ((meal.get("portions") or {}).get("diana") or {}).get("macros", {})
            lines.append(
                f"- {em} **{meal.get('name','')}** ({meal.get('time','')}) — "
                f"Diego {dg.get('kcal','?')} kcal · Diana {dn.get('kcal','?')} kcal"
            )
        tot = day.get("day_totals", {})
        td, tn = tot.get("diego", {}), tot.get("diana", {})
        lines.append(f"  - **Day totals** — Diego {td.get('kcal','?')} kcal, Diana {tn.get('kcal','?')} kcal")
        lines.append("")
    return "\n".join(lines)


# ── Write all output files ────────────────────────────────────────────────────
with open(BASE / "weekly_menu.md", "w") as f:
    f.write(f"# Meal Plan — Week of {next_monday.strftime('%d %B %Y')}\n\n")
    f.write(f"**Generated:** {today.strftime('%d %B %Y')}  \n")
    f.write(f"**Diego:** {users['diego'].get('macro_targets', {}).get('kcal','?')} kcal/day  \n")
    f.write(f"**Diana:** {users['diana'].get('macro_targets', {}).get('kcal','?')} kcal/day  \n\n---\n\n")
    f.write(build_menu_md())

with open(BASE / "weekly_menu.json", "w") as f:
    json.dump(menu_json, f, indent=2)

with open(BASE / "shopping_list.json", "w") as f:
    json.dump(shopping_out, f, indent=2)

with open(BASE / "price_book.json", "w") as f:
    json.dump(price_book, f, indent=2, ensure_ascii=False)

with open(BASE / "prep_plan.json", "w") as f:
    json.dump(prep_out, f, indent=2)

with open(BASE / "notif_schedule.json", "w") as f:
    json.dump(notif_out, f, indent=2)

# ── Update plan status ────────────────────────────────────────────────────────
plan_status = {
    "status": "published",
    "generated": today.isoformat(),
    "week_of": next_monday.isoformat(),
    "meal_count": sum(len(d.get("meals", [])) for d in menu_json),
    "shopping_items": len(shopping_sorted),
    "prep_batches": len(prep_json),
    "prep_minutes": prep_total_min,
    "notification_events": len(events),
    "fresh_shop_items": sum(1 for it in shopping_sorted if not it.get("staple")),
    "pantry_staple_items": sum(1 for it in shopping_sorted if it.get("staple")),
    "locked_palette": palette or None,
}
with open(BASE / "plan_status.json", "w") as f:
    json.dump(plan_status, f, indent=2)

# ── Archive to menu history ───────────────────────────────────────────────────
all_meal_names = []
for day_data in menu_json:
    for meal in day_data.get("meals", []):
        if meal.get("slot") not in ("am_snack", "pm_snack"):
            all_meal_names.append(meal.get("name", ""))

snapshot = {
    "week_of": next_monday.isoformat(),
    "generated": today.isoformat(),
    "meal_names": all_meal_names[:10],
    "shopping_items": len(shopping_sorted),
    "prep_minutes": prep_total_min,
    "day_kcal": {
        m: round(sum(
            d["day_totals"].get(m, {}).get("kcal", 0) for d in menu_json if d.get("day_totals")
        ) / max(1, len(menu_json)))
        for m in MEMBERS
    },
}
menu_history.append(snapshot)
menu_history = menu_history[-12:]
with open(BASE / "menu_history.json", "w") as f:
    json.dump(menu_history, f, indent=2)

print("\n" + "=" * 60)
print(f"✓ Weekly menu: {len(menu_json)} days")
print(f"✓ Shopping list: {len(shopping_sorted)} items")
print(f"✓ Prep plan: {len(prep_json)} batches, ~{prep_total_min} min active")
print(f"✓ Notifications: {len(events)} events scheduled")
print(f"✓ Plan saved for week of {next_monday}")

# Success — remove any stale diagnostic logs so they don't linger in the repo.
for _f in (ERROR_LOG, BASE / "_run.log"):
    try:
        if _f.exists():
            _f.unlink()
    except Exception:
        pass
if errors:
    print("\nNon-fatal warnings:")
    for e in errors:
        print("  ⚠", e)
