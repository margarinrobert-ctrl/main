# 110,250 configurations, selected in-sample and read once out of sample

`research/vbt/sweep_engine.py`, `run_sweep.py`, `analyse_sweep.py`.

Requested as "find the most profitable version". Run so the answer is usable: **selection on the
in-sample block only**, one read of the untouched block, the plateau reported next to the peak, and
the multiplicity stated. 402,266 chart bars across six markets; the in-sample pass takes 34 seconds.

Two-stage by design: the sweep resolves barriers on **chart bars**, which is the resolution
`STUDY_ATME_LIVE.md` showed can overstate a barrier system fivefold. It **ranks**; survivors must be
re-run on the true intraday path before any number is believed.

## The grid

Entry channel {none, 10, 20, 30, 55} × stop {channel 5/10/20, ATR 1.0/1.5/2.0/3.0} × target
{fixed 1/2/3/5R, ladder 1-2-3 / 1-2-4 / 0.5-1.5-3} × HTF EMA {10, 20, 50, 100, 200} ×
avoid-resistance tolerance {0, 0.5, 1, 2, 3} × break-even {off, on} × max hold {none, 24, 72} ×
side {long, short, both}. **"No entry trigger" is deliberately in the grid**: a risk-matched control
had already shown the Donchian breakout contributes nothing, so the sweep is free to discard it.

## The top of the sweep, and its out-of-sample behaviour

| rank | configuration | IS n | IS E[R] | IS PF | OOS n | OOS E[R] | OOS PF |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | EMA100, ent 55, stop ch20, **fixed 5R**, tol 1.0, **long** | 388 | +0.435 | 1.56 | 294 | +0.098 | 1.12 |
| 3 | EMA50, ent 20, stop ch20, fixed 5R, tol 3.0, long | 378 | +0.428 | 1.55 | 254 | +0.150 | 1.18 |
| 5 | EMA50, ent 10, stop ch20, fixed 5R, tol 3.0, long | 417 | +0.424 | 1.54 | 291 | **−0.351** | 0.74 |
| 7 | EMA100, ent 20, stop ch20, fixed 5R, tol 2.0, long | 396 | +0.416 | 1.53 | 266 | +0.301 | 1.38 |
| 9 | EMA200, ent 55, stop ch20, fixed 5R, tol 0.0, long | 368 | +0.414 | 1.53 | 256 | +0.244 | 1.30 |

**The best in-sample configuration earns +0.098 R out of sample — statistically indistinguishable
from the un-swept starting point (+0.097).** 110,250 configurations bought nothing. And the
neighbourhood is unstable: rank 5 goes +0.424 → **−0.351**, so two configurations one channel-length
apart differ by 0.5 R out of sample.

Decay: the top 0.1% average **+0.3679 in-sample and +0.1022 out of sample**; the whole population
averages −0.0803 and −0.1441. 7.6% of all configurations are positive out of sample, against 89.1%
of the top 0.1%.

## What the sweep actually selected

| | top 0.1% | population |
| --- | ---: | ---: |
| **5R fixed target** | **100.0%** | 14.3% |
| **long only** | **100.0%** | 33.3% |
| channel stop | 74.5% | 42.9% |
| no entry trigger | 3.6% | 20.0% |

Every one of the top 110 configurations is **long-only with a 5R target**. On a sample where all six
markets rose, that is drift capture with a wide net — the same conclusion `STUDY_TURTLE.md` reached
about the Turtle itself. It is not a rule the sweep discovered; it is the sweep finding the longest
exposure to an up-move.

## The trap this sweep walked into, and the diagnostic that caught it

The in-sample/out-of-sample expectancy correlation is **+0.8389** across 110,250 configurations —
absurdly high for a strategy sweep, where near-zero is normal. It survives within fixed geometry
cells (mean **+0.876**), so it is not simply the mechanical effect of target size.

The grid contains what looks like a perfect internal control: `ent=0` is the same configuration with
**no breakout trigger**. Pairing all 88,200 triggered configurations with their triggerless twin
appears to show the trigger contributing **+0.163 in-sample and +0.189 out of sample**, helping in
89% of pairs — which would flatly contradict the risk-matched random-entry control that said the
breakout adds nothing.

**It is the contradiction that is wrong, not the earlier control.** `ent=0` enters on every admitted
bar, so it inherits exactly the defect already diagnosed in `STUDY_TURTLE_YOUTUBE.md`: at an
arbitrary bar the 10-bar channel stop is close, the R denominator collapses, and any adverse move
becomes an enormous multiple. Splitting by stop type isolates it, because **an ATR stop cannot
collapse**:

| stop type | pairs | trigger IS | trigger OOS | helps IS | helps OOS |
| --- | ---: | ---: | ---: | ---: | ---: |
| channel | 37,800 | **+0.3500** | **+0.4167** | 97.3% | 97.9% |
| **ATR** | 50,400 | **+0.0220** | **+0.0178** | 83.2% | 75.6% |

The triggerless baselines confirm where the artifact lives: `ent=0` with a channel stop averages
−0.401 / −0.528, with an ATR stop −0.067 / −0.121.

**So 94% of the apparent trigger contribution is the degenerate denominator.** With a stop that
cannot collapse, the breakout is worth **+0.02 R**, which is nothing, and the risk-matched control's
verdict stands.

The high IS/OOS correlation has the same character: it is the persistence of drift and of the
geometry's mechanical signature across two blocks in which the same six markets rose, not evidence
that the ranking identifies skill.

## Verdict

**The sweep did not find a more profitable version. It found the longest-exposure way to be long in
a rising sample**, and its apparent discovery about entry triggers is an artifact of the risk
denominator. The requested search was run in full and its answer is negative.

What it does establish, and this is worth keeping: **a channel-based stop is not a safe unit of risk
for any control, null or baseline** on this branch. Anything measured in R against a channel stop
must be checked against an ATR-stop version before it is believed.
