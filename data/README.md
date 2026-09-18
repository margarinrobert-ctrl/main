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

## Bitcoin

`research/fetch_btc.py` pulls BTC bars straight from an exchange into the format above, so a
crypto file is reproducible the same way an NQ one is:

```bash
python3 research/fetch_btc.py --tf 1d --start 2017-08-17 --out data/BTCUSDT_1d.csv
python3 research/fetch_btc.py --tf 1m --start 2023-01-01 --source vision --out data/BTCUSDT_1m.csv
python3 research/fetch_btc.py --tf 1h --source coinbase --out data/BTCUSD_1h.csv   # different tape
```

Use `--source vision` (archive ZIPs) for minute and sub-minute bars and `binance` for hourly or
daily; below an hour the paged REST endpoint needs thousands of calls to cover the same span. It
reports gap and OHLC-violation counts on the way out.

**Sub-minute.** No venue publishes a 30-second bar. Binance's finest native kline is **1 second**,
and a 30s bar is an exact fold of 30 of them -- first open, max high, min low, last close, summed
volume, nothing interpolated. `--tf 30s` does that fold; so does any other multiple (`45s`, `2m`).
Coinbase is floored at one minute and refuses.

```bash
python3 research/fetch_btc.py --tf 30s --start 2025-01-01 --source vision --dry-run
python3 research/fetch_btc.py --tf 30s --start 2025-01-01 --source vision --out data/BTCUSDT_30s.csv
```

Price it with `--dry-run` first, because the 1s source data is the expensive part: one year of 30s
bars is 1.05M output rows but 31.5M one-second bars and ~330 MB of ZIPs; three years is 94.7M bars
and ~1 GB. The 1s interval is published as DAILY archive files for much of its history, so a long
pull is ~365 requests per year rather than 12.

Two things BTC is not. It is not a second sample of the same market -- it trades 24/7 with no RTH
session, so every minute-of-day, session-index and daily-trend construction on this branch has to
be re-derived rather than re-pointed. And BTCUSDT is not BTCUSD: do not splice the two venues into
one file to extend history.

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
