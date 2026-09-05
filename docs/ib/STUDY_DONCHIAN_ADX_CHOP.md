# Donchian + EMA + ADX + CHOP, reverse-engineered and tested

`research/donchian/`. The rules come from a published video strategy and are specified completely —
there is nothing to guess, which is exactly what makes it worth testing. Close crosses above the
20-bar Donchian upper band, ADX above 20, choppiness index below 40, price above the 50 EMA, enter
next candle, exit on a 3×ATR trailing stop. Short is the mirror. One hour. The source reports
**+140% on ETH perpetuals over a year against a −32% market**, tuned on eight months and tested on
four, over a 432-combination grid.

Measured on NQ, 2022-12 → 2025-12, MNQ fees and bar-speed slippage (1.72 points round turn), split
at the first 65% of sessions with the locked block read once.

## The headline: on its own timeframe, the system is a random entry

Every one of the 432 published combinations was scored on the research block against a **matched
control** — random entries with the same side, the same trailing-stop geometry, the same
minute-of-day distribution and the same ATR at entry, so drift, costs, barrier width and session
timing are all priced in and only the trigger differs.

| timeframe | positive R | beats control | **p < 0.05** | expected by chance | median R | median control |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5m | 368/432 | 432/432 | 422/432 | 21.6 | +0.0483 | −0.0492 |
| 15m | 334/432 | 343/432 | 228/432 | 21.6 | +0.0767 | −0.0027 |
| 30m | 429/432 | 427/432 | 67/432 | 21.6 | +0.1079 | +0.0169 |
| **60m (published)** | 309/432 | 171/384 | **0/384** | 19.2 | **+0.0312** | **+0.0373** |
| 240m | 252/432 | 8/63 | 0/63 | 3.2 | +0.0294 | +0.1092 |

**Zero of 384 scorable combinations beat the control on the 1-hour chart, where 19 are expected by
chance, and the median combination earns less than its own control.** The 432-combination grid is
not a search over a family of edges; on 1H it is a search over noise. Note also that the timeframe
ranking runs the wrong way from the source's choice: the edge, such as it is, is on the *faster*
charts, and the published one is the worst of the five.

### A hypothesis I raised and had to withdraw

The 5m row above — every configuration beating a control that is itself *negative* — looked like a
denominator artifact. R is P&L over `mult × ATR(signal bar)`; a breakout fires in a fast bar, so if
signal-bar ATR were much larger than a random bar's, the fixed round-turn cost would be a smaller
fraction of R for the strategy than for the control, and the excess would be free. So the control
was rebuilt to draw each entry from bars whose ATR is within ±15% of that trade's own.

It changed almost nothing (5m p 0.007 → 0.005, 15m 0.059 → 0.046, 30m 0.035 → 0.025). Measured,
median ATR at signal bars is only **1.10–1.21×** the population median. The guess was wrong and the
excess is not a cost artifact. The risk-matched control is kept because it is the stricter test.

## None of the three filters earns its keep

Each filter tested against a **random filter of identical selectivity** drawn from the breakout
population — the only test that is not rigged, since comparing total dollars fails every restrictive
condition and comparing per-trade edge passes every one.

60-minute, published thresholds:

| gate | n | keeps | mean R | selectivity control | p |
| --- | ---: | ---: | ---: | ---: | ---: |
| raw breakout, no filters | 905 | 100% | **+0.0904** | — | — |
| EMA only | 871 | 96.2% | +0.1021 | +0.0903 | 0.047 |
| ADX only | 674 | 74.5% | +0.0879 | +0.0903 | 0.553 |
| CHOP only | 371 | 41.0% | +0.0394 | +0.0897 | **0.863** |
| all three (published) | 301 | 33.3% | **+0.0792** | +0.0900 | 0.567 |

**The full published stack scores below the raw unfiltered breakout.** Choppiness is worse than a
coin flip discarding the same proportion of trades — at p 0.863, a random filter beats it five times
in six. The EMA's p 0.047 is one significant cell in thirty and it keeps 96% of the signals.

On 15m the picture changes and it is the *pair* that carries: ADX + CHOP p 0.031, and **dropping the
EMA improves it** (+0.0741 against +0.0684 for all three). The trend filter the source treats as
essential is the ingredient the data can most easily do without.

## The locked block, read once

Multiplicity: the configuration below was **not** selected on research — it is the source's own
published default. What was searched is the timeframe, five of them. Bonferroni factor 5.

