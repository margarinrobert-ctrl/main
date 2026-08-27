# V16 — 2,167 momentum conditions on a Donchian breakout, and why none of them work

**The result is negative and the mechanism is legible.** A Donchian break is itself a momentum
event, so a momentum filter is 1.9–3.2× redundant with the trigger and can only discard trades.
95% of breakout bars already pass an RSI filter.

---

## 1. The design

The brief was to add a momentum indicator to a Donchian 30/20 breakout, **market orders only**, and
find the most profitable model. The motivating literature is the commodity-futures momentum /
trend-following result — rank a cross-section on past return, buy the winners, apply a
trend-following overlay — whose own headline is that *the marginal contribution of trend following
far outweighs momentum*. Three of its four moving parts port to one intraday instrument:

| paper | here |
| --- | --- |
| cross-sectional momentum rank | **time-series momentum** — this instrument's own past return, signed and sized. There is no cross-section to rank. |
| volatility-weighting the past return | `tsmom` = past return ÷ (rolling σ × √L), a t-statistic of drift; `roc` is the unscaled control |
| the trend-following overlay | **the Donchian breakout itself** |
| risk-parity portfolio weights | not portfolio-testable on one instrument, but its per-trade equivalent is applied throughout: every result is in **R**, P&L over the trade's own stop distance |

