# Turtle Long-Only, confined to 07:00–11:00 New York

*A request to maximise Sharpe and profit factor for intraday scalping, answered on four uploaded
data files. Research block first 65% of sessions per instrument; locked block read once.*

```bash
# ingest + identification + audit
python3 research/turtle_data.py
python3 research/turtle_bars.py

# verification (must pass before any number below is read)
python3 research/turtle_test.py

# phase 0: the supplied strategy, research block only
python3 research/turtle_baseline.py

# phases 1-3: search, coherence, finalists
/tmp/turtle_sweep/run_all.sh
python3 research/turtle_report.py 1
python3 research/turtle_report.py 2
python3 research/turtle_report.py 3 <tf>
```

---

## 0. What the data turned out to be

Four archives arrived with no provenance beyond their filenames. Two facts had to be established
from the bytes before a session-gated study could mean anything, because getting either wrong
silently invalidates every number downstream.

### The unnamed file is US30

`1m_data.csv` is 2.88M one-minute bars, tab-separated, MetaTrader export (`Volume` identically
zero, `TickVolume` carrying the activity), naming no instrument. It prints 18,200 in October 2016
and 44,160 in July 2025. Scored against published index levels at three anchor dates:

| candidate | mean absolute level error |
| --- | --- |
| **US30 (Dow Jones)** | **1.36%** |
| DE40 (DAX) | 94.5% |
| US100 (Nasdaq 100) | 187.9% |
| US500 (S&P 500) | 704.8% |

### Both MetaTrader files are stamped in EET/EEST, not UTC and not exchange time

A broker export is stamped in *server* time. The timezone is measured rather than assumed:
`identify_timezone` converts the naive stamps under each candidate zone, finds the New York
minute-of-day at which each session's largest one-bar move lands, and scores the candidate by how
tightly that anchor concentrates. The largest one-minute move of a US index session lands on the
09:30 cash open far more often than on any other minute, so the correct zone piles those anchors
onto one minute and a wrong one smears them.

| source zone | US30 anchor (NY) | concentration | XAU anchor (NY) | concentration |
| --- | --- | --- | --- | --- |
| **Europe/Athens** | **09:30** | **0.196** | **08:30** | **0.064** |
| Europe/London | 11:30 | 0.192 | 10:30 | 0.056 |
| Etc/GMT-2 (fixed +02) | 10:30 | 0.123 | 09:30 | 0.053 |
| America/New_York | 16:30 | 0.161 | 15:30 | 0.053 |

Athens wins on both, and the anchors it produces are the right events — 09:30 is the US cash open,
08:30 is the US data release that moves gold. A fixed +02:00 offset scores far worse than Athens
precisely because it does not follow European DST.

That leaves one ambiguity a concentration score cannot settle: "EET with European DST" and
"GMT+2/+3 following *American* DST" agree for about 48 weeks a year. They disagree in the ~3 weeks
between the US spring-forward and the EU one, and the week between the EU fall-back and the US one.
Checked directly on those weeks:

| US30, Europe/Athens | sessions | anchor at 09:30 ±3 | at 10:30 | at 08:30 |
| --- | --- | --- | --- | --- |
| weeks where EU and US DST agree | 2,096 | 22.9% | 0.8% | 8.9% |
| weeks where they disagree | 156 | 16.0% | **0.0%** | 7.7% |

The anchor stays put. If the feed followed American DST the mismatch weeks would show the mass at
10:30 and nothing at 09:30. Europe/Athens it is. The gap structure agrees independently: US30's
modal gap starts at 23:00 server = 16:00 New York (the CFD daily close), XAU's at 00:00 server =
17:00 New York (the gold rollover).

BTC is Binance klines, UTC by definition. The anchor test is uninformative for a 24/7 market
(concentration 0.032 against 0.034 for the best alternative) and is reported as such rather than
dressed up.

### What is in each file after ingest

| file | instrument | native | span | sessions | research block ends |
| --- | --- | --- | --- | --- | --- |
| `1m_data.csv` | US30 | 1m | 2016-10-27 → 2025-07-15 | 2,703 | 2022-06-30 |
| `XAU_5m_data.csv` | XAU/USD | 5m | 2007-01-02 → 2026-01-30 | 5,889 | 2019-05-09 |
| `btc_15m_data…csv` | BTCUSDT | 15m | 2018-01-01 → 2026-06-15 | 3,087 | 2023-07-02 |
| `Bitcoin…coinmarketcap.csv` | BTC daily | 1d | 2025-07-23 → 2026-08-24 | 398 | *not used — daily bars cannot test a four-hour window* |

Two duplicate uploads of `XAU_5m_data.7z` (identical MD5) were de-duplicated at extraction.

In-window data completeness, which is what the study actually depends on, is 99.6–100% in every
year of every instrument; the thin early gold years are thin *outside* 07:00–11:00. The only
material data defect is 2010–2012 gold, where 0.9–1.3% of in-window bar-to-bar steps exceed one
timeframe.