| timeframe | block | n | pts/trade | R | control | excess | p | win | PF |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5m | research | 1,282 | +1.18 | +0.0164 | −0.0365 | +0.0529 | **0.0055** | 35.6% | 1.07 |
| 5m | LOCKED | 641 | +5.43 | +0.0574 | −0.0099 | +0.0673 | **0.0190** | 36.8% | 1.21 |
| 15m | research | 476 | +5.90 | +0.0566 | −0.0009 | +0.0575 | 0.0575 | 38.2% | 1.19 |
| 15m | LOCKED | 240 | +16.81 | +0.1511 | +0.0337 | +0.1174 | 0.0120 | 40.8% | 1.37 |
| 30m | research | 256 | +20.70 | +0.1269 | +0.0278 | +0.0991 | **0.0255** | 39.8% | 1.57 |
| 30m | LOCKED | 149 | +26.71 | +0.1960 | +0.0339 | +0.1621 | **0.0060** | 46.3% | 1.49 |
| 60m | research | 170 | +11.06 | +0.0458 | +0.0457 | +0.0001 | 0.4975 | 38.8% | 1.20 |
| 60m | LOCKED | 87 | +35.54 | +0.1439 | +0.0049 | +0.1390 | 0.0345 | 43.7% | 1.47 |
| 240m | research | 49 | +31.19 | +0.0896 | +0.0646 | +0.0250 | 0.3935 | 38.8% | 1.32 |
| 240m | LOCKED | 20 | +192.67 | +0.3550 | +0.0354 | +0.3196 | 0.0175 | 60.0% | 2.76 |

Two timeframes are significant on **both** blocks after the factor of 5: 5m and 30m.

## Three reasons to distrust even that

**1. The shape is wrong, and uniformly so.** Every timeframe scores better on the locked block than
on research — including the two that plainly failed research (60m p 0.498 → 0.035; 240m p 0.394 →
0.018). A rule chosen on research should decay out of sample; the holdout is where an edge dies, not
where it appears. One instance is a curiosity, five out of five is a **regime**: the later block was
simply a better period for trend following on NQ. Read the 30m and 5m rows knowing that the same
block also resurrected two dead configurations.

**2. One year carries it.** 30-minute, published defaults, by calendar year:

| year | n | pts | pts/trade | R | win |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2022 | 3 | +142 | +47.38 | +0.7190 | 66.7% |
| 2023 | 146 | **−690** | **−4.73** | **−0.0757** | 34.9% |
| 2024 | 119 | **+7,278** | **+61.16** | +0.4505 | 49.6% |
| 2025 | 137 | +2,547 | +18.59 | +0.1238 | 43.1% |

2024 supplies +7,278 of the +9,277 total points. 2023 loses money.

**3. A handful of trades carry that year.** On 5m the **top 1% of trades — 19 of 1,923 — supply 171%
of net P&L**; remove them and the system is a loser. Top 5%: 470%. On 30m the top 1% supply 47%.

## It cannot be made intraday, and the reason is mechanical

Every session-constrained variant, signals restricted to the window and the position forced flat at
its end:

| timeframe | window (New York) | research excess / p | LOCKED excess / p | LOCKED PF |
| --- | --- | ---: | ---: | ---: |
| 5m | 06:00–12:00 | +0.0229 / 0.288 | −0.0039 / 0.507 | 0.80 |
| 5m | 09:30–12:00 | +0.0543 / 0.161 | −0.0661 / 0.791 | 0.75 |
| 5m | 09:30–16:00 | +0.0961 / **0.011** | −0.0629 / 0.863 | 0.89 |
| 15m | 06:00–12:00 | +0.0401 / 0.242 | +0.0297 / 0.369 | 0.96 |
| 15m | 09:30–12:00 | +0.0279 / 0.332 | −0.0410 / 0.611 | 0.78 |
| 30m | 06:00–12:00 | +0.0209 / 0.391 | −0.0370 / 0.615 | 1.05 |
| 30m | 09:30–12:00 | −0.0043 / 0.510 | −0.0036 / 0.489 | 1.13 |

**Not one cell is significant out of sample**, and the best research cell (5m 09:30–16:00, p 0.011)
inverts to p 0.863. The mechanism is visible in the holding times: on 5m the median winner runs
**2.1 hours against the median loser's 0.8**, and trades carried past the session supply **338% of
net P&L** even though 84.3% of trades close the same day. A 3×ATR trailing stop is paid in the tail;
a daily flatten removes the tail and leaves the losers. This is a swing system by construction, and
no session box turns it into a scalp.

## What this is evidence about, and what it is not

Only NQ was available when this ran, so **none of this is cross-market evidence** and the source's
own result was on ETH. The claim being tested is narrower than the source's: not "does this work on
crypto", but "do these four indicators, combined this way, beat a matched random entry" — and on the
timeframe the source publishes, on this instrument, the answer is a clean no across all 432 of its
own parameter combinations.

`pine/donchian/DCS_strategy.pine` is the reproduction, lint-clean, with the grid left free and the
session box present but defaulted OFF. Two Pine traps were live here: `ta.dmi` returns
`[+DI, −DI, ADX]` in that order, so destructuring the first element silently substitutes +DI for
ADX; and bare `hour`/`minute` are exchange time, so the session box reads `America/New_York`
explicitly.
