# Turtle Long-Only, confined to 07:00–11:00 New York

*A request to maximise Sharpe and profit factor for intraday scalping, answered on four uploaded
data files. Research block first 65% of sessions per instrument; locked block read once.*

## Summary

The supplied Turtle earns from its **multi-day hold**. Confined to four hours it does not: every
preset drops from a research Sharpe of 0.47–0.78 to 0.05–0.30 (§2).

Rebuilt for the window and searched over **14,261,040 configurations** on three instruments and
both sides, the answer is a **negative result with one weak survivor**:

* **Five of six candidates lost money on the holdout**, including the one with the best research
  numbers by a wide margin — US30 60m at research Sharpe 1.05 / PF 1.47 / control excess $69 a
  trade at p 0.002, and holdout **−0.36** with a *gross* result of **−$14.43 a trade** (§4).
* The survivor is **US30 15m**: holdout Sharpe **0.22**, PF **1.04**, +$18.70 a trade over 898
  trades, drawdown $40,672 against a $16,789 gain, **6 of 10 gates**, Sharpe 95% CI **[−0.83, 1.31]**
  (§4.3–4.4). A paper-trading candidate, nothing more.
* **Gold and BTC produce nothing at all** — not one of 645,120 cells clears the research gates on
  either, and over a uniform grid sample their median configuration is *worse* than a matched
  random entry (§3.4).

A second pass (§7) asked whether a more profitable, less market-correlated version exists. It does
not, and it established something worse about the one that ships: **87% of its holdout profit is
market beta** — strip the exposure and its Sharpe is 0.032, not 0.222. Optimising directly for
market-neutrality finds beta 0.17 configurations on the block it optimises on, and the correlation
between their selection-block and validation-block residual Sharpe is **−0.057**.

Two methodological results are worth more than the strategy. Running the identical pipeline on the
**short mirror** showed that a matched-control p-value computed on a selected winner is not a
p-value — the short side, on the side the sample was against, scored the *larger* control excess
(+$122.17 a trade against +$69.10) and both then lost money out of sample (§4.2). And the mirror
test **predicted the holdout ranking exactly**, where PBO and walk-forward got it backwards (§4.1).