**The pool.** 58 scores — raw and vol-scaled momentum at 7 lookbacks, four multi-horizon agreement
constructs, EMA distance and price slope at 4 lengths (the trend axis, measured in the same pool so
the paper's primary claim is testable), and RSI / Stochastic / Williams %R / CCI / CMO / Aroon /
TRIX at 4 periods each plus MACD line, MACD histogram, TSI and the Awesome Oscillator. Each carries
its own threshold ladder, 366 rungs in total, on 5m / 15m / 30m bars of NQ (2022-12-26 → 2025-12-12,
1-minute source), both sides. **2,167 tests.**

Every score is signed so positive means up-momentum and every condition is applied as
`side × (score − centre) ≥ offset`. The mirroring is not cosmetic: a rule that tunes its long and
short thresholds separately spends degrees of freedom on direction, and on a sample where NQ rose
89% a search allowed to pick a side always picks long.

**The null** is a random filter of the same selectivity drawn from the same breakouts and run
through the same position lock — not total dollars, which fails every restrictive condition, and
not per-trade edge, which passes every one.

---

## 2. What the research block said, and what the holdout said

| | |
| --- | --- |
| conditions tested (research only, first 65% of sessions) | 2,167 |
| profitable there | 742 |
| **and** beating a same-selectivity control at p ≤ 0.05 | **99** |
| expected by chance | ≈ 37 |

That looks like a result. It is not:

| locked block | |
| --- | --- |
| of the 99, still profitable | 69 (70%) |
| of the 99, still beating the **unfiltered breakout** | **28 (28%)** |
| expected by chance | 50% |
| correlation, research edge vs locked edge | **+0.107** |

They replicate *worse than a coin flip*. The 15m long group is the clearest: 50 survivors, 96% still
profitable on the holdout, **8%** still better than doing nothing — they "work" only because being
long works.

**The best cell in the whole search was rejected before the holdout was read.** `agree20_60 ≥ 1`
on 15m long: 285 trades, +91.1R, Sharpe 2.30, p 0.0000. Its own neighbourhood disqualifies it — the
four rungs below score −1.2, +6.1, −1.1 and −4.4 against the same control. A win rate that exists at
one threshold and nowhere near it is not a mechanism. (`tsmom40`, which was carried forward instead,
had a genuine plateau: +12.8, +25.5, +52.6, +45.7, +50.1 across five consecutive rungs. It still
failed the holdout — the shape was necessary, not sufficient.)

---

## 3. Why it cannot work

A Donchian break **is** a momentum event. Share of bars satisfying each condition, 30m research:

| condition | all bars | breakout bars | lift |
| --- | --- | --- | --- |
| RSI(14) ≥ 55 | 41.0% | **94.7%** | 2.31× |
| ema(50) distance ≥ 0.5N | 49.4% | 93.2% | 1.89× |
| CMO(21) ≥ 20 | 30.3% | 79.1% | 2.61× |
| tsmom(40) ≥ 0.5 | 36.2% | 74.1% | 2.05× |
| Aroon(7) osc ≥ 60 | 24.9% | 70.9% | 2.85× |

The filter is not adding information; it is removing a twentieth of the sample. This is the paper's
headline seen from underneath — and it is *sharper* intraday on one instrument than cross-sectionally
on thirty, because there is no cross-section for a momentum rank to contribute.

Ten filters spanning every family, applied to the shipped configuration, locked R/trade:

| filter | locked R/trade | vs base |
| --- | --- | --- |
| **none** | **+0.1033** | — |
| aroon7 ≥ 60 | +0.1587 | +0.0555 |
| tsmom40 ≥ 1 | +0.1051 | +0.0018 |
| emadist50 ≥ 0.5 | +0.0755 | −0.0278 |
| rsi14 ≥ 55 | +0.0726 | −0.0307 |
| cmo21 ≥ 20 | +0.0703 | −0.0330 |
| roc40 ≥ 2 | +0.0352 | −0.0681 |
| tsmom40 ≥ 0.5 | +0.0213 | −0.0820 |
| agree20_60 ≥ 1 | +0.0028 | −0.1004 |
| macd ≥ 0.5 | −0.0073 | −0.1105 |
| slope50 ≥ 0.02 | −0.0754 | −0.1787 |

Two of ten beat doing nothing, neither by enough to survive its own multiplicity.

### The volatility-scaling question, answered

The paper insists past returns be volatility-scaled before ranking. That argument is about a
cross-section; on one instrument there is nothing for the scaling to fix, and matched on trade
count the two versions are the same rule:

| condition | trades | net R | PF | Sharpe |
| --- | --- | --- | --- | --- |
| `tsmom40 ≥ 0.5` (vol-scaled) | 585 | +71.9 | 1.193 | 1.01 |
| `roc40 ≥ 2.0` (raw) | 553 | +65.0 | 1.188 | 0.99 |
| `tsmom40 ≥ 1.0` | 409 | +76.2 | 1.304 | 1.40 |
| `roc40 ≥ 3.0` | 448 | +73.4 | 1.282 | 1.34 |

---

## 4. What the search actually measured

The one configuration that holds its edge across both blocks is the one the brief already named,
with no filter: **Donchian 30 entry / 20 exit, market order at the next open, long only, 30-minute
bars**, stop at the nearer of 2.0 × ATR(14) and the 20-bar low.

| block | trades | days | net R | R/trade | PF | win% | Sharpe | maxDD | worst day |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| research | 435 | 360 | +49.0 | +0.1126 | 1.193 | 32.18% | 1.03 | 25.16R | −3.13R |
| **locked** | 226 | 196 | +23.3 | **+0.1033** | 1.188 | 35.84% | 1.03 | 23.53R | −3.85R |

The two blocks agree to within 0.01 R per trade. Nothing else in this study does. Quarter by
quarter over the whole sample: **9 of 13 positive, worst −10.1R**. Monte Carlo on the locked daily
series: realised drawdown 23.5R against a median of 18.0 and a p99 of 34.5.

**And it does not beat its matched control.** Random entries with the same side, geometry and
minute-of-day mix, 2,000 draws: research **p = 0.1625**, locked **p = 0.1610**. Bootstrap on the
locked daily series puts P(mean daily R ≤ 0) at **0.182**. The +0.10 R per trade is consistent with
being long, at these times, with these barriers. The break itself is not established as the source.

### Geometry, by marginal average per axis

72 cells, research block, unfiltered, 30m long — the median over each axis, never the top cell:

| axis | rungs |
| --- | --- |
| exit channel | 10: +0.032 · 15: +0.040 · **20: +0.071** · 25: +0.066 · 30: +0.057 · 40: +0.075 |
| ATR stop | 1.5: +0.035 · **2.0: +0.065** · 2.5: +0.065 · 3.0: +0.044 |
| target | **none: +0.076** · 2R: +0.042 · 3R: +0.049 |

97% of the 72 cells are profitable, so the exit is not what is being fitted. **No take profit beats
every take profit — the fifth time on this branch.** On 15m the same sweep prefers a longer exit
channel and only 60% of cells are profitable, which is why 30m ships and 15m does not.

The short side loses on both blocks (−0.0950 research, −0.0552 locked) and ships off.

---

## 4b. The trading window and the flatten

Added to the script on request, both **off by default**, and measured rather than offered. Seven
windows and three flatten times — a set fixed in advance, not a sweep, because a swept start and end
is a free lottery on a sample where the intraday constraint has already failed eleven independent
times here.

| entry window | research R/trade | locked R/trade | locked PF | control p (locked) |
| --- | --- | --- | --- | --- |
| all hours | +0.1126 | +0.1033 | 1.188 | 0.152 |
| **08:00–12:00** | **+0.1521** | **+0.1872** | **1.339** | **0.024** |
| 07:00–11:00 | +0.0394 | +0.1736 | 1.287 | 0.100 |
| 09:30–12:00 | +0.0972 | +0.0491 | 1.098 | 0.246 |
| 09:30–16:00 | +0.0903 | +0.0198 | 1.040 | 0.416 |
| 13:00–16:00 | +0.1440 | +0.0289 | 1.075 | 0.368 |
| 09:30–11:00 | +0.0705 | +0.0119 | 1.023 | 0.487 |

**08:00–12:00 New York is the only window better than all hours on both blocks**, and the only one
clearing a minute-of-day matched control out of sample. It is a **candidate, not a finding**: seven
windows were tested, so p 0.024 corrects to **0.168** and does not clear its own multiplicity.

Read the other rows for what they are. 13:00–16:00 has the best *research* profit factor in the
table (1.423) and dies out of sample. 09:30–11:00 — which `STUDY_TREND_PULLBACK` preferred on a
different instrument and a different family — is the **worst** cell here, +0.0705 → +0.0119 at
p 0.487. A session preference does not transfer across strategies.

The flatten costs about half the per-trade edge when there is no window, because it truncates
exactly the trades the channel exit exists to hold:

| configuration | research R/trade | locked R/trade | locked PF | locked Sharpe |
| --- | --- | --- | --- | --- |
| window off, flatten off | +0.1126 | +0.1033 | 1.188 | 1.03 |
| window off, flatten 16:00 | +0.0380 | +0.0481 | 1.116 | 0.73 |
| 08:00–12:00, flatten off | +0.1521 | +0.1872 | 1.339 | 1.79 |
| 08:00–12:00, flatten 16:00 | +0.0957 | +0.1853 | 1.347 | 1.94 |

Inside the window the flatten is roughly free — a trade entered before noon rarely survives to 16:00
— and on research it still costs 0.06 R a trade.

**The flatten fills at the next bar's open**, not at the close of the bar that triggers it, because
that is what `strategy.close_all()` does. The research engine was changed to match the script rather
than the other way round (`flat_open` in `v16core._walk`), so the figures above are the script's.

---

## 5. Parity

`research/v16/v16_parity.py` re-implements the shipped script's order model and diffs it against the
engine on both blocks, both sides, 15m and 30m: **exit-bar match 100%, P&L correlation 1.0000,
signal match 99.6–100%** (the residual is one trade at a block boundary). Three things it had to get
right, each of which has been wrong on this branch before: the bracket must be live on the entry
bar; `strategy.exit(stop=, loss=)` gives `max(ATR stop, channel)` because Pine takes the smaller
loss, where two separate orders would race; and the exit channel takes **no `[1]`**, since the order
is placed at this bar's close and is live on the next.

## Files

`research/v16/v16mom.py` (the 58-score pool) · `v16core.py` (precomputed outcomes + numba position
lock) · `v16run.py` (the 2,167-test sweep and its selectivity null) · `v16phase2.py` (ladders,
geometry, minute-of-day control) · `v16final.py` · `v16verdict.py` (the replication test) ·
`v16ship.py` · `v16window.py` (the window and flatten measurements) · `v16_parity.py` · `pine/turtle/V16_DONCHIAN_MOM_strategy.pine`.
