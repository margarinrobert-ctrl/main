# The 09:00 range breakout on 1-minute US30: feature engineering against a dead primary

**Question asked:** engineer features and timeframe parameters until the 09:00 range breakout
reaches profit factor 2, on 1 minute or wherever it works, using whatever quant technique helps.

**Answer:** profit factor 2 was reached — **PF 2.476 at 1 minute, and PF 3.898 on the grid's best
cell** — on the block the search was allowed to see. The same two configurations read **PF 0.859
and PF 0.749** on the block it was not. Every route to PF 2 found here is a route to PF 2 *on the
research block only*, and the study is mostly an account of how cleanly that can be demonstrated.

The load-bearing number is not any profit factor. It is that **White's Reality Check over the
declared grid returns p = 0.7495** — a set of worthless candidates searched this hard produces a
winner this good three times out of four — and that the **deflated Sharpe of the winner is 0.124,
below the 0.194 that 960 pure-noise trials would be expected to throw up on their own.**

---

## 0. The data, and what it can and cannot support

`US30_30s.csv`, 390,552 thirty-second bars, 2025-08-18 → 2026-09-16, 293 sessions. Clean: no
duplicate stamps, no out-of-order stamps, no impossible OHLC, no NaNs, every price on the 0.01
grid, no return beyond 10 robust (MAD) sigma.

**One structural fact reshapes the whole question, and it is a property of the file:**

| | sessions |
| --- | --- |
| total in file | 293 |
| containing 09:00-09:15 — the range the strategy is named for | **92** |
| containing 09:30-10:00 | 271 |

Everything before 2026-04-30 starts at 09:30. The 09:00 range therefore does not exist for 69% of
the sample, and on the 92 sessions that do have one the whole strategy produces 101 trades at
15 minutes — a sample that cannot resolve an effect of the size in question. The range window is
a declared input of the script, so it was swept as a parameter rather than assumed, and the
09:30-anchored windows carry the statistical weight.

**Thirty-second source data is the one asset here.** Every earlier study on this branch had to
book a bar containing both the stop and the target as a loss, because the intrabar path was
unknown. The exit walk in `research/nineam/sim.py` steps the 30-second array, so that race is
observed rather than assumed: **0 ambiguous bars** across every configuration run.

Accounting: $1 per index point, round turn **2.29 points** (the figure this branch already uses
for US30), plus 0.5 points of extra slippage when the exit is a stop. Costs are applied at read
time and never baked into the cached gross, so the cost sweep below is free.

The split is the **first 65% of sessions**, computed on the sessions each window can actually
produce, so shortening the window cannot silently move the boundary.

---

## 1. Engine parity, before any result

`research/nineam/sim_test.py` reimplements the rule the slowest, most obvious way and requires the
fast numba state machine to agree on **every field of every trade** across five configurations
spanning 1m to 30m, ATR and R targets, and a no-flatten variant.

```
tf=15m 540-555 stop1.5 tgt0.0 none  ref= 101 fast= 101  OK
tf= 5m 570-585 stop1.0 tgt2.0    r  ref= 350 fast= 350  OK
tf= 1m 570-600 stop2.0 tgt3.0  atr  ref= 319 fast= 319  OK
tf= 3m 570-585 stop1.5 tgt0.0 none  ref= 354 fast= 354  OK
tf=30m 540-570 stop2.5 tgt1.0    r  ref=  95 fast=  95  OK
```

---

## 2. GATE 1 — the primary alone, before a single feature exists

The declared grid: **6 timeframes × 5 windows × 2 sides × 4 stops × 4 targets = 960 cells**,
scored on research only, each against a matched random control with the same side, geometry and
minute-of-day distribution.

| | 09:00 anchor (92 sess) | 09:30 anchor (271 sess) |
| --- | --- | --- |
| cells profitable on **research** | 31.0% | 36.3% |
| median PF | 0.884 | 0.957 |
| **cells reaching PF ≥ 2.0** | **0 of 384** | **0 of 576** |

**Not one cell in 960 reaches PF 2 on the research block**, before any holdout is involved.

Against the matched control: **9 of 960 cells clear p ≤ 0.05 where 48.0 are expected by chance** —
five times *fewer* than chance, meaning the rule sits systematically *below* random entries of the
same geometry. **0 of 960 cells exceed their own minimum detectable effect.**

### The grid's marginal averages — the only reading taken from it

The maximum of 960 looks is not evidence. The marginals are.

