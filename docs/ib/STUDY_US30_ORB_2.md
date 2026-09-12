# US30 09:00 range, second pass: the time held, every other rule widened — still nothing

*Follow-up to [`STUDY_US30_ORB.md`](STUDY_US30_ORB.md). The instruction was to keep tweaking the
rules, holding the time, until the strategy is profitable. This pass keeps the 09:00–09:30 range
and the 09:30–10:30 entry window fixed and widens the RULE space along axes that each name a
mechanism, with the same protocol in front: research block only, a matched control as the gate,
a plateau requirement, a bare-mechanic baseline, and one read of the locked block.*

*Result:* **12,672 more cells on top of the 16,200 in pass one. 13 beat the matched control at
z > 2 on research, where 41 would by chance. None of the 13 is a plateau; none beats its own
entry mechanic run with no filter. The one plateau cell carried to the locked block did better
there than on research — the wrong shape — and its bare limit-retest mechanic alone made
11.6 points a trade on locked, so what it found was an execution effect in one regime, not a
signal. Two passes, 28,872 cells, one file. A third pass on this file would be mining, and the
protocol would say so.**

> Reproducible: `python3 research/us30_orb2.py`. Same data, split and cost model as pass one.
> Research output, not financial advice.

---

## 1. What was widened

| axis | values | the mechanism each names |
| --- | --- | --- |
| entry mechanic | **close-break** at the next open (pass one); **stop** order resting at the level + 5 pt, filled intrabar; **limit** at the level after a close-break, filled on the retest (must trade through by 1 pt); **fade** — a close back inside the range after a break, traded against the break | immediacy vs a better fill vs a failed breakout |
| momentum | EMA 13/48 state; EMA 8/34 state; a fresh 13/48 cross within 2 bars; none | is the EMA condition doing anything |
| trend gate | EMA 200 on / off | |
| break distance | any close beyond; a close beyond by ≥ 25% of the range width | conviction of the break |
| volume | none; break-bar volume ≥ 1.5× the median of the 09:30–10:15 bars over the prior 20 sessions | the column pass one never read |
| range width | any; tight (≤ 1.5 × ATR(14)); wide (≥ 2 × ATR) | compression → expansion |
| overnight gap | any; the break must be with the gap; against it | gap continuation vs gap fill |
| exits | 100/100, 75/75, 50/100, 100/200 pt; stop at the range midpoint or far side with a target of 1× or 2× the width beyond the level; break-even after half the target; flat 12:00 or 16:00 | |

4 × 4 × 2 × 2 × 2 × 3 × 3 = 1,152 rules × 11 geometries = 12,672 cells; 1,781 have at least 60
research trades.

Conditions are read on the bar before the fill for every mechanic. For the stop entry that is
the prior bar, because the fill is intrabar. The stop entry can fill on the 09:30 bar itself,
whose median range is 160 points; a range-anchored stop of 40 points inside a 220-point bar is
booked as a loss under the stop-first rule, and that shows in the numbers below.

## 2. The gates, fixed before running

1. ≥ 60 research trades
2. both sides traded, ≥ 25% on the minority side (direction is not free on a file that rose 32%)
3. matched control z ≥ 2.0 — random sessions in the same block, same side, same fill minute,
   the trade's **own** stop and target, entry at that bar's open, 300 draws
4. neighbour stability ≥ 0.7 — the median z of the one-step neighbours on every rule axis,
   divided by the cell's own z
5. beats the same entry mechanic run on every session with no filter by ≥ 5 pt/trade, because a
   mechanic that pays on random days is an execution effect (`STUDY_LIMIT_ENTRY.md`)

## 3. The mechanics alone, research, no filter, both sides

| mechanic | geometry | n | win | per trade | control z |
| --- | --- | --- | --- | --- | --- |
| close-break | 100/100 pt | 324 | 48.8% | −6.1 | −0.30 |
| close-break | mid / 1× width | 143 | 43.4% | −20.9 | −2.01 |
| stop at level + 5 | 100/100 pt | 331 | 47.1% | −9.0 | −0.35 |
| stop at level + 5 | mid / 1× width | 308 | 15.3% | −34.2 | −6.95 |
| limit retest | 100/100 pt | 209 | 47.8% | −6.4 | −0.29 |
| limit retest | mid / 1× width | 169 | 33.7% | −7.6 | −0.67 |
| fade | 100/100 pt | 132 | 47.7% | −6.9 | −0.23 |
| fade | mid / 1× width | 73 | 42.5% | −17.4 | −1.28 |

