# ADX, ATR and EMA on a US30 Donchian breakout in 07:00–11:00 New York

**One question.** On a Donchian breakout bar in 07:00–11:00 New York on US30, do ADX, ATR and EMA
conditions carry information, or are they the trigger restated?

**Answer in one line.** They are **not** the trigger restated — this is the first pool on this
branch to survive the base-rate check largely intact, with a maximum cross-family |rho| of **0.236**
on the signal bars — and **not one of them carries an effect this sample can detect**: all 42
single-condition cells sit **inside their own minimum detectable effect**, and the drop-one
contributions are inside the full stack's MDE at both geometries. What *is* real and consistent is
a **direction**: ADX and ATR both prefer the **ceiling** and EMA prefers the **with-trend** side,
on both geometries, and that survives out of sample as a marginal while no individual threshold does.

Scripts: `research/us30team/base_rates.py`, `run_b1.py` (base rates + correlation), `run_b2.py`
(single-condition vetoes + drop-one), `run_b3.py` (the one holdout read), `run_b4.py` (null
diagnostic). Logs under the scratchpad; CSVs beside the scripts.

---

## 0. Setup, and what is inherited rather than re-derived

| | |
|---|---|
| feed | `US30_LONG_15m` (`US30L`), 193,942 bars, 2016-10-26 → 2025-07-15, 15-minute |
| blocks | **A_research** = before 2023-01-01 (135,968 bars) · **B_holdout** = the rest · **C_forward** = `US30_ISO_15m`, a **different provider**, after 2025-07-16 |
| window | 07:00–11:00 New York, **flatten at the 11:00 open**, and a signal whose fill would land at or after the bell is **refused**, not opened for zero P&L (`STUDY_V60`) |
| walker | `research/us30scalp/s30core.py`, one live position, barriers read as absolute **points** (`use_pts=1`), stop-first tie-break with the ambiguous share reported |
| cost | 2.29 index points round turn = **7.27% of one median in-window ATR** |
| ATR | median in-window ATR(14) on A = **31.52 pts** |
| geometries (declared in advance) | **30/150** → stop 0.95 ATR, cost **7.63% of risk**, driftless break-even **0.1794** · **50/150** → stop 1.59 ATR, cost **4.58% of risk**, break-even **0.2615** |
| ambiguous share | 0.0064–0.0072 at both geometries — the intrabar convention is not load-bearing here |

**ADX was verified, not imported on trust.** CLAUDE.md records that Pine's `ta.dmi` returns
`[+DI, −DI, ADX]` and destructuring the first element substitutes +DI for ADX silently.
`d50core.adx` was diffed against an explicit Wilder reference written from the definition:
correlation **1.000000**, mean |diff| **0.0**, and `ADX == +DI` is `False` (means 24.22 vs 21.43).

**The ATR baseline is causal time-of-day, and that is not cosmetic.** CLAUDE.md records that on a
24-hour tape `atr / sma(atr, n)` is a clock. Measured here on US30 for the first time:

| baseline for `atr ≥ baseline` | in-window (07–11) | outside the window | on breakout bars |
|---|---|---|---|
| trailing 50-bar mean (**wrong**) | 0.7612 | 0.3891 | **0.8504** — near-inert |
| causal time-of-day mean (min 20 prior obs) | 0.6630 | 0.6232 | 0.6819 |

The trailing form passes twice as often inside the session as outside; the causal form is nearly
flat, which is what a volatility reading rather than a clock looks like. On breakout bars the two
correlate only **+0.111** — they are substantially different columns, not two scalings of one.

---

## 1. Base rates on the trigger's own bars — computed before any P&L

`p(breakout bar)` is the share of Donchian long breakout bars in the window on A_research passing
the condition; `p(all in-window bars)` is the same share over every valid in-window bar; `lift` is
their ratio. A condition passing **≥95%** of breakout bars is flagged **INERT**: it cannot refuse a
trade, so it cannot carry information whatever its P&L reads.

2,226 breakout bars (Donchian 20) and 2,831 (Donchian 10) of 25,158 valid in-window bars.

#### Donchian 20 long

