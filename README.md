# OptionsFlow

Unusual options activity & basic quant analytics for US equities + ETFs, powered by the
[Barchart OnDemand](https://www.barchart.com/ondemand) API.

Built **fixtures-first**: the whole app runs on canned JSON with **no API key and zero quota**,
so you can develop and demo the full UI offline. Flip one flag to go live.

---

## Quick start

```bash
npm install
cp .env.example .env.local     # defaults to DATA_SOURCE=fixtures — no key needed
npm run dev                    # http://localhost:3000
```

You'll see the **Flow** table (scored unusual activity) and a **Quote** card, both served from
`/fixtures`. Click a ticker to open its detail page.

Other scripts:

```bash
npm run probe        # test which Barchart endpoints your key unlocks (see below)
npm run typecheck    # tsc --noEmit
npm run test         # vitest (covers the flow heuristic)
npm run build        # production build
```

---

## Deploy — click and open

This is a standard Next.js app, so the fastest path to a live URL is **Vercel** (it signs in with
your existing GitHub — no new password):

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fmargarinrobert-ctrl%2Fmain&project-name=options-flow&repository-name=options-flow)

Or manually: **Vercel → Add New… → Project → Import `margarinrobert-ctrl/main` → Deploy.**

- **First deploy needs zero config** — it boots in fixtures mode, so you get a fully working demo immediately at your `*.vercel.app` URL.
- **Want live underlying data?** Vercel → Settings → Environment Variables:
  - `DATA_SOURCE=live` + `MARKET_DATA_PROVIDER=stooq` → live quote + price chart, **no key**.
  - Add a paid `BARCHART_API_KEY` to also make the flow table + options chain live.