No mechanic pays on its own on the research block. The stop entry with a range-anchored stop is
the 09:30-bar problem above: 98 of 308 trades have both barriers inside the fill bar.

## 4. The sweep

| statistic | value |
| --- | --- |
| median z over 1,781 cells | **−0.95** |
| 90th percentile z | 0.81 |
| cells with z > 2 | **13 (0.7%)**, against 41 (2.3%) expected from noise |
| … that are plateaus (stability ≥ 0.7) | **0** |
| … that beat their bare mechanic by 5 pt | **0** |

Median z by axis value:

| axis | values → median z |
| --- | --- |
| entry | close −0.57 · fade −0.39 · limit −0.30 · stop **−2.19** |
| momentum | 13/48 −1.10 · 8/34 −0.74 · fresh cross −0.17 · none −1.10 |
| trend gate | off −0.95 · 200 −0.95 |
| break distance | any −1.01 · ≥ 25% width −0.87 |
| range width | any −0.85 · tight −0.58 · wide **−2.02** |
| gap | against **+0.03** · any −0.81 · with **−1.57** |
| exits | 100/100 flat 16:00 −0.30 · 100/100 flat 12:00 −0.41 · 75/75 −0.64 · 100/100 BE −0.45 · 50/100 −0.87 · 100/200 −0.99 · far/1× −1.93 · far/2× −1.77 · mid/2× −2.08 · mid/1× BE −2.95 · mid/1× **−3.20** |

Two things stand out and neither is an edge. Range-anchored exits are uniformly worse than fixed
points, because a 40-point stop on this instrument is inside one 15-minute bar's noise. And the
only axis value with a non-negative median is "break against the overnight gap", which is a
gap-fill regularity: it lifts the family from −0.8 to 0.0, i.e. from losing to a coin.

The 13 cells above z = 2 are all in that corner:

| entry | mom | trend | dist | gap | geometry | n | win | per trade | L / S | z |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| limit | none | off | 25% | against | far / 1× width | 89 | 69.7% | 25.2 | 37 / 52 | 3.90 |
| limit | none | off | 25% | against | mid / 1× width BE | 69 | 44.9% | 21.3 | 27 / 42 | 3.71 |
| limit | none | off | 25% | against | mid / 1× width | 69 | 49.3% | 21.6 | 27 / 42 | 3.46 |
| limit | none | off | any | against | far / 1× width | 115 | 62.6% | 16.7 | 50 / 65 | 3.07 |
| limit | none | off | 25% | against | 100/100 BE | 89 | 38.2% | 20.5 | 37 / 52 | 2.71 |
| limit | none | off | 25% | against | 75/75 | 89 | 61.8% | 14.3 | 37 / 52 | 2.54 |
| limit | none | off | 25% | against | mid / 2× width | 69 | 27.5% | 22.9 | 27 / 42 | 2.45 |
| limit | none | off | 25% | any | 100/100 BE | 172 | 35.5% | 13.4 | 77 / 95 | 2.42 |
| limit | none | off | 25% | against | 50/100 | 89 | 44.9% | 13.9 | 37 / 52 | 2.38 |
| close | 8/34 | off | any | against | far / 2× width | 70 | 68.6% | 24.1 | 31 / 39 | 2.26 |
| limit | none | off | 25% | any | far / 1× width | 170 | 61.2% | 8.4 | 76 / 94 | 2.26 |
| close | 8/34 | off | any | against | mid / 2× width | 70 | 58.6% | 17.6 | 31 / 39 | 2.03 |
| limit | 8/34 | off | 25% | any | far / 1× width | 130 | 60.0% | 8.1 | 62 / 68 | 2.01 |

