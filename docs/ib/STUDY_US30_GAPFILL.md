# US30: alpha discovery first, then one rule — the opening gap fill

*After three passes and 29,337 configurations of the 09:00 range-break structure found nothing
([`STUDY_US30_ORB.md`](STUDY_US30_ORB.md), [`_2`](STUDY_US30_ORB_2.md), [`_3`](STUDY_US30_ORB_3.md)),
the instruction was to find the most profitable design. The disciplined order is the protocol's:
measure where the file has any predictability at all (stage 2), build one rule on the largest
consistent effect, test it with the same gates, read the holdout once.*

*Result:* **No single effect survives false-discovery control on the research block, but two
effects have the same sign at every horizon and say one thing: on this file the open's first move
is reversed more often than continued. One pre-registered rule on that mechanism — fade the
opening gap toward the prior close — beats a matched control on research (z 2.62, +21.0
pt/trade, 224 trades), sits on a plateau (64 of 96 neighbouring cells at z > 2, stability 0.98),
survives a 10-point round turn, and on the single locked read is positive with the right shape
(+10.6 pt/trade, 143 trades). It is not proven: the holdout z is 1.21, the short side lost on the
holdout, and charged for the whole search history the deflated Sharpe is 0.06. It is the first
thing on this file worth a forward test.**

> Reproducible: `python3 research/us30_alpha.py` then `python3 research/us30_mech.py`. Same
> data, split and cost model as the earlier studies. Research output, not financial advice.

---

## 1. Stage 2: what predictability exists, research block only

| test | result |
| --- | --- |
| return autocorrelation, 15m RTH bars, lags 1–10, heteroskedasticity-robust t | nothing beyond ±1.9; the naive t-stats of ±4 to ±6 vanish once volatility clustering is priced in |
| Lo-MacKinlay variance ratios at 2/4/8/16 bars, robust | 0.93–0.97, z −0.3 to −0.8: mild reversal, not significant |
| time-of-day profile, drift-adjusted, HAC, BH across 26 slots | 0 slots at q < 0.10 at 1-bar or 4-bar horizons |
| event studies at the open, lift over non-event bars, drift-adjusted, HAC lag = h, BH across 20 cells | 0 cells at q < 0.10 |

The event table is where the signal is, in the signs rather than the p-values:

| event (side) | h=1 | h=2 | h=4 | h=8 | n |
| --- | --- | --- | --- | --- | --- |
| gap ≥ 0.5 ATR, side **toward** the prior close | +3.8 | +9.8 | +8.5 | **+25.0** (t 2.35) | 293 |
| first close beyond the 09:00 range, side **with** | −7.7 | **−16.5** (t −2.17) | −8.9 | −13.4 | 324 |
| first close beyond the overnight range, side with | −7.2 | −13.2 | −15.1 | −12.9 | 227 |
| first 30-minute move ≥ 0.75 ATR, side against | −2.8 | −2.8 | −5.6 | −6.8 | 233 |
| bar ≥ 2 ATR, side with | −4.7 | −0.5 | +5.7 | +2.8 | 268 |

Points, drift-adjusted. Breaks of the pre-open range and of the overnight range are followed by
moves against them at every horizon; gaps are followed by moves toward the prior close at every
horizon, growing with the horizon. That is one mechanism, the opening auction overshooting, seen
from two sides, and it is the opposite of the breakout premise the first three passes were built
on. The range-break row is also the cleanest statement of why those passes failed: the structure
was pointed the wrong way.

## 2. Two pre-registered candidates

| | A: failed break | B: gap fill |
| --- | --- | --- |
| signal | first close beyond the 09:00 range, 09:30–10:15 | at the 09:30 close, gap = 09:30 open − prior session close, gap ≥ 0.5 ATR(14) |
| entry | next open, against the break | 09:45 open, toward the prior close |
| geometries | 100/100 flat 16:00 · 100/100 flat 11:00 · anchored (target the far side of the range, stop one width beyond the break) flat 16:00 · anchored flat 11:00 | 100/100 flat 16:00 · 100/100 flat 12:00 · anchored (target the prior close, stop one gap) flat 16:00 · anchored flat 12:00 |

Eight cells, gates as before (≥ 60 research trades, both sides ≥ 25%, matched control z ≥ 2),
and the multiplicity carried is these 8 plus the 20 event cells that produced them.

