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

## 3. The search

### 3.1 What was searched

The presets in §2 are 60- to 240-minute strategies evaluated inside a 240-minute window, which
gives them one or two bars to decide anything. Phase 1 sizes the bars to the window and sweeps the
geometry, on the research block, with entries confined to 07:00–11:00 and a hard flatten at 11:00.

| axis | levels |
| --- | --- |
| System 1 entry channel | 4, 6, 8, 10, 14, 20, 28 bars |
| System 2 entry channel | 8, 12, 16, 24, 40, 60 (≥ System 1) |
| trailing exit channels | 2, 3, 4, 6, 8, 12 bars, paired |
| ATR stop multiple | 1.0, 1.5, 2.0, 2.5, 3.0 × ATR(20) |
| pyramid | off, 0.5N × 4 units, 1.0N × 4 units |
| take profit | off, 1R, 2R, 3R |
| trailing channel exit | on / off |
| trailing channel lag | `chanLo[1]` (the shipped script) / `chanLo` |
| stop live on the entry bar | no (the shipped script) / yes |
| skip System 1 after a win | on / off |

**645,120 cells per instrument, per timeframe, per side. 22 runs. 14,192,640 cells.** Every one is
scored against its own matched control, which is affordable because the exit tensor already holds
each bucket's mean (§1).

Two things the sweep is not allowed to do. It cannot choose a direction — the strategy is long-only
by construction and the short mirror is run separately as a control, never as a candidate. And it
cannot use a calendar condition; weekday and month partitions are banned here as they are
everywhere else in this repository.

### 3.2 The timeframe gradient is monotone, and it is the cost line

| | US30 5m | US30 15m | US30 30m | US30 60m |
| --- | --- | --- | --- | --- |
| best Sharpe of 645,120 | 0.28 | 0.47 | 0.78 | **0.81** |
| **mean** Sharpe over the grid | **−1.59** | −0.45 | −0.08 | −0.06 |
| best config: units per trade | 2.51 | 2.65 | 1.65 | 1.00 |
| gross $/trade | 73.19 | 73.19 | 69.06 | 55.57 |
| modelled cost $/trade | 34.84 | 34.84 | 22.34 | **13.56** |
| break-even cost multiple | ~1.1× | 2.10× | 3.09× | **4.10×** |
| median hold | 65 min | 75 min | 75 min | 84 min |

Three readings, in increasing order of usefulness.

**The average configuration of this family loses money at every speed**, and the loss shrinks as
the bars get longer: −1.59 Sharpe at 5 minutes, −0.06 at 60. That is the protocol's §3b arithmetic
happening in front of the strategy — halving the bar halves the move and leaves the cost alone.

**The gross edge per trade barely moves; the cost per trade triples.** $73 of gross at 5 minutes
against $73 at 15, $69 at 30 and $56 at 60 — but the cost goes 34.84 → 34.84 → 22.34 → 13.56,
because the pyramid fills more units on faster bars. Speed is not buying opportunity here; it is
buying turnover.

**The trade has a natural length of about 75 minutes, at every timeframe.** 65, 75, 75, 84 minutes
of median hold across a 12× range of bar sizes. The bar size is not choosing how long the trade
lasts — the move is — so a faster chart is subdividing the same trade into more decisions and
paying for each of them.

### 3.3 The direction control

`CLAUDE.md` §4c: on a sample that rose, a long-only search finds the sample, and every holdout
agrees with it. The mirror image of the whole search — Donchian *low* breakout, stop above, adds
below, same grid, same 645,120 cells — is the empirical answer to "what does a search of this size
find when it has no reason to work".

| US30 | best long | best short | gap |
| --- | --- | --- | --- |
| 5m | 0.281 | −0.005 | 0.286 |
| 15m | 0.466 | 0.118 | 0.348 |
| 30m | 0.783 | 0.575 | **0.208** |

That is a far more useful bar than the parametric one. Bailey & López de Prado's expected maximum
over 645,120 *independent* trials at the observed dispersion is 1.7 to 2.7 depending on the
timeframe — a threshold nothing could clear, and rightly ignored, because these cells are nowhere
near independent (a uniform sample of 500 of them has a mean pairwise daily-P&L correlation of 0.75
and an eigenvalue participation ratio of 1.8: they are one strategy with knobs). The short mirror
measures the same quantity empirically and puts it at 0.0 to 0.58.

The 30-minute result is the one this test damages. Its long side scores 0.783 and its mirror 0.575
— a search of that size on those bars finds three quarters of the result with the sign reversed.

### 3.4 The cost line, not the signal, is what separates the three instruments

The matched control is positive on **every** instrument and every timeframe. Best cell per run,
research block:

| instrument | tf | gross $/trade | cost $/trade | net $/trade | control $/trade | **excess** | break-even |
| --- | --- | --- | --- | --- | --- | --- | --- |
| US30 | 60m | 55.57 | 13.56 | +42.01 | +0.26 | **+41.75** | **4.10×** |
| US30 | 30m | 69.06 | 22.34 | +46.72 | −9.13 | **+55.86** | 3.09× |
| US30 | 15m | 73.19 | 34.84 | +38.35 | −13.96 | **+52.32** | 2.10× |
| XAU | 60m | 40.26 | 38.49 | +1.77 | −21.27 | **+23.05** | 1.05× |
| XAU | 30m | 44.36 | 50.87 | −6.51 | −35.77 | **+29.26** | 0.87× |
| XAU | 15m | 22.44 | 46.78 | −24.35 | −39.70 | **+15.36** | 0.48× |
| BTC | 15m | 27.16 | 49.68 | −22.52 | −47.02 | **+24.50** | 0.55× |

