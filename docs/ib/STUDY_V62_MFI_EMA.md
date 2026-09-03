# V62 — ADX and CHOP out, the Money Flow Index and EMA-cross momentum in, and both are null

`research/v62/` — `v62core.py` (the grid, built so every filtered cell has an exact `off` twin),
`run_v62.py` (base rates, population, marginals, matched pairs — research only), `run_v62b.py` (one
locked read), `run_v62c.py` (the drop-one and the spike test), `run_v62d.py` (post-hoc, and labelled
so). Output in `results/v62/`. Ships `pine/v62/V62_CVD_MFI_EMA_strategy.pine`.

---

## 1. The base rate, which comes first

The branch rule is explicit: **compute a proposed confirmation's base rate on the trigger's own bars
before sweeping anything.** On NQ 30-minute Donchian-20 breakout bars:

| condition | passes of breakouts | of all bars | lift |
|---|---|---|---|
| MFI(9) ≥ 50 | **91.7%** | 52.4% | 1.75 |
| MFI(14) ≥ 55 | 85.8% | 43.0% | 1.99 |
| MFI(14) ≥ 60 | 77.2% | 34.5% | 2.24 |
| MFI(9) ≤ 80 | **58.6%** | 87.8% | **0.67** |
| EMA 13/48 state | 80.1% | 57.8% | 1.39 |
| EMA 21/55 spread rising | **91.1%** | 49.2% | 1.85 |
| EMA 21/55 spread momentum ≥ 0.02 ATR | 85.4% | 38.9% | 2.20 |
| EMA 13/48 cross within 5 bars | **14.9%** | 6.6% | 2.25 |

**A breakout IS a money-flow event and IS an EMA-spread event.** `MFI ≥ 50` removes 8% of the
signals; `spread rising` removes 9%. Only two readings in the whole pool actually bind: the
overbought CEILING (`MFI ≤ 80`, the one reading with a lift *below* 1) and the RECENCY form of the
cross. Fourth time this has been measured here — RSI(14) ≥ 55 at 94.7% (`STUDY_V16`), Aroon
osc ≥ 0 at 100.0% (`STUDY_V60`), MACD > 0 at 99.8–100.0% (`STUDY_V60`), and now these.

## 2. The grid, and why it is built in twins

3,096,576 cells: timeframe 15/30/60 × entry channel 15/20/30 × exit channel 10/20/30 × stop
1.5–3.0 N × target none/3/4/6 ATR × adaptive stop on/off × CVD gate (off, k∈{3,5} × w∈{10,20,30}) ×
prior-session-high on/off × **16 MFI settings** (off + 5 readings × 3 lengths) × **16 EMA settings**
(off + 5 readings × 3 pairs). ADX and CHOP are gone, as asked; the max-hold axis was dropped
because V61 measured it inert.

Every filtered cell therefore has an exact `off` twin with every other axis held fixed, which makes
the ablation free. 2,064,245 cells clear a 60-trade research floor; **94.8% of them are profitable
on research**.

## 3. What the marginals say, and what the matched pairs say

The marginal average per axis is mildly encouraging for both families — `MFI ≥ 60` at +9.4% total
against `off` at +8.4%, `spread > 0 and rising` at +9.0% against +8.7%. **The matched pairs, which
hold every other axis fixed, settle it. Chance is 50%.**

| family | research pairs improved | **locked pairs improved** | research→locked Spearman |
|---|---|---|---|
| MFI, 15 readings | 57.8% | **49.3%** | **−0.257** |
| EMA, 15 readings | 59.0% | 58.0% | **−0.618** |

**The MFI is chance.** And the EMA's 58% is worse than it looks, because the ordering *inverts*:

