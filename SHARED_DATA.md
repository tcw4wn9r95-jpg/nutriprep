# Shared data: NutriPrep ↔ Coach Claudio

Two apps, one owner per fact. This file is identical in both repos
(`tcw4wn9r95-jpg/nutriprep` and `tcw4wn9r95-jpg/training-ai`); change it in both.

| Fact | Owner (writes) | Reader | File (in the owner's repo) |
|---|---|---|---|
| Diego's day macros — kcal, protein, carbs, fat, fibre | NutriPrep | Claudio | `users/diego/macro_targets.json` |
| This week's dishes and Diego's portion of each | NutriPrep | Claudio | `weekly_menu.json` → `[].meals[].portions.diego` |
| Body weight | NutriPrep | Claudio (`sync.py`) | `users/diego/weight_log.json` |
| Training fuel for **completed** sessions | Claudio | NutriPrep | `fuel.json` |
| Completed workouts, planned sessions, sleep | Claudio | NutriPrep | `workouts.json`, `weekly_plan.json`, `sleep.json` |
| What Diego actually ate, diet compliance | Claudio | — | `food_log.json` |
| Free-sugar and water targets, meal structure | Claudio | — | `nutrition_plan.json` |
| Household preferences, shopping, pantry, "I made this" | NutriPrep | — | `preferences.json`, `shopping_list.json`, `inventory.json`, `cooked_log.json` |

## Rules

- **Only completed training adds food, in both apps.** A planned session shows what it
  will add once done; nothing is added up front.
- **Claudio computes fuel** (watch calories net of resting, or MET estimate; carbs ~60%,
  body-weight caps). `training-ai/fuel.py` publishes it as `fuel.json` on every Garmin
  sync (`sync_activities` / `generate_plan` workflows); `tests/test_fuel.py` keeps it in
  step with the dashboard's `fuelFor`. NutriPrep never recalculates it.
- **NutriPrep's targets win** for the five macros in Claudio; Claudio keeps free sugar and
  water, and fills any macro NutriPrep doesn't have from its own plan / reference values.
- **NutriPrep dishes become planned meals in Claudio** (source `nutriprep`,
  `nutriprep_ref = "<date>|<slot>"`): they reserve budget and count only after
  "I ate it". Claudio never overwrites what Diego logged himself, doesn't re-add a
  NutriPrep meal he removed (`day.nutriprep_dismissed`), and updates a still-planned
  entry when the household swaps the dish. "I made this" in NutriPrep does **not** mark
  anything eaten — cooking isn't eating.
- Readers go through the GitHub contents API with the saved token (fresh), falling back
  to `raw.githubusercontent.com` (can lag a few minutes).

## fuel.json

```json
{ "version": 1, "member": "diego", "rule": "completed sessions only", "updated": "2026-10-05",
  "body_kg": 80, "base": {"kcal": 1900, "protein_g": 150, "carbs_g": 180, "fat_g": 60, "fiber_g": 30},
  "days": { "2026-10-05": { "session_kcal": 880, "hours": 1.5, "src": "measured", "sessions": ["cycling"],
                            "add": {"kcal": 590, "carbs_g": 132, "protein_g": 10, "fat_g": 1, "water_ml": 900} } } }
```
