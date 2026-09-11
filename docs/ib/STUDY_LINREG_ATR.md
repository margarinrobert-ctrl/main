# A linear regression as the primary, with ATR doing the risk

`research/linreg/`. Three feeds — `US30_LONG_15m`, `US100_LONG_15m`, `NQ_1m` — resampled to 15/30/60m.
Scored in **percent of entry price** (the stop moves with ATR, so R divides by a moving
denominator), long and short, one unit, each feed's own round turn.

## Why this is not the fourth run of a dead idea

`STUDY_V20_LINREG`, `STUDY_V25_LINREG_CROSS` and `STUDY_V38_LINREG_GRID` all bolted a regression
onto a Donchian breakout as a **confirmation**, and all three found it worthless — V20 measured the
most literal reading passing 12.1% of breakout bars, lift **0.24×**, because a breakout has just
jumped above the range the line is fitted to. **None of them ran the regression as the entry.**

Phase 0, stated before any code: a regression line is a least-squares estimate of where price
"should" be and its residual band is a scale-free distance from that estimate. Two mechanisms are
available and they point **opposite ways**, so both are declared: *trend* (the slope carries
information) and *reversion* (a large residual is corrected). No counterparty is named for either,
so this is a fitted pattern carrying the full deflation burden.

Five readings, each mirrored for the short side so no freedom is spent on direction: **S** slope > 0,
**X** slope crosses 0, **V** close > value, **B** close > value + k·σ, **R** close < value − k·σ.

The rolling OLS was checked against `numpy.polyfit` before use: **0 mismatches of 4 probes** on
value, slope and residual σ.

## Base rates first, and two of the five die there

Share of **all** research bars on which each reading fires long, over 3 markets × 3 timeframes:

| reading | S slope state | V close>value | R revert | B break | X cross |
|---|---|---|---|---|---|
| fires on | **0.5568** | **0.4963** | 0.1298 | 0.1214 | **0.0137** |

A condition that holds on half the bars is a direction label, not an entry. That prediction is what
the grid then confirms: the only two readings with a positive marginal are the two selective ones.

## The grid — 1,080 declared cells, research blocks only

5 readings × 3 lengths × 2 bands × 2 stops × 2 targets × 3 timeframes × 3 markets. **29.5% profitable.**
Marginal average of %/trade:

| axis | | | | |
|---|---|---|---|---|
| reading | X **+0.0109** | B **+0.0034** | S −0.0051, V −0.0056 | R **−0.0160** |
| length | 100 −0.0008 | 50 −0.0019 | 20 −0.0080 | |
| band | 2.0 σ −0.0022 | 1.5 ATR −0.0071 | | |
| target | none −0.0010 | 2R −0.0062 | | |
| timeframe | 60m −0.0003 | 30m −0.0036 | 15m −0.0068 | |

Every marginal is negative except the two selective readings; the timeframe axis runs to the slow
edge of the grid; **no take profit wins for the 22nd time**; and the reversion reading is the worst
row in the table, so on this data the regression band is not a level price returns to.

## Against a matched random entry — nothing clears

Same side mix, same stop, same target, same opposite-reading exit, sorted, 400 draws. 60m, length 50,
k = 2.0σ, 2.5 ATR stop, no target.

| reading | market | block | n | %/trade | PF | control | p | P(mean≤0) |
|---|---|---|---|---|---|---|---|---|
| B break | US30 | research | 1131 | +0.0041 | 1.015 | −0.0025 | 0.357 | 0.458 |
| B break | US30 | HOLDOUT | 415 | −0.0347 | 0.853 | −0.0046 | 0.932 | 0.865 |
| B break | US100 | research | 1210 | +0.0242 | 1.069 | −0.0037 | 0.102 | 0.187 |
| B break | US100 | HOLDOUT | 409 | +0.0387 | 1.127 | −0.0042 | 0.120 | 0.191 |
| B break | NQ | research | 436 | +0.0422 | 1.160 | +0.0010 | **0.070** | 0.123 |
| B break | NQ | HOLDOUT | 143 | +0.0555 | 1.179 | −0.0193 | 0.145 | 0.261 |
| X cross | US30 | research | 456 | +0.0844 | 1.210 | −0.0255 | 0.100 | 0.110 |
| X cross | US30 | HOLDOUT | 153 | +0.0871 | 1.249 | +0.0628 | 0.422 | 0.221 |
| X cross | US100 | research | 494 | +0.0467 | 1.087 | −0.0472 | 0.115 | 0.263 |
| X cross | NQ | research | 172 | +0.1203 | 1.304 | +0.0033 | 0.128 | 0.105 |
| X cross | NQ | HOLDOUT | 61 | **−0.2668** | **0.590** | −0.1207 | 0.792 | 0.877 |

**Not one cell clears p ≤ 0.05 on research**; the best p anywhere is 0.070. `B channel break` is
positive on **5 of 6** market-blocks with its control sitting at zero — an honest null rather than a
losing one, which `STUDY_IB_US30_OPTUNA` and `STUDY_VWAP_EMA_GOLD` both flag as the distinction that
matters. `X slope cross` has the largest numbers and **inverts on NQ out of sample** (+0.1203 →
−0.2668, PF 1.304 → 0.590). At length 100 it fails research on US30 (p 0.453) and then reads PF
1.970 on the holdout — the wrong shape, and a defect rather than a result.

The holdout column is **descriptive**: these blocks have been read many times here, and this is a
1,080-cell search on top of that.

## Parity

Residual σ: Pine has no built-in, so the script writes the loop out using the identity that
`ta.linreg(close, n, k)` is the same fit evaluated k bars back — value − slope·k. Against the
engine: **max |diff| 1.6e-12 to 3.1e-12, correlation 1.0000000000** on all three feeds. Order model:
trade count ratio 0.997/0.998/0.997, per-trade correlation 0.9994/0.9997/1.0000, gap conservative on
five of six blocks (the exception is US30 research at +20.4% on a +4.59% base — a near-zero
denominator, so read the sign not the percentage).

## Verdict

Ships `pine/linreg/LINREG_ATR_CHANNEL_strategy.pine` with all five readings selectable, `B` as the
default because it is the best-behaved and not because it passed anything, and every number above in
its header. **No edge is claimed.** The median hold at the leaders is 6–26 hours, so it is not a
scalp and the hold cap is off. What the study does establish is the base-rate table: two of the five
readings people commonly trade fire on half of all bars, and the grid's marginals agree with that
before any p-value is computed.
