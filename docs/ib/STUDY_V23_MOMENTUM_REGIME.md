# V23 — Momentum crossed against ADX and CHOP on the V20 base

**The answer: CHOP alone. ADX makes it worse, momentum makes it worse, and all three together does
not have enough trades to score.**

## What this asked that V16 did not

V16 settled "does a momentum filter improve a Donchian breakout" — 2,167 conditions, 99 beat a
same-selectivity control on research against 37 expected, and on the holdout **28%** still beat the
unfiltered rule where chance is 50%. That question was not reopened.

This asks a different one: on the V20 base (Donchian 30/20 + a 50-period linear-regression
confirmation, 2.0N stop, 2R target), is the best configuration momentum alone, ADX + CHOP, or all
three? The two families had never been crossed, and V21 found they behave very differently — CHOP
lift 1.93× and clears a selectivity control on both blocks, ADX lift 1.11× and clears nothing.

**The grid was declared before it was run:** 12 momentum readings × 3 rungs (plus OFF) = 37, × 4 ADX
floors × 4 CHOP ceilings × 2 timeframes = **1,184 cells**, of which **531** clear a 25-trade floor.

**One market.** A container recycle destroyed every feed except NQ. V20's own table was five
markets; this is two timeframes on one, and it is weaker than the finding it sits beside.

## 0. The population, before any ranking

```
scorable cells: 531
share with research PF > 1: 68.9%      share with LOCKED PF > 1: 54.9%
correlation between a cell's RESEARCH PF and its LOCKED PF: +0.489
```

The ranking half-transfers — better than V20's ADX×CHOP grid at +0.035 — but row 1 of 531 still
carries a selection premium. **The top 100 average research PF 1.369 and locked PF 1.163.** That
0.21 gap is the premium, and it is what a top-of-grid number costs you.

## 1. The marginal average per axis — never the top cell

| momentum setting | cells | research PF | LOCKED PF | LOCKED Sharpe | % cells locked PF>1 |
| --- | --- | --- | --- | --- | --- |
| `tsi >= 5` | 14 | 1.113 | 1.151 | 0.36 | 64% |
| `ao >= 0.25` | 14 | 1.185 | 1.133 | 0.34 | 64% |
| `cmo14 >= 20` | 15 | 1.093 | 1.125 | 0.27 | 60% |
| `ao >= 0.75` | 14 | 1.206 | 1.087 | 0.29 | 57% |
| `tsmom20 >= 0.75` | 14 | 1.145 | 1.071 | 0.11 | 43% |
| `cci21 >= 100` | 15 | 1.094 | 1.070 | 0.15 | 60% |
| **OFF (no momentum)** | 17 | 1.061 | **1.037** | 0.09 | 47% |
| `roc20 >= 2` | 13 | 1.099 | 0.947 | −0.22 | 23% |
| `slope50 >= 0.2` | 8 | **1.299** | 0.946 | −0.33 | 50% |
| `aroon21 >= 80` | 10 | 1.089 | 0.939 | −0.40 | 10% |

**16 of the 36 momentum settings beat the no-momentum baseline on the locked block — 44%, where
chance is 50%.** Note `slope50 >= 0.2`: the best research PF in the whole momentum axis (1.299) and
0.946 on locked. That is the shape V16 described.

| ADX | cells | research PF | LOCKED PF | % locked PF>1 |
| --- | --- | --- | --- | --- |
| `>= 20` | 210 | 1.073 | 1.070 | 44% |
| **off** | 296 | 1.084 | 1.023 | 50% |
| `>= 25` | 25 | 1.166 | — | 0% (starved) |

| CHOP | cells | research PF | LOCKED PF | % locked PF>1 |
| --- | --- | --- | --- | --- |
| **`<= 45`** | 132 | 1.088 | **1.072** | 52% |
| `<= 40` | 95 | 1.070 | 1.066 | 43% |
| `<= 50` | 150 | 1.095 | 1.024 | 43% |
| off | 154 | 1.077 | 1.009 | 43% |

CHOP is the only axis whose best setting beats its own OFF row on the locked block and on the share
of cells that stay positive.

## 2. The three-way question, asked directly against a same-selectivity control

