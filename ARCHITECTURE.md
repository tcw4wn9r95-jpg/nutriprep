# Mindful Eating App — Architecture Plan ("NutriPrep")

> Working name: **NutriPrep** · in-app coach: **Coach Léa** (both easily renamed).
> Built as a sibling of the existing **AthleteIQ** app, reusing its proven, zero-backend pattern.
>
> Status: **approved architecture, ready to build.** This is the design doc; implementation follows the
> MVP-first sequence at the bottom.

## Context

A **two-person household in Luxembourg — Diego and Diana** — wants a mindful-eating companion. It takes a
**nutritionist's meal plan** as input, asks about **weight goals, food preferences and allergies**,
then every **Sunday** produces: a **weekly menu** (with mid-morning and afternoon healthy snacks), a
**shopping list** (English + French, only products available in Luxembourg), and a **meal-prep plan**
that minimises day-of cooking while respecting **food-safety storage guidelines**. A **food coach**
builds the plans weekly, answers questions and makes changes on request. **Notifications** tell the
user when to meal-prep, when to start cooking, and when to take a snack. All recommendations use
**scientifically proven** nutrition knowledge.

**Two users, shared kitchen:** Diego and Diana eat the same dishes (one shared menu, shopping list and
prep plan for the household), but have **different macro/calorie requirements — handled purely as portion
differences** of the same meals. Each installs the PWA on their **own phone**, picks their identity, and
gets **their own weight tracking, their own goals, and their own private conversations with the coach**.
**Weekly weight is entered manually** by each user (a weigh-in, typically Sunday) and drives that person's
progress view and informs their coach. Allergies are enforced as the **union** of both users (never serve
an allergen either person has).

We already own a battle-tested architecture in this repo: **AthleteIQ** (`sync.py`, `dashboard.html`,
GitHub Actions cron, Claude API, JSON files committed to git, vanilla-JS PWA on GitHub Pages, web
push via `pywebpush`). The nutrition app maps almost 1:1 onto it. **Decision: clone the pattern into a
new `nutrition/` subfolder** rather than reinvent anything. This keeps cost ~a few $/month, needs no
servers, and lets us ship an MVP fast then layer on coach + notifications.

**Build target:** full architecture, **MVP-first** (working onboarding → menu → shopping → prep end-to-end
before coach/notifications).

## Reused AthleteIQ patterns (do not reinvent — copy & adapt)