| reading | research helps | locked helps |
|---|---|---|
| `spread > 0 and rising` 21/55 | **82.5%** | 55.8% |
| `state` 21/55 | 78.6% | **43.2%** |
| `spread > 0 and rising` 13/48 | 72.5% | 59.1% |
| `spread rising` 21/55 | 56.9% | 73.3% |
| `cross ≤ 5` 9/21 | 49.5% | 71.9% |
| `cross ≤ 5` 13/48 | **30.3%** | **85.3%** |

The reading that helped *least* on research helps *most* on the locked block and vice versa. That
is noise with a sign, not a filter — and note that the two readings that do best out of sample are
the RECENCY forms, which is what `STUDY_V41` already identified as the only selective form of an
EMA cross.

Individually the MFI readings behave the same way: `MFI ≥ 55` at length 14 and 21 helps 74.4% of
pairs on research and **40.5% and 32.2%** on locked.

## 4. The drop-one at the best cell the search could find

The top-Sharpe cell of 2,055,874 does contain both an MFI and an EMA condition — 30m, entry channel
15, exit 10, 3.0 N adaptive stop, 3 ATR target, CVD k3/w20, `MFI(14) ≥ 60`, `spread momentum ≥ 0.02
ATR` on 21/55. Removing its conditions one at a time, at that exact geometry, on the **locked**
block:

| variant | n | %/trade | PF | random-filter p | random-entry p | bootstrap |
|---|---|---|---|---|---|---|
| as found (MFI + EMA) | 84 | +0.1203 | 1.68 | 0.001 | 0.070 | 0.040 |
| drop the MFI | 116 | +0.1025 | 1.59 | 0.003 | 0.065 | 0.036 |
| drop the EMA momentum | 92 | +0.1080 | 1.65 | 0.002 | 0.100 | 0.044 |
| **drop BOTH** | **128** | +0.0978 | 1.61 | 0.005 | **0.061** | 0.032 |
| drop the CVD gate as well | 459 | +0.0270 | 1.15 | — | 0.179 | 0.143 |

**Dropping both earns more in total** (128 × 0.0978 = 12.5% of price against 84 × 0.1203 = 10.1%)
and gives the *best* p-value against a random entry in the table. **Dropping the CVD gate is what
kills it** — PF 1.68 → 1.15, and the entry null stops rejecting. The gate carries the strategy; the
two confirmations subtract.

## 5. The population, again

```
corr(research %/trade, locked %/trade)   Pearson +0.0079   Spearman +0.0232   (2,055,874 cells)
  top 100      research +0.3410  ->  locked -0.0300     27% profitable on locked
  top 1%       research +0.2145  ->  locked +0.0037     45% profitable
  top decile   research +0.1560  ->  locked +0.0321     63% profitable
  ALL CELLS    research +0.0609  ->  locked +0.0461     81% profitable
```

The top 100 research cells are **negative** out of sample against a population average of +0.0461.
Second measurement of this on the same base after V61's −0.026; the sign of the correlation moved
and the conclusion did not.

## 6. The incumbent, unchanged

| | V61 incumbent | best V62 cell |
|---|---|---|
| research | n 157, +0.1203, PF 1.73 | n 159, +0.1371, PF 2.28 |
| locked | n 87, **+0.1371**, PF 1.58 | n 84, +0.1203, PF 1.68 |
| random-filter null (locked) | p 0.010 | **p 0.001** |
| random-entry null (locked) | p 0.205 | **p 0.070** |
| bootstrap P(mean ≤ 0) locked | 0.113 | **0.040** |
| shape | grows out of sample | **decays (right shape)** |

The best V62 cell is better on every *evidence* axis and worse on per-trade return — and its own
drop-one says the improvement is the geometry, not the confirmations. It is the top of two million
draws in a population whose top 100 is negative out of sample. It is not shipped as a preset.

One thing in its neighbourhood is worth recording because it is not a one-cell result: its
**no-target** neighbour reads research +0.1856 and locked **+0.2620**. No target beating every
target is now the fourteenth independent confirmation on this branch. Every post-hoc combination in
`results/v62/stage_d.txt` also reads *better* on locked than on research, which is the regime
warning, and every one of them was chosen after the locked read.