| timeframe | $/trade | median PF | | window | $/trade | median PF |
| --- | --- | --- | --- | --- | --- | --- |
| **1m** | **−2.41** | 0.977 | | 09:00-09:15 | −9.17 | 0.852 |
| 2m | −5.07 | 0.894 | | 09:00-09:30 | −5.56 | 0.913 |
| 3m | −5.43 | 0.895 | | 09:30-09:45 | −6.09 | 0.902 |
| 5m | −3.90 | 0.966 | | **09:30-10:00** | **+2.96** | **1.045** |
| 15m | −3.81 | 0.951 | | 09:30-10:30 | −3.88 | 0.935 |
| 30m | −5.46 | 0.950 | | | | |

| side | $/trade | | stop ×ATR | $/trade | | target | $/trade |
| --- | --- | --- | --- | --- | --- | --- | --- |
| long | −3.23 | | 1.0 | −4.70 | | none | −5.37 |
| both | −5.46 | | 1.5 | −4.28 | | 1R | −6.41 |
| | | | 2.0 | −5.05 | | 2R | −2.81 |
| | | | **2.5** | **−3.36** | | **3R** | **−2.79** |

Read plainly: **1 minute is the least-bad timeframe of the six**, which is the direct answer to
"make it work on 1 minute" — it is the best of a set in which every member is negative. The only
positive marginal anywhere in the table is the 09:30-10:00 window. Every stop and every target
marginal is negative.

The grid's best single cell reads PF 1.740 at $15.36/trade. The grid's own dispersion is
$10.3/trade, so **E[max of 960 pure-noise looks] ≈ $38.1/trade** — the winner is not merely
unproven, it is *smaller than what noise alone would have produced.*

### Gate 1 verdicts

| primary | research | PF | $/trade | bootstrap p | verdict |
| --- | --- | --- | --- | --- | --- |
| P1 1m 09:30-10:00 long 2.5N 3R | 109 tr | 1.044 | +2.03 | 0.391 | MARGINAL |
| P2 1m 09:30-10:00 both 2.5N 3R | 210 tr | 1.078 | +3.74 | 0.310 | MARGINAL |
| P3 1m 09:30-10:30 both 1.0N none | 187 tr | 1.740 | +15.36 | 0.043 | PASS\* |
| P4 5m 09:30-10:00 long 2.5N 3R | 109 tr | 1.096 | +6.66 | 0.330 | MARGINAL |

\* P3's "PASS" is the maximum of the 960-cell grid. A gate applied to the winner of a search is
not a gate; it is the search reported twice. It is carried forward specifically so the next
section can show what meta-labelling does to a cell already selected on its maximum.

**The mechanism-first verdict: the primary does not clear Gate 1.** A meta-labeller trades recall
for precision and cannot create direction skill, so nothing downstream can be credited with
rescuing it. The rest of the study measures how convincingly it appears to anyway.

---

## 3. The features, and proof they are causal

22 features in five families, every one read at the **SIGNAL bar** — never `ent_bar`, which is the
fill bar and closes after the order is sent.

| family | features |
| --- | --- |
| A range geometry | range width in ATR, break extension, bars since arm, close-in-range, extension vs range |
| B volatility | ATR(14)/ATR(50), ATR vs trailing, bar vs ATR, prior-day range |
| C location | distance to EMA200 *in ATR*, 13−48 spread, distance to prior close, position in prior day's range, distance to range midpoint |
| D microstructure (30s) | close position in bar, path efficiency, upper wick share, share of 30s bars making a new high, pullback from the bar's high |
| E session | gap, opening drive, volume vs trailing |

Family D is the one this file could build that the rest of the branch could not, because the
source is 30-second. Distance-to-EMA200 is offered as a **distance** rather than a state, because
STUDY_V40 found the MA200 is priced by its distance. **No calendar conditions** — weekday and
month partition the sample and hand the search a free lottery. **No global standardisation** —
every scaler is fit inside the training fold.

**Causality audit:** 40 probes truncate the series at the feature's own bar, rebuild from scratch,
and compare. **0 mismatches.** A feature that peeks cannot survive truncation.

---

## 4. GATE 2 — the meta layer, unsized, against a random filter of the same selectivity

The architecture: the primary emits events, the features only score them. Labels are the realised
triple-barrier outcome of **every** event (the one-position lock is removed for labelling, since
whether an event is worth taking must not depend on which other events happened to be open).
Folds are **purged and embargoed** by the label-overlap horizon.

Two refusals, both load-bearing:

* the gate is applied to the **triggers** and the book is **re-simulated**. A conditional split of
  realised trades is not a filter test.
* the gate is scored against a **random filter keeping the same number of events**, re-simulated
  end to end — not against the ungated rule, because total dollars falls for every restrictive
  condition and per-trade edge rises for every one.