| Concern | AthleteIQ source to copy | Adapt to |
|---|---|---|
| Weekly Claude generation + JSON/MD split parsing | `sync.py` (lines 374–625: prompt build, `messages.create`, ` ```json ` parse, date enforcement, fallback) | `nutrition/generate.py` |
| Multi-week memory + subjective check-ins | `sync.py` (lines 29–86 history; 38–72 check-ins) | `menu_history.json`, `checkins.json` |
| "Skip if plan already exists this week / FORCE override" | `sync.py` lines 323–341 | same guard in `generate.py` |
| Web push send + expired-sub cleanup | `notify.py` (`webpush`, VAPID temp-pem, 404/410 prune) | `nutrition/notify.py` |
| Cron + commit-back workflow | `.github/workflows/generate_plan.yml`, `notify.yml` | `nutrition_*.yml` |
| PWA shell, tabs, GitHub-API read/write, in-browser Claude coach with `tool_use`, service-worker push, subscribe flow | `dashboard.html`, `sw.js`, `manifest.json` | `nutrition/dashboard.html` etc. |
| Secrets | `ANTHROPIC_API_KEY`, `VAPID_PRIVATE_KEY` already configured | reuse same secrets |

Models (mirror AthleteIQ): **`claude-sonnet-4-6`** for plan generation + vision plan-parsing (deeper
reasoning, image input); **`claude-haiku-4-5-20251001`** for in-browser Coach chat (fast/cheap).

## Folder layout

```
nutrition/
  generate.py            # Sunday engine: menu → shopping list → prep plan → notif schedule  (← sync.py analog)
  parse_plan.py          # Claude vision: nutritionist photo/PDF → nutrition_plan.json
  notify.py              # web push; fires prep/cook/snack reminders due in the current window
  food_safety.py         # deterministic, evidence-based storage/shelf-life/reheat rules
  lux_products.py        # EN→FR translations + Luxembourg availability (Cactus/Auchan/Delhaize/Aldi/Lidl/Match)
  requirements.txt       # anthropic>=0.40.0, pywebpush>=2.0.0, pdf2image/pypdf (PDF→image), tzdata
  dashboard.html         # PWA (Today / Menu / Shopping / Prep / Coach / Settings)
  sw.js  manifest.json  icon-192.png icon-512.png apple-touch-icon.png
  # ---- committed JSON data (the "database") ----
  # SHARED / household-level (one menu, one kitchen):
  household.json         # members list, kitchen equipment, cooking skill, budget, tz=Europe/Luxembourg,
                         #   shared cuisines, ALLERGY UNION + combined dislikes
  schedule.json          # prep day/time, per-day meal times, eat-out days (shared meals)
  nutrition_plan.json    # parsed nutritionist plan — may carry PER-MEMBER daily targets
  weekly_menu.json / .md # 7 days × 5 slots; each meal carries PER-MEMBER portions + macros
  shopping_list.json     # household totals (= sum of both members' portions), EN+FR, qty, aisle, store
  prep_plan.json / .md   # Sunday batch steps (ordered) + storage/shelf-life per cooked item (household)
  notif_schedule.json    # prep/cook/snack/weigh-in datetimes this week
  menu_history.json      # last ~12 weeks (continuity + variety)
  plan_status.json       # {status, generated, week_of}
  # PER-USER (one folder each; same shape):
  users/
    diego/  profile.json  goals.json  macro_targets.json  weight_log.json
            checkins.json  coach_history.json  push_subscriptions.json
    diana/  …same files…
.github/workflows/
  nutrition_generate.yml # cron: Sun 18:00 UTC (≈ Sun 19/20:00 Luxembourg) + manual
  nutrition_parse.yml    # manual/dispatch: parse a freshly uploaded plan image
  nutrition_notify.yml   # cron: every 15 min, fires due reminders
```

## Data model (key schemas)

```jsonc
// household.json  (shared)
{ "members": ["diego","diana"],
  "allergies": ["peanuts","shellfish"],              // UNION of both members — never appear in any menu
  "intolerances": ["lactose"], "dislikes": ["liver","cilantro"],   // combined
  "diet_style": "omnivore",                          // omnivore|vegetarian|vegan|pescatarian|...
  "cuisines_loved": ["mediterranean","japanese"], "spice_tolerance": "medium",
  "budget_eur_per_week": 140, "cooking_skill": "intermediate", "tz": "Europe/Luxembourg",
  "max_prep_minutes_sunday": 150, "max_cook_minutes_weekday": 20 }

// users/diego/goals.json  (per user — Diana has her own with different numbers)
{ "name": "Diego", "goal_type": "weight_loss",       // weight_loss|maintain|muscle_gain|recomp
  "start_weight_kg": 82, "target_weight_kg": 76, "target_rate_kg_per_week": 0.5,
  "target_date": "2026-09-01", "notes": "sustainable, no crash diets", "set_on": "2026-05-31" }

// users/diego/macro_targets.json  (per user — drives that person's portion sizing)
{ "kcal": 1900, "protein_g": 140, "carbs_g": 180, "fat_g": 60, "fiber_g": 30,
  "source": "nutritionist" }                          // or "derived" if computed from goals

// users/diego/weight_log.json  (per user — MANUAL weekly weigh-ins)
[ { "date": "2026-05-25", "weight_kg": 82.3 },
  { "date": "2026-06-01", "weight_kg": 81.6 } ]       // app shows trend vs target; coach reads this

// nutrition_plan.json  (shared; produced by parse_plan.py from the nutritionist's photo/PDF)
{ "source": "nutritionist_upload", "parsed_on": "2026-05-31", "confidence": 0.9,
  "per_member_targets": {                             // plan may specify each person separately
    "diego": { "kcal": 1900, "protein_g": 140, "carbs_g": 180, "fat_g": 60, "fiber_g": 30 },
    "diana": { "kcal": 1550, "protein_g": 110, "carbs_g": 150, "fat_g": 50, "fiber_g": 28 } },
  "meal_structure": ["breakfast","am_snack","lunch","pm_snack","dinner"],
  "prescribed_foods": ["oily fish 2x/week","legumes daily"],
  "restricted_foods": ["added sugar","ultra-processed snacks","alcohol weekdays"],
  "hydration_l": 2.0, "nutritionist_notes": "..." }    // parse_plan.py fans each member's targets into users/<m>/macro_targets.json

// weekly_menu.json  (array of 7 day objects — SAME dishes, PER-MEMBER portions)
[ { "day":"Monday","date":"2026-06-01",
    "meals":[ { "slot":"breakfast","name":"Greek yogurt & berry bowl","time":"07:30",
                "prep_ahead":true,"cook_minutes_day_of":3,"recipe":["..."],"storage_ref":"prep_batch_1",
                "portions":{
                  "diego":{ "ingredients":[{"item":"Greek yogurt","qty":"200 g"}],
                            "macros":{"kcal":380,"protein_g":28,"carbs_g":40,"fat_g":12} },
                  "diana":{ "ingredients":[{"item":"Greek yogurt","qty":"150 g"}],
                            "macros":{"kcal":300,"protein_g":22,"carbs_g":32,"fat_g":9} } } },
              { "slot":"am_snack","name":"Apple + almonds","time":"10:30","portions":{ … } },
              { "slot":"lunch", … }, { "slot":"pm_snack","time":"16:00", … }, { "slot":"dinner", … } ],
    "day_totals":{ "diego":{"kcal":1895,…}, "diana":{"kcal":1548,…} } } ]

// shopping_list.json  (household totals = SUM of both members' portions across the week)
{ "week_of":"2026-06-01", "currency":"EUR", "est_total_eur":132,
  "items":[ { "name_en":"Chicken breast","name_fr":"Blanc de poulet","qty":"2.0 kg",
              "aisle":"Meat / Boucherie","available_in_lux":true,
              "stores":["Cactus","Auchan","Delhaize"],"have_at_home":false } ] }

// prep_plan.json
{ "week_of":"2026-06-01","prep_day":"Sunday","total_active_minutes":135,
  "batches":[ { "id":"prep_batch_1","title":"Cook grains & proteins",
                "order":1,"active_minutes":40,
                "steps":["Roast 1.2 kg chicken breast at 200°C to internal 74°C","Cook 500 g quinoa"],
                "yields":["roast chicken","cooked quinoa"],
                "storage":{ "method":"refrigerate","container":"airtight",
                            "fridge_c":"≤4","cool_within_hours":2,
                            "use_within_days":3,"freeze_option_days":60,
                            "reheat_c":74,"safety_note":"Cool fast; never leave >2h at room temp." } } ],
  "day_of_assembly":{ "Monday":["Reheat chicken+quinoa 2 min, add fresh salad"] } }

// notif_schedule.json  (consumed by notify.py every 15 min). `audience` = which members get it.
{ "tz":"Europe/Luxembourg",
  "events":[ { "id":"prep-2026-06-01","type":"prep","audience":["diego","diana"],"at":"2026-06-01T15:00:00+02:00",
               "title":"Meal prep time 🥗","body":"~2h15 of prep sets up your whole week. Tap for the steps.","sent":false },
             { "id":"cook-mon","type":"cook","audience":["diego","diana"],"at":"2026-06-02T18:40:00+02:00",
               "title":"Start dinner soon 🍳","body":"Mediterranean bowl — 20 min. Reheat batch 1.","sent":false },
             { "id":"snack-mon-am","type":"snack","audience":["diego","diana"],"at":"2026-06-02T10:30:00+02:00",
               "title":"Mid-morning snack 🍎","body":"Apple + almonds — keeps energy steady toward your goal.","sent":false },
             { "id":"weighin-2026-06-01","type":"weigh_in","audience":["diego","diana"],"at":"2026-06-01T08:00:00+02:00",
               "title":"Sunday weigh-in ⚖️","body":"Log your weight to track progress this week.","sent":false } ] }
```

`users/<m>/profile.json`, `checkins.json`, `coach_history.json`, `push_subscriptions.json`, plus
`schedule.json`, `plan_status.json`, `menu_history.json` mirror the structure/roles of the AthleteIQ
equivalents. `users/<m>/checkins.json`, `coach_history.json` and `push_subscriptions.json` are **per user**
(separate coach memory and devices); the menu/shopping/prep/nutrition_plan are **shared**.

## Component design

### 1. `parse_plan.py` — nutritionist plan ingestion (Claude vision)
- Triggered by `nutrition_parse.yml` (or the Coach) after the user uploads an image/PDF (stored to the
  repo via the dashboard's GitHub-API PUT, base64 — same mechanism AthleteIQ uses for availability/subs).
- PDF → images via `pdf2image`/`pypdf`; send image block(s) to `claude-sonnet-4-6` with a strict prompt:
  "Extract daily calorie & macro targets, meal structure, prescribed and restricted foods, hydration.
  Return JSON only. If a value is absent, set null and lower `confidence`. Do not invent clinical advice."
- Writes shared `nutrition_plan.json` **and fans `per_member_targets` out** into each
  `users/<m>/macro_targets.json`. Low confidence → Coach asks the user to confirm/fill gaps. If the
  uploaded plan covers only one person, the other member's targets are **derived** (Mifflin-St Jeor BMR ×
  activity, adjusted for that user's `goals.json` deficit/surplus) and flagged `"source":"derived"`.

### 2. `generate.py` — the Sunday engine (analog of `sync.py`)
Single Claude (Sonnet) call that returns **Markdown + three labelled JSON blocks** (menu, shopping,
prep), parsed exactly like `sync.py` splits ` ```json ` / ` ```json-block `. Inputs: shared
`nutrition_plan.json` (authority), `household.json` (allergy union = hard blocks, budget, equipment),
`schedule.json`, **both** `users/<m>/macro_targets.json` + `goals.json` + recent `weight_log.json` +
`checkins.json`, and `menu_history.json` (variety/continuity).
Prompt rules:
- **One shared menu, per-person portions.** Design the same dishes for the household, then size each
  meal's `portions.<member>` so every member hits **their own** daily macro/calorie targets. Differences
  are portion/quantity only — not different recipes.
- **Honour the nutritionist's targets** as the source of truth; keep each member's day within macro tolerance.
- **Always** include mid-morning + afternoon **healthy snacks**; respect meal times from `schedule.json`.
- **Allergies (union of both members) are absolute**; never include disliked items; bias to loved cuisines
  and the household weekly budget.
- **Evidence-based only**: align with EFSA Dietary Reference Values / WHO; no fad diets, detoxes, or
  unproven claims; sustainable rate of weight change (≈0.25–0.75 kg/week).
- **Minimise weekday cooking**: design meals so most components are batch-cooked Sunday; mark `prep_ahead`
  and keep `cook_minutes_day_of` under `schedule.json` limits.
- **Luxembourg**: only ingredients realistically available at LU supermarkets; provide French names.
- After Claude returns, `generate.py` post-processes deterministically:
  - **Shopping list**: **sum both members' portion quantities** for every ingredient across the week, then
    enrich via `lux_products.py` (authoritative EN→FR + availability/stores/aisle), aggregate duplicates,
    flag `have_at_home` staples.
  - **Prep plan storage**: overwrite/validate each batch's `storage` block via `food_safety.py`
    (do not trust the LLM for safety-critical numbers).
  - **Notification schedule**: compute `notif_schedule.json` from `schedule.json` meal times,
    `cook_minutes_day_of` (cook reminder = mealtime − cook time − 5 min buffer), snack times, the
    Sunday prep slot, and a **Sunday weigh-in reminder** — all in `Europe/Luxembourg` via `zoneinfo`
    (DST-correct). Meal/prep events target both members (`audience`); weigh-in targets each member.
- Reuse `sync.py`'s "skip if a plan already exists for this `week_of` unless `FORCE_GENERATE`" guard so
  Coach edits are never clobbered; append a snapshot to `menu_history.json` (keep last 12).

### 3. `food_safety.py` — deterministic, cited rules
A lookup module (not LLM) encoding evidence-based guidance, e.g.: refrigerate cooked food within **2 h**
(1 h if ambient >32 °C); fridge **≤4 °C**; most cooked dishes **3–4 days**; cooked rice eat within **1 day**
(*B. cereus*); reheat leftovers to **74 °C / 165 °F**; don't refreeze thawed raw items; freezer extends to
weeks/months by category. Sourced from **USDA FoodKeeper / FDA**, **EFSA**, **ANSES**, EU/Luxembourg food
hygiene guidance — sources listed in a header docstring and surfaced in the Prep tab. `get_storage(food_category)`
returns the `storage` dict embedded into `prep_plan.json`.

### 4. `lux_products.py` — Luxembourg localisation
Curated dict of common ingredients → `{name_fr, aisle, available_in_lux, typical_stores}` for
Cactus, Auchan, Delhaize, Aldi, Lidl, Match, Pall Center; helper to translate/annotate any shopping item
(falls back to the LLM-provided French name when not in the dict). Notes seasonal/local LU produce.

### 5. `notify.py` — reminders (analog of AthleteIQ `notify.py`)
Run every 15 min by `nutrition_notify.yml`. Load `notif_schedule.json`, select events whose `at` is in
`[now−10min, now]` and `sent:false`. For each, `webpush` to the subscriptions of every member in the
event's `audience` (iterating each `users/<m>/push_subscriptions.json`; reuse VAPID temp-pem + 404/410
pruning verbatim), mark `sent:true`, commit. Reminder types: **prep** (Sunday), **cook** (daily,
mealtime-aware), **snack** (am/pm), **weigh_in** (Sunday). > Note: GitHub Actions cron can drift a few
minutes — fine for food reminders; documented as a known limitation with an upgrade path (client-side
scheduled notifications or a tiny always-on worker) if tighter timing is wanted later.

### 6. `dashboard.html` — the PWA (copy AthleteIQ shell)
**Identity:** on first open each phone picks **"I'm Diego" / "I'm Diana"** (stored in `localStorage`);
a switcher lives in Settings. The active identity selects which `users/<m>/…` files are read/written
(macros, weight log, check-ins, coach history, this device's push subscription). Shared tabs (Menu,
Shopping, Prep) are identical for both; personalised tabs (Today macros, Progress, Coach) follow identity.
Tabs:
- **Today** — today's 5 slots with times, the *next action* (prep / start cooking / snack), and **the active
  user's portion + day macro ring** (toggle to peek at partner's portion).
- **Menu** — 7-day plan; tap a meal for recipe, per-person portions, macros, prep-ahead badge.
- **Shopping** — household list grouped by aisle, **EN + FR**, quantities, store chips, checkable, "have at home" toggle.
- **Prep** — Sunday batch steps in order, per-item **storage & shelf-life** card, reheat temps, timers.
- **Progress** — the active user's **manual weekly weigh-in entry** + weight trend chart vs target
  (writes `users/<m>/weight_log.json`; reuses AthleteIQ's Chart.js trend pattern). Each user sees only their own.
- **Coach (Coach Léa)** — in-browser Claude (Haiku) with `tool_use`, **per-user private chat**
  (`users/<m>/coach_history.json`). System prompt includes that user's goals, macro targets and recent
  weight trend, plus the shared menu. Tools: `swap_meal`, `edit_menu` (rewrites shared `weekly_menu.json`
  + regenerates shopping/prep — applies to the household), `log_checkin` (→ `users/<m>/checkins.json`),
  `log_weight` (→ `users/<m>/weight_log.json`), `regenerate_plan`. Either user can request menu changes;
  changes affect the shared plan (with a note in chat that it's household-wide).
- **Settings** — pick/switch identity, upload nutritionist plan (image/PDF), edit household preferences +
  this user's goals/schedule, enable notifications (reuse AthleteIQ subscribe flow → this device into
  `users/<m>/push_subscriptions.json`), API-key/token gear.

`sw.js` + `manifest.json` copied and re-pathed to `/training-ai/nutrition/dashboard.html`.

### 7. Workflows
- `nutrition_generate.yml` — `cron: '0 18 * * 0'` (Sun ~19–20:00 Luxembourg) + `workflow_dispatch`; runs
  `generate.py`; commits the menu/shopping/prep/notif/history/status JSON + MD (copy generate_plan.yml's
  commit step). Secret: `ANTHROPIC_API_KEY`.
- `nutrition_parse.yml` — `workflow_dispatch`; runs `parse_plan.py`; commits `nutrition_plan.json`.
- `nutrition_notify.yml` — `cron: '*/15 * * * *'` + dispatch; runs `notify.py`; commits
  `push_subscriptions.json` + `notif_schedule.json`. Secret: `VAPID_PRIVATE_KEY`.

## MVP-first build sequence (for tomorrow)

1. **Scaffold** `nutrition/` — folder, `requirements.txt`, `household.json` + seed `users/diego/` and
   `users/diana/` (goals, macro_targets, empty weight_log/checkins), `schedule.json`, PWA shell with the
   **identity picker**, manifest/sw, enable GitHub Pages path. *Deliverable:* app loads, you can pick a user.
2. **MVP core (end-to-end, the heart of the request):** `parse_plan.py` → shared `nutrition_plan.json` +
   per-member `macro_targets.json`; then `generate.py` + `food_safety.py` + `lux_products.py` producing
   **shared weekly menu with per-person portions (incl. snacks) → household shopping list (EN+FR) → prep
   plan (with storage safety)**. Wire **Today / Menu / Shopping / Prep** tabs (Today shows active user's
   portion). Run `nutrition_generate.yml` manually and verify on the dashboard. *Satisfies the core
   "Sunday I know exactly what to prep" goal for both eaters.*
3. **Progress + weight tracking** — per-user manual weigh-in entry, trend chart vs target, `log_weight` data path.
4. **Coach Léa** — per-user private in-browser Claude chat + tools (swap/edit/regenerate/log check-in/log weight).
5. **Notifications** — `notify.py` + `notif_schedule.json` (incl. weigh-in) + per-user service-worker push +
   `*/15` cron + subscribe UI fanning to both members.
6. **Polish** — adherence/macro trend on Today, history-aware variety, expand `lux_products` + `food_safety`
   citations, cost estimate accuracy, rename app/coach if desired.

## Verification (end-to-end)

- **Parse:** upload a sample nutritionist plan (photo/PDF) → run `nutrition_parse.yml` → confirm
  `nutrition_plan.json` has sane daily targets + confidence; low-confidence path asks for confirmation.
- **Generate:** run `nutrition_generate.yml` → check `weekly_menu.json` (7 days, all 5 slots incl. both
  snacks; **each meal has `portions.diego` and `portions.diana`**, and each member's `day_totals` land
  within their own macro target), `shopping_list.json` (quantities = sum of both portions; every item has
  `name_fr` + LU availability), `prep_plan.json` (ordered batches, each cooked item has a `food_safety`
  storage block with cool-time + use-within + reheat temp). Sanity-assert **no allergen** from
  `household.json` appears anywhere (a guard in `generate.py` fails the run if violated).
- **Two users:** in two browsers/devices pick Diego vs Diana → Menu/Shopping/Prep identical; Today shows
  each person's own portion + macro ring; Progress + Coach are private per identity.
- **Weight tracking:** as Diego log a weigh-in on Progress → `users/diego/weight_log.json` gains an entry,
  trend chart updates toward target; Diana's log is unaffected.
- **Dashboard:** open `…/training-ai/nutrition/dashboard.html`; Today shows next action; Shopping shows
  EN+FR; Prep shows storage cards.
- **Coach:** as Diego, "Swap Tuesday dinner to vegetarian and rebuild the shopping list" → shared
  `weekly_menu.json` updates, shopping/prep regenerate, allergens still absent, and Diana's coach history
  is untouched (separate `coach_history.json`).
- **Notifications:** enable on each device; with a near-future test event in `notif_schedule.json`, run
  `nutrition_notify.yml` and confirm both members' devices get the push and the event flips to `sent:true`.
- **Food safety spot-check:** cooked rice → use-within ≈1 day; reheat targets 74 °C; cool-within ≤2 h.
- Local dry-run before pushing: `python nutrition/generate.py` with `ANTHROPIC_API_KEY` set.

## v2 additions (built)

- **Plan sync via chat**: Coach Léa has `swap_meal` / `attach_video` tools that rewrite the *shared*
  `weekly_menu.json` and re-aggregate `shopping_list.json` in-browser, so either person's change is seen by
  the other on next load (shared tabs reload data on view).
- **Rich meal sheets**: each meal carries an `image_prompt` (rendered via free Pollinations AI-image URLs),
  `prep_steps` (Sunday) vs `day_of_steps` (detailed day-of), macro pills, an "eaten ✓" button, and an
  optional `video_url` — YouTube embeds inline; Instagram/TikTok get a launch button; otherwise a
  "Search YouTube" fallback. Videos are user/coach-attached (no hallucinated links). Prep batches likewise
  support attachable technique videos.
- **Fridge/Pantry** (`inventory.json` + `inventory.py` + `nutrition_inventory.yml` daily 19:00 UTC):
  seeded weekly to required quantities, depleted each day from confirmed meals (`units.py` parses/subtracts
  quantities). `generate.py` subtracts pantry stock from the shopping list ("✓ in pantry" when enough).
- **Compliance & gamification**: per-user `meal_logs.json` from the "eaten" buttons drive a compliance %,
  day-streak (🔥) and milestone badges (1/2/4 weeks) shown at the top of Home alongside the weight tracker.
- **Hydration tracker** (v17): Home card surfaces the plan's `nutrition_plan.json → hydration_l` target as a
  tappable row of 250 ml glasses with a progress bar. Intake is logged per-user, per-day in `localStorage`
  (`nutriprep_water`, instant, no token/write — mirrors the shopping `checkedItems` pattern); resets daily.
  Falls back to a 2.0 L default when no plan is uploaded.
- **Auto-parse on upload + detailed macros (v18)**: uploading a nutritionist plan in Settings now auto-dispatches
  the `parse.yml` workflow (no manual Actions run) and polls for the result. `parse_plan.py` extracts a far richer
  schema — it **translates non-English plans** (e.g. Spanish), captures the full meal-by-meal exchange structure
  (`meals[]`: per-meal time, per-component category/portion/options, per-meal water), the `methodology`
  (e.g. Glucose Goddess), `client_name`, and **estimates daily kcal/macros from the prescribed portions** when the
  plan is exchange-based with no explicit numbers (`targets_estimated`). `generate.py` feeds this structure to Claude
  so menus honour the plan's categories and portions. Settings shows a **"Your nutrition targets"** card: kcal +
  hydration, macro grams with % of calories and g/kg, source badge, methodology, eat-regularly / avoid chips, and the
  full translated daily meal structure.

## Open / deferred (note, don't block MVP)
- GitHub Actions cron timing drift on snack/cook reminders (upgrade path noted in §5).
- Storing uploaded plan images in a public repo — consider a private repo or stripping the image after parse.
- `lux_products.py` / `food_safety.py` start curated-but-small; grow over weeks. Nutritionist plan remains
  the clinical authority — the app never overrides it, only operationalises it.