| candidate | research n | win | per trade | PF | control z | long / short per trade |
| --- | --- | --- | --- | --- | --- | --- |
| A, 100/100 flat 16:00 | 324 | 50.6% | −2.1 | 0.96 | 0.49 | +1.4 / −5.7 |
| A, 100/100 flat 11:00 | 324 | 50.3% | −1.1 | 0.98 | 0.72 | −0.7 / −1.4 |
| A, anchored flat 16:00 | 323 | 50.8% | +6.3 | 1.10 | 1.36 | +24.0 / −11.7 |
| A, anchored flat 11:00 | 323 | 50.2% | +2.3 | 1.05 | 1.09 | +13.1 / −8.6 |
| B, 100/100 flat 16:00 | 293 | 51.9% | +0.4 | 1.01 | 0.81 | −4.4 / +4.2 |
| B, 100/100 flat 12:00 | 293 | 52.2% | +2.4 | 1.05 | 1.17 | −4.1 / +7.5 |
| B, anchored flat 16:00 | 224 | 46.4% | +9.5 | 1.13 | 1.20 | +9.5 / +9.5 |
| **B, anchored flat 12:00** | **224** | **51.3%** | **+21.0** | **1.38** | **2.62** | **+31.5 / +12.6** |

One cell passes. The failed-break fade with fixed 100-point barriers is a coin, which is what
pass two's "fade" mechanic already showed; anchoring the barriers to the structure is what makes
either candidate move, and only the gap fill with the gap itself as the unit of risk clears the
gate. Both sides are positive on research.

## 3. The gap fill, in full

**Rule.** At the close of the 09:30 bar, if the 09:30 open is at least 0.5 × ATR(14) from the
prior session's 16:00 close, enter at the 09:45 open toward that close. Target the prior close.
Stop one gap-width from the fill. Flat at 12:00. One trade a session. Trades with a target or
stop under 25 points are skipped.

**Research block, 224 trades:**

| | value |
| --- | --- |
| win rate | 51.3% |
| per trade | **+21.0 pt** |
| net | +4,715 pt ($23,573 on one YM contract) |
| profit factor | 1.38 |
| Sharpe (daily, annualised) | 1.75 |
| max drawdown | 1,164 pt |
| exits: target / stop / flat | 68 (+162.8 each) / 74 (−126.2) / 82 (+36.4, 57% win) |
| median gap (= 1R) | 165 pt |
| long (gap down) / short (gap up) | +31.5 / +12.6 pt per trade, 100 / 124 trades |
| by year | 2024: 59 trades, −3.0 pt · 2025: 165 trades, +29.6 pt |
| matched control (2,000 draws) | −950 ± 2,165 → **z 2.62, p 0.007**; win 51.3% vs 46.8% |
| quarters profitable | 5 of 6 |

**Neighbourhood, research only** — gap threshold 0.3 / 0.5 / 0.75 / 1.0 ATR × stop 0.75 / 1.0 /
1.5 gap × target 0.75 / 1.0 gap × flat 11:00 / 12:00 / 13:00 / 16:00, 96 cells:

| statistic | value |
| --- | --- |
| cells with z ≥ 2 | **64 of 96** |
| median z | 2.30 |
| cells with positive per-trade | 94 of 96 |
| the chosen cell's one-step neighbours, median z | 2.59 → **stability 0.98** |

The surface is flat along the gap threshold (every value works), prefers a tighter stop (0.75
gap is better than 1.0, 1.5 is worse), and prefers a midday flat over a 16:00 one. It is a
plateau, and it is the first one on this file.

**Robustness, research:**

| probe | result |
| --- | --- |
| cost sweep, per trade at 0 / 3 / 6 / 10 pt | 24.0 / 21.0 / 18.0 / 14.0 |
| bootstrap 95% CI, net | [132, 9,487] pt; P(net ≤ 0) = 0.021 |
| bootstrap 95% CI, Sharpe | [0.06, 3.32] |
| Monte Carlo max drawdown, observed / median / 95th | 1,164 / 1,550 / 2,599 pt |
| deflated Sharpe, N = 28 trials (this family) | 0.55 |
| deflated Sharpe, N = 29,461 trials (everything ever tried on this file) | **0.06** |

## 4. The locked block, read once

