# 76,546 configurations of RSI + lower wick, and what survived

The starting point was `pine/oneR/BEST_60m_long_RSI14gt70_lowerwick50.pine` — `RSI14>70 AND
RSI14 rising AND lower wick>50%`, 60-minute bars, long, 2.5×ATR stop, 1.0R target, no time stop.
The brief was to search hard for versions that take **more trades** and survive Monte Carlo,
out-of-sample, walk-forward, robustness and realistic execution.

`research/tuner.py` ran the grid. Two primitives were added to `research/indpool.py` to express
the rule: `lowick` / `upwick` (wick as a percent of the bar's range) and `rsichg(n)` (one-bar RSI
change, so "RSI rising" is `rsichg14>0`). The transcription was verified against the Pine text
bar for bar before anything was searched: **153 triggers, identical**.

## The grid

| axis | values |
| --- | --- |
| RSI period | 7, 9, 14, 21, 28 |
| RSI threshold | 55, 60, 65, 70, 75 |
| RSI rising | on / off |
| lower wick % | 20, 30, 40, 50, 60 |
| timeframe | 15m, 30m, 60m |
| window | all session, 09:30–16:00, 09:30–12:00 |
| stop | 1.0, 1.5, 2.0, 2.5, 3.0, 4.0 × ATR |
| target | 0.5, 1.0, 1.5, 2.0 R |
| flatten | none, 16:00 |

**76,546 configurations**, all filtered to hold at least 102 trades — the baseline's own count —
so every survivor satisfies "more trades" by construction. Bonferroni for a single claim at that
multiplicity is **p < 6.5e-07**, which nothing below clears.

No calendar conditions were searched: weekday and month partition the sample and hand the search
a free lottery (CLAUDE.md).

## Ranking on dollars is the wrong objective, and the corner table proves it

The top 15 by research $/trade all sat on the same grid corner — stop 4.0, target 2.0. Extending
the geometry past the searched grid, rule held fixed:

| research $/trade | target 1.0 | 2.0 | 3.0 | 4.0 | 6.0 |
| --- | ---: | ---: | ---: | ---: | ---: |
| **stop 2.5×** | 22 | 42 | 81 | 115 | 284 |
| **stop 4.0×** | 44 | 231 | 351 | 521 | 333 |
| **stop 6.0×** | 127 | 528 | 518 | 479 | 938 |
| **stop 8.0×** | 336 | 827 | 748 | 807 | 1,289 |
| **stop 12.0×** | 710 | 605 | 1,014 | 856 | **1,578** |

The optimum never stops climbing — it runs off the edge of the grid to a 12×ATR stop and a 6R
target at **$1,578/trade on 9 trades**. That is the search buying **hold time** on a market that
rose 89%, not edge. It is the same pathology as `STUDY_M4_ANATOMY.md`, reached from the opposite
direction.

So ranking moved to **excess over a matched control** — random entries with the same side,
geometry, window and minute-of-day, which prices the drift and the hold time out. Candidates were
drawn **geometry-stratified** (the best rules within each of 432 geometry cells, where the
comparison between rules is fair), and 2,160 were control-tested: median excess **+$25.9/trade**,
99.7% positive, **70.5% beat their control at research p ≤ 0.05 against 5% expected**. That ratio
is inflated by picking the best rules per cell first, so it is a screen, not a claim.

Every candidate family's parameter neighbourhood was swept and found **smooth** — no single-rung
spikes, every cell positive.

## The locked block, read once

Three configurations were committed on research, then the holdout was read.

| | trades | research $/t | **locked $/t** | locked p vs control | verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| **BASELINE** your script | 102 | 86.7 | **67.7** | 0.116 | decays correctly, control not separated |
| V1 wider target, looser wick | 145 | 142.2 | **−25.9** | 0.875 | **FAILED — loses money out of sample** |
| **V2** RSI28>65 · wick>30 · 30m RTH · 4×ATR/1R | **117** | 148.2 | **220.1** | **0.004** | passes both blocks; grew on locked |
| V3 RSI28>60 · wick>50 · 60m RTH · 2.5×/2R | 60 | 201.5 | **23.4** | 0.465 | **FAILED**, and takes fewer trades |

