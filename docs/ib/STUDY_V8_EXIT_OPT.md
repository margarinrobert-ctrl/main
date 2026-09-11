# Version #8 on US30, 07:00–10:00: the exits are not the problem

A ten-part optimisation of Version #8 — Donchian 30/20, 2.5×ATR stop, 3 units, ADX ≥ 15, TP 2R —
against a PF ≥ 1.80 target inside a hard 07:00–10:00 New York window. US30 ISO 15-minute,
48,937 bars, 2024-08-19 → 2026-08-26. Train = pre-2026; **2026 was read once, at the end.**

Cost 3.216 points per unit round turn, set to the same **fraction of the 2N stop** that NQ pays.

---

# CORRECTION — a ladder bug invalidated the partial-exit results

**Everything below this section that involves a PARTIAL EXIT was wrong when first published.**
`eem.run` keyed the ladder off the *live* position size:

```python
while size < max_units and h[j] >= nxt:      # WRONG
```

A partial exit reduces `size`, which makes `size < max_units` true again — so the ladder
**re-opened a unit it had just closed**. Trades finished at 1.5 units on a `max_units=1`
configuration. It was found by building the V9 parity harness (`research/v8opt/v9_parity.py`) and
noticing that target-hit trades paid +270.53 in the engine against +133.48 in the port, where
+133.48 is what the arithmetic says. The fix counts units *opened*, not units live.

### What changed

| | as published | corrected |
| --- | ---: | ---: |
| **Config D** (3 units + partial + trail) train → OOS | 1.38 → 1.29 | **1.10 → 0.95** |
| Config A (structure + partial) train → OOS | 1.67 → 1.18 | reject either way |
| Partial exits, train, vs 1.05 baseline | 1.14 – 1.19 | **0.82 – 1.02** |
| 1-unit prop config train → OOS | 1.87 → 1.62 (never published) | **1.12 → 0.98** |
| Peak prop P(pass) / P(bust) | 44.9% / 45.1% | **no positive-edge cell at 30 days** |

**Partial exits are worth approximately nothing here.** The apparent 1.14–1.19 "plateau" was the bug
applying uniformly across the block — which is exactly why a flat, consistent improvement looked
like a robust one.

### What did NOT change

Everything without a partial exit, which is most of the study: the baseline, the 88-cell stop ×
target grid, the window analysis, the exit-efficiency model, the break-even / trailing / structure /
time rows, the entry-vs-exit control, and the walk-forward. The three headline findings stand — the
window costs two-thirds of the result and doubles drawdown, the target surface wants to be further
out, and the entry does not beat a matched random entry.

### The corrected recommendation

Not Config D. **One unit, 2.0N stop, 200-point target, 100-point trail, no partial**:

| | n | PF | pts/trade | max DD |
| --- | ---: | ---: | ---: | ---: |
| all hours, train | 752 | 1.12 | +4.31 | 1,573 |
| all hours, OOS 2026 | 423 | **1.20** | +7.14 | **1,488** |
| 07:00–10:00, full span | 349 | 1.23 | +8.66 | **1,172** |

Profit factor is ordinary. **Drawdown is a third of Version #8's** (4,428 all-hours, 6,685 in the
window), and drawdown is what an evaluation kills you for. Dropping the ladder from three units to
one is the whole of that improvement, and it replicates a finding already on this branch
(`STUDY_TURTLE_15M`: one unit is the lowest-drawdown answer).

### The prop-firm answer, corrected

Under a 30-day / 6% / 4%-trailing evaluation, **nothing passes**: every size large enough to reach
the target in 30 days busts more often than it passes. The binding constraint is the *evaluation*,
not the strategy — same rules, same sizing, $0.50/point:

| rule set | 4 ctr | 6 ctr | 10 ctr |
| --- | ---: | ---: | ---: |
| 30 days, 4% trailing | 0% / 0% | 5% / 7% | 25% / 37% |
| 90 days, 4% trailing | 17% / 10% | 39% / 30% | 45% / 54% |
| 180 days, 4% trailing | **48% / 21%** | 53% / 44% | 46% / 54% |
| 90 days, 4% **static** | 14% / 4% | **39% / 12%** | 59% / 32% |
| 60 days, 4% static | 5% / 2% | 22% / 8% | 47% / 29% |

*(pass / bust)*. The static-drawdown, no-time-limit cells are the only region in this entire study
where pass probability meaningfully exceeds bust probability.

Shipped as `pine/turtle/TURTLE_V9_PROP_strategy.pine`, parity-checked at 96.7–98.9% signal match
and 0.949–0.970 per-trade correlation against the engine.