84 trials: 4 primaries × 3 models (logit / random forest / gradient boosting) × 7 keep-thresholds.

| | |
| --- | --- |
| rows reaching **PF ≥ 2.0 on research** | **17 of 84** |
| rows clearing the random filter at p ≤ 0.05 | 13 of 84 (4.2 expected) |
| **median out-of-fold AUC** | **0.500** |
| out-of-fold AUC range | 0.381 – 0.622 |

**The median out-of-fold AUC is exactly 0.500 — no skill.** The models order the events no better
than a coin flip out of fold, while 17 rows nevertheless reach the requested profit factor.

---

## 5. The locked block, read once, multiplicity first

**Configurations evaluated in this study: 1,065** (960 grid + 84 meta + 20 user-config + 1 fade).

| accounting | value | verdict |
| --- | --- | --- |
| White Reality Check over the grid | **p = 0.7495** | FAIL |
| best candidate mean vs null max p95 | $20.62 vs $43.51 | FAIL |
| Deflated Sharpe of the winner | **0.124** | FAIL |
| winner per-session Sharpe vs E[max \| 960 noise trials] | 0.117 vs **0.194** | below noise |
| effective trials (mean pairwise corr 0.112) | 852 of 960 | — |
| **PBO (CSCV, 3,432 partitions)** | **0.737** | selection is worse than random |

PBO above 0.5 means a better research number is *actively bad news*. At 0.737 the median
out-of-sample rank of the in-sample winner is 0.296.

### The reveal

| candidate | research | | | LOCKED | | | vs matched random (locked) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| | n | PF | $/tr | n | PF | $/tr | |
| P2 primary alone | 210 | 1.078 | +3.74 | 120 | **0.805** | −10.67 | pctile 25.5, p 0.746 |
| **P2 + logit meta, keep 40%** | 84 | **2.476** | +48.47 | 69 | **0.859** | −7.71 | pctile 38.5, p 0.616 |
| **P3 gridmax + logit meta, keep 30%** | 56 | **3.898** | +50.87 | 41 | **0.749** | −6.65 | pctile 39.5, p 0.606 |
| P3 primary alone | 187 | 1.740 | +15.36 | 104 | 0.925 | −1.85 | pctile 60.2, p 0.399 |
| Fade (P2 events traded the other way) | 200 | 1.027 | +1.34 | 107 | 0.973 | −1.42 | — |

The requested profit factor was reached twice. Both readings inverted.

### It is not the costs

| cost multiple | research PF | locked PF |
| --- | --- | --- |
| 0.0× (free trading) | 2.620 | **0.904** |
| 0.5× | 2.546 | 0.881 |
| 1.0× (modelled) | 2.476 | 0.859 |
| 1.5× | 2.408 | 0.838 |
| 2.0× | 2.343 | 0.818 |

**At literally zero cost the locked block still reads PF 0.904.** No execution improvement, broker
change or fee rebate reaches this. The failure is signal, not friction.

### The threshold neighbourhood — the shape that settles it

| keep | n res | PF res | $/tr res | n lock | PF lock | $/tr lock |
| --- | --- | --- | --- | --- | --- | --- |
| 90% | 189 | 1.279 | +12.55 | 111 | 0.874 | −6.80 |
| 80% | 168 | 1.377 | +16.36 | 103 | 0.928 | −3.92 |
| 70% | 147 | 1.682 | +26.94 | 96 | 0.787 | −11.89 |
| 60% | 126 | 1.913 | +34.00 | 90 | 0.812 | −10.55 |
| 50% | 105 | 2.210 | +42.06 | 76 | 0.920 | −4.28 |
| 40% | 84 | 2.476 | +48.47 | 69 | 0.859 | −7.71 |
| 30% | 63 | 3.205 | +59.37 | 51 | 0.947 | −2.94 |

Research PF climbs **monotonically** from 1.279 to 3.205 as the gate tightens. Locked PF does not
move with it at all — it wanders between 0.787 and 0.947 with no relationship to the threshold.
The model's confidence score orders the research block almost perfectly and carries **zero**
information on the locked block. A real edge decays across a neighbourhood; this does not decay,
it simply is not there.

### Where the money went

| exit | research | | locked | |
| --- | --- | --- | --- | --- |
| | trades | net $ | trades | net $ |
| stop | 41 (49%) | −2,759 | 50 (**72%**) | −3,725 |
| target | 36 (**43%**) | +6,419 | 12 (**17%**) | +2,389 |
| flatten | 7 (8%) | +412 | 7 (10%) | +804 |