**Two of the three chosen alternatives failed the holdout outright.** V1 had the second-highest
research figure in the whole search and loses money out of sample. This is the multiple-comparisons
tax arriving where theory says it should.

## V2, the one that survived

117 trades (vs the baseline's 102), $19,570 net, 69.2% win, PF 2.59, and it beats its matched
control on **both** blocks — research p < 0.001, locked p 0.004.

| test | result |
| --- | --- |
| matched control, 4,000 draws | research p 0.000, locked p **0.004** |
| Monte Carlo, 100,000 paths | bootstrap P(net<0) **0.00%**; p5 net $12,052 |
| permutation drawdown | median $1,507, p95 $2,396, realised $1,229 — **the realised path was luckier than median** |
| walk-forward, 6 folds, no re-fitting | **6/6 profitable** ($111–338/trade) |
| cost stress | profitable at **3× modelled friction** |
| true 1-minute path execution | **117/117 trades, identical net, 0.0% unresolved** |
| entry timing spread | 12% of the at-open result |
| parameter neighbourhood | smooth, no spike |

**Its one flag: it earns more per trade on the locked block ($220.1) than on research ($148.2).**
That is the wrong shape — an edge decays out of sample, it does not appear there. Every shipped
leg on this branch carries the same flag, so it is partly a property of this sample's later
period, but it is a caution and not a clean pass.

**Second caution: V2 depends on having no time cap.** With the stop and target fixed, adding any
max-hold or a 16:00 flatten cuts it roughly in half:

| flatten | max hold | n | research $/t |
| --- | --- | ---: | ---: |
| none | none | 117 | **148.2** |
| none | 8 bars | 155 | 38.1 |
| none | 32 bars | 134 | 67.5 |
| 16:00 | none | 134 | 46.0 |

## Entry test

Market at the next open against a resting limit in your favour, V2's rule and geometry fixed:

| entry | trades | research $/t | win % | PF |
| --- | ---: | ---: | ---: | ---: |
| **market at next open** | 117 | **148.2** | 68.6 | 2.59 |
| limit 0.25×ATR better | 105 | 103.1 | 63.2 | 2.15 |
| limit 0.50×ATR better | 97 | 101.1 | 63.2 | 2.30 |
| limit 0.75×ATR better | 86 | 98.0 | 64.4 | 1.95 |

Market wins. That is the expected shape for a *real* signal: the limit mechanic substitutes for a
signal rather than complementing one (`STUDY_LIMIT_ENTRY.md`), so waiting for an adverse excursion
discards exactly the trades whose edge is in the immediacy of the move.

## A defect in the script as pasted

The copy supplied for this study was missing `barstate.isconfirmed` on the entry:

```
if trig and ready and isFlat and inWindow          // as pasted
if trig and ready and isFlat and inWindow and barstate.isconfirmed   // repo version
```

Without it the Strategy Tester's "Script execution" boxes change the result — measured on one rule
here at **5.1× as many signals, 80% of them on bars that never satisfied the rule**. The version
in `pine/oneR/` already has the guard; the pasted copy was stale.

## What shipped

`pine/rsiWick/V2_strategy.pine` and `pine/rsiWick/BASE_strategy.pine`, both with the
configuration lock from `STUDY_PINE_CONFIG.md` — every input overridden by the measured constant,
a refusal to trade off the design timeframe, and an `AS MEASURED` / `CUSTOM` / `WRONG TIMEFRAME`
banner. Rule logic verified against the research masks: **303/303 and 153/153 shared, zero on
either side.**

## The honest summary

Of 76,546 configurations, **one** is a defensible improvement on the script that started this, and
it carries a wrong-shape flag and a dependence on unlimited hold time. Two of the three best
research candidates lost money or stalled out of sample. The multiplicity is far too large for any
of this to clear a Bonferroni threshold, and the whole study is still **one instrument in one
regime**, 88% of it a rising market. Treat V2 as the best available candidate, not as proven.
