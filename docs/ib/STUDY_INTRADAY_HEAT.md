# Open-trade drawdown in points — and the discovery that the target is inert

`research/vbt/heat.py`, `research/vbt/intraday.py`. Configuration: 15-minute chart, **09:30–12:00
New York with a hard flatten**, long only, 30-bar Donchian entry, 20-bar channel stop, 5R target,
4H EMA(20) filter, 1.0R clearance to prior daily/weekly/monthly highs.

## The headline is not the heat, it is the exit mix

| block | n | reached TARGET | stopped out | flattened on the clock |
| --- | ---: | ---: | ---: | ---: |
| in-sample | 1,651 | **5 (0.3%)** | 192 (11.6%) | 1,454 (88.1%) |
| out-of-sample | 1,027 | **0 (0.0%)** | 155 (15.1%) | 872 (84.9%) |

**The 5R target is never reached — not rarely, essentially never.** Out of sample it fired zero
times in 1,027 trades. The strategy is not "breakout to a 5R target"; it is **"be long above the
4H EMA until either the channel stop or the clock closes you"**. Every number this family produces
comes from the stop and the flatten, and the take-profit is decoration.

## Heat, in points and in R

| group | n | MAE pts | MAE/R | p90 MAE/R | MFE pts | MFE/R |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **out-of-sample, all signals** | 1,027 | 135.7 | **0.43** | 1.08 | 160.6 | 0.57 |
| stopped out | 155 | 347.4 | 1.21 | 1.54 | 94.4 | 0.37 |
| flattened on the clock | 872 | 98.1 | **0.29** | 0.69 | 172.4 | **0.61** |
| *in-sample, reached the target* | 5 | 5.3 | **0.09** | 0.24 | 182.7 | 5.27 |

Read in the unit a stop is actually set in, per market, out of sample:

| market | n | risk (pts) | MAE, all signals (pts) | MFE, all signals (pts) |
| --- | ---: | ---: | ---: | ---: |
| US30 | 243 | 204.8 | 81.9 | 110.7 |
| US100 | 250 | 118.6 | 47.0 | 64.9 |
| XAUUSD | 310 | 19.6 | 6.1 | 7.6 |
| BTC | 224 | 1,172.3 | 472.6 | 533.3 |

Three things worth taking from this.

**Average heat is 0.43R, and the 90th percentile is 1.08R.** A stop tighter than about 1.1× the
current one converts a meaningful share of survivors into losers. Stopped trades show MAE/R of 1.21
because price gaps through the level, so the realised loss exceeds 1R.

**The few trades that ever reached the target barely drew down at all** — 0.09R, against 0.43R for
the population. On this sample a winner declares itself immediately; a trade that goes 0.5R against
you is not a winner having a wobble.

**Flattened trades reach +0.61R on average before the clock closes them.** That is favourable
excursion being handed back, and it is the one genuinely actionable measurement here.

## So test the target properly — the whole axis, not the peak

Everything else fixed, only the target varied. Both blocks reported.

| target | IS n | IS E[R] | IS PF | OOS n | OOS win% | OOS E[R] | OOS PF | % that hit TP (OOS) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.5R | 2,119 | +0.040 | 1.23 | 1,331 | 58.5 | +0.014 | 1.07 | 36.0 |
| 1.0R | 1,819 | +0.072 | 1.34 | 1,132 | 52.7 | +0.032 | 1.13 | 16.2 |
| **1.5R** | 1,725 | +0.089 | 1.40 | 1,081 | 51.5 | **+0.046** | **1.18** | 7.9 |
| 2.0R | 1,683 | +0.092 | 1.40 | 1,057 | 50.8 | **+0.047** | **1.18** | 4.4 |
| 3.0R | 1,659 | +0.098 | 1.42 | 1,034 | 50.7 | +0.043 | 1.16 | 1.0 |
| 5.0R | 1,651 | +0.103 | 1.44 | 1,027 | 50.5 | +0.046 | 1.17 | 0.0 |

**This is a plateau, not a peak** — 1.5R through 5R all land at +0.043 to +0.047 out of sample, and
the only sharp move is the *degradation* below 1.5R. A broad flat region is the shape a real
parameter makes; a spike is the shape noise makes. That is the reassuring part.

The unflattering part: the plateau exists **because the target stops mattering**. At 1.5R only 7.9%
of trades reach it, at 3R only 1.0%, at 5R none. Above about 1.5R the take-profit is switched off
and every configuration is the same system. **Setting it to 5R and setting it to "none" are the same
strategy.**

## What this means for a points-based target

The Pine exposes the target in points as well as in R, and the per-market table above is what to set
it from — but note what the axis says: a fixed point target that works out below ~1.5R will *reduce*
expectancy (0.5R costs a third of it), and one above ~1.5R will never fill. The usable band is
narrow, and it is narrow in R, not in points, which is why a fixed point distance has to be re-set
per instrument: 1.5R is roughly **307 points on US30, 178 on US100, 29 on gold and 1,758 on BTC**.

## Verdict

The intraday system is real but thin, and it is **not** the strategy it looks like. It is a
stop-and-clock system wearing a take-profit it never touches. The honest description is: long above
the 4H EMA, out on a 20-bar channel stop or at 12:00, expectancy **+0.046 R at PF 1.18** out of
sample, with 0.43R of average heat and a 1.08R 90th percentile.
