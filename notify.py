"""
NutriPrep — push notification dispatcher.
Runs every 15 min via GitHub Actions cron. Finds events in notif_schedule.json
that are due (within the last 15 min, not yet sent) and pushes them to the
household's devices via web push (pywebpush). Prunes expired subscriptions.

The app is run by one household admin, so devices subscribe to the shared
push_subscriptions.json. Older per-member files (users/<m>/push_subscriptions.json)
are still honoured; each device gets an event at most once.
"""
import os, json, tempfile
from datetime import datetime, timezone
from pathlib import Path
from pywebpush import webpush, WebPushException

BASE = Path(__file__).parent
MEMBERS = ["diego", "diana"]
WINDOW_MINUTES = 16  # look-back window to catch cron drift

VAPID_PRIVATE_KEY_PEM = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS = {"sub": "mailto:nutri@nutriprep.local"}


HOUSEHOLD = "household"


def _subs_path(owner: str) -> Path:
    if owner == HOUSEHOLD:
        return BASE / "push_subscriptions.json"
    return BASE / "users" / owner / "push_subscriptions.json"


def load_subs(owner: str) -> list[dict]:
    path = _subs_path(owner)
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def save_subs(owner: str, subs: list[dict]) -> None:
    with open(_subs_path(owner), "w") as f:
        json.dump(subs, f, indent=2)


def main():
    if not VAPID_PRIVATE_KEY_PEM:
        print("VAPID_PRIVATE_KEY not set — skipping notifications.")
        return

    notif_path = BASE / "notif_schedule.json"
    if not notif_path.exists():
        print("No notif_schedule.json found.")
        return

    with open(notif_path) as f:
        schedule = json.load(f)

    events: list[dict] = schedule.get("events", [])
    now_utc = datetime.now(tz=timezone.utc)
    cutoff_utc = now_utc.replace(second=0, microsecond=0)
    window_start = cutoff_utc.timestamp() - WINDOW_MINUTES * 60

    due_events = [
        e for e in events
        if not e.get("sent")
        and datetime.fromisoformat(e["at"]).timestamp() >= window_start
        and datetime.fromisoformat(e["at"]).timestamp() <= cutoff_utc.timestamp()
    ]

    if not due_events:
        print(f"No due events at {now_utc.strftime('%H:%M UTC')}.")
        return

    print(f"Found {len(due_events)} due event(s) at {now_utc.strftime('%H:%M UTC')}.")

    # Write VAPID private key to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as tf:
        tf.write(VAPID_PRIVATE_KEY_PEM)
        pem_path = tf.name

    try:
        for event in due_events:
            audience = event.get("audience", MEMBERS)
            payload = json.dumps({"title": event["title"], "body": event["body"]})

            sent_to: set[str] = set()
            owners = [HOUSEHOLD] + [m for m in audience if m in MEMBERS]
            for member in owners:
                subs = [s for s in load_subs(member) if s.get("endpoint") not in sent_to]
                sent_to.update(s.get("endpoint") for s in subs)
                expired_endpoints: set[str] = set()

                for sub in subs:
                    try:
                        webpush(
                            subscription_info=sub,
                            data=payload,
                            vapid_private_key=pem_path,
                            vapid_claims=VAPID_CLAIMS,
                        )
                        print(f"  ✓ Sent '{event['title']}' to {member} ({sub['endpoint'][-20:]}…)")
                    except WebPushException as exc:
                        status = exc.response.status_code if exc.response else None
                        if status in (404, 410):
                            expired_endpoints.add(sub["endpoint"])
                            print(f"  ✗ Expired sub for {member} (HTTP {status}) — removing.")
                        else:
                            print(f"  ✗ Push failed for {member}: {exc}")

                # Prune expired subscriptions
                if expired_endpoints:
                    save_subs(member, [s for s in load_subs(member) if s["endpoint"] not in expired_endpoints])

            # Mark event as sent
            event["sent"] = True
            event["sent_at"] = now_utc.isoformat()

    finally:
        import os as _os
        _os.unlink(pem_path)

    # Save updated schedule
    with open(notif_path, "w") as f:
        json.dump(schedule, f, indent=2)

    print("Notification dispatch complete.")


if __name__ == "__main__":
    main()