| | value |
| --- | --- |
| trades | 143 |
| win rate | 54.5% |
| per trade | **+10.6 pt** |
| net | +1,512 pt ($7,558) |
| profit factor | 1.16 |
| Sharpe | 0.93 |
| max drawdown | 1,154 pt |
| exits: target / stop / flat | 47 (+148.5) / 34 (−133.8) / 62 (**−14.8**) |
| long / short | **+33.9 / −6.8** pt per trade, 61 / 82 trades |
| matched control | −882 ± 1,972 → z 1.21, p 0.11; win 54.5% vs 48.0% |
| quarters | 2025Q4 −332 · 2026Q1 +1,611 · 2026Q2 +304 · 2026Q3 −71 |
| cost sweep at 0 / 3 / 6 / 10 pt | 13.6 / 10.6 / 7.6 / 3.6 |
| shape | research 21.0 → locked 10.6: decays, the right way round |

Whole file: 367 trades, 52.6% win, +6,226 pt ($31,131), PF 1.29, max drawdown 1,164 pt.

## 5. What this says

**For it:** it was built from a measured mechanism rather than a search; it passed the matched
control on research before the holdout was touched; its neighbourhood is a plateau; it survives
three times the modelled cost; the holdout is positive, decays the right way, and its profit
comes from the target rather than the time exit, so it is a barrier edge and not a direction bet.

**Against it, and none of these can be waved away:**

1. **The holdout is not significant on its own.** z 1.21 on 143 trades. The research block's
   2024 quarter lost. The edge is concentrated in 2025–2026.
2. **The short side lost on the holdout** (−6.8 pt/trade on 82 trades) after being positive on
   research. The file rose 32%; fading a gap down is partly buying dips in a bull market. The
   control prices in drift and the long side still beats it, but "gap fill" as a symmetric
   mechanism is not established here, and a rule that only works long on a bull-market file is
   the regime bet §4c of the protocol warns about.
3. **Deflated Sharpe fails.** 0.55 if only this family is charged, 0.06 if every configuration
   ever tried on this file is, and the protocol charges everything. The honest reading is that
   after 29,000 trials a z of 2.6 on 224 trades is what one expects to find somewhere.
4. **One file, one regime, 15-minute bars.** The same three caveats as every study here.

**Verdict:** the most profitable design this file supports is the opening gap fill, and it is a
candidate for a forward test, not a system. The Pine ships with alerts for that purpose, with the
short side switchable off (the conservative setting), and with every parameter an input at the
pre-registered values.

## 6. Where the first three passes went wrong, in one sentence

The event table in §1 shows the structure they were built on — trade the break of the pre-open
range with it — has a negative lift at every horizon on this file; no parameter, entry mechanic,
filter, exit or direction gate can fix a rule that is pointed against the mechanism.

## 7. Second step: walk-forward, and the one design change the mechanism suggests

`research/us30_gap2.py`, after the locked read above.

**Walk-forward** — fit on 120 sessions, trade the next 40, step 40; grid of gap threshold
0.3 / 0.5 / 0.75 / 1.0 ATR × stop 0.75 / 1.0 / 1.5 gap × flat 11:00 / 12:00 / 13:00 (36 cells);
objective in-sample net. This is the first record that includes the cost of having to choose
parameters, and it spans both blocks by construction.

| fold | test from | chosen (gap, stop, flat) | IS net | OOS n | OOS per trade |
| --- | --- | --- | --- | --- | --- |
| 0 | 2025-02-20 | 0.75, 0.75, 12:00 | 1,417 | 33 | +47.7 |
| 1 | 2025-04-17 | 1.0, 0.75, 13:00 | 3,640 | 27 | +28.2 |
| 2 | 2025-06-13 | 1.0, 0.75, 13:00 | 4,275 | 25 | +7.0 |
| 3 | 2025-08-08 | 1.0, 0.75, 13:00 | 3,308 | 21 | −0.4 |
| 4 | 2025-10-03 | 1.0, 0.75, 12:00 | 1,487 | 26 | +52.2 |
| 5 | 2025-11-28 | 1.0, 0.75, 12:00 | 1,943 | 23 | −4.3 |
| 6 | 2026-01-27 | 1.0, 0.75, 12:00 | 1,376 | 29 | +38.3 |
| 7 | 2026-03-24 | 1.0, 0.75, 12:00 | 2,368 | 32 | +32.1 |
| 8 | 2026-05-20 | 1.0, 0.75, 13:00 | 2,553 | 29 | +4.5 |