| condition | family | p(breakout bar) | p(all in-window bars) | lift | n | flag |
|---|---|---|---|---|---|---|
| `ema13x48 fresh<=5` | EMA | 0.1918 | 0.0934 | **2.054** | 427 |  |
| `+DI>-DI` | ADX | 0.9784 | 0.5171 | **1.892** | 2178 | **INERT** (≥95%) |
| `d_ema200>=2.0` | EMA | 0.6927 | 0.4210 | **1.645** | 1542 |  |
| `ema13>34>89` | EMA | 0.6622 | 0.4221 | **1.569** | 1474 |  |
| `d_ema200>=1.0` | EMA | 0.7794 | 0.5017 | **1.554** | 1735 |  |
| `ema13>48` | EMA | 0.8419 | 0.5643 | **1.492** | 1874 |  |
| `d_ema200>=0` | EMA | 0.8567 | 0.5870 | **1.459** | 1907 |  |
| `atrpct250>=0.5` | ATR | 0.6851 | 0.5926 | **1.156** | 1525 |  |
| `adx>=30` | ADX | 0.3252 | 0.2964 | **1.097** | 724 |  |
| `atrpct250>=0.8` | ATR | 0.2830 | 0.2603 | **1.087** | 630 |  |
| `adx>=20` | ADX | 0.7219 | 0.6912 | **1.044** | 1607 |  |
| `adx>=25` | ADX | 0.4870 | 0.4674 | **1.042** | 1084 |  |
| `adx>=15` | ADX | 0.9281 | 0.9017 | **1.029** | 2066 |  |
| `atr/tod>=1.0` | ATR | 0.6819 | 0.6630 | **1.029** | 1518 |  |
| `atr/tod>=1.2` | ATR | 0.5099 | 0.5042 | **1.011** | 1135 |  |
| `adx<=25` | ADX | 0.5130 | 0.5326 | **0.963** | 1142 |  |
| `atr/tod<=1.0` | ATR | 0.3181 | 0.3370 | **0.944** | 708 | selective (lift<1) |
| `adx<=20` | ADX | 0.2781 | 0.3088 | **0.901** | 619 | selective (lift<1) |
| `atr/tod<=0.8` | ATR | 0.1469 | 0.1666 | **0.882** | 327 | selective (lift<1) |
| `atrpct250<=0.5` | ATR | 0.3176 | 0.4111 | **0.773** | 707 | selective (lift<1) |
| `atrpct250<=0.2` | ATR | 0.0629 | 0.1123 | **0.560** | 140 | selective (lift<1) |
| `d_ema200<=1.0` | EMA | 0.2206 | 0.4983 | **0.443** | 491 | selective (lift<1) |
| `ema13<48` | EMA | 0.1581 | 0.4357 | **0.363** | 352 | selective (lift<1) |
| `-DI>+DI` | ADX | 0.0216 | 0.4829 | **0.045** | 48 | selective (lift<1) |

#### Donchian 10 long

| condition | family | p(breakout bar) | p(all in-window bars) | lift | n | flag |
|---|---|---|---|---|---|---|
| `ema13x48 fresh<=5` | EMA | 0.1727 | 0.0934 | **1.849** | 489 |  |
| `+DI>-DI` | ADX | 0.9304 | 0.5171 | **1.799** | 2634 |  |
| `d_ema200>=2.0` | EMA | 0.6372 | 0.4210 | **1.514** | 1804 |  |
| `d_ema200>=1.0` | EMA | 0.7220 | 0.5017 | **1.439** | 2044 |  |
| `ema13>34>89` | EMA | 0.5860 | 0.4221 | **1.388** | 1659 |  |
| `d_ema200>=0` | EMA | 0.8001 | 0.5870 | **1.363** | 2265 |  |
| `ema13>48` | EMA | 0.7457 | 0.5643 | **1.321** | 2111 |  |
| `atrpct250>=0.5` | ATR | 0.6595 | 0.5926 | **1.113** | 1867 |  |
| `adx>=30` | ADX | 0.3094 | 0.2964 | **1.044** | 876 |  |
| `atr/tod>=1.0` | ATR | 0.6824 | 0.6630 | **1.029** | 1932 |  |
| `atr/tod>=1.2` | ATR | 0.5175 | 0.5042 | **1.026** | 1465 |  |
| `atrpct250>=0.8` | ATR | 0.2653 | 0.2603 | **1.019** | 751 |  |
| `adx>=20` | ADX | 0.7036 | 0.6912 | **1.018** | 1992 |  |
| `adx>=15` | ADX | 0.9131 | 0.9017 | **1.013** | 2585 |  |
| `adx>=25` | ADX | 0.4723 | 0.4674 | **1.010** | 1337 |  |
| `adx<=25` | ADX | 0.5277 | 0.5326 | **0.991** | 1494 |  |
| `adx<=20` | ADX | 0.2964 | 0.3088 | **0.960** | 839 |  |
| `atr/tod<=1.0` | ATR | 0.3176 | 0.3370 | **0.942** | 899 | selective (lift<1) |
| `atr/tod<=0.8` | ATR | 0.1551 | 0.1666 | **0.931** | 439 | selective (lift<1) |
| `atrpct250<=0.5` | ATR | 0.3440 | 0.4111 | **0.837** | 974 | selective (lift<1) |
| `atrpct250<=0.2` | ATR | 0.0731 | 0.1123 | **0.651** | 207 | selective (lift<1) |
| `ema13<48` | EMA | 0.2543 | 0.4357 | **0.584** | 720 | selective (lift<1) |
| `d_ema200<=1.0` | EMA | 0.2780 | 0.4983 | **0.558** | 787 | selective (lift<1) |
| `-DI>+DI` | ADX | 0.0696 | 0.4829 | **0.144** | 197 | selective (lift<1) |
