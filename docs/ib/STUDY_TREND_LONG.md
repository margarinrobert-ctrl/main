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
are **unanswerable here** rather than guessed at. The US100 leg of the final cross-instrument
check could not be completed either: the uploaded file was cleared from the session's upload
directory mid-study.

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

The briefed window is the least bad of the three. **This contradicts `STUDY_TREND_PULLBACK.md`,
which found 09:30–11:00 worth 4× the per-trade result** — that finding was measured on a different
rule family and does not generalise to this one. Recorded as a conflict, not resolved.

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

## Verdict

**The hypothesis does not contain a robust edge on this data.** Every component of the briefed
regime — the 200 EMA, its slope, and ADX — either does nothing or makes the result worse, and the
best configuration found across the whole battery loses money out of sample. This is the third
independent negative on this structure.

**What would be required to make it stronger**, in order of expected value:

1. **A different exit.** Every table above is dominated by the 2×ATR/1R geometry needing >50% to
   pay. The one setup that clears its control by 10 points on research still loses money on the
   holdout at 52.3%. Before any more entry engineering, the geometry needs to be the thing that is
   varied — this branch's tuner does that in under a second and it was not the brief.
2. **More instruments.** Three years of one contract cannot separate a 1-point excess from noise.
   The US100 file would have given six unseen years; it was cleared mid-study.
3. **Abandon the trend framing.** The two legs on this branch that survived a change of instrument
   and a change of era (`STUDY_US100.md`) are both **counter-trend**: V1 buys a close at a 5-bar
   low after a squeeze, V2L requires EMA20 < EMA50. A 9.3M-strategy search on unseen US100 data
   independently converged on **long into a new low**. The data keeps pointing at mean reversion,
   and the brief explicitly rules it out.
