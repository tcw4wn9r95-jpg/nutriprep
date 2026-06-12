"""
NutriPrep ↔ AthleteIQ cross-app data link.
Reads the training app's public JSON over the shared cross-repo channel — the
training-ai repo's raw.githubusercontent.com endpoint — so the meal planner can
fuel training days, adapt to sleep, and share the athlete's profile/goals. Body
weight stays single-sourced in NutriPrep (users/<m>/weight_log.json); the
training app reads it back over the same channel.

All reads are best-effort: if the training app's data is missing or the network
hiccups, every helper returns an empty/neutral result and meal generation
proceeds unchanged.
"""
import json
import urllib.request

# Shared channel: AthleteIQ's public repo root.
CHANNEL = "https://raw.githubusercontent.com/tcw4wn9r95-jpg/training-ai/main"

# Default energy cost per TSS point (kcal). ~1 h threshold ≈ 100 TSS ≈ 700 kcal.
KCAL_PER_TSS = 7
BUMP_CAP_KCAL = 700


def _load(base: str, name: str, default):
    """Fetch <base>/<name> JSON over HTTP; return default on any error."""
    url = f"{base.rstrip('/')}/{name}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.load(r)
    except Exception:
        return default


def training_calorie_bump(tss: float, kcal_per_tss: float = KCAL_PER_TSS) -> int:
    """Extra kcal to fuel a session of the given training stress."""
    if not tss or tss <= 0:
        return 0
    return int(min(BUMP_CAP_KCAL, round(tss * kcal_per_tss)))


def split_bump_macros(extra_kcal: int) -> dict:
    """Allocate the fuelling bump: mostly carbs, some protein, a little fat."""
    if extra_kcal <= 0:
        return {"kcal": 0, "carbs_g": 0, "protein_g": 0, "fat_g": 0}
    return {
        "kcal": extra_kcal,
        "carbs_g": round(extra_kcal * 0.60 / 4),
        "protein_g": round(extra_kcal * 0.20 / 4),
        "fat_g": round(extra_kcal * 0.20 / 9),
    }


def load_training_week(week_dates: dict, base: str = CHANNEL) -> dict:
    """
    Return {iso_date: {name, sport, tss, duration_min, extra_kcal}} for any
    training session whose date falls within the upcoming menu week.
    """
    plan = _load(base, "weekly_plan.json", [])
    wanted = set(week_dates.values())
    out: dict = {}
    for s in plan if isinstance(plan, list) else []:
        d = s.get("date")
        if d in wanted:
            tss = s.get("planned_tss", 0) or 0
            out[d] = {
                "name": s.get("name", "Training"),
                "sport": s.get("sport", ""),
                "tss": tss,
                "duration_min": round((s.get("total_duration_secs", 0) or 0) / 60),
                "extra_kcal": training_calorie_bump(tss),
            }
    return out


def sleep_summary(base: str = CHANNEL) -> str:
    """Compact recent-sleep summary string for the prompt (empty if no data)."""
    sleep = _load(base, "sleep.json", [])
    if not sleep:
        return ""
    scored = [d for d in sleep if d.get("score")][-7:]
    if not scored:
        return ""
    avg = round(sum(d["score"] for d in scored) / len(scored))
    last = sleep[-1]
    poor = [d["date"] for d in scored if d["score"] < 65]
    parts = [f"7-day avg sleep score {avg}/100."]
    if last.get("score"):
        parts.append(f"Last night {last['score']}/100, {last.get('duration_h','?')}h.")
    if poor:
        parts.append(f"Poor nights (<65): {', '.join(poor)} — bias toward easy-to-digest, blood-sugar-stable meals and earlier dinners on the days after.")
    else:
        parts.append("Sleep looks consistent.")
    return " ".join(parts)


def shared_profile(base: str = CHANNEL) -> dict:
    """Athlete name + training goal/injuries/notes shared from AthleteIQ."""
    profile = _load(base, "profile.json", {})
    goals = _load(base, "goals.json", {})
    return {
        "name": profile.get("name", ""),
        "training_goal": goals.get("primary_goal", ""),
        "injuries": goals.get("injuries", ""),
        "coach_notes": goals.get("coach_notes", ""),
    }