## 7. What ships

`pine/v62/V62_CVD_MFI_EMA_strategy.pine` — V61 with **ADX and CHOP removed**, and the MFI and
EMA-momentum readings present as inputs, **default OFF**, each carrying its measured locked-block
matched-pairs share in its tooltip. The two V61 presets are unchanged and remain the recommendation:

- **Incumbent 30m** — channel 20/20, 2.0 N, no target, k3 / w20 (90 / 600 minutes).
- **High activity 15m** — channel 15/30, 3.0 N, 6 ATR target, k3 / w30 (45 / 450 minutes).

The EMA cross-recency window is declared in MINUTES, like the order-flow settings, because a bar
count is a setting times a timeframe (`STUDY_V57`). The order model is untouched from V61, so
V61's parity figures carry: trade count 1.000 / 0.995, R correlation 0.9998 / 0.9992, and the
script reads conservative against the engine on both presets.

**The linter caught this script before TradingView did.** The V61 fix to `pine_lint` — checking
Pine's continuation rule inside unclosed brackets, not only at a statement's first continuation —
flagged two wrapped ternaries in the V62 HUD at 12 spaces on the first lint pass. That is the
defect that shipped in V61 and in three older scripts.

## 8. What this says

1. **Neither confirmation earns a place**, and the base-rate table predicted it before a single
   backtest: most readings of either indicator pass 80–92% of the bars the breakout already fires
   on.
2. **A research matched-pairs share of 58–59% is what a null looks like here.** V16 measured 99 of
   2,167 momentum conditions beating a control on research and 28% surviving; V41 measured 42.0%
   research and 50.0% locked. This is the third instance and the first where the *ordering* was
   measured to invert (Spearman −0.62).
3. **Removing ADX and CHOP cost nothing** — both were already at or below their `off` marginal on
   the V61 grid.
4. **The CVD gate is the whole strategy.** Drop it at the best cell and profit factor goes 1.68 to
   1.15 and the entry null stops rejecting.


## 9. Is any of it a scalp?

`research/v62/run_v62e.py`, `results/v62/stage_e.txt`. Asked directly, and answerable from the grid
without a new sweep.

**How long it holds:**

| configuration | n | median hold | under 60 min | under 15 min | winners vs losers | %/trade | PF |
|---|---|---|---|---|---|---|---|
| incumbent 30m | 244 | **660 min** (22 bars) | 11.1% | **0.0%** | 1290 vs 240 min | +0.1263 | 1.66 |
| high activity 15m | 623 | 315 min | 11.6% | 1.3% | 585 vs 225 min | +0.0698 | 1.44 |
| the tightest cell the grid allows | 609 | 90 min | 37.3% | 9.2% | 165 vs 75 min | **+0.0229** | **1.23** |

**The grid is monotone against scalping on both axes that define one**, over a million cells:

```
stop    1.5N +0.0506   2.0N +0.0589   2.5N +0.0649   3.0N +0.0704   %/trade
target  3 ATR +0.0439  4 ATR +0.0550  6 ATR +0.0622  none +0.0845
```

**And it is not a cost problem.** On NQ 30m the median ATR(14) is 33.1 points against a modelled
round turn of 1.94, so at a 1–3 ATR stop the cost is 2–6% of risk and break-even at 1:1 is
51.0–52.9%. Push the stop to 0.25 ATR and it becomes 23.5% of risk and 61.7% — but the grid never
gets there, because it is already losing money to the tightening long before the cost floor bites.

The mechanism is in the last column of the first table: **winners hold 5.4× longer than losers**
(1290 against 240 minutes on the incumbent). The edge lives in the tail, and a scalp is the exit
that cuts the tail off. Eleventh independent confirmation of the intraday-constraint finding on
this branch.
