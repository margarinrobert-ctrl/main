# US100 Edge Lab

A long-only morning-session research pipeline for US100 CFD 15-minute data, built to a 54-section
brief. Full results: `docs/ib/STUDY_US100_EDGELAB.md`.

```bash
python3 research/edgelab/run_all.py          # everything, in the brief's order
python3 research/edgelab/run_discovery.py    # stage 1: search DISCOVERY only
python3 research/edgelab/run_validate.py     # stage 2: freeze, dedupe, read validation+production
python3 research/edgelab/run_report.py       # stage 3: walk-forward, Monte Carlo, surfaces
```

## What this data can answer, and what it cannot

| | |
| --- | --- |
| resolution | **15-minute only**. No 1m/3m/5m entry timeframe, no intrabar path validation. |
| volume | `Volume` is identically zero. `TickVolume` is a broker tick **count**, not exchange volume. |
| instrument | US100 **CFD**. Kept separate from this repo's NQ futures series; never mixed. |
| clock | Broker wall clock that follows US DST. `data.verify_clock()` re-measures this each run. |
| costs | **Assumed, not measured** — OHLC bars carry no spread. See `data.Costs`. |

The binding constraint is the first row. At a 0.25×ATR stop, **47% of trades touch both barriers
inside one 15-minute bar**, so the outcome is set by the tie-break rule rather than by the market.
Sub-0.5×ATR results are not measurable here in either direction.

## The three blocks

```
DISCOVERY    2016-11 -> 2021-12    search, thresholds, every choice
VALIDATION   2022-01 -> 2023-12    frozen rules only
PRODUCTION   2024-01 -> 2025-10    read once, at the end
```

## Rules the pipeline enforces

* **Conservative intrabar resolution.** Both barriers touched in one bar resolves as a STOP,
  always, and the ambiguous share is reported with every result.
* **Matched control, not a population mean.** The base rate varies 15 points across 07:00-11:00,
  so a rule is scored against random entries with the same minute-of-day distribution.
* **The day is the unit of inference.** Trades cluster 2-3 per session; `fast.score_days`
  resamples days, not bars.
* **Truncation audit.** Every feature is recomputed on history that ends at bar *i* and must
  reproduce its value exactly. This caught two real leaks in the session features.
* **Near-duplicates collapse.** Candidates whose trade sets overlap above Jaccard 0.5 are merged,
  because a top-25 of permuted conditions is one hypothesis, not 25.
* **Multiplicity is printed, not hidden.** 27,786 tests; a p-value drawn from that is labelled.

## Result

No configuration reached the briefed 80% win rate at 1:1. Best unseen-data result: **56.9% at 1.5R
over 109 trades**, status **PROMISING**, never `ROBUST`. Costs alone require a 95% win rate to
break even at a true scalping stop. See the study for the full accounting.