The target-hit rate more than halves, 43% → 17%, and the stop share rises 49% → 72%. The win rate
falls 51.2% → 21.7%. The meta layer learned which research-block events reached a 3R target, and
that mapping did not exist on the next 95 sessions.

---

## 6. The settings from the screenshots, measured

Panel settings as shown: range 09:00-09:05, earliest entry 09:28, both sides, fresh 13×48 EMA
cross within 7 minutes, 100-point stop, 100-point target, breakeven arming at 43 securing 5,
flatten 16:00. On the 92 sessions that have a 09:00 range:

| timeframe | sessions | trades | **stop ÷ ATR** | PF research | PF locked |
| --- | --- | --- | --- | --- | --- |
| 1m | 33 | 33 | **4.16** | 0.499 | 0.349 |
| 3m | 13 | 15 | 2.48 | 0.393 | 0.497 |
| 5m | 13 | 15 | 1.97 | 0.497 | 1.015 |
| 15m | 9 | 9 | 1.28 | 1.015 | — (9 trades) |

**A 100-point stop is 4.16 × ATR at 1 minute and 1.28 × ATR at 15.** It is not one geometry
carried across timeframes; it is four different strategies wearing one number. This is the single
most actionable finding for anyone moving this script down a timeframe.

### Decomposition at 1 minute, 09:30 anchor, all 271 sessions

| variant | trades | PF research | PF **locked** |
| --- | --- | --- | --- |
| MA gate off | 355 | 1.025 | 0.743 |
| MA gate = fresh 13×48 cross | 66 | 1.367 | 1.079 |
| MA gate = state (13 > 48) | 325 | 0.957 | 0.797 |
| breakeven off | 350 | 0.974 | 0.899 |
| breakeven on, 43 / 5 | 355 | **1.025** | **0.743** |
| no target | 349 | **1.259** | **0.643** |
| target 100 pts | 350 | 0.974 | 0.899 |
| target 200 pts | 350 | 1.123 | 0.927 |

Three readings worth keeping:

1. **The breakeven improves research and damages locked** (0.974 → 1.025 research, 0.899 → 0.743
   locked). That is the same sign the script's own header already records for this mechanic from
   an independent sample, now reproduced on a fourth block.
2. **"No target" shows the largest research-to-locked inversion in the table** — PF 1.259 at the
   85th control percentile on research, PF 0.643 on locked. The 100-point target currently set is
   the more robust of the choices available.
3. **The fresh-cross gate cuts 81% of trades** (355 → 66) to buy a locked PF of 1.079 on 25
   locked trades, which is not a resolvable quantity.

---

## 7. What would actually change the answer

Nothing in the parameter space. The grid is 34% profitable on the block it was fitted to, its
winner is smaller than noise of the same search size, and its selection procedure has PBO 0.737.
Searching it harder moves all three the wrong way.

| lever | why it might matter |
| --- | --- |
| **more history** | 271 usable sessions and ~330 events is the binding constraint. Every MDE in this study exceeds every effect in it. The screenshots' own four-year run is the right sample; this file is 13 months of it, and 69% of that cannot form the range. |
| **a second instrument** | one instrument, one regime. A range-break mechanism that is real should appear on NQ and ES too, and the branch already has that data. |
| **a named counterparty** | Phase 0 was never passed. "Price left a 30-minute box" does not say who is forced to trade against it, which is why the event stream has no unconditional edge to refine. |
| **the execution layer** | STUDY_LIMIT_ENTRY found a resting limit 0.75 × ATR in favour earns $4.3-37.7/trade with **no rule at all**, on both blocks and both sides. That is the largest effect this branch has measured, and it substitutes for a signal rather than complementing one. It is a better use of a 30-second file than this rule is. |

---

## 8. Reproducing

```bash
python3 research/nineam/sim_test.py        # engine parity, 5 configurations, trade for trade
python3 research/nineam/run_grid.py        # the declared 960-cell grid vs matched controls
python3 research/nineam/run_meta.py        # Gate 1 + Gate 2, purged CV, random-filter controls
python3 research/nineam/run_deflate.py     # reality check, deflated Sharpe, PBO
python3 research/nineam/run_locked.py      # the locked read, multiplicity printed first
python3 research/nineam/run_userconfig.py  # the screenshot settings, decomposed
```

---

## 9. The one-line version

> The 09:00 range breakout reached PF 2.476 at 1 minute after 22 engineered features and a
> meta-labeller — on the 65% of sessions the search could see. On the 35% it could not, the same
> configuration reads PF 0.859, at zero cost it still reads 0.904, its out-of-fold AUC is 0.500,
> and White's Reality Check over the 960-cell search returns p 0.75. The profit factor was
> reachable; the edge was not.