Stitched out-of-sample: **245 trades, 49.8% win, +24.6 pt/trade, PF 1.42, Sharpe 1.97, max
drawdown 1,160 pt.** 7 of 9 folds profitable. Walk-forward efficiency 0.97. The stop was 0.75
gap in **9 of 9** folds, the threshold 1.0 ATR in 8 of 9, the flat 12:00 in 5 of 9. That is a
stable family, not a re-fit every window; gate 10 (efficiency ≥ 0.4) passes.

**Entry timing**, pre-registered before running, research only. The event study's lift begins
at the open, so the question was whether the rule should enter at the 09:30 open instead of
waiting for the 09:30 bar to close and filling at 09:45. On a confirmed-bar script that means
reading the gap from the 09:15 close (the last pre-open price, which has the same sign as the
09:30 gap on 100% of qualifying sessions) and filling at the 09:30 open.

| entry | stop | n | win | per trade | PF | control z |
| --- | --- | --- | --- | --- | --- | --- |
| E1 09:45 open, gap from the 09:30 open | 1.0 | 224 | 51.3% | +21.0 | 1.38 | 2.62 |
| E1 | **0.75** | 223 | 48.4% | **+26.3** | 1.54 | **3.28** |
| E2 09:30 open, gap from the 09:15 close | 1.0 | 280 | 46.1% | +0.3 | 1.00 | 0.81 |
| E2 | 0.75 | 275 | 42.9% | +7.9 | 1.15 | 1.68 |

Entering at the open is decisively worse. The first 15-minute bar *is* the overshoot the rule
fades; entering before it finishes buys the overshoot instead of fading it. The 09:45 fill stays.

**The stop.** Research prefers 0.75 gap (z 3.28 against 2.62) and the walk-forward chose it in
every fold, so it was read on locked once:

| stop | research per trade (z) | locked per trade (z) | locked long / short | whole file |
| --- | --- | --- | --- | --- |
| 1.0 gap | +21.0 (2.62) | +10.6 (1.21) | +33.9 / −6.8 | 367 trades, +17.0, PF 1.29 |
| 0.75 gap | +26.3 (3.28) | +6.3 (0.86) | +36.4 / −15.7 | 365 trades, +18.5, PF 1.34 |

Both are positive on both blocks with the right shape. The holdout mildly prefers 1.0; choosing
on that would be selecting on the holdout, so the shipped default is **0.75**, the research and
walk-forward choice, with 1.0 one input away. The honest expectation for either on new data is
the holdout number, +6 to +11 points a trade, not the research number.

## 8. Third step: the fill mechanic and four conditions

`research/us30_gap3.py`. Base for this step: stop 0.75 gap, flat 12:00 (research 223 trades,
+26.3 pt/trade).

**The fill.** `STUDY_LIMIT_ENTRY.md` found a resting limit beats a market order on random bars,
so a limit k × ATR beyond the 09:30 close, resting 09:45–10:15, was measured on the same signal
days as the market fill at 09:45:

| k | filled | fill rate | per filled trade | net, same days | base net |
| --- | --- | --- | --- | --- | --- |
| 0 (at the 09:30 close) | 220 of 223 | 98.7% | +24.9 | 5,475 | 5,868 |
| 0.25 ATR | 195 | 87.4% | +27.0 | 5,273 | 5,868 |
| 0.50 ATR | 161 | 72.2% | +9.0 | 1,450 | 5,868 |

No. The unfilled days are the best days, which is the same lesson as the entry-timing test:
this trade wants the overshoot complete and then wants in. The market fill at 09:45 stays.

**Conditions**, each pre-registered with a mechanism, each scored as the working notes require,
against a random filter of the same selectivity on the research trades (2,000 draws):

| condition | kept side | n | per trade | win | excess z | p |
| --- | --- | --- | --- | --- | --- | --- |
| C1 the 09:30 bar extended the gap (overshoot intact) | yes | 142 | +30.3 | 44% | 0.48 | 0.33 |
| | no | 81 | +19.4 | 56% | −0.42 | |
| C2 the 09:30 open is inside the prior session's 09:30–16:00 range | yes | 118 | **−2.1** | 42% | −2.52 | |
| | **no (outside)** | **105** | **+58.2** | **55%** | **+2.40** | **0.01** |
| C3 ATR(14) above its 60-session median | yes | 110 | +49.3 | 54% | 1.85 | 0.03 |
| | no | 113 | +4.0 | 43% | −1.85 | |
| C4 gap ≥ 1.0 ATR | yes | 212 | +28.2 | 50% | 0.70 | 0.24 |
| | no | 11 | −10.5 | 27% | | |

