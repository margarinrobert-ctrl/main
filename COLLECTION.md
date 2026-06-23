# 24/7 Collection — accruing history while the site is closed

By default the intelligence layer (the **Intel** tab) records and scores predictions **only while a
browser tab is open**, in that browser's `localStorage`. To keep collecting **even when the site is
closed**, run the headless collector on a schedule and persist to a durable store. Two pieces:

1. **A durable store (KV)** — so data survives between serverless invocations.
2. **A scheduler** — to call `GET /api/collect` on a cadence.

The browser then pulls everything the server gathered (`GET /api/intel`) on open and merges it locally,
so you see the full record — not just your session.

> Honest limits: data is still ~15‑min‑delayed CBOE options + Yahoo candles (no real‑time OPRA, no
> trade tape). Outcomes are scored from the recorded price series — real, but only as frequent as the
> scheduler runs. I can't provision your accounts/keys; the steps below are yours to do once.

---

## 1) Durable store — Vercel KV or Upstash Redis (free tiers)

The store auto‑activates when these env vars are present (either naming works):

```
KV_REST_API_URL / KV_REST_API_TOKEN            # Vercel KV
UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN   # Upstash Redis
```

- **Vercel KV:** Vercel dashboard → Storage → Create → KV → connect it to this project. Vercel injects
  `KV_REST_API_URL` + `KV_REST_API_TOKEN` automatically. Redeploy.
- **Upstash:** create a free Redis DB → copy the **REST URL** + **REST token** → add them as the env
  vars above in Vercel → redeploy.

Without these, the store falls back to per‑instance memory (works, but resets on cold starts). The
Intel tab shows the current mode (KV connected vs ephemeral).

## 2) Scheduler — pick one

**A. GitHub Actions (free, included)** — `.github/workflows/collect.yml` pings the endpoint every 5 min
during market hours. Setup (repo → Settings → Secrets and variables → Actions):

- Variable `COLLECT_URL` = `https://<your-vercel-domain>/api/collect`
- Secret `CRON_SECRET` = a random string (also set it as an env var on Vercel — see below)

Scheduled workflows run **only from the default branch**, so merge this branch there to activate.

**B. Vercel Cron** — `vercel.json` already declares a daily cron hitting `/api/collect`. On the Hobby
plan crons run ~once/day; upgrade to Pro for intraday frequency. Vercel sends `CRON_SECRET`
automatically when that env var is set.

**C. Any external pinger** (e.g. cron‑job.org) — hit
`https://<domain>/api/collect?key=<CRON_SECRET>` on whatever schedule you like.

## 3) Protect the endpoint (recommended)

Set `CRON_SECRET` (any random string) as an env var on Vercel. The endpoint then requires
`Authorization: Bearer <CRON_SECRET>` or `?key=<CRON_SECRET>`. If unset, the endpoint is open.

---

## Endpoints

| Route | Purpose |
| --- | --- |
| `GET /api/collect` | Fetch live chain/candles for the watchlist, record a snapshot, journal each engine's call, resolve matured ones. Returns a per‑symbol summary + `storeMode`. |
| `GET /api/collect?symbol=SPY` | Collect a single symbol. |
| `GET /api/intel?symbol=SPY` | Return the stored history + journal for a symbol (the browser merges this on open). |

Watchlist symbols come from `OPTIONS_WATCHLIST` (default `SPY,QQQ`).

## Verify

```
curl -H "Authorization: Bearer $CRON_SECRET" https://<domain>/api/collect
# → {"ok":true,"storeMode":"kv","results":[{"symbol":"SPY","added":1,"resolved":0,...}]}
```

`storeMode:"kv"` confirms persistence is live. Then open the **Intel** tab — it should show the
server‑collected records, and the count grows on each scheduled run.
