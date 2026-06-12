"""
NutriPrep — nutritionist plan parser.
Reads a photo (JPEG/PNG) or text-based PDF of the nutritionist's meal plan,
sends it to Claude vision, and extracts:
  - per-member daily calorie & macro targets
  - meal structure, prescribed and restricted foods
  - hydration target
Writes nutrition_plan.json (shared) and fans targets into users/<m>/macro_targets.json.
"""
import os, json, base64, sys
from pathlib import Path
from datetime import date

import anthropic

BASE = Path(__file__).parent
MEMBERS = ["diego", "diana"]

UPLOAD_PATHS = [
    BASE / "nutritionist_plan_upload.jpg",
    BASE / "nutritionist_plan_upload.jpeg",
    BASE / "nutritionist_plan_upload.png",
    BASE / "nutritionist_plan_upload.pdf",
]


def find_upload() -> Path | None:
    for p in UPLOAD_PATHS:
        if p.exists():
            return p
    return None


def load_image_as_base64(path: Path) -> tuple[str, str]:
    """Return (base64_data, media_type)."""
    suffix = path.suffix.lower()
    media_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
    if suffix in media_map:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode(), media_map[suffix]
    raise ValueError(f"Unsupported file type: {suffix}")


def extract_text_from_pdf(path: Path) -> str:
    """Extract text from a text-based PDF using pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(pages).strip()
        return text
    except Exception as e:
        print(f"PDF text extraction failed: {e}")
        return ""


def build_prompt(members: list[str]) -> str:
    member_list = " and ".join(m.capitalize() for m in members)
    members_json = ", ".join(
        f'"{m}": {{"kcal": null, "protein_g": null, "carbs_g": null, "fat_g": null, "fiber_g": null}}'
        for m in members
    )
    return f"""You are a clinical-nutrition data extractor. You are reading a nutritionist's meal plan
document (a photo or PDF). It is FUNDAMENTAL that you capture this plan completely and faithfully —
it is the clinical authority that a downstream meal-plan generator will follow exactly.

The household members are: {member_list}.

IMPORTANT — LANGUAGE: The document may be written in Spanish (or another language). TRANSLATE every
extracted value into clear English. When a meal name or food-category label is meaningful in the
original language, also keep the original text in the matching `*_original` field.

Return ONLY a JSON object (no prose, no markdown fences) with this exact schema:

{{
  "source": "nutritionist_upload",
  "parsed_on": "{date.today().isoformat()}",
  "confidence": 0.0,
  "language_detected": "",
  "client_name": "",
  "methodology": "",
  "targets_estimated": false,
  "per_member_targets": {{
    {members_json}
  }},
  "meal_structure": ["breakfast", "am_snack", "lunch", "pm_snack", "dinner"],
  "meals": [
    {{
      "slot": "breakfast",
      "label": "Breakfast",
      "label_original": "Desayuno",
      "time": "09:00",
      "water_ml": 500,
      "components": [
        {{
          "category": "Protein",
          "category_original": "Carnes",
          "portion": "2 eggs OR 2 slices of smoked salmon OR a protein serving",
          "options": ["2 eggs", "2 slices smoked salmon", "1 protein serving"]
        }}
      ]
    }}
  ],
  "prescribed_foods": [],
  "restricted_foods": [],
  "hydration_l": 2.0,
  "nutritionist_notes": ""
}}

Rules:
- `language_detected`: ISO code of the document's language (e.g. "es", "en").
- `client_name`: the person the plan is written for, exactly as printed (e.g. "Diego Casares").
- `methodology`: if the plan references a method or philosophy (e.g. "Glucose Goddess"), name it and
  add a one-sentence plain-English description of its core principle.
- `meals`: capture the FULL meal-by-meal structure. For EVERY meal include its `slot`
  (breakfast | am_snack | lunch | pm_snack | dinner), an English `label`, the original-language
  `label_original`, the `time` as "HH:MM" 24h, any per-meal water in `water_ml`, and a `components`
  array. Each component is one food category/row with its English `category`, the `category_original`,
  the full `portion` text (translated, keeping quantities like grams, cups, pieces), and `options`:
  every interchangeable alternative split into its own string. Do not summarise or drop options.
- `meal_structure`: the ordered list of slots actually present in this plan.
- `prescribed_foods`: foods/groups the plan tells the client to eat regularly.
- `restricted_foods`: the "avoid / limit" list (e.g. Spanish "Evitar Consumir"), translated.
- `hydration_l`: total daily water in litres. If per-meal water amounts are given, SUM them.
- `nutritionist_notes`: any other clinical notes, verbatim then translated (max 600 chars).
- `per_member_targets`: daily calorie & macro targets.
    • If the document states explicit kcal/macro numbers, use them exactly and set
      "targets_estimated": false.
    • If the plan is PORTION/EXCHANGE-based with NO explicit numbers (common), ESTIMATE realistic
      daily targets by summing a representative mid-range choice from each meal's components across
      the whole day (kcal, protein_g, carbs_g, fat_g, fiber_g). Set "targets_estimated": true.
      Use standard food composition values; be careful and clinically plausible.
    • Assign the numbers to the member whose first name matches `client_name`. Leave any member not
      covered by the plan as null (their targets are derived separately).
