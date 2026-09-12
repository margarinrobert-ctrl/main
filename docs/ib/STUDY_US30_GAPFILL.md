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

## Files

| file | what |
| --- | --- |
| `research/us30_alpha.py` | stage 2: robust autocorrelation, Lo-MacKinlay variance ratios, drift-adjusted time-of-day profile, event studies with lift / HAC / BH, predictability budget |
| `research/us30_mech.py` | the two pre-registered candidates, matched control, gates, one locked read |
| `pine/us30/US30_GapFill.pine` | the gap-fill rule as a Pine v6 strategy with forward-test alerts; linted with `research/pine_lint.py` |
| `pine/us30/US30_OpenRangeEmaCross.pine` | the original range-break rule, kept for the record |
