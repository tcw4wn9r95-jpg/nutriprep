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
    return f"""You are extracting structured nutritional data from a nutritionist's meal plan document.

The household members are: {member_list}.

Extract and return ONLY a JSON object (no prose, no markdown fences) with this exact schema:

{{
  "source": "nutritionist_upload",
  "parsed_on": "{date.today().isoformat()}",
  "confidence": 0.0,
  "per_member_targets": {{
    {", ".join(f'"{m}": {{"kcal": null, "protein_g": null, "carbs_g": null, "fat_g": null, "fiber_g": null}}' for m in members)}
  }},
  "meal_structure": ["breakfast", "am_snack", "lunch", "pm_snack", "dinner"],
  "prescribed_foods": [],
  "restricted_foods": [],
  "hydration_l": 2.0,
  "nutritionist_notes": ""
}}

Rules:
- Set `confidence` between 0.0 (very uncertain) and 1.0 (clearly stated).
- If the plan covers only ONE person, populate their targets and leave the other as null.
- If macros are not explicitly stated, set them to null (do NOT estimate).
- `prescribed_foods`: list foods/food groups the nutritionist says to eat regularly (e.g. "oily fish 2x/week").
- `restricted_foods`: list foods the nutritionist says to limit or avoid.
- `meal_structure`: include "am_snack" and "pm_snack" if the plan includes snacks; otherwise omit them.
- `hydration_l`: daily water target in litres (default 2.0 if not stated).
- `nutritionist_notes`: copy any important clinical notes verbatim (max 500 chars).
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
                max_tokens=2000,
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
            max_tokens=2000,
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

    # Fan targets into per-user macro_targets.json
    for member in MEMBERS:
        targets = (plan.get("per_member_targets") or {}).get(member)
        if not targets or all(v is None for v in targets.values()):
            print(f"  {member}: targets not in plan — deriving from goals...")
            targets = derive_macros_from_goals(member)
        else:
            targets["source"] = "nutritionist"

        if targets:
            out = BASE / "users" / member / "macro_targets.json"
            with open(out, "w") as f:
                json.dump(targets, f, indent=2)
            print(f"  Saved {out} ({targets.get('kcal')} kcal)")

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