- `confidence`: 0.0 (very unsure) to 1.0 (clearly legible and complete).
- Return ONLY valid JSON. No prose. No markdown.
"""


def derive_macros_from_goals(member: str) -> dict:
    """Derive macro targets using Mifflin-St Jeor if not provided by nutritionist."""
    goals_path = BASE / "users" / member / "goals.json"
    if not goals_path.exists():
        return {}
    with open(goals_path) as f:
        goals = json.load(f)
    weight = goals.get("start_weight_kg", 75)
    goal_type = goals.get("goal_type", "maintain")
    # Simple Mifflin-St Jeor approximation (sedentary baseline)
    # BMR ≈ 10*w + 6.25*h - 5*a ± s  — we don't have height/age, use weight-only proxy
    bmr = 10 * weight + 500  # rough proxy without height/age
    tdee = bmr * 1.4  # light activity
    if goal_type == "weight_loss":
        kcal = round(tdee - 400)
    elif goal_type == "muscle_gain":
        kcal = round(tdee + 200)
    else:
        kcal = round(tdee)
    protein_g = round(weight * 1.8)
    fat_g = round(kcal * 0.28 / 9)
    carbs_g = round((kcal - protein_g * 4 - fat_g * 9) / 4)
    return {
        "kcal": kcal,
        "protein_g": protein_g,
        "carbs_g": max(carbs_g, 50),
        "fat_g": fat_g,
        "fiber_g": 28,
        "source": "derived",
    }


def main():
    upload = find_upload()
    if not upload:
        print("ERROR: No upload found. Place your nutritionist's plan as:")
        print("  nutritionist_plan_upload.jpg  (or .png / .pdf)")
        sys.exit(1)

    print(f"Found upload: {upload}")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = build_prompt(MEMBERS)

    if upload.suffix.lower() == ".pdf":
        text = extract_text_from_pdf(upload)
        if text:
            print("Extracted text from PDF, sending as text to Claude.")
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt + "\n\nNUTRITIONIST PLAN TEXT:\n" + text}],
            )
        else:
            print("PDF has no extractable text (scanned image?). Please upload as JPEG or PNG.")
            sys.exit(1)
    else:
        b64, media_type = load_image_as_base64(upload)
        print(f"Sending image to Claude vision ({upload.name}, {len(b64)//1024} KB base64)...")
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )

    raw = message.content[0].text.strip()
    print("Claude response received.")

    # Strip markdown fences if Claude added them despite instructions
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()

    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse JSON response: {e}")
        print("Raw response:", raw[:500])
        sys.exit(1)

    confidence = plan.get("confidence", 0)
    print(f"Parsed nutrition plan (confidence: {confidence:.0%})")

    # Save shared plan
    plan_path = BASE / "nutrition_plan.json"
    with open(plan_path, "w") as f:
        json.dump(plan, f, indent=2)
    print(f"Saved {plan_path}")

    # Shared plan context surfaced on every member's macro card (and to generate.py).
    estimated = bool(plan.get("targets_estimated"))
    shared_ctx = {
        "hydration_l": plan.get("hydration_l", 2.0),
        "methodology": plan.get("methodology", ""),
        "prescribed_foods": plan.get("prescribed_foods", []),
        "restricted_foods": plan.get("restricted_foods", []),
        "client_name": plan.get("client_name", ""),
        "nutritionist_notes": plan.get("nutritionist_notes", ""),
        "updated_on": date.today().isoformat(),
    }

    # Fan targets into per-user macro_targets.json
    for member in MEMBERS:
        targets = (plan.get("per_member_targets") or {}).get(member)
        if not targets or all(v is None for v in targets.values()):
            print(f"  {member}: targets not in plan — deriving from goals...")
            targets = derive_macros_from_goals(member)
        else:
            targets = {k: v for k, v in targets.items() if v is not None}
            targets["source"] = "nutritionist (estimated from plan)" if estimated else "nutritionist"
            # The detailed nutritionist plan applies to the named client only.
            targets.update(shared_ctx)

        if targets:
            out = BASE / "users" / member / "macro_targets.json"
            with open(out, "w") as f:
                json.dump(targets, f, indent=2)
            print(f"  Saved {out} ({targets.get('kcal')} kcal · source: {targets.get('source')})")

    if confidence < 0.6:
        print(
            "\n⚠ LOW CONFIDENCE (< 60%). Some values may be missing or unclear."
            "\nPlease review nutrition_plan.json and update users/<m>/macro_targets.json if needed."
        )

    # Remove upload after parse to avoid re-parse on next run
    upload.rename(upload.with_name("nutritionist_plan_parsed" + upload.suffix))
    print(f"\nParse complete. Upload moved to {upload.stem}_parsed{upload.suffix}.")


if __name__ == "__main__":
    main()