Nine of thirteen are one rule (limit retest, no momentum, no trend, break by 25% of the width,
against the gap) under different exits, on 69–89 trades. Its stability is below 0.7 on every
geometry: move any one axis a step and the z collapses. That is the definition of a spike, and
the momentum condition the strategy is built around is absent from every one of them.

**Volume.** The 1.5× threshold qualifies only 10.6% of break bars (the break bar's volume over
the prior-20-session window median has a median of 1.13 and a 90th percentile of 1.53), so no
volume cell reached 60 research trades and the axis was effectively untested in the sweep. An
addendum at thresholds that leave a sample, research only, matched control:

| mechanic | threshold | momentum | n | z |
| --- | --- | --- | --- | --- |
| close | ≥ 0.8× | none / 13/48 | 303 / 233 | −0.02 / −0.66 |
| close | ≥ 1.0× | none / 13/48 | 247 / 178 | 0.19 / 0.22 |
| close | ≥ 1.25× | none / 13/48 | 106 / 75 | **−1.86 / −1.60** |
| limit | ≥ 0.8× | none / 13/48 | 192 / 130 | −0.04 / 0.23 |
| limit | ≥ 1.0× | none / 13/48 | 149 / 98 | 0.14 / 0.61 |
| limit | ≥ 1.25× | none / 13/48 | 71 / 46 | −0.13 / −0.46 |

The higher-volume breaks are the worse ones. The column adds nothing.

## 5. The one cell carried to the locked block

Nothing passed the research gates, so per the pre-registered fallback the single best plateau
cell was read on locked once, for the shape to be on record: **limit retest, EMA 13/48 state, no
trend gate, break ≥ 25% of the width, 75/75 points, flat 16:00** — research z 1.73, stability 0.76.

| block | n | win | net | per trade | PF | control z | bare mechanic, same block |
| --- | --- | --- | --- | --- | --- | --- | --- |
| research | 123 | 56.9% | 784 pt | 6.4 | 1.19 | 1.73 (p 0.045) | −0.1 pt/trade |
| **locked** | 68 | 61.8% | 970 pt | **14.3** | 1.47 | 2.30 (p 0.014) | **+11.6 pt/trade** |

Deflated Sharpe on research against 15,206 trials: **0.000** (per-trade SR 0.085 against a hurdle
of 0.774). Bootstrap 95% CI on research net [−675, 2,193] pt, P(net ≤ 0) 0.15. Cost sweep on
research: 9.4 / 6.4 / 3.4 / −0.6 pt at 0 / 3 / 6 / 10 points.

On the locked block it made more than twice per trade what it made on research, and 44 of its 68
trades were long at 20.5 pt/trade against 2.8 for the shorts. Two independent facts explain it
without a signal:

1. **The bare mechanic made 11.6 pt/trade on locked with no filter at all**, against −0.1 on
   research. A resting limit at the broken level, filled on the retest, paid in the 2026 regime
   and not in 2025. That is exactly the `STUDY_LIMIT_ENTRY.md` finding — short-horizon mean
   reversion at the execution layer — and it is a property of the fill, not of the EMA cross.
2. **Better on locked than on research is the wrong shape.** A rule chosen on research should
   look better there; the holdout is where an edge decays, not where it appears. This is the
   third time this repository has seen the shape and each time it was a defect.

## 6. What this says

| gate | pass one, as specified | pass one, best plateau | pass two, best plateau |
| --- | --- | --- | --- |
| positive net on research | ✗ | ✓ | ✓ |
| beats matched control z ≥ 2 on research | ✗ (−0.84) | ✗ (1.38) | ✗ (1.73) |
| plateau | n/a | ✓ (0.98) | ✓ (0.76) |
| beats bare mechanic by 5 pt | ✗ | n/a | ✗ (+6.5 research, +2.7 locked) |
| deflated Sharpe > 0.95 | ✗ (0.00) | ✗ (0.23) | ✗ (0.00) |
| right shape on locked | decays to −23.4 | decays to −8.1 | **improves** to +14.3 |
| walk-forward ≥ 0.4 | ✗ | ✗ | not run — failed upstream |

