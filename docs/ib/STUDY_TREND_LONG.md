# The long-only 200 EMA + ADX + pullback hypothesis: every component subtracts

Briefed as *price > 200 EMA + strong trend regime + controlled pullback + bullish continuation*,
long only, 07:00–11:00 New York. `research/trend_long.py`.

## The prior, stated first

This structure has been tested twice on this branch. `STUDY_TREND_BRIEF.md` found the framework
does not survive, that the slope condition is **redundant** and that **ADX contributes
negatively**. `STUDY_TREND_PULLBACK_2.md` swept **5,723,136** combinations — 46 trend states
(including close vs 15 EMAs and ADX+DI), 36 pullbacks (EMA20/50, VWAP, ATR retrace, structure,
RSI/Stoch), 24 resumptions — in this exact window: **127 beat a time-matched control on research,
zero survived the holdout**, against 6.4 expected by chance. CLAUDE.md marks it do-not-re-run.

This run exists to answer the fourteen numbered questions with measurements rather than a
citation.

## What could not be tested

This repository holds **NQ and US100 only**. There is no ES, YM, RTY, CL, GC or VIX file, so the
multi-market comparison, the ES/NQ cross-market question and anything keyed on implied volatility
are **unanswerable here** rather than guessed at. The US100 cross-instrument check is now complete
and has its own section below.

## A construction error, found and fixed

The first version required the pullback and the trigger **on the same bar** — "close below EMA20"
*and* "close above the 3-bar high" — which is close to self-contradictory and produced **41
triggers in three years**. A pullback-continuation setup is a *sequence*. `trend_long.recent()`
now asks whether the pullback occurred within the last k bars, strictly **before** the trigger
bar, which yields 379–961 triggers depending on k. Every number below uses the corrected form.

## Q1. Does each regime component earn its place? No — all three subtract

NQ 5-minute, 07:00–11:00, pullback below EMA20 within 6 bars, trigger = break of the pullback
high, 2.0×ATR stop / 1.0R. **Research block only**, scored against a minute-of-day matched control.

| variant | n | win % | control | **excess** | $/trade |
| --- | ---: | ---: | ---: | ---: | ---: |
| full regime (200 EMA + slope + ADX>25) | 241 | 49.0 | 50.0 | **−1.1** | −7.7 |
| drop the 200 EMA | 241 | 49.0 | 50.0 | −1.1 | −7.7 |
| drop the slope condition | 319 | 51.1 | 49.9 | +1.2 | −4.4 |
| drop ADX | 763 | 49.5 | 49.7 | −0.2 | −4.7 |
| **no regime at all** | 1408 | 51.3 | 49.8 | **+1.5** | **−0.7** |

**Removing the entire regime gives the best result.** Dropping the 200 EMA changes nothing at all
— in this window price is essentially always above it, so it is a null condition, not a filter.
Dropping the slope *improves* excess. This replicates `STUDY_TREND_BRIEF.md` independently.

## Q2/Q3. Is ADX > 25 optimal? No, and no range is robust

| ADX > | 0 | 15 | 20 | 22 | **25** | 28 | 30 | 35 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| excess | −0.2 | +0.8 | +1.0 | +0.1 | **−1.1** | +0.2 | +0.9 | −0.4 |
| $/trade | −4.7 | −3.2 | −3.4 | −3.6 | **−7.7** | −6.6 | −6.3 | −12.3 |

The briefed 25 is the **worst** value tested. The whole surface sits within ±1.7 points of zero —
a flat, noisy plateau around no effect, not a peak. **There is no robust ADX range because there
is no ADX effect.** Every cell is negative in dollars.

## Q4. What EMA200 slope is required? None helps

Excess across slope thresholds −0.05 → +0.10 ATR: **−0.8, −1.1, +1.3, +0.0, +1.7**. Dollars stay
between −$4.0 and −$7.7 throughout. No threshold produces a profitable configuration.