Read the excess column and the break-even column together. **The entry rule carries information on
all three instruments** — it beats random entries at the same clock times with the same barriers by
$15 to $56 a trade, everywhere. **What differs is whether that information is worth more than the
round turn.** On US30 the gross edge is 2–4× the cost. On gold it is 0.5–1.05×. On BTC, 0.55×.

That is not "the strategy works on the Dow and not on gold". It is: the same edge is there, and
only one of these three is cheap enough to trade it. The gold number is a **retail spot** cost line
— a 20-cent spread plus 5 cents of stop slippage on a 100 oz lot, $25 per unit per round turn, and
about $53 a trade at 2.1 units. A futures desk on GC pays roughly half that, which is exactly where
XAU 60m's 1.05× break-even sits.

**Not one of the 645,120 cells on gold or BTC clears the research gates** (≥ 250 trades, positive
control excess, PF ≥ 1.05) at any timeframe. Neither is shipped.

### 3.5 What the volatility-matched control ruled out

A Donchian break does not fire at a random moment: it fires when the bar is large. A larger bar
could mean a wider ATR stop, more ladder units and a longer hold — and on a drifting sample "larger"
and "better" have the same sign, so a control matched only on the clock would credit that to the
rule. `turtle_tensor.vol_slot` strata the draw pool by ATR quantile *within* each minute, so the
control enters at the same times **and** in the same volatility state.

On the US30 30m winner the two controls are indistinguishable — −$12.17 clock-matched against
−$11.97 volatility-matched, both at p = 0.0025. The reason is measurable: trigger bars have
essentially the population's ATR(20) distribution (mean 45.7 against 49.6; quintile shares 0.23 /
0.19 / 0.20 / 0.20 / 0.18 against 0.20 each). The break selects on the *bar's own* range, which is
1.14× average, but the stop is sized on ATR(20), which the bar barely moves. The confound is real
in principle and absent here.

### 3.6 What refinement was allowed to change

Phase 2 holds the geometry fixed and sweeps the session window inside 07:00–11:00, the ADX and
EMA-extension ceilings, the break-through distance, a hold cap and a one-trade-per-session rule —
12,000 cells per structure.

Taking that grid's **argmax** moves US30 60m from Sharpe 0.81 to 1.18, by changing five things at
once. That is the shape this repository has been burned by, so the rule was fixed before the locked
block was read:

> Adopt the best level of an axis if, and only if, the axis is **binary**, or its **marginal** —
> the median objective over every other axis — is **monotone** in the axis's natural order.

A binary axis has no shape to mine. A monotone marginal is a claim about the axis rather than about
one cell. A marginal that dips and rises again is a peak, and a peak in a 12,000-cell grid is
precisely what the rule refuses.

On US30 60m it adopts two of seven axes:

| axis | marginal (median Sharpe by level) | verdict |
| --- | --- | --- |
| **entries end** | 10:00 **+0.546** · 10:30 +0.401 · 11:00 +0.401 | monotone → **adopt 10:00** |
| **one trade per session** | off +0.400 · **on +0.487** | binary → **adopt on** |
| entries start | 07:00 +0.520 · 07:30 +0.421 · 08:00 +0.421 · 08:30 +0.446 · 09:00 +0.446 · 09:30 +0.311 · 10:00 +0.311 | not monotone → refuse |
| ADX ceiling | off +0.546 · 18 −0.161 · 22 +0.174 · 26 +0.449 · 30 +0.435 | not monotone → refuse |
| EMA-extension ceiling | off +0.444 · 2 +0.271 · 3 +0.348 · 4 +0.431 · 6 +0.531 | not monotone → refuse |
| break-through distance | 0 +0.485 · 0.05 ATR +0.462 · 0.15 ATR +0.389 | monotone → adopt 0 (no change) |
| max hold | 0 +0.444 · 2 +0.439 · 4 +0.444 · 8 +0.444 | flat → refuse |

Both adoptions have a mechanism, which is the point of the rule rather than a coincidence. Entries
stop at 10:00 because the trade's natural hold is ~75 minutes and the flatten is at 11:00, so a
later entry is systematically truncated. One trade per session, because a re-entry after a failed
breakout is a second attempt at a range that has already shown it will not break.

Research-block result of the three variants, US30 60m:

| | trades | net $ | $/trade | Sharpe | PF | MAR | control excess | break-even | HAC *t* | years profitable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Phase-1 geometry | 542 | 22,772 | 42.01 | 0.81 | 1.30 | 4.49 | +$42.48 (p 0.005) | 4.10× | 2.10 | 100% |
| **marginal-supported** | **391** | **26,654** | **68.17** | **1.05** | **1.47** | **4.74** | **+$68.99 (p 0.0025)** | **5.94×** | **2.67** | **100%** |
| grid argmax *(not shipped)* | 354 | 29,233 | 82.58 | 1.18 | 1.60 | 7.84 | +$82.32 (p 0.0025) | 7.17× | 3.05 | 100% |

*Sections 4 onwards — the locked read, the gates and the shipped Pine — follow.*