**A caveat that is not resolvable from these files.** All three are single-series files with no
contract-by-contract history. US30 from a CFD feed and gold spot are both continuous by
construction; nothing here can say whether a level in 2016 is what the front month printed. As with
`data/README.md`'s note on the NQ file, R-multiples and win rates are unaffected, and the locked
block sits in the recent part of each sample where any adjustment is smallest.

---

## 1. The engine, and three defects the verification caught

Every number below comes from `research/turtle_sim.py`, which reproduces the supplied Pine's
execution model rather than approximating it: a decision on the close of bar *i* fills at the OPEN
of bar *i+1*; `strategy.exit(stop=…)` issued at that close is live from *i+1*, so **the first bar of
a position carries no stop** (the script derives the level from `strategy.opentrades.entry_price`,
which does not exist until the fill has happened); and a bar containing both barriers is booked at
the stop.

`research/turtle_test.py` is the evidence, not the assertion:

* a literal transcription of the Pine with an explicit order book agrees **trade for trade across
  52 configuration/instrument pairs**;
* a driftless martingale pays **zero gross** on every stop-only variant;
* truncating the series to 30%, 50% and 75% reproduces every decision made before the cut on all
  three instruments;
* a scan over the cached exit tensor reproduces the bar-walking engine on **33 further
  configurations**, so the fast path used by the sweep is the same strategy that was verified.

Three defects surfaced, all of which would have flattered a result:

**The null generator was manufacturing a loss.** The first synthetic series drew wick lengths as
independent noise around the open-to-close leg. That is not a martingale *path*: a stop filled at a
low the price never visited on its way to the next open books a price systematically worse than the
price at that instant, so every stop-out harvested a fabricated wick — **−20 points per position on
a driftless series**, from the data generator alone. Building each bar from a fine sub-step path
fixes it, and the residual converges to zero as the path refines: **+4.69 (t = 5.28) at 60 sub-steps,
+0.81 (t = 0.90) at 480**. That residual is the "fill exactly at the stop level" assumption every
bar-level backtest makes, and it is why `stop_slip` is a per-instrument cost input rather than zero.

**The short mirror reused the exit-length channels for entries**, because the Pine is long-only and
its `chanLo` is only ever an exit channel. Caught by the mirror test.

**A flatten order could rest across a market closure.** Gold's 2008 New Year's Eve session ends at
10:45 New York, so an 11:00 flatten never fired and the trade was carried into January. In scalp
mode a position now never crosses a session boundary: if the next bar is not in this session and
inside a grace window, the position closes at this bar's close, which is what a desk does.

And one fidelity defect found not by a test but by reading the emitted Pine back against the
original: **the supplied script's trailing exit reads `chanLo1[1]`**, the channel as of the previous
bar, and the engine was using the current bar's. Including the current bar can only push a long's
channel low down, so the unlagged form trails looser and gives back more. The reference
implementation written to check the engine had made the same slip — which is exactly the failure
mode a reference is supposed to prevent, and a reminder that "written independently" is a claim
about process, not a guarantee. The lag is now an explicit parameter defaulting to the shipped
script's `[1]`, and both variants are swept.

---

## 2. Phase 0 — what the supplied strategy does on this data

Research block only. The locked block is not consulted here; a baseline peek is still a peek.

| | US30 | XAU | BTC |
| --- | --- | --- | --- |
| best preset **as shipped** (no session limit) | T3 120m, Sharpe **0.78** | T3 120m, Sharpe **0.47** | T3 120m, Sharpe **0.61** |
| … its excess over a matched control | +$331/trade (p 0.030) | +$328/trade (p 0.015) | +$282/trade (p 0.010) |
| best preset **confined to 07:00–11:00** | Spec defaults, Sharpe **0.30** | T3 120m, Sharpe **0.05** | T2 240m, Sharpe **0.17** |
| … its net over the research block | +$17,157 | +$2,199 | +$1,270 |

Two things are already settled by that table.

**The shipped strategy's edge is the multi-day hold.** Confining entries to a four-hour window and
flattening at 11:00 takes every preset on every instrument from a Sharpe of 0.47–0.78 to 0.05–0.30,
and takes most of them negative. That is not a subtle degradation; it is the strategy's mechanism
being removed. A Turtle position is held for days by design, and the request is for a four-hour
one.

**But the signal is not worthless in the window.** The matched control inside 07:00–11:00 runs at
about **−$20 per trade** — that is what random entries at the same clock times, with the same
barriers and the same pyramiding, cost. Several presets beat it while still losing money in
absolute terms. The breakout is carrying a small positive selection value that the cost line is
eating. That is the gap the search has to close, and it is a much more specific problem than
"optimise the strategy".

Note also that the 07:00–11:00 rows of that table are not really scalps: a 240-minute preset inside
a 240-minute window takes at most one or two bars of decision. Sizing the bars to the window is the
first thing Phase 1 does.

---

*Sections 3 onwards — the search, coherence across instruments, the locked read and the shipped
Pine — are filled in by the phases below.*