## Q5/Q6. Which pullback definition? All ≈ zero or worse

| pullback | n | excess | $/trade |
| --- | ---: | ---: | ---: |
| volume contraction | 232 | +1.8 | **+0.2** |
| 2 down closes | 374 | +2.4 | −0.9 |
| higher low (3-bar) | 536 | −0.6 | −3.7 |
| retrace > 38% of impulse | 404 | −1.8 | −5.7 |
| retrace > 1 ATR | 490 | −2.1 | −7.0 |
| below EMA20 | 241 | −1.1 | −7.7 |
| **below VWAP** | 212 | **−5.7** | −9.2 |
| **below EMA50** | 161 | **−5.3** | −13.5 |

The best is barely breakeven; the two deepest pullbacks (VWAP, EMA50) are the worst. **Q6 answer:
volume contraction during the pullback is the only variant that reaches zero**, which is a weak
yes at best.

## Q7. Which continuation trigger? One stands out

| trigger | n | win % | control | **excess** | $/trade |
| --- | ---: | ---: | ---: | ---: | ---: |
| **reclaim EMA20** | 209 | **60.3** | 50.0 | **+10.2** | **+9.9** |
| close > prior high | 338 | 50.3 | 50.0 | +0.3 | −4.9 |
| momentum expansion | 262 | 51.5 | 50.7 | +0.9 | −1.8 |
| volume expansion | 382 | 50.0 | 50.3 | −0.3 | −7.3 |
| break pullback high | 241 | 49.0 | 50.0 | −1.1 | −7.7 |
| reclaim VWAP | 110 | 50.0 | 50.8 | −0.8 | −1.0 |

**Q7 answer: volume expansion on the trigger does not help (−0.3).** The only component in the
entire battery with a material positive excess is `reclaim EMA20`.

## The one survivor, taken to the holdout

| | block | n | win % | control | excess | **$/trade** | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| full regime + reclaim EMA20 | research | 209 | 60.3 | 50.1 | **+10.1** | **+9.9** | **0.0020** |
| full regime + reclaim EMA20 | **locked** | 111 | 52.3 | 48.2 | **+4.0** | **−5.3** | **0.2256** |
| no regime + reclaim EMA20 | research | 1176 | 51.4 | 49.8 | +1.6 | +0.8 | 0.1432 |
| no regime + reclaim EMA20 | locked | 620 | 48.9 | 48.1 | +0.8 | −5.6 | 0.3585 |

**It fails.** The excess more than halves out of sample, the p-value goes from 0.0020 to 0.2256,
and — decisively — **the per-trade result turns negative on the holdout (−$5.3)** even though the
win rate stays above its control. With a 2×ATR stop and a 1R target you need materially more than
50% to profit after costs, and 52.3% is not enough.

Note also that `reclaim EMA20` is partly mechanical here: the setup already requires a close
*below* EMA20 within six bars, so "cross back above EMA20" is close to the definition of the
pullback ending rather than an independent confirmation.

## Q10. Which window?

| window | n | excess | $/trade |
| --- | ---: | ---: | ---: |
| 07:00–11:00 as briefed | 241 | −1.1 | −7.7 |
| 09:30–11:00 | 124 | **−9.2** | −17.1 |
| all day | 1135 | −3.9 | −5.5 |

The briefed window is the least bad of the three. This appeared to contradict
`STUDY_TREND_PULLBACK.md`, which found 09:30–11:00 worth 4× the per-trade result. **The conflict
is resolved below in favour of 09:30–11:00**: measured on the regime alone rather than on this
one 5-minute rule, the cash session wins on both out-of-sample blocks and on both instruments.
The cell above is an artifact of scoring a fragile rule instead of the session.

## Answers to the remaining questions

* **Q8 (higher-timeframe alignment):** the 200 EMA *is* the higher-timeframe proxy on 5-minute
  bars and it is a null condition here, so the answer is no on this data.
