# Research data

Bar files live here and are **git-ignored** — they are large, frequently licensed, and always
reproducible from the ingest command recorded in each study's header.

## Canonical format

`timestamp,open,high,low,close,volume`, one row per bar, timestamps in **UTC ISO-8601**, sorted
ascending. Produced by the ingest script rather than written by hand:

```bash
# Source stamped in US Eastern wall clock (the usual case for CME data)
npx tsx scripts/quant-ingest.ts --in raw_1min.csv --out data/NQ_5m.csv --tf 5 --tz America/New_York

# Source already in UTC
npx tsx scripts/quant-ingest.ts --in raw_1min.csv --out data/XAUUSD_5m.csv --tf 5 --tz UTC
```

The script reads the source timestamps as **exchange wall clock** and converts to true UTC, so a file
stamped in Eastern time survives both daylight-saving transitions. Resampling buckets are anchored to
*local* midnight, so a 5-minute bar lines up with the 09:30 session open instead of straddling it. It
reports any row landing in a non-existent (spring-forward) or ambiguous (fall-back) local hour.

The source column order is free and headers are matched loosely, so `timestamp ET,open,high,low,
close,volume,Vwap_RTH,Vwap_ETH` works as-is; extra columns are ignored.

## Then run a study

```bash
npx tsx scripts/quant-research.ts --data data/NQ_5m.csv --symbol NQ --out docs/STUDY_NQ.md
```

`--symbol` selects the contract spec and cost model from `src/lib/quant/instruments.ts`
(`NQ`, `ES`, `CL`, `MCL`, `GC`, `MGC`, `XAUUSD`). Optional: `--holdout 0.3`, `--combos 400`,
`--seed 20250822`.

See [`docs/RESEARCH_PROTOCOL.md`](../docs/RESEARCH_PROTOCOL.md) for what each stage tests and how to
read the result.

## What `NQ_1m.csv` actually is, and what it is not

Audited 2026-08-23, from the file itself. 1,048,575 one-minute bars,
2022-12-26T23:01Z → 2025-12-12T01:52Z, sorted, no duplicate timestamps.

**It is real market data.** Four independent checks, none of which synthetic data passes by
accident:

* every open, high, low and close sits on the 0.25 tick grid, and every bar satisfies
  `high >= max(open, close)` and `low <= min(open, close)`
* the New York-hour volume profile has the real double hump — 1,370 and 1,585 contracts/minute
  average at 09h and 10h, a midday trough at 849, and a 15h close ramp back to 1,062
* the weekday distribution is the CME calendar: ~210,000 bars each Mon-Thu, 153,266 on Friday
  (the 17:00 ET stop), 54,180 on Sunday (the 18:00 ET open), and **zero on Saturday**
* the eight largest one-minute moves in three years fall on 2025-04-06, 04-07 and 04-09 (twice
  within nine minutes of 13:20 ET on the 9th), 2025-02-02, 2025-10-12 and 2025-04-22 — the
  tariff selloff and its reversal, correctly dated

**It is a back-adjusted continuous contract, not a raw front-month stitch.** Checked directly:
in all twelve quarterly roll windows the largest one-minute move lands at 08:30 or 14:00 ET (data
releases and FOMC) or at the 18:00 ET session open — never at the roll itself. There is no roll
discontinuity because the adjustment removed it.

Consequently the historical *levels* are not what the front month printed at the time. The file's
2022-12-31 close is 13,696.75; NQ front-month traded near 11,000 then. That offset decays to zero
at the right-hand edge, which is exactly how back-adjustment anchored to the newest contract
behaves, and the implied ~4-5%/year of carry matches the 2023-25 rate environment.

**What that changes, and what it does not.** Which adjustment method a vendor used — additive
(preserves point differences) or ratio (preserves percentage returns) — cannot be determined from
this file alone, and it is the one open provenance question here:

* under **additive** adjustment the dollar P&L in every study on this branch is exact
* under **ratio** adjustment, dollar figures in the *earliest* part of the sample are overstated
  by up to the level ratio, about 25% at the very start, decaying to 0% at the end

Two things bound the damage. R-multiples and win rates are unaffected either way, because ATR
scales with the series. And the research/locked split puts the holdout in the **recent** 35% of
the sample, where the adjustment is smallest — so the locked-block dollar figures, which are the
ones every conclusion rests on, are the least exposed of any number here.

Resolving it needs the raw contract-by-contract file, which is not in this repository.

## US100_15m.csv — a non-canonical file, kept as delivered

The US100 15-minute file does **not** use the canonical format above and is deliberately not
converted, so it stays byte-identical to what was delivered. It is tab-separated, headed
`DateTime Open High Low Close Volume TickVolume`, stamped `YYYY.MM.DD HH:MM:SS`, sorted
**descending**, and its clock is **New York + 7 hours** — an offset that is stable across DST, so
a fixed −7h shift is right year round. `Volume` is all zeros; `TickVolume` is the usable one.
`research/us100.py` handles all of that; nothing else should parse this file directly.

Keep it at `data/US100_15m.csv`. It arrives by upload, and an upload directory is not durable —
it has been cleared mid-study once already, which is why `us100.find_raw()` searches several
locations and why this path is the one to restore it to.