---

## The answer to the question that was actually asked

**PF ≥ 1.80 is not reachable here, and the ceiling is not close.** Across an 88-cell stop × target
grid, ~50 exit models, and six walk-forward folds, the best in-sample profit factor inside the
window is **1.67**, and it decays to **1.18** out of sample. **0 of 6** walk-forward folds reach 1.80.
Nothing was filtered to force the number, and nothing needs to be: the in-sample *maximum* already
sits below the target.

## The window is a large negative, and its apparent strength is a 2026 regime

| | n | PF | pts/trade | max DD |
| --- | ---: | ---: | ---: | ---: |
| all hours, train | 635 | **1.31** | +36.65 | 3,374 |
| all hours, OOS 2026 | 309 | **1.19** | +28.96 | 4,428 |
| 07:00–10:00, train | 208 | **1.05** | +5.46 | 6,685 |
| 07:00–10:00, OOS 2026 | 128 | 1.28 | +37.55 | 3,286 |

The window costs two-thirds of the per-trade result **and raises drawdown** — 6,685 against 3,374
on a third of the trades. And it shows the **wrong shape**: worse on train, better on the block it
never saw. So do five of the six 30-minute sub-windows:

| sub-window | n train | PF train | n OOS | PF OOS | shape |
| --- | ---: | ---: | ---: | ---: | --- |
| 07:00–07:30 | 47 | 0.69 | 29 | 1.15 | wrong |
| 07:30–08:00 | 32 | 1.57 | 20 | 2.52 | wrong |
| 08:00–08:30 | 31 | 2.02 | 27 | 1.02 | decays |
| 08:30–09:00 | 73 | 0.84 | 36 | 1.11 | wrong |
| 09:00–09:30 | 46 | 0.45 | 17 | 1.23 | wrong |
| 09:30–10:00 | 132 | 0.76 | 70 | 1.28 | wrong |

Six of seven variants improve on the *later* block. That is a property of 2026, not of a clock rule.
On the full span 07:30–08:00 shows PF 1.90 and is the only sub-window beating a matched control
(p 0.031, 0.30 expected below 0.05 from six tests) — on **52 trades**, split 32/20. It is a lottery
ticket, and this repository already has a standing rule against reading one as a finding.

## The profit-target work says the opposite of "scalp"

Train, in-window, stop held at 2.5N (= 108.7 points):

| TP (pts) | 40 | 60 | 80 | 100 | 120 | 150 | 175 | 200 | 250 | 300 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| PF | 0.60 | 0.82 | 0.90 | 0.90 | 0.97 | 0.99 | 1.07 | **1.10** | 1.06 | 0.94 |
| win | 46.1% | 42.7% | 38.7% | 34.6% | 34.0% | 31.9% | 32.1% | 32.4% | 32.0% | 30.9% |

Smooth, single-peaked, no spike — a real relationship. **It rises monotonically with target distance
to ~200 points and the 40–100 point region you asked for is the worst part of the surface.** The
88-cell joint grid says the same about the stop: PF climbs with stop width from 0.01 at 0.5N to
1.19 at 2.0N. Tight stops are destroyed; the best cell anywhere is **2.0N / TP 200 → PF 1.19**.

The arithmetic is the reason. A 50-point target against a 109-point stop needs **68% wins** to break
even; this wins 32–46%. And **median MAE is 66 points** — more than half of trades travel further
*against* you than a 50-point target is away, before they go for you. 62% see MAE ≥ 50.

## Exit efficiency: real, and mostly not fixable

208 train trades. Median exit efficiency **−0.42**; **61% of trades give back the entire favourable
excursion**. That looks like an exit problem until it is split by reason:

| reason | n | share | mean MFE | mean MAE | total |
| --- | ---: | ---: | ---: | ---: | ---: |
| stopped out | 120 | 57.7% | **50.3** | 102.7 | −19,114 |
| target hit | 38 | 18.3% | 243.0 | 23.2 | +17,851 |
| session flat | 50 | 24.0% | 112.4 | 55.2 | +2,400 |

**The 57.7% that stop out reach a mean MFE of 50 points against a 109-point stop.** They never went
anywhere. No exit rule recovers a trade that does not move in your favour, and that is where all
the loss is.

Excursion frequencies: 59.6% reach +50, 47.1% reach +75, 40.9% reach +100, 14.9% reach +200. Of the
trades that reach +50, **31% die before +100**.

## A look-ahead worth 0.2 profit factor