One condition passes: the gap must open **outside** the prior session's range. That is the
opposite of the "gap and go" lore, which says a gap beyond yesterday's range runs; on this file
those are the gaps that fill, and the gaps inside yesterday's range are a coin. High volatility
(C3) is close and is largely the same days. Read once on locked:

| | research | locked | whole file |
| --- | --- | --- | --- |
| trades | 105 | 69 | 174 |
| win | 55.2% | 55.1% | 55.2% |
| per trade | **+58.2** | **+15.1** | +41.1 |
| net | +6,115 pt | +1,043 pt | +7,158 pt ($35,789) |
| profit factor | 2.19 | 1.21 | 1.71 |
| Sharpe | 4.06 | 1.16 | 2.97 |
| max drawdown | 506 pt | 1,147 pt | 1,147 pt |
| long / short per trade | +93.6 / +33.7 | +45.0 / −12.3 | +72.5 / +16.8 |
| vs the unfiltered rule, same block | +26.3 | +6.3 | +18.5 |
| excess over a random filter of the same size | z 2.40 | z 0.62 | |
| cost sweep 0 / 3 / 6 / 10 pt | 61.2 / 58.2 / 55.2 / 51.2 | 18.1 / 15.1 / 12.1 / 8.1 | |

Half the trades, roughly double the per-trade result, and the same or higher total, on both
blocks. The locked improvement (+15.1 against +6.3) is in the direction the research predicted
and is not significant on its own (z 0.62 on 69 trades), and the short side is still negative on
the holdout. The filter ships **on** by default because research chose it and the holdout did
not contradict it; it is one input to switch off.

Where this leaves the rule after three engineering steps: research +58 pt/trade, holdout +15,
walk-forward +25 on the unfiltered family. The honest expectation on new data remains the
holdout number, and the short side remains the part that has not earned its place.

## 9. The holdout profit-factor target, and why it cannot be engineered

The instruction after step three was a minimum profit factor of 1.70 on the locked block. Two
facts decide what can honestly be done with that.

**A holdout target cannot be iterated toward.** The locked block is informative only because
each design is read there once, after being chosen on research. A design changed until the
locked profit factor reaches 1.70 has been fitted to the locked block, and the number then
says nothing about the future. So the only admissible procedure is the one used at every step
here: choose on research, read once, report.

**On 69 trades the profit factor cannot be measured to that precision.** Bootstrap of the
locked trades of the shipped rule:

| | point estimate | 95% interval | P(≥ 1.70) by resampling |
| --- | --- | --- | --- |
| locked profit factor (69 trades) | 1.21 | **[0.66, 2.22]** | 0.14 |
| research profit factor (105 trades) | 2.19 | [1.30, 3.60] | |

The interval on the holdout number is ±0.8 wide. A target of 1.70 is inside the noise of a
69-trade sample either way; it is a question the data cannot answer, not a question of
engineering.

**The remaining research-side variants**, pre-registered, picked by control z with ≥ 60
research trades, read on locked only if the pick changed:

| variant | n | win | per trade | research PF | control z |
| --- | --- | --- | --- | --- | --- |
| **shipped** (both sides, target the prior close, stop 0.75, flat 12:00, outside prior range) | 105 | 55.2% | +58.2 | 2.19 | **3.94** |
| long only | 43 | 62.8% | +93.6 | 3.01 | 3.68 |
| target 0.75 gap | 105 | 57.1% | +47.9 | 2.01 | 3.50 |
| flat 11:00 | 105 | 55.2% | +40.8 | 1.88 | 3.32 |
| flat 13:00 | 105 | 54.3% | +62.0 | 2.14 | 3.93 |
| plus the high-volatility regime | 56 | 62.5% | +104.1 | 3.31 | 4.74 |
| long only + target 0.75 gap | 43 | 62.8% | +75.2 | 2.61 | 3.10 |
| stop 1.0 gap | 105 | 57.1% | +54.8 | 2.02 | 3.53 |

The shipped rule is the pick. The high-volatility combination has the highest z on research and
the highest research profit factor, and it is not read on locked, because 56 trades is below
the gate and it is exactly the kind of cell that would produce a flattering holdout number by
chance. Long-only is the same story at 43 trades: it is also the regime bet §5 warns about.