```bash
# ingest + instrument/timezone identification + audit
python3 research/turtle_data.py
python3 research/turtle_bars.py

# verification -- must pass before any number below is read
python3 research/turtle_test.py

# phase 0: the supplied strategy, research block only
python3 research/turtle_baseline.py

# phase 1: the sweep -- 22 runs x 645,120 cells, four at a time
for tf in 5 15 30 60; do for i in US30 XAU; do
  python3 research/turtle_run_sweep.py $i $tf 1; python3 research/turtle_run_sweep.py $i $tf -1
done; done
for tf in 15 30 60; do
  python3 research/turtle_run_sweep.py BTC $tf 1; python3 research/turtle_run_sweep.py BTC $tf -1
done

# phases 1-2: search size, direction control, cross-instrument coherence
python3 research/turtle_report.py 1
python3 research/turtle_report.py 2

# phase 3: pick + refine, research only.  --short runs the procedure control.
python3 research/turtle_ship.py US30 15
python3 research/turtle_ship.py US30 60 --short

# phase 4: the locked read, once, for every candidate at the same time
python3 research/turtle_reveal.py

# ship
python3 research/turtle_emit.py US30:15 US30:60 US30:30 US30:5
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
| best Sharpe of 645,120 | 0.281 | 0.466 | 0.783 | **0.808** |
| **mean** Sharpe over the grid | **−1.59** | −0.45 | −0.08 | −0.06 |
| best config: trades | 1,998 | 1,347 | 1,200 | 542 |
| best config: units per trade | 2.51 | 2.65 | 1.65 | **1.00** |
| gross $/trade | 53.65 | 73.19 | 69.06 | 55.57 |
| modelled cost $/trade | 35.15 | 34.84 | 22.34 | **13.56** |
| net $/trade | 18.50 | 38.35 | **46.72** | 42.01 |
| break-even cost multiple | 1.53× | 2.10× | 3.09× | **4.10×** |
| median hold | 65 min | 75 min | 74 min | 84 min |

Three readings, in increasing order of usefulness.

**The average configuration of this family loses money at every speed**, and the loss shrinks as
the bars get longer: −1.59 Sharpe at 5 minutes, −0.06 at 60. That is the protocol's §3b arithmetic
happening in front of the strategy — halving the bar halves the move and leaves the cost alone.

**The cost per trade falls monotonically with the bar size, and the gross edge does not rise to
meet it.** Cost goes 35.15 → 34.84 → 22.34 → 13.56, tracking the unit count almost exactly (2.51 →
2.65 → 1.65 → 1.00): the pyramid ladder is spaced in ATR, so a faster chart fills more of it and
pays another round turn for each fill. Gross, meanwhile, is humped — $54 at 5 minutes, peaking at
$73 at 15, back to $56 at 60 — so the break-even multiple, which is the ratio of the two, climbs
monotonically from 1.53× to 4.10×. Speed is not buying opportunity here; it is buying turnover.

**The trade has a natural length of about 75 minutes, at every timeframe.** 65, 75, 74, 84 minutes
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

| US30 | best long | best short | gap |
| --- | --- | --- | --- |
| 60m | 0.808 | 0.600 | **0.208** |

The 30- and 60-minute results are the ones this test damages. Their long sides score 0.78 and 0.81
and their mirrors 0.58 and 0.60 — a search of that size, on those bars, on the side the sample was
*against*, finds three quarters of the result.

**And the matched control does not rescue them.** Put the short mirror through the identical
pipeline — spike test, marginal-supported refinement — and its research-block winner beats *its*
matched control by **+$122.17 a trade at p = 0.008**, against the long winner's **+$69.10 at
p = 0.002**. The side this sample was against scores the larger excess, and both are emphatic.

That is not a defect in the control. It is what a p-value means after selection: the excess and the
objective are correlated, so choosing the maximum of 645,120 cells on either side produces a
winner whose control excess is large by construction. The control remains the right instrument for
asking whether *a given* configuration carries information — §3.4 is entirely built on it — but it
cannot be quoted as significance for a configuration the search chose. Only the holdout can.

The version of this test that **is** free of selection scores a uniform grid sample on both sides:

| US30 | long: share excess > 0 | long: mean excess | *t* | short: share > 0 | short: mean excess | *t* |
| --- | --- | --- | --- | --- | --- | --- |
| 5m | 72.9% | **+$4.18** | 12.6 | 22.4% | −$3.62 | −13.2 |
| 15m | 76.2% | **+$5.83** | 13.3 | 45.7% | −$0.89 | −2.6 |
| 30m | 86.6% | **+$11.06** | 22.0 | 54.7% | +$2.03 | 3.3 |
| 60m | 59.9% | **+$6.43** | 8.4 | 63.7% | **+$5.96** | 7.8 |

Nothing was selected to make that table, so the *t*-statistics mean what they say. At 5, 15 and 30
minutes the breakout carries information upward that it does not carry downward — an upside break
in an index has follow-through, a downside break in a rising index mean-reverts. **At 60 minutes
the asymmetry vanishes**: +$6.43 long against +$5.96 short. The 60-minute effect is a breakout
momentum effect that works equally in both directions, and the long side's higher Sharpe there
comes from the drift the control already prices out of the excess.

That is not a reason to reject the 60-minute configuration — a long-only strategy on the long side
of a symmetric effect, on an instrument with positive drift, is a coherent thing to trade. It is a
reason not to claim the 60-minute result demonstrates something the short side lacks.

### 3.3b What survives out of sample *inside* the research block

PBO and walk-forward, over the same uniform 500-cell grid sample (never the sweep's kept rows):

| US30 | PBO | walk-forward efficiency | stitched OOS Sharpe | universe median Sharpe | universe share positive |
| --- | --- | --- | --- | --- | --- |
| **60m** | **0.103** ✓ | **0.44** ✓ | **0.31** | −0.045 | 44% |
| **15m** | **0.266** ✓ | **0.52** ✓ | 0.17 | −0.256 | 20% |
| 30m | 0.397 ✗ | −0.01 ✗ | 0.17 | −0.047 | 44% |
| 5m | 0.000 † | −0.31 ✗ | −0.28 | −1.108 | 1% |

† 5m's PBO of zero is not a pass. PBO asks where the in-sample winner lands in the out-of-sample
ranking, and at 5 minutes only 1% of the universe is profitable at all — the winner is above the
median of a uniformly bad field every time, which says nothing about selection and everything about
the field.

**60m and 15m clear both; 30m and 5m clear neither.** That, and not the maximum Sharpe, is what
decides which timeframes ship as presets.

### 3.4 The entry rule carries information on US30, and does not on gold or BTC

The first version of this section said the opposite, and the way it was wrong is worth keeping.
Reading the **best cell** of each run, the matched-control excess is positive everywhere — +$15 to
+$56 a trade on all three instruments — which reads as "the signal works everywhere and only the
cost line differs". That claim does not survive being asked of the parameter space rather than of
its maximum.

Scored over a **uniform random sample of 500 grid cells** (the same universe the PBO uses, not the
sweep's kept rows):

| run | share with **positive control excess** | median excess $/trade | median net $/trade | share net-profitable |
| --- | --- | --- | --- | --- |
| US30 30m | **86.6%** | +8.93 | −2.08 | 44.5% |
| US30 15m | **76.2%** | +4.37 | −8.87 | 20.2% |
| US30 5m | **72.9%** | +2.15 | −20.42 | 1.4% |
| US30 60m | **59.9%** | +3.24 | −2.90 | 44.1% |
| XAU 60m | 33.1% | **−3.67** | −26.27 | 0.0% |
| BTC 60m | 24.4% | **−5.65** | −28.69 | 0.0% |
| BTC 15m | 14.6% | **−5.10** | −45.13 | 0.0% |
| XAU 15m | **7.6%** | **−9.85** | −53.12 | 0.0% |

On US30 a randomly chosen configuration of this family beats a random entry at the same clock times
with the same barriers 60–87% of the time. That is a property of the space, not of a cell someone
picked, and it is the strongest single piece of evidence in this study.

On gold and BTC the median configuration is **worse than a matched random entry**. The positive
excess on their best cells was selection: take the maximum of 645,120 draws from a distribution
centred below zero and it will be above zero. Reporting only that maximum is how a negative result
gets written up as "the signal is there, the costs are too high" — which is what the first draft of
this section said.

The costs still matter, and they are why even US30's typical configuration loses money (median net
−$2 to −$20 a trade). But the ranking of the three instruments is not a cost ranking. Best cell per
run, research block, for reference:

| instrument | tf | gross $/trade | cost $/trade | net $/trade | control $/trade | **excess** | break-even |
| --- | --- | --- | --- | --- | --- | --- | --- |
| US30 | 60m | 55.57 | 13.56 | +42.01 | +0.26 | **+41.75** | **4.10×** |
| US30 | 30m | 69.06 | 22.34 | +46.72 | −9.13 | **+55.86** | 3.09× |
| US30 | 15m | 73.19 | 34.84 | +38.35 | −13.96 | **+52.32** | 2.10× |
| XAU | 60m | 40.26 | 38.49 | +1.77 | −21.27 | **+23.05** | 1.05× |
| XAU | 30m | 44.36 | 50.87 | −6.51 | −35.77 | **+29.26** | 0.87× |
| XAU | 15m | 22.44 | 46.78 | −24.35 | −39.70 | **+15.36** | 0.48× |
| BTC | 15m | 27.16 | 49.68 | −22.52 | −47.02 | **+24.50** | 0.55× |

The break-even column is the useful one: gross edge divided by modelled round turn, or how wrong the
cost model can be before the result dies. On US30 it is 2.1–4.1×. On gold and BTC it is 0.5–1.05×,
which for a *selected* cell on a space whose median excess is negative means there is nothing there
at all.

Gold's cost line is a **retail spot** one — a 20-cent spread plus 5 cents of stop slippage on a 100
oz lot, $25 per unit per round turn, about $53 a trade at 2.1 units — and a futures desk on GC pays
roughly half. That halving would move XAU 60m's best cell from break-even to marginally profitable.
It would not change the finding, because the finding is the 33% in the table above, not the 1.05×
in this one.

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

---

## 4. The locked read

**14,261,040 configurations** were evaluated to produce these candidates: 22 sweeps × 645,120
cells, plus five short-mirror sweeps, refinement grids, spike tests and PBO universes. The locked
block had never been touched. Every number below is the first time it was consulted, and no
selection followed it.

| candidate | research Sharpe | research PF | **locked Sharpe** | locked PF | locked $/trade | locked net | gates |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **US30 15m** | 0.466 | 1.107 | **+0.222** | 1.039 | **+$18.70** | **+$16,789** | **6 / 10** |
| US30 5m *(refined)* | 0.565 | 1.152 | −0.053 | 0.988 | −$4.97 | −$3,336 | 3 / 10 |
| US30 60m *(unrefined)* | 0.808 | 1.296 | −0.265 | 0.931 | −$16.22 | −$5,806 | 3 / 10 |
| US30 5m *(unrefined)* | 0.281 | 1.058 | −0.330 | 0.948 | −$22.22 | −$27,531 | 3 / 10 |
| US30 60m *(refined)* | **1.054** | **1.470** | **−0.359** | 0.884 | −$29.06 | −$7,002 | 3 / 10 |
| US30 30m | 0.783 | 1.250 | **−0.633** | 0.870 | −$42.86 | −$31,543 | 2 / 10 |
| *US30 60m SHORT — procedure control* | 0.587 | 1.353 | −0.574 | 0.798 | −$97.24 | −$15,656 | 3 / 10 |
| *XAU 60m — rejected on research* | 0.019 | 1.007 | +0.062 | 1.021 | +$8.93 | +$6,457 | 4 / 10 |
| *BTC 60m — rejected on research* | 0.024 | 1.011 | −0.100 | 0.967 | −$14.28 | −$3,399 | 2 / 10 |

**One configuration out of six survives with a positive holdout, and it is not the one with the
best research numbers.** The 60-minute configuration — research Sharpe 1.05, PF 1.47, PSR-above-zero
0.9991, matched-control excess +$69.10 a trade at p = 0.002, 100% of research years profitable,
neighbourhood a plateau at 0.91 — earns **−$29.06 a trade** on the holdout, and its *gross* result
before any cost is **−$14.43 a trade**. Nothing about its research profile was a warning.

The 30-minute configuration is worse: research 0.783, locked −0.633.

### 4.1 The research-side control that predicted this, and the two that did not

Ranking the timeframes by locked Sharpe gives **15m > 5m > 60m > 30m**. Three research-block
diagnostics were available before the holdout was read. They did not agree with each other.

| US30 | short mirror clears the pipeline's gates? | uniform-grid excess asymmetry | PBO | walk-forward efficiency | **locked Sharpe** |
| --- | --- | --- | --- | --- | --- |
| 15m | **no — 0 of 8,000** | clean: +$5.83 vs −$0.89 | 0.266 ✓ | 0.52 ✓ | **+0.222** |
| 5m | **no — 0 of 8,000** | clean: +$4.18 vs −$3.62 | 0.000 † | −0.31 ✗ | −0.053 |
| 60m | **yes — 8,000 of 8,000** | **none: +$6.43 vs +$5.96** | 0.103 ✓ | 0.44 ✓ | −0.265 |
| 30m | **yes — 7,958 of 8,000** | weak: +$11.06 vs +$2.03 | 0.397 ✗ | −0.01 ✗ | −0.633 |

**The mirror test got the order exactly right.** Where the identical pipeline — same gates, same
spike test, same refinement rule — produces nothing at all from the short side, the long side
survived the holdout. Where it produces a candidate just as readily from the short side, the long
side did not. The uniform-grid asymmetry test agrees with it, which is unsurprising since they
measure the same thing two ways.

**PBO and walk-forward got it backwards.** They selected 60m and 15m; 60m was the second-worst
result on the holdout. Both are computed *within* the research block, so both are answering
"does selection work on this sample" — and on a sample where the whole family is a directionless
breakout effect, selection works fine and predicts nothing about the next sample.

† 5m's PBO of zero is not a pass; only 1% of its universe is profitable, so the in-sample winner
beats the out-of-sample median of a uniformly bad field every time.

### 4.2 The control p-value did not survive selection, and the short mirror shows why

On the research block the 60-minute long winner beat its matched control by **$69.10 a trade at
p = 0.002**. The **short** winner, chosen by the identical procedure on the side the sample was
against, beat *its* control by **$122.17 a trade at p = 0.008**. Both were emphatic; both were
wrong. On the holdout the long went to −$35.21 of excess (p = 0.86) and the short to −$40.49
(p = 0.76).

The control is not the problem — §3.4's grid-wide result is entirely built on it and is the
strongest evidence here. What fails is quoting a control p-value for a configuration the search
selected, because the objective and the excess are correlated and the maximum of 645,120 cells is
extreme in both. The way to keep the control honest is to compute it **before** selection, over the
space, which is what §3.4 does and what §3.3's mirror table does.

### 4.3 The one that survived

US30, 15-minute bars, entries 07:00–11:00 New York, flat at 11:00.

```
entry channel   System 1: 20 bars (5 hours)    System 2: 60 bars (15 hours)
trailing exit   channel exit OFF -- the ATR stop alone
stop            2.5 x ATR(20), re-anchored to every fill, LIVE ON THE ENTRY BAR
pyramid         add 0.5N in favour, up to 4 units
take profit     2R
System 1 filter skip the next System 1 entry after a winner
```

| | research (2016-10 → 2022-06) | **locked (2022-06 → 2025-07)** |
| --- | --- | --- |
| trades | 1,347 | **898** |
| net | $51,662 | **$16,789** |
| per trade | $38.35 | **$18.70** |
| Sharpe (annualised, per session, zero-filled) | 0.466 | **0.222** |
| profit factor | 1.107 | **1.039** |
| win rate | 39.0% | 35.4% |
| max drawdown | $24,642 | **$40,672** |
| MAR | 2.10 | **0.41** |
| matched-control excess | +$60.00 (p 0.002) | **+$28.17 (p 0.110)** |
| break-even cost multiple | 2.10× | **1.55×** |
| Newey-West *t* | — | **0.42** |
| Sharpe 95% CI (stationary bootstrap) | — | **[−0.83, 1.31]** |

Exit split on the holdout — the protocol asks for this first, because "profitability" that is really
one exit reason is not an edge:

| exit | trades | net | per trade |
| --- | --- | --- | --- |
| ATR stop | 470 | −$376,719 | −$801.53 |
| take profit (2R) | 148 | +$314,131 | +$2,122.50 |
| session flatten (11:00) | 280 | +$79,378 | +$283.49 |

The 2R take-profit is doing the work, and the 11:00 flatten is a small positive rather than a tax —
which is the one structural thing that transferred cleanly from research to holdout.

Cost sensitivity on the holdout: **+$35.82** a trade at 0.5×, **+$18.70** at 1×, **+$1.57** at
1.5×, **−$15.56** at 2×. It clears the protocol's 1.5× gate with almost nothing to spare.

By year on the holdout: 2022 +$25,860 · 2023 −$1,866 · 2024 −$24,457 · 2025 +$17,252. Two years of
four profitable, and 2024 gives back most of 2022.

### 4.4 The verdict

**6 of 10 gates.** It fails the ones that matter most for a claim of edge:

| | |
| --- | --- |
| PASS | ≥ 100 OOS trades (898) · positive net edge (+$18.70) · PBO 0.270 · survives 1.5× costs (+$1.57) · surface is a plateau (0.85) · no single year > 60% of gains (60%) |
| **FAIL** | **HAC *t* 0.42** (needs > 2) · **Deflated Sharpe 0.0000** (needs > 0.95) · **profitable in 50% of years** (needs ≥ 60%) · **walk-forward efficiency −0.38** (needs ≥ 0.4) |

The Sharpe's 95% confidence interval is **[−0.83, 1.31]**. The minimum track record length needed to
establish the result at 95% is **13,681 sessions — 54 years**. The Monte Carlo trade reshuffle puts
the median drawdown at $36,225 and the 95th percentile at $55,679 against a $16,789 gain.

This is not a tradeable strategy. It is the only configuration out of 14.2 million that did not
lose money out of sample, and it did so at a Sharpe of 0.22, a profit factor of 1.04 and a
drawdown two and a half times its total gain. Under `docs/RESEARCH_PROTOCOL.md` §4 the correct
reading is:

> *These rules, on this instrument, in this session, at this timeframe, under this cost model, over
> this sample, do not demonstrate an edge.*

---

## 5. What would move this, in order of expected value

**1. Change the cost regime — but the arithmetic says it is not enough here.** At half the modelled
round turn the holdout Sharpe goes 0.22 → 0.43 and the profit factor 1.04 → 1.08. Better, and still
not tradeable. The gross edge is $52.95 a trade against $34.26 of cost; even free execution leaves
a Sharpe under 0.5.

**2. Widen the window.** This is the constraint that costs the most. §2 measured it directly: the
same presets that score 0.47–0.78 with a multi-day hold score 0.05–0.30 confined to 07:00–11:00.
The Turtle's mechanism is the multi-day hold, and four hours is not enough room for it. A version
of this study with the session unconstrained would be answering a different question, but it is the
question with the better prior.

**3. Trade the instrument the edge is on.** §3.4 is unambiguous: on US30 a random configuration of
this family beats a matched random entry 60–87% of the time; on gold and BTC the median
configuration is *worse* than a random entry. Whatever the Donchian break is measuring, it is a
property of the index and not of the metal or the coin. Two more index files — NQ, ES, DAX — would
test that directly, and cross-instrument agreement on three indices would be worth more than
anything another parameter axis can buy.

**4. Stop searching this space.** 14.2 million cells produced one survivor at Sharpe 0.22. The
family's uniform-grid median Sharpe is −0.05 at 30 and 60 minutes and −1.11 at 5. There is no
corner of this grid that has not been looked at, and the one thing the search reliably produced was
research-block winners that lose money out of sample.

**Do not re-run the geometry sweep on this data.** Do not re-run it on gold or BTC at all.

---

## 6. What ships

`TurtleScalp_0700_1100.pine`, generated by `research/turtle_emit.py`, with the 15-minute
configuration as the default preset and the original 20/55 Turtle alongside it for comparison. The
presets that failed the holdout are included and **labelled with the number they failed at**, so the
next person to look at this data does not rediscover them.

It is a paper-trading candidate under §3 of the protocol, and it has not earned more than that.

---

## 7. Second pass: is any of it an edge rather than exposure?

The obvious follow-up question is whether a more profitable, higher-Sharpe, *less market-correlated*
version exists. Answering it needed a different objective and a different holdout.

### 7.1 What the shipped champion actually is

Regress the strategy's session P&L on the market's own 07:00-11:00 move and the picture changes
completely:

| block | sessions | trades | net | Sharpe | **residual Sharpe** | beta | **beta's share of P&L** |
| --- | --- | --- | --- | --- | --- | --- | --- |
| research-A 2016-10 → 2020-10 | 1,230 | 941 | $12,284 | 0.186 | **0.008** | 0.490 | **96%** |
| research-B 2020-10 → 2022-06 | 527 | 406 | $39,379 | 0.922 | 1.343 | 0.670 | −26% |
| locked 2022-06 → 2025-07 | 946 | 898 | $16,789 | 0.222 | **0.032** | 0.578 | **87%** |

Two things fall out of that table, and neither is visible in a raw Sharpe.

**On the holdout, 87% of the profit is market exposure.** Strip the beta and the Sharpe goes
0.222 → **0.032**, and $16,789 becomes **$2,147 of alpha**. The strategy is close to "be long the
Dow from 07:00 to 11:00 at 0.58 units-equivalent". The matched control differences out *some* of
this — it is long too — but not all, because a control drawn at random has a different holding
profile from a breakout's, which is why its excess (+$28.17/trade, p 0.110) reads more favourably
than the regression does.

**Its research-block Sharpe of 0.466 came from one 20-month window.** research-B is 20% of the
research sessions and 76% of its profit; on research-A the residual Sharpe is 0.008. The protocol's
gate 9 (no single period > 60% of P&L) is applied to the *out-of-sample* record; applied to the
research block it would have flagged this candidate before it was ever chosen. That is a gap in the
procedure, not in this strategy.

### 7.2 The objective and the split, both changed

`resid_sharpe` — the Sharpe of what remains once the session's market move is regressed out —
replaces raw Sharpe as the thing being maximised. And because the locked block has already been
read once, it can no longer arbitrate a new search: the result is known, and knowing it is a channel
through which the holdout biases what gets chosen. So the research block was split again:

    research-A   sessions 0-1230     2016-10 → 2020-10   select here
    research-B   sessions 1230-1757  2020-10 → 2022-06   validate, never selected on
    locked       unchanged           already read once, not used

research-B contains the 2022 bear market, which is what a market-neutral claim has to survive.

**901,120 further configurations** per run, US30 5m and 15m, both sides, scored on research-A.

### 7.3 The search found what was asked for, and it did not transfer

Ranking on residual Sharpe does produce materially less market-coupled configurations:

| | shipped champion | best by residual Sharpe |
| --- | --- | --- |
| beta to market | 0.490 | **0.166** |
| beta's share of P&L | 96% | **30%** |
| research-A Sharpe | 0.186 | **0.584** |
| research-A residual Sharpe | 0.008 | **0.454** |

The lever is `max_hold = 4` bars. Capping the hold at an hour cuts time in market, and beta is
mechanically time-in-market × size. It is a real effect and it is exactly what was wanted.

On **research-B** it is worth nothing:

| | research-A (selected on) | **research-B (untouched)** |
| --- | --- | --- |
| trades | 1,062 | 453 |
| net | +$13,336 | **−$3,658** |
| Sharpe | 0.584 | **−0.250** |
| residual Sharpe | 0.454 | **−0.041** |
| profit factor | 1.134 | **0.952** |

### 7.4 The diagnostic that settles it

One number, computed over a sample of the 4,703 configurations that cleared the research-A gates
rather than over a winner:

> **The correlation between a configuration's research-A residual Sharpe and its research-B residual
> Sharpe, within the gate survivors, is −0.057.**

Selection carries no information whatsoever. And the survivors do *worse* out of sample than
configurations nobody selected — 39.0% of them have a positive research-B residual Sharpe against
46.0% for a uniform random sample of the same grid. The gates are mildly anti-predictive.

The +0.775 correlation in the *unselected* sample is not a contradiction: it is the broad quality
axis, bad configurations being bad in both blocks. Condition on being good in research-A and every
bit of that signal is gone. This is the same lesson as §4.1's PBO result, measured directly on the
quantity of interest instead of through a rank statistic.

### 7.5 The last mechanism: a resting-limit entry

`CLAUDE.md` records the entry mechanic as the largest single lever found on this repository — a
resting limit 0.75 × ATR in your favour beats a market order on every bar with no rule at all — and
also records that it **substitutes for a signal rather than complementing one**. A breakout is the
case where that should bite hardest, because the edge of a break is in the immediacy of the move.

Implemented (`limit_k`, `limit_bars`; engine, tensor and the literal Pine reference all agree
across 64 configurations) and measured across four different geometries on research-A:

| limit_k | median trades | median Sharpe | median residual | median beta | median $/trade |
| --- | --- | --- | --- | --- | --- |
| 0.00 (market) | 1,115 | −0.022 | −0.218 | 0.363 | **+1.18** |
| 0.25 | 1,012 | −0.184 | −0.388 | 0.348 | −11.33 |
| 0.50 | 928 | −0.387 | −0.528 | 0.208 | −12.92 |
| 0.75 | 821 | −0.156 | −0.318 | 0.186 | −8.31 |
| 1.00 | 701 | −0.198 | −0.326 | **0.137** | −2.67 |

It does what was hoped to beta — 0.363 down to 0.137, because a limit that never fills is a trade
never taken — and it destroys the return doing it. No geometry improves consistently. The finding
replicates on a family it was never measured on.

### 7.6 Verdict on the second pass

Nothing shipped changes. There is no more profitable, higher-Sharpe, lower-correlation version of
this strategy in this data:

* optimising directly for market-neutrality **works on the block it is optimised on and nowhere
  else**, and the selection is anti-predictive out of sample;
* the one untried mechanism with a documented track record on this repository **is destructive
  here**;
* and the strategy that does ship is now known to be **87% market exposure on the holdout**, with a
  research-block record that rests on a single 20-month window.

That last point is the one worth acting on. If the goal is a low-correlation intraday edge, this
family is the wrong place to look for it: what it has is a small entry-timing effect sitting on top
of a large directional exposure, and removing the exposure removes the profit. §5's ranking is
unchanged — more index instruments, or a wider window — with one addition at the top: **rank on
residual Sharpe from the start**, and apply the sub-period gate to the research block, not only to
the holdout.