The first exit-model sweep made a trailing stop the best model at PF 1.37 and made break-even stops
look catastrophic (PF 0.19–0.54). Both were artefacts: the engine updated the running peak from the
current bar's high and then tested the same bar's low against it, assuming the high came first.
Reading the peak only from bars that have closed moved trailing 40p from **1.37 → 1.16** and
break-even from 0.19–0.54 to a roughly neutral **0.97–1.06**. *A trailing level may only read bars
that have closed.*

## What the exit models are worth once that is fixed

~50 models on train. Partial exits are a genuine, small, **flat** improvement — 1.14–1.19 across the
whole 25/50/75% × 50/75/100pt block, which is a plateau rather than a peak. Break-even is neutral.
Time stops are neutral to negative. The structure-only exit (channel, no ATR stop) is the best on
train at 1.35 — **and the most fragile**, falling to 0.96 out of sample.

## The three configurations, chosen on train and read once

| | train PF | OOS PF | OOS pts/tr | OOS DD | verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| **A** structure exit + partial 50%@75 | **1.67** | 1.18 | +32.28 | 5,648 | closest to target, **decays hardest — reject** |
| **B** 2.0N + TP200 + partial 50%@75 | 1.19 | 1.39 | +42.77 | 2,310 | wrong shape; the 2026 regime again |
| **D** 2.0N + TP200 + partial 50%@75 + trail 100p | 1.38 | **1.29** | +28.57 | 2,522 | correct shape, best drawdown — **the recommendation** |

D is the only candidate that is strong on train, decays gently, and holds the lowest drawdown on
both blocks. Perturbation on D: TP ±10% moves PF by ±0.01, partial point ±10% by ±0.02, trail +10%
by +0.01 — a **ridge**. The one sensitive axis is the stop: −10% costs 0.21. Random 10% trade
omission gives PF p5 1.24 / median 1.34. Trade-order Monte Carlo over 20,000 shuffles: realised max
DD 2,757 against a median of 2,856, so the sequence was mildly **lucky**. Bootstrap mean 95% CI
**[+0.3, +56.8]**, P(mean ≤ 0) = 0.024 — positive, and barely.

## Walk-forward

Six chronological folds, no refit:

| | folds PF > 1 | median | min | max | folds ≥ 1.80 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 07:00–10:00 | 4/6 | 1.30 | 0.49 | 1.54 | **0/6** |
| all hours | **6/6** | 1.22 | 1.11 | 1.67 | 0/6 |

All hours is less spectacular and more consistent. That is the robustness ordering.

## Entry or exit?

Against a matched random entry — same window, same geometry, same trade count — the breakout entry
returns **p = 0.347** in the window and **p = 0.278 / 0.273** at all hours on train and OOS. It does
not beat entering at a random bar with the same stop and target.

This is a *different* control from `STUDY_MEGA_144K`'s p 0.0013, and both are true: that one was a
**selectivity** control (does ADX ≥ 15 help *given* you take breakouts — yes), this is an **entry**
control (does the breakout beat a random bar — no). The gate earns its keep; the trigger does not.

**So the weakness is not the exit.** Ranked: (E) time-of-day first — the window costs 2/3 of the
result and doubles drawdown; (A) entry second — indistinguishable from random; (C) target third —
correctly identified as too near in the scalp region, and the fix is to widen it, not tighten it.

## Prop firm, 30 days

Config D, 1.21 trades/day in the window (~36 in 30 days), $0.50/point (MYM), 6% target / 4% trailing
/ 2% daily:

| contracts | risk/trade | P(pass) | P(bust) | median 30d |
| ---: | ---: | ---: | ---: | ---: |
| 3 | $130 | 5.0% | 1.8% | +1,505 |
| 5 | $217 | 25.3% | 20.6% | +2,284 |
| **8** | **$348** | **44.9%** | **45.1%** | +2,498 |
| 12 | $522 | 42.4% | 57.4% | +577 |
| 20 | $869 | 37.2% | 62.7% | −1,051 |

Peak **44.9% P(pass) against 45.1% P(bust)**. Better than the 34.6% ceiling in `STUDY_MEGA_144K`,
because 30 days gives less time to bust than 120 and D's drawdown is lower — but it is still a coin
flip, and every contract size past 8 buys bust probability faster than pass probability.

## What would actually move this

Not exits. The window is the largest single negative and it was imposed, not found; the entry does
not beat random; and the target is already at the far end of a surface that wants it further out.
The honest paths are: **drop the window** (all hours, 6/6 folds positive, PF 1.19 OOS), **replace
the trigger** (it is the component failing its control), or accept **PF ≈ 1.3 with a 45% evaluation
pass rate** as what this family is.
