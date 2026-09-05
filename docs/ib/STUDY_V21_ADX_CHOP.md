# V21 — ADX or CHOP on the V20 base: which one earns its place

**CHOP does; ADX does not; and adding ADX to CHOP makes the holdout worse.** On breakout bars
ADX ≥ 25 has a lift of 1.11× — it barely discriminates — while CHOP ≤ 40 has 1.93×.

---

## 1. The population, before any ranking

Base (V20: Donchian 30/20, 2.0N stop, 2R target, linreg-50 confirmation, 30m, five markets pooled
in R): **research PF 0.959** on 5,779 trades, **locked PF 0.968** on 3,305.

| | cells | % with PF > 1 | median PF | median EV |
| --- | --- | --- | --- | --- |
| research | 110 | 22% | 0.967 | −0.0185 |
| locked | 110 | 36% | 0.979 | −0.0111 |

**Correlation between a cell's research PF and its locked PF: +0.035.** That is the number that
says a ranking of this grid should not be expected to transfer — and it is why the top-20 table
below is printed with its trade counts and its locked column attached.

---

## 2. The top 20 by profit factor, as asked

Ranked on research, the same cells read on locked.

| # | kind | ADX | CHOP | n | PF | EV (R) | mkts | LOCK n | LOCK PF | LOCK EV | kept? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | both | 18 | 35 | 1,909 | 1.052 | +0.0278 | 4/5 | 1,023 | 1.036 | +0.0196 | yes |
| 2 | both | 28 | 35 | 1,273 | 1.048 | +0.0250 | 4/5 | 672 | 1.026 | +0.0134 | yes |
| 3 | both | 25 | 35 | 1,486 | 1.046 | +0.0241 | 4/5 | 797 | 1.021 | +0.0110 | yes |
| 4 | both | 22 | 35 | 1,683 | 1.046 | +0.0242 | 4/5 | 915 | 1.055 | +0.0294 | yes |
| 5 | both | 30 | 35 | 1,137 | 1.042 | +0.0220 | 4/5 | 591 | 1.042 | +0.0210 | yes |
| 6 | both | 18 | 40 | 2,892 | 1.042 | +0.0226 | 4/5 | 1,580 | 1.005 | +0.0026 | yes |
| 7 | both | 15 | 40 | 3,079 | 1.038 | +0.0204 | 4/5 | 1,698 | 0.996 | −0.0025 | **NO** |
| 8 | both | 15 | 35 | 2,004 | 1.036 | +0.0197 | 3/5 | 1,084 | 1.032 | +0.0173 | yes |
| 9 | both | 20 | 40 | 2,695 | 1.034 | +0.0183 | 4/5 | 1,490 | 0.984 | −0.0086 | **NO** |
| 10 | both | 20 | 35 | 1,817 | 1.032 | +0.0171 | 4/5 | 972 | 1.013 | +0.0071 | yes |
| 11 | both | 10 | 40 | 3,177 | 1.029 | +0.0159 | 4/5 | 1,727 | 1.018 | +0.0100 | yes |
| 12 | **CHOP alone** | 0 | 40 | 3,177 | 1.029 | +0.0159 | 4/5 | 1,730 | 1.015 | +0.0080 | yes |
| 13 | both | 10 | 35 | 2,042 | 1.027 | +0.0147 | 4/5 | 1,098 | 1.048 | +0.0263 | yes |
| 14 | **CHOP alone** | 0 | 35 | 2,042 | 1.027 | +0.0147 | 4/5 | 1,100 | 1.044 | +0.0243 | yes |
| 15 | both | 35 | 35 | 789 | 1.022 | +0.0113 | 3/5 | 414 | 0.943 | −0.0303 | **NO** |
| 16 | both | 25 | 40 | 2,114 | 1.019 | +0.0099 | 4/5 | 1,178 | 1.009 | +0.0049 | yes |
| 17 | both | 15 | 45 | 4,023 | 1.015 | +0.0085 | 4/5 | 2,266 | 1.014 | +0.0078 | yes |
| 18 | both | 25 | 45 | 2,597 | 1.014 | +0.0077 | 4/5 | 1,464 | 1.001 | +0.0008 | yes |
| 19 | both | 20 | 45 | 3,446 | 1.012 | +0.0064 | 3/5 | 1,931 | 0.960 | −0.0224 | **NO** |
| 20 | both | 10 | 45 | 4,201 | 1.008 | +0.0046 | 4/5 | 2,343 | 1.023 | +0.0129 | yes |

16 of the top 20 keep PF > 1 on locked, against a 36% base rate — **but read what the table is made
of.** Every row has CHOP ≤ 45. Rows 11 and 12 are the *same cell* (ADX ≥ 10 removes nothing), as are
13 and 14. The ranking transferred because CHOP transferred, not because the grid did.