| configuration | research PF | research p | LOCKED PF | LOCKED p |
| --- | --- | --- | --- | --- |
| 30m no filter (the V20 default) | 1.082 | 1.000 | 1.014 | 1.000 |
| 30m MOMENTUM alone (best cell, `agree20_60>=0.75`) | 1.252 | **0.003** | 0.977 | 0.750 |
| 30m **CHOP ≤ 45 alone** | 1.191 | **0.000** | **1.138** | **0.048** |
| 30m ADX ≥ 20 alone | 1.135 | 0.417 | 0.990 | 0.680 |
| 30m ADX ≥ 20 + CHOP ≤ 45 | 1.204 | 0.345 | 1.212 | 0.395 |
| 30m CHOP ≤ 45 + momentum | 1.257 | 0.022 | 1.064 | 0.427 |
| 30m ALL THREE | — | — | under 25 trades | not scorable |
| 15m MOMENTUM alone (best cell, `slope50>=0.2`) | 1.448 | **0.005** | **0.726** | **0.943** |

**CHOP ≤ 45 alone is the only cell clearing its control on both blocks.** Every other row either
fails research, or passes research and inverts. The 15m momentum cell is the clearest: research
p 0.005, and on locked a random filter of the same selectivity beats it 94% of the time.

Adding ADX to CHOP takes locked p from 0.048 to 0.395. Adding momentum to CHOP takes it from 0.048
to 0.427. **Both additions destroy the one thing that worked**, which replicates V21's finding that
ADX makes CHOP worse out of sample.

## 3. Why — a breakout is already a momentum event

| reading | all bars | BREAKOUT bars | lift | signals it removes |
| --- | --- | --- | --- | --- |
| `rsi14 >= 55` | 39.9% | **96.3%** | 2.41× | **3.7%** |
| `stoch14 >= 70` | 37.4% | 91.8% | 2.46× | 8.2% |
| `ao >= 0.25` | 49.6% | 92.5% | 1.87× | 7.5% |
| `cci21 >= 100` | 22.6% | 89.0% | 3.94× | 11.0% |
| `cmo14 >= 20` | 32.8% | 85.7% | 2.61× | 14.3% |
| `slope50 >= 0` | 54.9% | 77.8% | 1.42× | 22.2% |

The "signals removed" column is a **ceiling** on what a filter can be worth — RSI ≥ 55 can only
affect 3.7% of the trades.

The cleanest demonstration is inside the grid itself. Every momentum reading set at its **zero
rung** — `cmo14>=0`, `aroon21>=0`, `roc20>=0`, `tsmom20>=0`, `agree20_60>=0` — reproduces the
no-momentum row **exactly**: same 277 research and 147 locked trades, same PF to three decimals
(rows 51–53, 59, 62–63 of the top 100). They are not weak filters; on a breakout bar they are not
filters at all.

## 4. Stacking starves the sample

**653 of 1,184 cells could not be scored** at a 25-trade floor, and **31 of the top 100 have zero
locked trades**. ADX ≥ 25 survives in 25 cells and none of them has a readable holdout; ADX ≥ 30
vanishes entirely. This is the `n=3` lesson from `STUDY_DIVERGENCE_CONFIRM` — three filters at
realistic firing rates leave nothing to measure, and a profit factor computed on 25 trades is not a
profit factor.

## 5. What ships

**Nothing changes in the recommended configuration**, because the answer was already available:
**30 minutes, CHOP on, ADX off, momentum off.** A momentum input was added to the script anyway —
six readings, default OFF — so the option is present and its measurements travel with it, exactly as
ADX does. What the evidence supports is leaving it off.

The best readable cell in the whole grid is `30m · ao>=0.25 · ADX off · CHOP<=40` at locked PF 1.276
on 143 trades, against the no-momentum `30m · off · off · CHOP<=40` at **1.229 on 147 trades**. The
momentum column is worth +0.047 PF for 4 fewer trades. That is noise, and it is the single best case
out of 531.

## Files

| file | what it does |
| --- | --- |
| `research/v23/v23mom.py` | the declared 1,184-cell grid, the marginal averages, the top 100, the controls, the lift diagnostic |
| `pine/turtle/V20_DONCHIAN_LINREG_strategy.pine` | the momentum input, default off, with this table in its header |