* **Q9 (regimes to avoid):** no regime produced positive expectancy after costs, so the honest
  answer is that the regime classifier has nothing to select between.
* **Q11 (ES/NQ):** unanswerable — no ES data.
* **Q12 (independent predictive value):** only `reclaim EMA20` showed any, and it did not survive.
* **Q13 (survives realistic costs):** no. Every configuration except one is negative per trade
  *before* the holdout, under the itemised cost model.
* **Q14 (survives out of sample):** no.

## The cross-instrument test, and the trap inside it

`research/trend_long_xmkt.py`, 15-minute (US100's source resolution, so the coarsest common
timeframe), same geometry, same window. US100 splits at 2022-12-26, where NQ's file begins.

**The 2023-2025 US100 block is not a test.** It is the same calendar as NQ's whole sample on the
same underlying index, and the module now measures exactly what that costs:

| | NQ triggers | US100 triggers | same 15-minute bar | within ±2 bars |
| --- | ---: | ---: | ---: | ---: |
| full regime + break pullback high | 312 | 309 | **211 (68%)** | 246 (79%) |
| full regime + reclaim EMA20 | 175 | 177 | **111 (63%)** | 129 (74%) |

Two thirds of the trades are *literally the same trades* on a second data feed. So the strong
numbers on that block — +10.9 excess at p 0.0011 — are a re-measurement of the block the rule was
selected on, not confirmation of it. They are reported only so the dependence is visible.

**That leaves 2016-2022 as the only independent evidence**, and it is thin:

| variant | n | win % | control | excess | $/trade | p(win) | **p($)** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| full regime + break pullback high | 416 | 54.1 | 49.6 | **+4.5** | **+0.2** | 0.0364 | **0.1133** |
| full regime + reclaim EMA20 | 326 | 51.2 | 49.3 | +1.9 | −3.6 | 0.2654 | 0.4367 |
| drop the 200 EMA | 327 | 51.1 | 49.6 | +1.5 | −3.7 | 0.3118 | 0.4367 |
| NO regime + reclaim EMA20 | 1682 | 50.4 | 49.2 | +1.2 | −5.9 | 0.1628 | 0.7900 |

The best variant clears its control on **win rate** (p 0.036) and not on **dollars** (p 0.113),
and earns **$98 in total across 416 trades and six years**. Its exit split is 177 stops at
−$75.57, 206 targets at +$62.65, 33 time exits at +$17.25 — a 1:1 barrier where the win-rate
excess buys back the round turn and nothing beyond it. By year: **−4, −1, +16, −8, +5, −7**
(2017→2022). Three of six years negative, one carrying it.

**And the two instruments pick different variants.** `reclaim EMA20`, the only component with a
material positive excess on NQ, is null on the six unseen years (+1.9, p 0.27, −$3.6/trade).
`break pullback high`, which died on NQ's holdout (+1.7, p 0.44), is the one that shows anything.
Two independent blocks, two different answers, neither strong.

### The ADX gradient, and why it is not real

Swept on the unseen US100 block, ADX looks like a clean monotone edge — excess +2.2, +4.6, +8.3,
+10.6, +10.6 at thresholds 22, 25, 28, 30, 35, with dollar excess climbing to +$19.67. That is a
much better-looking surface than the flat NQ one in Q2/Q3 above, and it is worth being explicit
about why it was not believed.

The minute-of-day matched control is matched on **time and not on volatility**. An ADX filter
concentrates trades in high-ATR bars; the control at the same minutes draws average-ATR bars. So
the harder null is **the regime alone** — enter every eligible bar the regime admits, same window,
same geometry — which isolates the pullback and trigger from "be long in this regime":

| | US100 2016-2022 (unseen) | NQ holdout | NQ research |
| --- | ---: | ---: | ---: |
| no ADX | **+2.39** | −8.08 | +5.18 |
| ADX>20 | +1.90 | −10.05 | +14.88 |
| ADX>25 | +4.39 | −3.13 | +18.05 |
| ADX>28 | +10.37 | −8.43 | +17.30 |
| ADX>30 | **+15.50** | **−29.65** | +12.09 |
| ADX>35 | +15.05 | −29.63 | +17.36 |