---

## 3. Each filter alone

**ADX — flat on both blocks.** Every floor from 10 to 40: research PF 0.911–0.977, locked
0.951–1.025. Only **10%** of ADX-alone cells have PF > 1 on locked.

**CHOP — monotone on both blocks.**

| CHOP ceiling | research n | research PF | locked n | locked PF | locked EV |
| --- | --- | --- | --- | --- | --- |
| 100 (none) | 5,779 | 0.959 | 3,305 | 0.968 | −0.0179 |
| 55 | 5,425 | 0.965 | 3,108 | 0.971 | −0.0162 |
| 50 | 4,933 | 0.992 | 2,816 | 0.986 | −0.0081 |
| **45** | 4,204 | **1.007** | 2,347 | **1.022** | +0.0123 |
| 40 | 3,177 | 1.029 | 1,730 | 1.015 | +0.0080 |
| 35 | 2,042 | 1.027 | 1,100 | 1.044 | +0.0243 |
| 30 | 1,065 | 0.962 | 530 | 1.141 | +0.0717 |

| family | cells | research PF | locked PF | % PF > 1 on locked |
| --- | --- | --- | --- | --- |
| ADX alone | 10 | 0.959 | 0.961 | **10%** |
| CHOP alone | 9 | 0.965 | 0.986 | **44%** |
| both | 90 | 0.969 | 0.981 | 39% |
| no filter | 1 | 0.959 | 0.968 | 0% |

---

## 4. The test that decides it

A restrictive filter raises profit factor by construction, so the null is a **random subset of the
same signals of the same size**, scored the same way — 4,000 draws.

| filter | kept | research p | locked p |
| --- | --- | --- | --- |
| ADX ≥ 25 | 3,156 | 0.248 | 0.372 |
| ADX ≥ 40 | 867 | 0.736 | 0.269 |
| CHOP ≤ 50 | 4,933 | 0.003 | 0.133 |
| **CHOP ≤ 45** | 4,204 | **0.005** | **0.015** |
| CHOP ≤ 40 | 3,177 | 0.005 | 0.108 |
| CHOP ≤ 35 | 2,042 | 0.041 | 0.083 |
| ADX ≥ 25 + CHOP ≤ 35 | 1,486 | 0.040 | **0.215** |
| ADX ≥ 18 + CHOP ≤ 35 | 1,909 | 0.016 | 0.127 |

**ADX fails on both blocks at every level.** CHOP clears on all four rungs on research and on one of
four on locked with the rest marginal (0.083–0.133). **Adding ADX on top of CHOP makes the holdout
worse** — CHOP ≤ 35 alone is p 0.083 and with ADX ≥ 25 it is 0.215.

### Why, mechanically

| condition | share of bars | share of **breakout** bars | lift |
| --- | --- | --- | --- |
| ADX ≥ 25 | 50.0% | 55.6% | **1.11×** |
| CHOP ≤ 40 | 21.3% | 41.1% | **1.93×** |
| both | 14.5% | 29.3% | 2.02× |

ADX ≥ 25 barely discriminates on breakout bars. And **68.3% of the bars CHOP keeps already pass
ADX**, so stacking them removes little CHOP has not already removed. (Correlation ADX vs CHOP on all
bars: −0.244 — related but not the same filter, unlike ADX and the efficiency ratio at +0.642.)

---

## 5. The harder null

Minute-of-day matched control — random entries with the same geometry and time-of-day mix, which
prices drift, costs and session timing:

| market | CHOP ≤ 40 research / locked | CHOP ≤ 35 research / locked |
| --- | --- | --- |
| **US30** | **0.016 / 0.039** | **0.010 / 0.001** |
| US100 | 0.057 / 0.159 | 0.541 / 0.100 |
| NQ | 0.003 / 0.059 | 0.080 / 0.393 |
| US30L (8.5 yr) | 0.006 / 0.224 | 0.006 / 0.484 |
| XAU (22 yr) | 0.020 / 0.483 | 0.034 / 0.237 |

**US30 is the only market where CHOP clears this on both blocks.** Everywhere else research passes
and the holdout does not.

---

## 6. Verdict

Use **CHOP ≤ 45** and leave ADX off. That is the only regime setting that beats a same-selectivity
control on both blocks, it sits in the middle of a monotone ladder rather than at its peak, and it
takes the pooled profit factor from 0.968 to 1.022 on the holdout. Understand what that is: a
filter that clears a selectivity null broadly and a drift-priced null on one market of five, applied
to a base that has no edge of its own. It improves a losing configuration to roughly break-even.

## Files

`research/v21/v21regime.py` (ADX, CHOP, the 110-cell grid) · `v21run.py` (population, ladders,
top-20, family medians) · `v21control.py` (selectivity and minute-of-day controls, redundancy).
