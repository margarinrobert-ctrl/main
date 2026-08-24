# The Market Profile "80% rule", tested to its published specification

The most widely cited statistic in Market Profile. Researched, specified exactly, and measured on
three years of NQ.

## The claim, as published

Traced to *The Profile Reports* (Dalton Capital Management, 1987–1991) and popularised in Jim
Dalton's *Mind Over Markets*. The rule as stated across the sources:

> When the market opens **outside** the prior session's value area, then trades back **inside** it
> and is **accepted** there — meaning it trades inside the value area for **two consecutive
> 30-minute TPO periods (60 minutes)** — there is an **80% probability** that it will fill the
> entire value area and test the far edge.

Independent verification is thin. The figure originates with its authors' own reports; secondary
sources cite "67% accuracy in independent testing" and one trader's informal 18-month tracking at
"about 70%", neither with a published method or sample.

## Why my earlier test was invalid

My first pass tested a "traverse" with a hold requirement of 1–4 bars on 5-minute data — **5 to 20
minutes against the specified 60**. That is 3–12× too weak a filter, so it was not testing the rule.
The web research is what surfaced the correct specification; the number below replaces the earlier
41% figure.

## The measurement

NQ, Dec 2022 – Dec 2025, 09:30–16:00 ET, 5-minute bars. Acceptance requires two consecutive
clock-aligned 30-minute periods closing inside the value area. Target is the far edge; the trade
version uses a 1:1 stop and books the stop on any ambiguous bar.

| value area | sample | triggers / eligible | **value area filled** | win @ 1:1 | expectancy | p |
| --- | --- | --- | --- | --- | --- | --- |
| **Volume** | research | 114 / 339 | **46.5%** | 48.2% | −0.024 R | 0.76 |
| **Volume** | holdout | 52 / 150 | **42.3%** | 44.2% | +0.010 R | 0.93 |
| **Volume** | full | 167 / 490 | **45.5%** | 47.3% | −0.008 R | 0.91 |
| **TPO** | research | 122 / 351 | **44.3%** | 47.5% | −0.030 R | 0.68 |
| **TPO** | holdout | 56 / 152 | **48.2%** | 42.9% | −0.054 R | 0.64 |
| **TPO** | full | 179 / 504 | **45.8%** | 46.4% | −0.032 R | 0.61 |

## What this says

**The value area fills roughly 46% of the time, not 80%.** The result is stable across the research
and holdout halves, and — importantly — **identical on the TPO value area and the volume value
area** (45.8% vs 45.5%), which closes the obvious objection that a *Market Profile* rule was being
tested against a *Volume Profile* construction. It is not a construction artefact.

**As a trade at 1:1 it is flat.** Win rate 46–47%, expectancy between −0.03 and +0.01 R, every
p-value above 0.6. Under the user's constraint of at least 1:1 reward-to-risk, this rule is not a
high-win-rate strategy on this market and period; it is a coin flip that costs a spread.

**The acceptance filter does work, just not nearly enough.** Without it, the unconditional traverse
rate after an outside-value open was 41%. Requiring the full 60-minute acceptance lifts it to ~46%.
That is a real five-point improvement and evidence the underlying idea is not empty — it is simply
nowhere near the claim.

## Caveats worth stating

- **One instrument, one period.** NQ 2022–2025. The rule was formulated on late-1980s data, most
  likely S&P and bonds, in a floor-traded market with a completely different microstructure.
  A 46% reading here does not prove it was never 80%.
- **The "80%" may never have meant a tradeable win rate.** "Fills the value area at some point in the
  session" is a statement about eventual touch, not about surviving a stop first. Even at a true 80%
  touch rate, a trade with a stop converts far less. The two numbers are routinely conflated when the
  rule is sold as a strategy.
- Profiles here spread each bar's volume uniformly across its range, an approximation. The TPO
  profile has no such issue — it counts periods, not volume — and it agreed, which is reassuring.

## Bottom line

Tested to its own published specification, on both construction methods, across a research/holdout
split: **the 80% rule is a ~46% rule on NQ, and flat as a 1:1 trade.** It should not be traded on the
strength of the published number, and any backtest reporting a high win rate for it deserves to be
checked for a weakened acceptance filter — which is the exact error my own first pass made.