## EURUSD_M30.csv — a fifth format, an independent era, and the first measured spread

Audited 2026-08-25 from the file itself. 230,400 30-minute bars,
2003-07-21 08:00 → 2022-02-22 04:00 New York. 0 duplicates, 0 OHLC violations, 0 non-positive
prices, 0.023% zero-range bars, 989 gaps over two hours (weekends).

A **fifth distinct export format**: comma-separated with an **unnamed integer index column**, then
`time,open,high,low,close,tick_volume,spread,real_volume`, stamped `YYYY-MM-DD HH:MM:SS`, sorted
ascending. `real_volume` is populated on only 10.5% of bars, so `tick_volume` is the activity
proxy. `research/edgelab/fx.py` owns this file; nothing else should parse it.

**Its clock was derived from FX's own anchors, not inherited.** There is no 09:30 cash equity open
in EURUSD, so the index feeds' anchor is meaningless here. Three independent measurements agree on
**New York + 7**, and all three are stable across daylight saving:

* the **weekly open** — FX opens Sunday 17:00 New York, and the bar after each weekend gap lands at
  file 00:00 in 964 of 984 weeks, separately 240/241 in winter and 241/242 in summer
* the **daily activity minimum** — mean tick volume bottoms at file hour 0 = 17:00 New York, the
  rollover lull to the minute
* the **volatility profile** — mean |30-minute return| peaks at file hour 16 = 09:00 New York, with
  the whole 14–17 block being the London/New York overlap and a secondary hump at file 9–11 =
  02:00–04:00 New York, the London open. That shape only appears at this offset.

**Two things nothing else here has.**

It does **not overlap the NQ sample by a single bar** — it ends 2022-02-22 and NQ starts
2022-12-26. `STUDY_TREND_LONG.md` established that a second instrument over the same calendar is
not a second test (68% of NQ's triggers fired on the identical 15-minute bar on US100). That
objection cannot be raised here.

And it reports a **measured spread**, the first on this branch. Use it through
`fx.usable_span()`, never raw: a quoted spread of exactly zero is a missing value, and the zero
share is 0% every year to 2013 but reaches 25.2% in 2017, 36.0% in 2020, 74.6% in 2021 and 87.7%
in the 2022 stub. Those four years are dropped whole and individual zero bars are dropped
elsewhere, leaving 190,319 of 230,400 bars (82.6%). See `docs/ib/STUDY_SPREAD_TRUTH.md`.


## BTC_15m.csv — a sixth format, a UTC clock, and real taker-side flow

Audited 2026-08-25 from the file itself. Raw **Binance BTCUSDT klines**, 15-minute, 295,882 bars
after cleaning, 2017-12-31 19:00 → 2026-06-15 19:15 New York. The file *name* says 2018–2025; the
data runs eighteen months further.

Comma-separated, headed `Open time,Open,High,Low,Close,Volume,Close time,Quote asset volume,Number
of trades,Taker buy base asset volume,Taker buy quote asset volume,Ignore`. Timestamps carry six
decimal places **and trailing whitespace**; `Ignore` is Binance's documented placeholder and is all
zeros. `research/edgelab/crypto.py` owns this file.

**Three defects, found rather than assumed.** The **final row is malformed** — both timestamps empty
with OHLCV present — and is dropped on the timestamp, because a bar that cannot be placed in time is
not a bar. Two timestamps are duplicated. And 14 bars carry zero volume, zero trades and zero range
*together*, which is an exchange outage, not a quiet market.

**Its clock is UTC, and this is the only feed here where a constant shift is wrong.** Every other
file is a broker export whose server follows US daylight saving. Measured against US30, winter
prefers −5h (corr 0.1289) and summer −4h (0.1625) — a one-hour disagreement, which is the DST
signature. A true `UTC → America/New_York` conversion scores each season's own best and +0.1337
pooled, against +0.0908 for the best single shift. The loader converts rather than shifts, and the
autumn fall-back hour's duplicate local timestamps are dropped.

**It is 24/7** — weekday bar counts run 42,184 to 42,370, flat. Every other instrument here has a
weekend hole, and every session condition on this branch was written against one.

**It carries real order flow.** `Taker buy base asset volume / Volume` is the share of volume that
lifted the offer — an *actual* imbalance rather than a constructed proxy — centred at 0.4965 mean /
0.4967 median. Exposed as `taker_share`. See `docs/ib/STUDY_BTC_LEGS.md`.

## The registry is the durable part

`research/datasets.py` records every dataset's format, delimiter, column meanings, exact row count
and span, derived clock and the evidence for it, measured defects, owning loader, provenance and a
sha256 prefix. It is committed; the bars are not.

```bash
python research/datasets.py        # inventory + verify what is on disk
```

`verify()` distinguishes MISSING from SIZE MISMATCH from CONTENT MISMATCH, so a re-uploaded file
can be proved identical to the copy every study was run on rather than assumed to be.

**Nothing in `data/` survives a container recycle.** Eight files, 427 MB, and all of them arrive by
upload. The registry is what makes re-attaching them mechanical instead of archaeological.