After 28,872 cells the best thing on this file is a limit-retest fill in one regime, with the
strategy's own momentum and trend conditions contributing nothing on any axis in either pass.
Under the protocol that is a null result, and it is the honest answer to "keep tweaking until it
is profitable": on 15-minute OHLC of this instrument, in this window, there is nothing to tune
toward. The three things that would change the question are unchanged from pass one, and the
first is the one that matters:

1. **One-minute bars for the same period.** The idea is a one-minute idea; here the 09:30 bar
   alone spans more than the barrier, and stop entries on it are decided before the open.
2. **The instrument's real cost.** Irrelevant to the verdict (the rule loses at zero cost) but
   the limit-retest mechanic's 11.6 pt on locked is the kind of number a 3-point assumption can
   make or break.
3. **A second instrument or more history.** Both blocks here sit inside one bull market.

## 7. Addendum: the entry at the line itself

The user's clarification after pass two: the entry belongs **at the 09:00 high or low**, not at
the close of the bar that breaks it. That is a stop order resting at the level, filled the moment
price trades through it, with the EMA and trend conditions read on the bar before the fill
(`Rule2(entry="stop", buffer=0)`; pass two's stop cells used a 5-point buffer). It is now the
Pine script's default. Same geometry, 100/100, flat 16:00:

| variant | block | n | win | per trade | PF | control z |
| --- | --- | --- | --- | --- | --- | --- |
| **at the line**, EMA 13/48 + EMA 200 | research | 263 | 49.0% | −5.5 | 0.90 | 0.03 |
| | locked | 151 | 41.1% | **−20.6** | 0.66 | −1.58 |
| at the line, no trend gate | research | 299 | 46.2% | −11.2 | 0.80 | −1.00 |
| | locked | 166 | 39.8% | −23.3 | 0.62 | −1.86 |
| at the line, every break, no conditions | research | 332 | 49.1% | −4.7 | 0.91 | 0.40 |
| | locked | 179 | 46.9% | −8.7 | 0.84 | 0.07 |
| limit at the line on the retest, EMA 13/48 + 200 | research | 123 | 49.6% | −4.5 | 0.91 | 0.02 |
| | locked | 84 | 56.0% | +10.0 | 1.23 | 1.45 |
| market at the next open (the original) | research | 232 | 47.4% | −10.1 | 0.81 | −0.85 |
| | locked | 130 | 40.0% | −23.4 | 0.62 | −2.24 |

A second clarification: the entry still looked late on the chart. The reason is sequencing, not
the order type. The resting stop can only sit at the line while the conditions already hold, and
on many days the break bar is what flips the fast EMA, so the conditions confirm at the close of
the break bar with price already beyond the line; a stop placed then is below the market and
fills at the next open. The Pine now has a "late rule" input for that case, and each choice was
measured as the first fill per session across the two mechanics:

| stop at the line, then when conditions confirm after the break … | block | n | win | per trade | control z |
| --- | --- | --- | --- | --- | --- |
| wait for the retest at the line (default) | research | 266 | 50.8% | −2.1 | 0.58 |
| | locked | 153 | 42.5% | −17.8 | −1.25 |
| enter at market now | research | 274 | 48.5% | −6.5 | −0.13 |
| | locked | 156 | 41.7% | −19.4 | −1.46 |
| EMA condition off, trend gate only (order always resting from 09:15) | research | 305 | 45.2% | −12.9 | −1.24 |
| | locked | 169 | 40.2% | −22.4 | −1.80 |

Entering at the line is better than entering at the next open by about 4.6 points a trade on
research, which is roughly the distance the close-break entry gives up, and it is still a coin
flip against its control (z 0.03) that loses 20.6 a trade on the holdout. The EMA conditions
make it worse than taking every break. The retest limit is the only positive locked number in
either pass, and §5 says why it is not a signal.

## Files

| file | what |
| --- | --- |
| `research/us30_orb2.py` | the second pass: session facts (range, ATR, gap, volume baseline), the four entry mechanics, filters, range-anchored and break-even exits, a matched control that carries each trade's own geometry, the bare-mechanic baseline, gates, one locked read |
| `research/us30_orb.py` | pass one, reused for data, metrics, bootstrap, Monte Carlo |
| `pine/us30/US30_OpenRangeEmaCross.pine` | unchanged defaults; header notes this pass |
