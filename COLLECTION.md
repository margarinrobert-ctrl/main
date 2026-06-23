# 24/7 Collection — accruing history while the site is closed

By default the intelligence layer (the **Intel** tab) records and scores predictions **only while a
browser tab is open**, in that browser's `localStorage`. To keep collecting **even when the site is
closed**, run the headless collector on a schedule and persist somewhere durable. The browser then
pulls everything the server gathered (`GET /api/intel`) on open and merges it locally, so you see the
full record — not just your session.

> Honest limits: data is still ~15‑min‑delayed CBOE options + Yahoo candles (no real‑time OPRA, no
> trade tape). Outcomes are scored from the recorded price series — real, but only as frequent as the
> scheduler runs.

There are two backends. **A** needs no external account.

---

## A) GitHub Actions + git store (no signup) — recommended

The included workflow `.github/workflows/collect.yml` runs the collector inside the GitHub runner every
10 min during market hours, computes the snapshot/journal/resolution, and commits the JSON to a
dedicated **`intel-data`** branch using GitHub's built‑in token. The website reads that branch back.

How it stays clean:

- The data branch is **force‑pushed as a single commit** each run → it never bloats.
- `vercel.json` sets `git.deploymentEnabled.intel-data = false` → Vercel does **not** deploy data
  commits → no deploy churn. Your default branch gets **no** data commits at all.
- The site auto‑detects the repo on Vercel (`VERCEL_GIT_REPO_OWNER/SLUG`) and reads
  `intel-data` via the raw CDN (public repos, keyless) or the contents API (private repos, with a token).

### Activate (one‑time)

1. **Merge this branch to your default branch.** Scheduled GitHub workflows only run from the default
   branch.
2. **Allow Actions to write.** Repo → Settings → Actions → General → Workflow permissions →
   "Read and write permissions".
3. **(Private repos only)** add a Vercel env var `GH_DATA_TOKEN` = a fine‑grained PAT with read access
   to this repo's contents, so the deployed site can read the `intel-data` branch. Public repos need
   nothing.
4. Optionally run it now: Actions tab → **Collect intel** → *Run workflow*.

That's it — the **Intel** tab banner turns green ("git store"), and the journal grows on every run.

---

## B) KV store (Vercel KV / Upstash Redis)

Read+write store with no branch involved. Auto‑activates when these env vars are present (either
naming works):

```
KV_REST_API_URL / KV_REST_API_TOKEN                  # Vercel KV
UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN    # Upstash Redis
```

- **Vercel KV:** dashboard → Storage → Create → KV → connect to this project (env vars injected) → redeploy.
- **Upstash:** create a free Redis DB → copy the REST URL + token → add as the env vars → redeploy.

Then point any scheduler at `GET /api/collect` (protect it with `CRON_SECRET`):

- **GitHub Actions** — change the workflow's last step to `curl -H "Authorization: Bearer $CRON_SECRET" "$COLLECT_URL"`.
- **External pinger** (cron‑job.org) — `https://<domain>/api/collect?key=<CRON_SECRET>`.

KV mode shows a green "KV connected" banner.

---

## Endpoints

| Route | Purpose |
| --- | --- |
| `GET /api/collect` | (KV mode) fetch live chain/candles for the watchlist, record, journal, resolve. CRON_SECRET‑protected. |
| `GET /api/intel?symbol=SPY` | Return the stored history + journal + `storeMode` (the browser merges this on open). |

Watchlist symbols come from `OPTIONS_WATCHLIST` (default `SPY,QQQ`).

## Verify

- **Git store:** run the **Collect intel** workflow once; confirm an `intel-data` branch appears with
  `data/intel/journal.json`. Open the Intel tab — records should load and grow each run.
- **KV store:** `curl -H "Authorization: Bearer $CRON_SECRET" https://<domain>/api/collect` →
  `{"ok":true,"storeMode":"kv",...}`, then check the Intel tab.
