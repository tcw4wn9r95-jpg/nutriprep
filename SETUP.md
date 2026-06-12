# NutriPrep → standalone repo: setup & cutover

This folder is the **ready-to-push** NutriPrep app, already path-adapted for its
own repo (`tcw4wn9r95-jpg/nutriprep`, GitHub Pages at `/nutriprep/`). Everything
here goes at the **root** of the new repo (the app no longer lives under a
`nutrition/` subfolder).

## 1. Create the repo and push this folder

Create an **empty public** repo named `nutriprep` on GitHub (no README/license),
then:

```bash
# from a fresh checkout of training-ai
git clone https://github.com/tcw4wn9r95-jpg/nutriprep.git
cp -a training-ai/nutriprep-export/.  nutriprep/   # note the trailing /. (copies .github too)
cd nutriprep
git add -A
git commit -m "NutriPrep standalone app"
git branch -M main
git push -u origin main
```

## 2. Add the Actions secrets (Settings → Secrets and variables → Actions)

- `ANTHROPIC_API_KEY` — same value as training-ai (plan generation).
- `VAPID_PRIVATE_KEY` — same value (web-push). Push subscriptions start fresh in
  this repo, so re-enable notifications in the app on each device.

## 3. Enable GitHub Pages

Settings → Pages → Source: **Deploy from a branch** → **main** / **/ (root)**.
Then confirm this loads: `https://tcw4wn9r95-jpg.github.io/nutriprep/dashboard.html`
(Settings tab should read **build v13 · nutriprep**.)

## 4. Token + re-install the PWA

- In the app's **Settings → GitHub token**, paste a token that can access the
  **nutriprep** repo (classic PAT with `repo` scope, or a fine-grained token
  scoped to `nutriprep` with Contents + Actions read/write). This token is what
  saves weigh-ins, menu edits, and dispatches the generate workflow.
- Remove the old NutriPrep icon from your home screen and **re-add** from the new
  URL so iOS installs it as a fresh, isolated PWA (own scope `/nutriprep/`).

## 5. Verify the data channel (no third repo — direct cross-repo reads)

- **AthleteIQ → NutriPrep:** the app + `generate.py` read `weekly_plan.json`,
  `sleep.json`, `profile.json`, `goals.json` from
  `raw.githubusercontent.com/tcw4wn9r95-jpg/training-ai/main/…`. Run the
  **Generate** workflow once (Actions → Generate → Run workflow) and confirm the
  Today tab shows Diego's training-day fuelling banner.
- **NutriPrep → AthleteIQ:** log a weigh-in (writes `users/diego/weight_log.json`
  in the nutriprep repo). AthleteIQ's `sync.py` reads it from
  `raw.githubusercontent.com/tcw4wn9r95-jpg/nutriprep/main/users/diego/weight_log.json`
  (with a local fallback during dual-run).

## 6. Cutover (after a clean week)

Once the new repo is confirmed working, remove the old copy from training-ai:
delete `nutrition/`, the four `.github/workflows/nutrition_*.yml`, and this
`nutriprep-export/` folder. AthleteIQ keeps reading weight via the channel (the
local fallback simply stops being used).