- Once the repo is connected, Vercel auto-builds a **preview URL for every branch/PR** (including this one).
- ⚠️ This app lives on branch `claude/peaceful-sagan-ksfof0` (PR #16), and the repo's default branch doesn't have it yet. Either **merge PR #16 first** (then the default branch has the app), or in Vercel set **Settings → Git → Production Branch** to `claude/peaceful-sagan-ksfof0`.

> The flow table + options chain are fixtures unless a paid Barchart key is set — no free options feed exists. Quote + chart go live for free via Stooq.

### Zero-setup demo: GitHub Pages

A GitHub Action (`.github/workflows/pages.yml`) builds a **static, fixtures-only** demo and publishes
it to GitHub Pages on every push to this branch — no account or local setup needed:

**https://margarinrobert-ctrl.github.io/main/**

Static = no server, so it's the canned-data demo (flow table, charts, chains). For live data, use the
Vercel deploy above.

## Data source: `fixtures` vs `live`

One flag controls everything (default is now **live**):

```bash
DATA_SOURCE=live       # default: fetch fresh data (Stooq underlying + Alpha Vantage / Barchart options)
DATA_SOURCE=fixtures   # offline: canned JSON in /fixtures
```

Every Barchart call goes through a single client (`src/lib/barchart/client.ts`). In `live` mode,
**any** failure (auth error, 204, rate-limit, network, bad JSON) is caught and the client
**falls back to fixtures** so the UI never renders half-broken. The key is injected server-side
only — it never reaches the browser. Live responses are cached in-memory for `CACHE_TTL_SECONDS`
(keyed by endpoint + params) to protect trial quota; swap `CacheStore` for Redis later.

### Providing your key

Either set `BARCHART_API_KEY` as an environment variable (preferred — never touches the repo) or
put it in `.env.local` (gitignored). Then set `DATA_SOURCE=live`.

### Fresh data — what's free vs. keyed

Everything live runs with **no key by default** — no signup required:

| Data | Default provider | Cost | Freshness |
| --- | --- | --- | --- |
| Underlying quote + price chart | **Stooq** | free, **no key** | EOD (~1 day old) |
| Options chain / heatmap / flow | **CBOE delayed quotes** | free, **no key** | **~15-min delayed** |
| Options (alternative) | Alpha Vantage (`ALPHAVANTAGE_API_KEY`) | free key | EOD (~1 day old) |
| Options intraday + full-market scan | Barchart (`BARCHART_API_KEY`, `OPTIONS_PROVIDER=barchart`) | paid key | real-time / delayed |

Out of the box, options come from **CBOE's public delayed-quotes feed** (`cdn.cboe.com`) — real
chains with volume, OI, IV and greeks, ~15 min delayed, **keyless**. The flow table is built from
`OPTIONS_WATCHLIST` (cached `CBOE_CACHE_TTL_SECONDS`, default 10m). Futures (ES/NQ) have no public
options feed, so they map to the matching CBOE cash index (**ES→SPX, NQ→NDX**) as a free stand-in.
Set `ALPHAVANTAGE_API_KEY` to switch to Alpha Vantage, or `OPTIONS_PROVIDER=barchart` (+ key) for
the paid real-time tier. Any live failure falls back to fixtures, so the UI never breaks.

---

## `npm run probe` — what your key unlocks

Barchart plans differ, and free-trial keys often can't reach the options endpoints. Before relying
on live data, run the probe. It makes **one** minimal request per endpoint and reports each as
`✅ usable / ⚠️ empty / 🔒 not on your plan / ⏳ rate-limited / ❌ error`. On success it also saves the
raw response to `/fixtures/<name>.live.json` so you can seed real fixtures, and it infers whether
your quote data is delayed or real-time.

```bash
npm run probe
npm run probe -- --only quote,history   # subset
```

With no key set, it tells you so and exits cleanly (the app still works in fixtures mode).

---

## Free tier vs PAID subscription

| Feature | Endpoint(s) | Tier |
| --- | --- | --- |
| Underlying quote + price chart | `getQuote`, `getHistory` | **likely FREE** |
| Flow table / unusual activity | `getOptionsScreener` | **likely PAID** |
| Full options chain, IV / greeks | `getEquityOptions` | **likely PAID** |
| Volume-spike baseline, sweep replay | `getEquityOptionsHistory` | **likely PAID** |

Everything works in **fixtures mode regardless of tier.** Run `npm run probe` to confirm exactly
what your key unlocks — that's what upgrading buys you. For live underlying data with **no key**,
set `MARKET_DATA_PROVIDER=stooq` (see above).

---

## The unusual-activity heuristic

There is no native Barchart "flow" endpoint — we synthesize it. For each contract
(`src/lib/flow/heuristic.ts`):

**Gates** (excluded as noise → score 0): `volume ≥ 100` **and** `openInterest ≥ 50`.

**Signals**, each normalized to 0–1 via a clamped ramp `clamp((x − floor)/(cap − floor), 0, 1)`:

| Signal | Formula | floor → cap | weight |
| --- | --- | --- | --- |
| Vol/OI ratio | `volume / openInterest` | 1.0 → 5.0 | 0.40 |
| Volume spike | `volume / avgVolume` (needs history; 0 if absent) | 2.0 → 10.0 | 0.20 |
| Notional | `volume × mid × 100`, `mid = (bid+ask)/2` (else last) | $250k → $5M | 0.30 |
| Short-dated OTM | `DTE ≤ 7` and `|moneyness| ≥ 5%` | — | 0.10 |

**Score** = `100 × Σ(wᵢ·fᵢ) / Σwᵢ`, rounded. If volume-spike data is unavailable (free tier), its
weight is redistributed so the score isn't unfairly capped. Each row also carries boolean **flags**
(`High Vol/OI`, `Volume Spike`, `Large Notional`, `Short-dated OTM`) so you can see *why* it ranked.

All thresholds are in `src/lib/barchart/config.ts` (`flowThresholds`). Rows also flag aggressive
**Sweeps** (high vol/OI + short-dated + large notional).

## Quant analytics (`src/lib/flow/analytics.ts`, unit-tested)

Each ticker page is a tabbed dashboard — **Overview · Chain · Heatmap · Gamma · OI · Skew · History** —
driven by a pure analytics engine computed from the chain:

- **Dealer gamma exposure (GEX)** by strike, net GEX ($/1% move), and the **zero-gamma flip** level
- **Dealer regime** badge: long gamma (mean-reverting) vs short gamma (trend-amplifying)
- **Call wall / put wall** (max call/put gamma strikes), **max pain**, **expected move** (ATM straddle)
- **Net Δ exposure**, **put/call ratios** (volume & OI)
- **Gamma Profile** chart (GEX-by-strike, spot + flip markers) and **IV skew** chart (call vs put IV)
- **Open-interest profile** (calls vs puts by strike) and a **History** tab — intraday spot + net-GEX
  time-series recorded client-side in your browser (no backend; Postgres + cron is the multi-day upgrade)
- Two-sided options chain (calls │ strike │ puts) with spot / expiration / updated pills
- **CSV export** of the ranked flow

---

## Project layout

```
fixtures/                 canned JSON (default data source); *.live.json from probe are gitignored
scripts/probe.ts          standalone endpoint probe (npm run probe)
src/
  app/
    page.tsx              home: Flow table + quote demo
    ticker/[symbol]/      ticker detail
    api/barchart/         server proxy routes (inject key, normalize) — quote, history, options, screener
  lib/
    barchart/             config, types, errors, zod schemas, client (fixtures|live, cached), endpoints
    providers/stooq.ts    free keyless quote+history provider (live, no key)
    cache/store.ts        CacheStore interface + in-memory impl (Redis-ready)
    flow/                 heuristic (pure, unit-tested) + screener-filter
    persistence/          SnapshotStore interface + in-memory impl (Prisma/Postgres later)
  components/             FlowTable, QuoteCard, loading/empty/error states
```

## Status / roadmap

- [x] **M0** scaffold + `npm run probe` + fixtures
- [x] **M1** `getQuote` end-to-end (client → zod → route → UI)
- [x] **M2** price chart on ticker page (`getHistory`, lightweight-charts)
- [x] **M3 (partial)** screener route + Flow table + heuristic (fixtures; live needs PAID)
- [x] **M4** options chain + IV summary on ticker page (`getEquityOptions`)
- [x] Screener UI controls mapped to `getOptionsScreener` params
- [x] Live response caching (TTL = `CACHE_TTL_SECONDS`), keyed by endpoint + params
- [x] Free keyless provider (Stooq) for live quote + history — no account needed
- [x] Index/ETF/futures focus (SPY, QQQ, ES, NQ) + interactive options **heatmap** (volume / vol-OI / notional)
- [ ] Postgres/Prisma snapshot store + scheduled polling (for flow-over-time)
- [ ] Live futures options (ES/NQ) via Barchart `getFuturesOptions` (fixtures provided for the demo)

> Note: persistence and background polling are intentionally deferred — meaningful flow-over-time
> needs the paid live screener, so the snapshot layer ships as an in-memory interface for now.