**What would let a 1.70 profit factor be demonstrated** is a larger out-of-sample sample, not a
different rule: more history on this instrument, the same rule on a second index (the mechanism
is the opening auction, not the Dow), or forward trades. At roughly one qualifying session in
three, 70 forward trades is four to six months.

## 10. Fourth step: probability of backtest overfitting, and sizing

`research/us30_gap4.py`, the two protocol stages the rule had not been through.

**PBO (combinatorially symmetric cross-validation).** The 72-cell family (gap threshold × stop
× flat × filter on/off) on the research block, 12 contiguous groups, all 924 choices of 6 train
groups; in each split the train-best cell by daily Sharpe is ranked out of sample among all 72.

| family | PBO | median OOS rank of the in-sample winner |
| --- | --- | --- |
| all 72 cells | 0.49 | 0.50 |
| the 36 unfiltered cells | 0.52 | 0.44 |
| the 36 filtered cells | 0.65 | 0.33 |

Gate 5 (PBO < 0.30) fails, and the reading matters more than the pass/fail. On a plateau every
cell is roughly as good as every other, so which one wins in sample is noise and its
out-of-sample rank is a coin — that is what a PBO of 0.5 on a family with 94 of 96 positive
cells means. The filtered family's 0.33 says the in-sample winner tends to do *worse* than the
family average afterwards: the specific cell's research number regresses to the family mean.
The practical consequence is the one already stated in §7 and §9: the number to expect on new
data is the family's typical out-of-sample result (the walk-forward's +24.6 pt/trade on the
unfiltered family, the holdout's +6 to +15 on the shipped cells), never the research winner's.

**Sizing.** The gap is the unit of risk and the stop distance runs from 31 to 1,043 points
(median 174), so the coefficient of variation of dollar risk per trade at one contract is
**0.83** — sizing has something to work with. One pre-registered scheme against fixed lots, in
MYM ($0.50/pt) so lots are whole numbers, ranked on MAR (net ÷ max drawdown):

| scheme | block | net $ | max DD $ | MAR | mean lots |
| --- | --- | --- | --- | --- | --- |
| fixed 1 MYM | research | 3,058 | 253 | **12.1** | 1.0 |
| | locked | 521 | 574 | **0.91** | 1.0 |
| VAPS, 1% of $50,000 per trade, cap 20 | research | 8,042 | 1,718 | 4.7 | 6.5 |
| | locked | 1,197 | 1,581 | 0.76 | 4.9 |

Risk-normalised sizing is worse on both blocks by MAR, and over 2,000 trade orderings on
research its median MAR is 2.7 against 7.9 for fixed lots. The reason is specific to this rule:
the trades with the largest stop distance are the largest gaps, and those are the best trades,
so normalising risk shrinks exactly the trades that carry the edge. Fixed lots stay, which is
also what §9 of the protocol found across the whole book.

**Where the engineering stands.** Every stage the protocol has for a single rule has now been
run on the gap fill: matched control, neighbourhood, cost sweep, bootstrap, Monte Carlo,
deflated Sharpe, walk-forward, PBO, sizing, and one locked read per design decision. The rule
passed the ones a real edge passes on research (control, plateau, cost, walk-forward) and failed
the two that price in the size of the search (deflated Sharpe, PBO). That is the honest profile
of a modest, mechanism-backed effect measured on one file of one regime: worth forward trading
at one contract, not worth believing beyond its holdout numbers.

## Files

| file | what |
| --- | --- |
| `research/us30_alpha.py` | stage 2: robust autocorrelation, Lo-MacKinlay variance ratios, drift-adjusted time-of-day profile, event studies with lift / HAC / BH, predictability budget |
| `research/us30_mech.py` | the two pre-registered candidates, matched control, gates, one locked read |
| `research/us30_gap2.py` | walk-forward of the gap-fill family; the pre-registered entry-timing test; the stop read once |
| `research/us30_gap3.py` | the limit-fill test on the same days; four pre-registered conditions against random filters of the same selectivity; the one that passed read once |
| `research/us30_gap4.py` | PBO by combinatorially symmetric cross-validation on the 72-cell family; risk-normalised sizing against fixed lots on MAR |
| `pine/us30/US30_GapFill.pine` | the gap-fill rule as a Pine v6 strategy with forward-test alerts; linted with `research/pine_lint.py` |
| `pine/us30/US30_OpenRangeEmaCross.pine` | the original range-break rule, kept for the record |