*(what the pullback and trigger add to the regime baseline, $/trade)*

**The rule adds at every threshold on US100's unseen years and subtracts at every threshold on
NQ's holdout.** The high-ADX gradient does not merely fail to replicate — it inverts, and hardest
at the thresholds where it looked best. On the block where the rule was chosen it adds +$18/trade;
on the two blocks it was not chosen on, it points in opposite directions. That is a coin flip
dressed as a parameter surface, and the NQ-holdout cells at ADX>30 rest on 30 and 20 trades, so
the inversion is not evidence of a reverse effect either — it is evidence of no effect.

### The one thing that does replicate: the window

Regime only, no pullback and no trigger, so this is a session effect or nothing:

| | 07:00-09:30 | 09:30-11:00 | difference |
| --- | ---: | ---: | ---: |
| US100 2016-2022 (unseen) | −$8.19 | **−$1.04** | **+7.15** |
| NQ holdout | −$4.93 | **+$12.36** | **+17.29** |
| NQ research | +$10.36 | +$3.90 | −6.46 |

**The cash session beats the pre-market half on both out-of-sample blocks and inverts only on the
in-sample one** — and the cost model does not widen the pre-09:30 spread, so the 07:00-09:30
column is measured optimistically and the true gap is larger than shown. This restores the
`STUDY_TREND_PULLBACK.md` recommendation that the 5-minute run in Q10 above appeared to
contradict: **that conflict resolves in favour of 09:30-11:00**, now on two instruments. It is a
window choice backed by measurement, not an edge claim — note that on US100's unseen years the
better window is still *negative*.

## Verdict

**The hypothesis does not contain a robust edge on this data, on either instrument.** Every
component of the briefed regime — the 200 EMA, its slope, and ADX — either does nothing or makes
the result worse. The 200 EMA is a null condition on both: dropping it changes NQ's 5-minute
result not at all, and moves US100's six unseen years from 326 trades to 327 with identical
dollars. The best configuration in the whole battery loses money out of sample on NQ, and on the
only genuinely independent block available — six unseen years of US100 — earns **$98 total across
416 trades**, with a dollar excess over its matched control that does not reach significance
(p 0.113) and three of six years negative.

The strong-looking US100 result was **not** a fourth negative turning positive. It was the same
trades over again: 68% of NQ's triggers fire on the exact same 15-minute bar on US100 in the
overlapping period. Two thirds of that "confirmation" was arithmetic.

This is the fourth independent negative on this structure, and the first with a second instrument
and six unseen years behind it.

**What would be required to make it stronger**, in order of expected value:

1. **A different exit.** Every table above is dominated by the 2×ATR/1R geometry needing >50% to
   pay. The one setup that clears its control by 10 points on research still loses money on the
   holdout at 52.3%. Before any more entry engineering, the geometry needs to be the thing that is
   varied — this branch's tuner does that in under a second and it was not the brief.
2. **A different structure, not more data.** This was the modification with the highest expected
   value before the US100 run, and the US100 run has now spent it. Six unseen years on a second
   instrument did not rescue the hypothesis — it produced a 4.5-point win-rate excess worth
   $0.24 per trade and a parameter surface that inverts against NQ's holdout. More history of the
   same structure is no longer the bottleneck; the structure is.
3. **Abandon the trend framing.** The two legs on this branch that survived a change of instrument
   and a change of era (`STUDY_US100.md`) are both **counter-trend**: V1 buys a close at a 5-bar
   low after a squeeze, V2L requires EMA20 < EMA50. A 9.3M-strategy search on unseen US100 data
   independently converged on **long into a new low**. The data keeps pointing at mean reversion,
   and the brief explicitly rules it out.
