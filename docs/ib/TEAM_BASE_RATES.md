# ADX, ATR and EMA on a US30 Donchian breakout in 07:00–11:00 New York

**One question.** On a Donchian breakout bar in 07:00–11:00 New York on US30, do ADX, ATR and EMA
conditions carry information, or are they the trigger restated?

**Answer in three lines.**

1. **One condition is the trigger restated and it is `+DI > −DI`**, which passes **97.84%** of
   Donchian-20 breakout bars (96.4% and 95.1% on the other two blocks). Flagged INERT and excluded
   before any P&L. `ema13>48` at **84.19%** is largely restated too, reproducing CLAUDE.md's NQ
   figure of 82.6% almost exactly. **Everything else genuinely binds** — ADX and ATR lifts run
   1.01–1.16, and the maximum cross-family |rho| on the signal bars is **0.236**, so this is the
   first filter pool on this branch to come through the base-rate and duplication checks intact.
2. **And none of it carries a measurable effect.** All 42 research cells, all 24 drop-one arms and
   all 88 out-of-sample cells have an edge **smaller than their own minimum detectable effect**, and
   4 of 88 out-of-sample cells clear a control against **4.4 expected by chance**.
3. **What does hold is a direction, and it is the opposite of the convention for ADX.** Pooled over
   three blocks, two providers and two geometries: an ADX **ceiling** beats its block's base in
   **12 of 12** cells (mean +3.37 pts) while ADX **floors** manage **6 of 24** (mean −0.97), and a
   **counter-trend** EMA reading manages **0 of 18** (mean −3.68). **ATR sits at chance in both
   directions** (58% and 44%) and its percentile ceiling inverts out of sample for the third time on
   this market. The conventional stack `adx>=25 & atr/tod>=1.0 & ema13>48` is the worst object
   measured here: **−5.68 and −7.73 points a trade on the holdout**, and removing ADX improves it at
   both geometries.

Scripts: `research/us30team/base_rates.py`, `run_b1.py` (base rates + signal-bar correlation),
`run_b2.py` (single-condition vetoes + drop-one), `run_b3.py` (the one holdout and forward read),
`run_b4.py` (null diagnostic). Log at `research/us30team/logs/b3_us30team.log`; CSVs
(`b1_baserate_d*.csv`, `b1_corr_d*.csv`, `b2_singles.csv`, `b2_dropone.csv`, `b3_holdout.csv`)
beside the scripts.

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

### What the base-rate table says

**One condition is INERT: `+DI > −DI`, which passes 97.84% of Donchian-20 breakout bars** against
51.71% of in-window bars (lift 1.892). It cannot refuse a trade, so it cannot carry information —
the ninth confirmation-is-the-trigger finding on this branch, after RSI 94.7%, Aroon 100.0%, MACD
99.8–100.0%, MFI 91.7%, EMA13>48 82.6%, `close>EMA50` 93.7% and %K-vs-VWAP at rho 0.831. Its mirror
`−DI > +DI` survives only 48 breakout bars. Both were **excluded from the P&L pool**, together with
`atrpct250<=0.2` (6.29%, too few bars to control). `adx>=15` at 92.81% is a hair under the flag and
is effectively inert too — it removes one signal in fourteen.

**`ema13>48` reproduces the NQ number almost exactly: 84.19% here against CLAUDE.md's recorded
82.6%.** On a different index, a different provider and a different session window. The EMA state
is largely the trigger restated; it removes a sixth of the signals.

**ADX and ATR are the two families that are genuinely NOT the trigger restated, and their lifts are
the reason.** Every ADX floor lands between **1.029 and 1.097** and every ATR expansion reading
between **1.011 and 1.156** — a breakout bar is barely more likely to pass them than any other bar
in the window. `adx>=25` measures **lift 1.042** here against CLAUDE.md's 1.11x on a different base,
so that finding replicates in kind. The practical consequence cuts both ways: these conditions can
genuinely refuse trades, and they are also close to an arbitrary coin-flip split of the sample.

**The largest lift is not the useful one.** `ema13x48 fresh<=5` has the highest lift in the table
(2.054) and is one of the two worst-performing cells in the P&L below. Lift measures co-selection
with the trigger, not information.

Donchian 10 tells the same story one notch weaker throughout (`+DI>-DI` 93.04%, just under the
flag; every ADX floor between 1.010 and 1.044). The shorter channel is a looser trigger, so every
lift moves toward 1.

---

## 2. Correlation on the signal bars

A filter only ever acts on the bars the base fires on, so the matrix is restricted to those 2,226
bars (Donchian 20) rather than to the whole series.

**Excluding the floor/ceiling mirrors I declared deliberately, there are ZERO pairs above
|rho| 0.90.** The mirrors sit at exactly −1.0000 by construction (`adx>=20` vs `adx<=20`, and so on
for every threshold, plus `+DI>-DI` vs `-DI>+DI` and `ema13>48` vs `ema13<48`) — that is the
both-directions requirement, not a pool defect, but it does mean the **effective independent test
count is roughly half the nominal one**. The one near-mirror that is not exact is
`atrpct250>=0.5` vs `atrpct250<=0.5` at **−0.9938**, the gap being bars sitting exactly on 0.5.

**Maximum CROSS-family |rho| is 0.236** (`adx>=30` vs `d_ema200>=2.0`) on Donchian 20 and 0.347 on
Donchian 10. ADX, ATR and EMA are three genuinely separate axes here. This branch has caught its own
pool duplicating seven times, twice at rho exactly 1.0000 — this pool is clean.

**The redundancy that does exist is WITHIN the EMA family**: `ema13>34>89` vs `d_ema200>=2.0` at
**+0.747**, vs `d_ema200>=1.0` at +0.678, vs `ema13>48` at +0.596. The triple-EMA alignment and the
EMA200 distance are substantially one reading. Anything treating them as two independent
confirmations is double-counting.

**The two conditions that survive the research P&L are not one finding.** `adx<=20` and
`atrpct250<=0.5` correlate **+0.171** on the signal bars, with Jaccard 0.263 and joint probability
0.124 against 0.088 under independence — related but far from duplicates.

---

## 3. Single-condition vetoes — population first

Each condition applied as a **veto** (filter the triggers, re-simulate end to end so the position
lock releases exactly as it would in a script) and scored against a **random gate of the same
selectivity**, 400 draws, also re-simulated. 21 usable rungs × 2 geometries = 42 cells.

| | 30/150 | 50/150 |
|---|---|---|
| cells | 21 | 21 |
| profitable | 76.2% | 57.1% |
| beat the unfiltered base | 38.1% | 47.6% |
| clear the control at p≤0.05 | 3 (chance 1.1) | 3 (chance 1.1) |
| best p | 0.007 | 0.000 |
| **cells whose edge exceeds its own MDE** | **0 of 21** | **0 of 21** |

### The marginal average by family and direction — never the top cell

| geometry | family | direction | cells | mean pts/trade | mean edge vs base | mean PF | beats base |
|---|---|---|---|---|---|---|---|
| 30/150 | ADX | floor (`>=`) | 4 | +0.745 | **−0.717** | 1.036 | **0%** |
| 30/150 | ADX | ceiling (`<=`) | 2 | +2.930 | **+1.468** | 1.142 | **100%** |
| 30/150 | ATR | floor / expansion | 4 | +0.329 | **−1.133** | 1.011 | 50% |
| 30/150 | ATR | ceiling / calm | 3 | +2.124 | **+0.663** | 1.106 | 33% |
| 30/150 | EMA | with-trend | 5 | +2.127 | **+0.666** | 1.103 | 60% |
| 30/150 | EMA | counter-trend | 3 | −2.312 | **−3.774** | 0.894 | **0%** |
| 50/150 | ADX | floor (`>=`) | 4 | −0.977 | **−1.960** | 0.965 | **0%** |
| 50/150 | ADX | ceiling (`<=`) | 2 | +4.663 | **+3.680** | 1.175 | **100%** |
| 50/150 | ATR | floor / expansion | 4 | −0.581 | **−1.564** | 0.971 | 50% |
| 50/150 | ATR | ceiling / calm | 3 | +3.493 | **+2.509** | 1.147 | 67% |
| 50/150 | EMA | with-trend | 5 | +1.549 | **+0.566** | 1.058 | 80% |
| 50/150 | EMA | counter-trend | 3 | −2.562 | **−3.545** | 0.910 | **0%** |

**This is the study's most consistent result.** ADX ceilings beat ADX floors and ATR ceilings beat
ATR expansion floors, on both geometries, with ADX floors beating the base in **0 of 8** cells and
ADX ceilings in **4 of 4**. The EMA runs the other way: with-trend beats counter-trend on both
geometries, counter-trend beating the base in 0 of 6. The picture is coherent — **on this base a
breakout is best taken when the tape is CALM and the trend background is UP**, i.e. the conventional
ADX/ATR readings are backwards and the conventional EMA reading is right.

That is the **seventh** move of an ATR-state sign on this branch and another ADX inversion, and it
was only visible because every reading was run as a floor *and* as a ceiling.

> **Read §6 before trusting the ATR half of this table.** On research the ADX and ATR directions
> look like one finding. Out of sample they separate completely: the **ADX** direction holds on all
> three blocks, and the **ATR** direction inverts on B_holdout and returns on C_forward, i.e. it is
> at chance. The research block cannot tell the two apart; only the block change can.

**Geometry 30/150 points** — unfiltered base +1.462 pts/trade

| condition | fam | kept | n | pts/trade | edge vs base | MDE (80% power) | PF | win | break-even | control median | control p | inside MDE? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `atrpct250<=0.5` | ATR | 0.318 | 432 | +5.314 | +3.853 | ±8.296 | 1.251 | 0.3287 | 0.1794 | +0.513 | 0.007 | yes |
| `adx<=20` | ADX | 0.278 | 415 | +3.973 | +2.511 | ±8.182 | 1.192 | 0.3277 | 0.1794 | +0.726 | 0.052 | yes |
| `ema13>34>89` | EMA | 0.662 | 704 | +3.186 | +1.724 | ±5.990 | 1.157 | 0.3295 | 0.1794 | +1.103 | 0.015 | yes |
| `d_ema200>=2.0` | EMA | 0.693 | 731 | +2.499 | +1.038 | ±5.859 | 1.122 | 0.3228 | 0.1794 | +1.086 | 0.072 | yes |
| `atr/tod>=1.2` | ATR | 0.510 | 651 | +2.409 | +0.947 | ±6.794 | 1.106 | 0.2796 | 0.1794 | +0.948 | 0.100 | yes |
| `ema13>48` | EMA | 0.842 | 916 | +2.405 | +0.944 | ±5.236 | 1.116 | 0.3242 | 0.1794 | +1.225 | 0.050 | yes |
| `atr/tod>=1.0` | ATR | 0.682 | 828 | +2.130 | +0.669 | ±5.831 | 1.096 | 0.2935 | 0.1794 | +1.113 | 0.110 | yes |
| `adx<=25` | ADX | 0.513 | 686 | +1.886 | +0.425 | ±6.060 | 1.091 | 0.3207 | 0.1794 | +0.881 | 0.205 | yes |
| `d_ema200>=0` | EMA | 0.857 | 944 | +1.348 | -0.114 | ±5.058 | 1.065 | 0.3167 | 0.1794 | +1.370 | 0.512 | yes |
| `atr/tod<=0.8` | ATR | 0.147 | 185 | +1.234 | -0.227 | ±9.242 | 1.076 | 0.3892 | 0.1794 | +0.335 | 0.395 | yes |
| `d_ema200>=1.0` | EMA | 0.779 | 847 | +1.199 | -0.263 | ±5.323 | 1.057 | 0.3164 | 0.1794 | +1.256 | 0.522 | yes |
| `adx>=15` | ADX | 0.928 | 1046 | +0.977 | -0.485 | ±4.832 | 1.046 | 0.3126 | 0.1794 | +1.413 | 0.828 | yes |
| `adx>=20` | ADX | 0.722 | 801 | +0.894 | -0.568 | ±5.460 | 1.043 | 0.3134 | 0.1794 | +1.122 | 0.610 | yes |
| `adx>=30` | ADX | 0.325 | 346 | +0.730 | -0.731 | ±8.054 | 1.035 | 0.3266 | 0.1794 | +0.719 | 0.497 | yes |
| `adx>=25` | ADX | 0.487 | 528 | +0.379 | -1.083 | ±6.696 | 1.018 | 0.3030 | 0.1794 | +0.897 | 0.652 | yes |
| `d_ema200<=1.0` | EMA | 0.221 | 325 | +0.092 | -1.370 | ±9.031 | 1.004 | 0.2862 | 0.1794 | +0.582 | 0.562 | yes |
| `atr/tod<=1.0` | ATR | 0.318 | 351 | -0.176 | -1.638 | ±6.880 | 0.990 | 0.3675 | 0.1794 | +0.706 | 0.680 | yes |
| `atrpct250>=0.5` | ATR | 0.685 | 840 | -0.439 | -1.900 | ±5.038 | 0.979 | 0.3179 | 0.1794 | +1.112 | 0.960 | yes |
| `atrpct250>=0.8` | ATR | 0.283 | 375 | -2.786 | -4.248 | ±7.140 | 0.863 | 0.3040 | 0.1794 | +0.392 | 0.968 | yes |
| `ema13x48 fresh<=5` | EMA | 0.192 | 260 | -3.244 | -4.705 | ±8.873 | 0.849 | 0.2923 | 0.1794 | +0.555 | 0.943 | yes |
| `ema13<48` | EMA | 0.158 | 271 | -3.784 | -5.246 | ±9.073 | 0.829 | 0.2694 | 0.1794 | +0.528 | 0.940 | yes |

**Geometry 50/150 points** — unfiltered base +0.984 pts/trade

| condition | fam | kept | n | pts/trade | edge vs base | MDE (80% power) | PF | win | break-even | control median | control p | inside MDE? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `atrpct250<=0.5` | ATR | 0.318 | 418 | +6.930 | +5.946 | ±10.382 | 1.247 | 0.4258 | 0.2615 | +0.614 | 0.000 | yes |
| `adx<=20` | ADX | 0.278 | 397 | +6.508 | +5.525 | ±10.328 | 1.246 | 0.4307 | 0.2615 | +0.151 | 0.000 | yes |
| `atr/tod<=0.8` | ATR | 0.147 | 181 | +3.379 | +2.395 | ±10.986 | 1.186 | 0.4751 | 0.2615 | -0.211 | 0.150 | yes |
| `ema13>34>89` | EMA | 0.662 | 665 | +2.877 | +1.893 | ±7.331 | 1.109 | 0.4120 | 0.2615 | +0.890 | 0.052 | yes |
| `adx<=25` | ADX | 0.513 | 646 | +2.818 | +1.835 | ±7.686 | 1.105 | 0.4118 | 0.2615 | +0.641 | 0.113 | yes |
| `atr/tod>=1.2` | ATR | 0.510 | 607 | +2.417 | +1.433 | ±8.696 | 1.078 | 0.3789 | 0.2615 | +0.844 | 0.142 | yes |
| `ema13>48` | EMA | 0.842 | 858 | +2.222 | +1.238 | ±6.471 | 1.082 | 0.4079 | 0.2615 | +1.046 | 0.035 | yes |
| `d_ema200>=2.0` | EMA | 0.693 | 692 | +1.368 | +0.384 | ±7.134 | 1.050 | 0.4046 | 0.2615 | +0.951 | 0.370 | yes |
| `atr/tod>=1.0` | ATR | 0.682 | 773 | +1.327 | +0.343 | ±7.397 | 1.044 | 0.3803 | 0.2615 | +0.901 | 0.375 | yes |
| `d_ema200>=0` | EMA | 0.857 | 892 | +1.001 | +0.018 | ±6.219 | 1.037 | 0.4013 | 0.2615 | +1.019 | 0.510 | yes |
| `d_ema200>=1.0` | EMA | 0.779 | 801 | +0.279 | -0.704 | ±6.558 | 1.010 | 0.3995 | 0.2615 | +0.997 | 0.780 | yes |
| `atr/tod<=1.0` | ATR | 0.318 | 342 | +0.169 | -0.815 | ±8.238 | 1.008 | 0.4444 | 0.2615 | +0.680 | 0.573 | yes |
| `adx>=15` | ADX | 0.928 | 980 | -0.055 | -1.039 | ±6.073 | 0.998 | 0.3918 | 0.2615 | +1.059 | 0.985 | yes |
| `d_ema200<=1.0` | EMA | 0.221 | 307 | -0.609 | -1.593 | ±11.631 | 0.979 | 0.3713 | 0.2615 | +0.067 | 0.603 | yes |
| `adx>=20` | ADX | 0.722 | 761 | -1.019 | -2.003 | ±6.642 | 0.963 | 0.3929 | 0.2615 | +0.895 | 0.985 | yes |
| `adx>=30` | ADX | 0.325 | 332 | -1.106 | -2.090 | ±9.792 | 0.959 | 0.4036 | 0.2615 | +0.436 | 0.777 | yes |
| `adx>=25` | ADX | 0.487 | 503 | -1.725 | -2.709 | ±8.145 | 0.938 | 0.3817 | 0.2615 | +0.711 | 0.950 | yes |
| `atrpct250>=0.5` | ATR | 0.685 | 804 | -1.733 | -2.716 | ±6.103 | 0.934 | 0.3955 | 0.2615 | +0.938 | 0.990 | yes |
| `ema13x48 fresh<=5` | EMA | 0.192 | 247 | -3.213 | -4.197 | ±11.282 | 0.884 | 0.3765 | 0.2615 | +0.337 | 0.853 | yes |
| `ema13<48` | EMA | 0.158 | 267 | -3.863 | -4.847 | ±11.760 | 0.868 | 0.3670 | 0.2615 | +0.161 | 0.880 | yes |
| `atrpct250>=0.8` | ATR | 0.283 | 368 | -4.333 | -5.317 | ±8.437 | 0.829 | 0.3777 | 0.2615 | +0.433 | 0.983 | yes |

### Reading these cells honestly

`atrpct250<=0.5` (ATR bottom half of its own last 250 bars) and `adx<=20` are the two survivors, at
both geometries, and both are **ceilings**. Three qualifications attach before either is believed:

1. **Both are inside their own MDE.** +5.95 pts against ±10.38 at 50/150; +3.85 against ±8.30 at
   30/150. The control says the subset ranks well *inside this sample*; the MDE says an effect this
   size cannot be told from zero with this many trades. See §5 — these are different questions.
2. **`atrpct250<=0.5` is a THIRD read of an ATR-percentile ceiling on this exact market.**
   `STUDY_V28` found `atr_pct 500<=0.2` at research p 0.003 / locked p 0.003 — one of only two
   survivors of 240 cells. `STUDY_MR30` then re-tested it as a pre-registered replication and got
   research 0.021 → **holdout 0.888 → forward 0.746**, with the *mirror* clearing the holdout at
   0.005. This is a replication attempt with a poor track record, not a discovery.
3. **The conventional readings are the negative ones.** `adx>=25`, the single most common breakout
   filter in circulation, is **−1.083 pts (p 0.652)** at 30/150 and **−2.709 (p 0.950)** at 50/150.
   `atrpct250>=0.8` is the worst cell in the table at both geometries.

---

## 4. Drop-one attribution

Three stacks, all named before any filtered P&L was run. Each component is scored by **removing**
it; the contribution is `full − (arm without it)`, so **a positive contribution means the component
earns its place**.

* **S1 CONV** — what a practitioner would build: `adx>=25` & `atr/tod>=1.0` & `ema13>48`
* **S2 LIFT** — the highest-lift usable rung of each family: `adx>=30` & `atrpct250>=0.5` & `ema13x48 fresh<=5`
* **S3 DIST** — S2 with the EMA slot taken by the DISTANCE reading: `adx>=30` & `atrpct250>=0.5` & `d_ema200>=2.0`

### 30/150 points — unfiltered base +1.462 pts on n=1115, PF 1.069

| arm | kept | n | pts/trade | vs base | MDE | PF | win | break-even | control p | **contribution** |
|---|---|---|---|---|---|---|---|---|---|---|
| S1 CONV **full** | 0.291 | 328 | +2.000 | +0.538 | ±9.260 | 1.089 | 0.2866 | 0.1794 | 0.237 | — |
| S1 CONV −ADX | 0.556 | 656 | +2.972 | +1.511 | ±6.553 | 1.136 | 0.3034 | 0.1794 | 0.040 | **−0.973** |
| S1 CONV −ATR | 0.434 | 455 | +2.818 | +1.356 | ±7.428 | 1.137 | 0.3253 | 0.1794 | 0.080 | **−0.818** |
| S1 CONV −EMA | 0.336 | 392 | −1.043 | −2.504 | ±8.150 | 0.955 | 0.2628 | 0.1794 | 0.843 | **+3.042** |
| S2 LIFT **full** | 0.020 | **24** | +7.418 | +5.957 | ±32.456 | 1.410 | 0.4167 | 0.1794 | 0.198 | — |
| S2 LIFT −ADX | 0.150 | 208 | −3.381 | −4.843 | ±9.357 | 0.836 | 0.3077 | 0.1794 | 0.882 | +10.800 |
| S2 LIFT −ATR | 0.022 | 26 | +4.364 | +2.902 | ±30.491 | 1.228 | 0.3846 | 0.1794 | 0.318 | +3.054 |
| S2 LIFT −EMA | 0.239 | 273 | −0.224 | −1.686 | ±8.493 | 0.989 | 0.3407 | 0.1794 | 0.640 | +7.642 |
| S3 DIST **full** | 0.196 | 219 | +0.276 | −1.185 | ±9.365 | 1.014 | 0.3470 | 0.1794 | 0.557 | — |
| S3 DIST −ADX | 0.453 | 526 | +0.759 | −0.702 | ±6.295 | 1.039 | 0.3308 | 0.1794 | 0.512 | **−0.483** |
| S3 DIST −ATR | 0.276 | 286 | +1.581 | +0.119 | ±8.898 | 1.077 | 0.3322 | 0.1794 | 0.305 | **−1.304** |
| S3 DIST −EMA | 0.239 | 273 | −0.224 | −1.686 | ±8.493 | 0.989 | 0.3407 | 0.1794 | 0.670 | **+0.500** |

### 50/150 points — unfiltered base +0.984 pts on n=1045, PF 1.035

| arm | kept | n | pts/trade | vs base | MDE | PF | win | break-even | control p | **contribution** |
|---|---|---|---|---|---|---|---|---|---|---|
| S1 CONV **full** | 0.291 | 309 | +0.526 | −0.458 | ±11.219 | 1.018 | 0.3786 | 0.2615 | 0.522 | — |
| S1 CONV −ADX | 0.556 | 613 | +2.602 | +1.619 | ±8.154 | 1.089 | 0.3883 | 0.2615 | 0.090 | **−2.077** |
| S1 CONV −ATR | 0.434 | 432 | +1.735 | +0.752 | ±8.936 | 1.065 | 0.4120 | 0.2615 | 0.265 | **−1.210** |
| S1 CONV −EMA | 0.336 | 371 | −3.783 | −4.767 | ±9.999 | 0.878 | 0.3450 | 0.2615 | 0.983 | **+4.309** |
| S2 LIFT **full** | 0.020 | **24** | +3.002 | +2.018 | ±36.140 | 1.124 | 0.4583 | 0.2615 | 0.352 | — |
| S2 LIFT −ADX | 0.150 | 200 | −6.150 | −7.134 | ±11.253 | 0.770 | 0.3800 | 0.2615 | 0.968 | +9.152 |
| S2 LIFT −ATR | 0.022 | 26 | −0.982 | −1.966 | ±34.195 | 0.962 | 0.4231 | 0.2615 | 0.557 | +3.984 |
| S2 LIFT −EMA | 0.239 | 268 | −3.551 | −4.535 | ±9.947 | 0.861 | 0.3955 | 0.2615 | 0.935 | +6.553 |
| S3 DIST **full** | 0.196 | 216 | −3.174 | −4.158 | ±10.856 | 0.874 | 0.3981 | 0.2615 | 0.892 | — |
| S3 DIST −ADX | 0.453 | 510 | −1.314 | −2.297 | ±7.376 | 0.948 | 0.4020 | 0.2615 | 0.895 | **−1.861** |
| S3 DIST −ATR | 0.276 | 274 | +0.425 | −0.558 | ±10.810 | 1.016 | 0.4161 | 0.2615 | 0.557 | **−3.600** |
| S3 DIST −EMA | 0.239 | 268 | −3.551 | −4.535 | ±9.947 | 0.861 | 0.3955 | 0.2615 | 0.935 | **+0.377** |

### The drop-one verdict

**In the two readable stacks (S1, S3), at both geometries, the ADX contribution and the ATR
contribution are NEGATIVE in 4 of 4 cells each, and the EMA contribution is POSITIVE in 4 of 4.**

* ADX: −0.973, −2.077 (S1) and −0.483, −1.861 (S3)
* ATR: −0.818, −1.210 (S1) and −1.304, −3.600 (S3)
* EMA: **+3.042, +4.309** (S1) and +0.500, +0.377 (S3)

Removing ADX from the conventional stack takes it from +2.000 to +2.972 and its control p from
0.237 to 0.040; removing ATR takes it to +2.818 at p 0.080. **The best cell in the whole drop-one
table is the one with neither ADX nor a conventional ATR floor in it.** The EMA is the only
component whose removal costs money, and in S1 it costs 3.0–4.3 points a trade — more than the
whole edge over the base.

**And every one of those contributions is inside the full arm's own MDE**, at all six
stack × geometry combinations. Reported as a sign pattern that is consistent 12 times out of 12,
not as a measured effect.

**S2 LIFT is a warning about the declaration rule, not a result.** Stacking the *highest-lift*
rung of each family leaves **24 trades of 1,115** — 2.0% of the sample, MDE ±32 points. High lift
means high co-selection with the trigger *and* with each other, and stacking co-selective conditions
starves the sample, exactly as `STUDY_V23_MOMENTUM_REGIME` recorded (653 of 1,184 cells unscorable).
Its apparent +7.418 pts is the mean of 24 trades and means nothing. The highest-lift rung is the
wrong thing to pick.

---

## 5. Diagnosing the null — why "clears the control" and "inside the MDE" are both true

CLAUDE.md: *"diagnose a null by its spread, not only its median."* The converse is the risk here.
The same-selectivity random gate draws **subsets of the same signal set**, so its draws are
correlated with each other and with the unfiltered base, and its spread is narrowed by a
finite-population factor. Measured (`run_b4.py`, 400 draws, plus a day-block bootstrap of the kept
set against the dropped set resampling whole **days** with their trades attached):

**30/150 — base +1.462 pts on n=1115**

| cell | n | edge | MDE | control median | control p5 | control p95 | control **sd** | control p | day-block mean | day-block P(≤0) |
|---|---|---|---|---|---|---|---|---|---|---|
| `atrpct250<=0.5` | 432 | +3.853 | ±8.296 | +0.781 | −2.181 | +3.450 | **1.699** | 0.000 | +5.660 | 0.040 |
| `adx<=20` | 415 | +2.511 | ±8.182 | +0.694 | −2.396 | +4.169 | 2.021 | 0.060 | +3.139 | 0.182 |
| `ema13>34>89` | 704 | +1.724 | ±5.990 | +1.117 | −0.417 | +2.858 | 0.994 | 0.015 | +5.454 | 0.050 |
| `ema13>48` | 916 | +0.944 | ±5.236 | +1.279 | +0.333 | +2.273 | **0.615** | 0.033 | +6.064 | 0.051 |
| `adx>=25` | 528 | −1.083 | ±6.696 | +0.949 | −1.205 | +3.005 | 1.291 | 0.647 | −1.507 | 0.691 |
| `atrpct250>=0.8` | 375 | −4.248 | ±7.140 | +0.428 | −2.613 | +3.756 | 1.963 | 0.958 | −5.879 | 0.962 |

**50/150 — base +0.984 pts on n=1045**

| cell | n | edge | MDE | control median | control sd | control p | day-block mean | day-block P(≤0) |
|---|---|---|---|---|---|---|---|---|
| `atrpct250<=0.5` | 418 | +5.946 | ±10.382 | +0.515 | 2.172 | 0.000 | +8.677 | 0.013 |
| `adx<=20` | 397 | +5.525 | ±10.328 | +0.432 | 2.452 | 0.005 | +7.692 | 0.038 |
| `ema13>34>89` | 665 | +1.893 | ±7.331 | +0.899 | 1.245 | 0.070 | +4.917 | 0.132 |
| `ema13>48` | 858 | +1.238 | ±6.471 | +0.911 | 0.773 | 0.045 | +5.956 | 0.103 |
| `adx>=25` | 503 | −2.709 | ±8.145 | +0.714 | 1.636 | 0.925 | −4.552 | 0.878 |
| `atrpct250>=0.8` | 368 | −5.317 | ±8.437 | +0.322 | 2.369 | 0.968 | −7.937 | 0.979 |

**The control null's sd is 3× to 10× tighter than the per-trade MDE**, so it can reject an effect
that is not measurable. Both numbers are correct answers to different questions:

* **control p** — does this subset rank better than a *random subset of the same size* drawn from
  the same signal set? A within-sample ranking question, correlated draws, a tight null.
* **MDE** — could an effect this size be told from zero given this dispersion and this many trades?
  The out-of-sample detectability bar, and the honest one.

**And the tightest null belongs to the least selective filter.** `ema13>48` keeps 84% of the
trades, so a random 84% subset is nearly the base itself: control sd **0.615** points. An edge of
+0.944 "clears at p 0.033" against a null that cannot move. Any filter keeping most of its signals
will clear a same-selectivity control on a trivial edge — read `kept` next to `p`, always.

---

## 6. One read of B_holdout and one of C_forward

Cells named in `run_b3.py`'s docstring before either block was opened, and the usable-rung set
**frozen from A_research** so the holdout cannot decide which rungs are tested. Nothing else was
read on B or C in this study.

**The unfiltered base is negative on B_holdout** — 30/150 reads **−0.571 pts, PF 0.976** on n=551
and 50/150 **−1.601 pts, PF 0.952** on n=508, against +1.462 / +0.984 on research. That reproduces
`STUDY_DL50` exactly (research PF 1.041 → holdout 0.956) and it frames everything below: on this
block a filter is being asked to rescue a losing base, not to improve a winning one.

### 6a. B_holdout — the structural claim, family × direction marginal

| geometry | family | direction | cells | mean pts | mean edge | beats base | research said |
|---|---|---|---|---|---|---|---|
| 30/150 | ADX | floor | 4 | −2.281 | **−1.710** | 25% | −0.717, 0% → **confirmed** |
| 30/150 | ADX | ceiling | 2 | +2.530 | **+3.101** | **100%** | +1.468, 100% → **confirmed** |
| 30/150 | ATR | floor / expansion | 4 | −0.077 | **+0.494** | **100%** | −1.133, 50% → **INVERTED** |
| 30/150 | ATR | ceiling / calm | 3 | −3.866 | **−3.295** | 33% | +0.663, 33% → **INVERTED** |
| 30/150 | EMA | with-trend | 5 | +0.451 | **+1.023** | 80% | +0.666, 60% → **confirmed** |
| 30/150 | EMA | counter-trend | 3 | −2.561 | **−1.990** | **0%** | −3.774, 0% → **confirmed** |
| 50/150 | ADX | floor | 4 | −3.903 | **−2.302** | 25% | −1.960, 0% → **confirmed** |
| 50/150 | ADX | ceiling | 2 | +2.901 | **+4.502** | **100%** | +3.680, 100% → **confirmed** |
| 50/150 | ATR | floor / expansion | 4 | +1.516 | **+3.117** | **100%** | −1.564, 50% → **INVERTED** |
| 50/150 | ATR | ceiling / calm | 3 | −2.926 | **−1.325** | **0%** | +2.509, 67% → **INVERTED** |
| 50/150 | EMA | with-trend | 5 | −0.821 | **+0.780** | 80% | +0.566, 80% → **confirmed** |
| 50/150 | EMA | counter-trend | 3 | −2.863 | **−1.262** | **0%** | −3.545, 0% → **confirmed** |

**The ADX direction and the EMA direction replicate on the holdout at both geometries. The ATR
direction inverts at both.** ADX ceilings beat the base in 4 of 4 holdout cells and ADX floors in
2 of 8; EMA with-trend in 8 of 10 and counter-trend in 0 of 6 — identical to research. ATR flips
completely: expansion floors go from beating the base 50% of the time to **100%**, and calm
ceilings from 50% to 17%.

### 6b. B_holdout — the declared cells and their mirrors

| cell | geometry | base rate | lift | kept | n | pts | edge | MDE | PF | win | break-even | control p | research → holdout |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `atrpct250<=0.5` | 30/150 | 0.2119 | 0.750 | 0.212 | 131 | **−7.735** | −7.164 | ±14.507 | 0.712 | 0.1679 | 0.1794 | 0.953 | +3.85 → **−7.16 INVERTED** |
| `atrpct250>=0.5` | 30/150 | 0.7938 | 1.099 | 0.794 | 460 | −0.146 | +0.425 | ±8.010 | 0.994 | 0.2391 | 0.1794 | 0.388 | −1.90 → +0.43 inverted |
| `adx<=20` | 30/150 | 0.2341 | 0.853 | 0.234 | 165 | +2.288 | **+2.859** | ±14.117 | 1.097 | 0.2485 | 0.1794 | 0.200 | +2.51 → **+2.86 held** |
| `adx>=20` | 30/150 | 0.7659 | 1.056 | 0.766 | 435 | −2.919 | −2.348 | ±7.976 | 0.881 | 0.2230 | 0.1794 | 0.975 | −0.57 → −2.35 held |
| `ema13>34>89` | 30/150 | 0.6204 | 1.583 | 0.620 | 330 | +2.767 | **+3.338** | ±9.999 | 1.118 | 0.2545 | 0.1794 | **0.018** | +1.72 → **+3.34 held** |
| `adx>=25` *(falsifier)* | 30/150 | 0.5260 | 1.015 | 0.526 | 302 | −4.095 | −3.524 | ±9.151 | 0.831 | 0.2285 | 0.1794 | 0.948 | −1.08 → **−3.52 confirmed negative** |
| `ema13>48` | 30/150 | 0.8304 | 1.547 | 0.830 | 447 | −0.816 | −0.245 | ±8.213 | 0.967 | 0.2304 | 0.1794 | 0.578 | +0.94 → −0.25 **failed** |
| `ema13<48` | 30/150 | 0.1696 | 0.366 | 0.170 | 132 | −3.300 | −2.729 | ±14.171 | 0.863 | 0.2273 | 0.1794 | 0.738 | −5.25 → −2.73 held |
| **S1 CONV stack** *(falsifier)* | 30/150 | — | — | 0.230 | 146 | **−5.684** | −5.113 | ±12.635 | 0.769 | 0.2260 | 0.1794 | 0.858 | +0.54 → **−5.11** |
| `atrpct250<=0.5` | 50/150 | 0.2119 | 0.750 | 0.212 | 127 | −3.589 | −1.988 | ±20.315 | 0.903 | 0.2756 | 0.2615 | 0.630 | +5.95 → **−1.99 INVERTED** |
| `atrpct250>=0.5` | 50/150 | 0.7938 | 1.099 | 0.794 | 429 | −0.495 | +1.106 | ±10.219 | 0.985 | 0.3240 | 0.2615 | 0.250 | −2.72 → +1.11 inverted |
| `adx<=20` | 50/150 | 0.2341 | 0.853 | 0.234 | 157 | +4.596 | **+6.197** | ±17.958 | 1.145 | 0.3439 | 0.2615 | 0.090 | +5.53 → **+6.20 held** |
| `adx>=20` | 50/150 | 0.7659 | 1.056 | 0.766 | 402 | −3.368 | −1.767 | ±10.405 | 0.899 | 0.3109 | 0.2615 | 0.897 | −2.00 → −1.77 held |
| `ema13>34>89` | 50/150 | 0.6204 | 1.583 | 0.620 | 310 | +1.126 | +2.727 | ±12.482 | 1.035 | 0.3258 | 0.2615 | 0.105 | +1.89 → +2.73 held |
| `adx>=25` *(falsifier)* | 50/150 | 0.5260 | 1.015 | 0.526 | 280 | −4.567 | −2.966 | ±12.137 | 0.863 | 0.3107 | 0.2615 | 0.922 | −2.71 → **−2.97 confirmed negative** |
| `ema13>48` | 50/150 | 0.8304 | 1.547 | 0.830 | 419 | −3.195 | −1.594 | ±10.463 | 0.907 | 0.2983 | 0.2615 | 0.930 | +1.24 → −1.59 **failed** |
| `ema13<48` | 50/150 | 0.1696 | 0.366 | 0.170 | 125 | −3.819 | −2.218 | ±18.233 | 0.884 | 0.3200 | 0.2615 | 0.655 | −4.85 → −2.22 held |
| **S1 CONV stack** *(falsifier)* | 50/150 | — | — | 0.230 | 139 | **−7.731** | −6.130 | ±17.168 | 0.781 | 0.2950 | 0.2615 | 0.900 | −0.46 → **−6.13** |

**Every cell on the holdout is inside its own MDE**, and every MDE is larger than on research
because B has half the trades. What can be read is sign agreement, and the sign agreement is
informative:

* **`adx<=20` held on both geometries** (+2.86, +6.20 against research +2.51, +5.53) — the closest
  thing to a replication in this study, and it clears nothing (p 0.200, 0.090).
* **`ema13>34>89` held on both** and is the only cell to clear a control on the holdout (p 0.018
  at 30/150) — while `ema13>48`, the *simpler* EMA reading, **failed**. The alignment and the state
  are not interchangeable even at signal-bar rho +0.596.
* **Both falsifiers failed to falsify.** `adx>=25` is more negative out of sample than in it, and
  the conventional S1 CONV stack is the single worst object in the table on both geometries
  (−5.68, −7.73 pts a trade, PF 0.769/0.781).
* **`atrpct250<=0.5` inverted, as `STUDY_MR30` predicted it would.** Which brings us to the reason.

### 6c. Why the ATR condition inverts and the EMA condition does not — the base rate drifts

Base rate on Donchian-20 breakout bars, same construction, three blocks and two providers:

| condition | A_research | B_holdout | C_forward | range | lift A / B / C |
|---|---|---|---|---|---|
| `ema13>48` | 0.842 | 0.830 | 0.850 | **0.019** | 1.492 / 1.547 / 1.457 |
| `ema13>34>89` | 0.662 | 0.620 | 0.644 | **0.042** | **1.569 / 1.583 / 1.590** |
| `d_ema200>=2.0` | 0.693 | 0.648 | 0.685 | 0.044 | 1.645 / 1.636 / 1.844 |
| `+DI>-DI` | 0.978 | 0.964 | 0.951 | 0.027 | 1.892 / 1.973 / 1.883 |
| `adx<=20` | 0.278 | 0.234 | 0.224 | 0.055 | 0.901 / 0.853 / 0.906 |
| `adx>=25` | 0.487 | 0.526 | 0.585 | 0.098 | 1.042 / 1.015 / 1.109 |
| `atr/tod>=1.0` | 0.682 | 0.535 | 0.522 | **0.160** | 1.029 / 1.116 / 1.061 |
| `atrpct250<=0.5` | 0.318 | 0.212 | **0.142** | **0.175** | 0.773 / 0.750 / 0.640 |
| `atrpct250>=0.8` | 0.283 | 0.355 | 0.463 | **0.180** | 1.087 / 1.210 / 1.194 |

**`atrpct250<=0.5` keeps 31.8% of breakouts on A and 14.2% on C — it is a different filter on each
block**, so of course it does not transfer. The EMA readings keep the same share to within two to
four points and their lifts are stable to the third decimal across two providers. ADX sits between.

This reproduces `STUDY_MR30` on a third construction: *"the CALM SHARE ITSELF MOVES, 47.9% → 23.3%
→ 22.0%, so a rule keyed to a fixed percentile cut is a different rule in each block."* The
practical rule: **before testing a condition out of sample, check that its kept share is stable
there. A rung whose selectivity drifts is not being replicated, it is being replaced.**
`+DI>-DI` is inert on all three blocks (0.978 / 0.964 / 0.951), which is the reassuring converse —
inertness is a structural property and it holds.

### 6d. C_forward — US30_ISO, a different provider, 2025-07-16 → 2026-08-26

492 breakout bars in the window; n = 284 / 274 trades. **The unfiltered base is POSITIVE here**
(+5.931 pts, PF 1.243 at 30/150; +4.613, PF 1.133 at 50/150), so the base runs
**+1.462 (A) → −0.571 (B) → +5.931 (C)** — regime, on a different feed, and it is why no single
block's verdict on the base can be trusted.

| geometry | family | direction | cells | mean pts | mean edge | beats base | A said | B said |
|---|---|---|---|---|---|---|---|---|
| 30/150 | ADX | floor | 4 | +4.708 | −1.223 | 25% | 0% | 25% |
| 30/150 | ADX | ceiling | 2 | +10.076 | **+4.146** | **100%** | **100%** | **100%** |
| 30/150 | ATR | floor | 4 | +4.325 | −1.605 | 50% | 50% | 100% |
| 30/150 | ATR | ceiling | 3 | +6.843 | +0.912 | 67% | 33% | 33% |
| 30/150 | EMA | with-trend | 5 | +5.762 | −0.168 | 20% | 60% | 80% |
| 30/150 | EMA | counter-trend | 3 | +0.163 | **−5.768** | **0%** | **0%** | **0%** |
| 50/150 | ADX | floor | 4 | +6.682 | +2.069 | 75% | 0% | 25% |
| 50/150 | ADX | ceiling | 2 | +7.937 | **+3.325** | **100%** | **100%** | **100%** |
| 50/150 | ATR | floor | 4 | +1.253 | −3.359 | **0%** | 50% | 100% |
| 50/150 | ATR | ceiling | 3 | +6.412 | +1.800 | 67% | 67% | 0% |
| 50/150 | EMA | with-trend | 5 | +3.634 | −0.979 | 40% | 80% | 80% |
| 50/150 | EMA | counter-trend | 3 | −1.125 | **−5.738** | **0%** | **0%** | **0%** |

Declared cells on C (every one inside its own MDE, which here runs ±12 to ±37 points):

| cell | geometry | base rate | kept | n | pts | edge | MDE | PF | win | break-even | control p |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `adx<=20` | 30/150 | 0.2236 | 0.224 | 77 | +8.566 | **+2.635** | ±23.450 | 1.358 | 0.2597 | 0.1794 | 0.245 |
| `ema13>34>89` | 30/150 | 0.6443 | 0.644 | 181 | +8.260 | **+2.329** | ±15.219 | 1.340 | 0.2486 | 0.1794 | 0.107 |
| `atrpct250<=0.5` | 30/150 | **0.1423** | 0.142 | 48 | +5.210 | −0.721 | ±29.877 | 1.204 | 0.2083 | 0.1794 | 0.450 |
| `atrpct250>=0.5` | 30/150 | 0.8598 | 0.860 | 255 | +5.072 | −0.858 | ±12.210 | 1.207 | 0.2392 | 0.1794 | 0.615 |
| `ema13>48` | 30/150 | 0.8496 | 0.850 | 241 | +5.304 | −0.627 | ±12.774 | 1.215 | 0.2324 | 0.1794 | 0.540 |
| `adx>=20` | 30/150 | 0.7764 | 0.776 | 221 | +4.594 | −1.337 | ±13.095 | 1.186 | 0.2308 | 0.1794 | 0.600 |
| `ema13<48` | 30/150 | 0.1504 | 0.150 | 57 | +3.863 | −2.068 | ±25.293 | 1.159 | 0.2456 | 0.1794 | 0.542 |
| **S1 CONV stack** | 30/150 | — | 0.272 | 85 | +3.729 | −2.202 | ±21.059 | 1.149 | 0.2235 | 0.1794 | 0.520 |
| `adx>=25` *(falsifier)* | 30/150 | 0.5854 | 0.585 | 170 | +2.374 | **−3.557** | ±14.362 | 1.095 | 0.2294 | 0.1794 | 0.762 |
| `ema13>34>89` | 50/150 | 0.6443 | 0.644 | 173 | +6.787 | **+2.174** | ±18.534 | 1.196 | 0.3295 | 0.2615 | 0.265 |
| **S1 CONV stack** | 50/150 | — | 0.272 | 84 | +6.878 | +2.265 | ±26.108 | 1.202 | 0.3452 | 0.2615 | 0.450 |
| `adx<=20` | 50/150 | 0.2236 | 0.224 | 76 | +6.382 | **+1.770** | ±28.224 | 1.184 | 0.3289 | 0.2615 | 0.470 |
| `adx>=20` | 50/150 | 0.7764 | 0.776 | 211 | +6.335 | +1.722 | ±16.374 | 1.186 | 0.3365 | 0.2615 | 0.210 |
| `ema13>48` | 50/150 | 0.8496 | 0.850 | 231 | +5.016 | +0.403 | ±15.884 | 1.143 | 0.3203 | 0.2615 | 0.398 |
| `adx>=25` *(falsifier)* | 50/150 | 0.5854 | 0.585 | 162 | +4.324 | −0.289 | ±18.136 | 1.127 | 0.3457 | 0.2615 | 0.545 |
| `atrpct250>=0.5` | 50/150 | 0.8598 | 0.860 | 248 | +3.989 | −0.624 | ±14.866 | 1.116 | 0.3306 | 0.2615 | 0.583 |
| `atrpct250<=0.5` | 50/150 | **0.1423** | 0.142 | 47 | +3.508 | −1.105 | ±36.862 | 1.094 | 0.2766 | 0.2615 | 0.583 |
| `ema13<48` | 50/150 | 0.1504 | 0.150 | 56 | −1.579 | **−6.192** | ±29.474 | 0.954 | 0.3214 | 0.2615 | 0.805 |

**4 of 88 out-of-sample cells clear p≤0.05 against a chance expectation of 4.4** — exactly chance.
No out-of-sample p-value in this study carries any weight. The only readable evidence is the
**sign pattern across three blocks and two providers**, tabulated next.

---

## 7. Verdict — which family earns a place

### 7a. The pooled tally — every cell, three blocks, two geometries

Each rung of each family, at both geometries, on all three blocks, compared with **its own block's**
unfiltered base. 126 cells.

| family | direction | cells beating their block's base | mean edge vs base |
|---|---|---|---|
| ADX | floor (`adx>=k`, `+DI>-DI`) | 6 of 24 — **25%** | **−0.974** pts |
| ADX | **ceiling** (`adx<=k`) | **12 of 12 — 100%** | **+3.370** pts |
| ATR | floor / expansion | 14 of 24 — 58% | −0.675 pts |
| ATR | ceiling / calm | 8 of 18 — 44% | +0.210 pts |
| EMA | with-trend | 18 of 30 — 60% | +0.314 pts |
| EMA | **counter-trend** | **0 of 18 — 0%** | **−3.680** pts |

**The two extremes are the result: 12 of 12 for an ADX ceiling and 0 of 18 for a counter-trend EMA,
with ATR sitting at chance in both directions (58% and 44%).** Read the caveat with it — **these
cells are not independent.** Every floor has its exact-complement ceiling in the pool, the two
geometries share their signal set, and A and B are the same feed over one calendar. A binomial
p-value on 12 of 12 would be 0.0002 and it would be wrong; the honest statement is that the
direction is consistent everywhere it was looked at, and that no individual cell is measurable.


Sign agreement across **six out-of-sample-capable cells** (3 blocks × 2 geometries), plus the
base-rate verdict. Nothing below is a measured effect: every individual cell in this study sits
inside its own minimum detectable effect.

### 7b. Family by family

| | base rate on breakout bars (A / B / C) | is it the trigger restated? | sign consistency | verdict |
|---|---|---|---|---|
| **`+DI > −DI`** | **0.978 / 0.964 / 0.951** | **YES — INERT** | n/a | **the Donchian restated.** Passes ≥95% on all three blocks; it cannot refuse a trade. Excluded before any P&L. |
| **`ema13>48` state** | 0.842 / 0.830 / 0.850, lift ~1.5 | **largely yes** (removes a sixth of signals) | +/−/± | **worth nothing.** Reproduces NQ's 82.6% almost exactly. Its edge is +0.94 research → −0.25, −1.59, −0.63, +0.40 out of sample. |
| **`adx>=25` and every ADX floor** | 0.487 / 0.526 / 0.585, lift **1.01–1.11** | **no** — genuinely independent | **negative in 6 of 6** | **backwards.** The conventional filter is −1.08, −2.71 (A), −3.52, −2.97 (B), −3.56, −0.29 (C). Pooled over three blocks and two geometries, ADX floors beat their block's base in **6 of 24** cells. |
| **`adx<=20` / ADX ceilings** | 0.278 / 0.234 / 0.224, drift 0.055 | **no** | **positive in 6 of 6**; ADX ceilings beat their block's base in **12 of 12** cells across three blocks and two providers, mean edge **+3.370** pts | **the one candidate.** +2.51, +5.53 (A) → +2.86, +6.20 (B) → +2.64, +1.77 (C). Never significant (best p 0.090 out of sample). Keeps 37% of trades and earns **more total points than the base** (1649 vs 1630; 2584 vs 1028), so it is not the trade-less artifact. |
| **ATR expansion vs a causal ToD baseline** | 0.682 / 0.535 / 0.522 | **no** — lift 1.011–1.156 | floors subtract on A and C, **add on B** | **no information.** Direction disagrees across blocks; the family-direction marginal flips. |
| **ATR percentile ceilings** | **0.318 / 0.212 / 0.142** | no | **fails 4 of 4** out-of-sample cells | **rejected, third strike.** `STUDY_V28` found it, `STUDY_MR30` failed to replicate it, and it fails again here. Its kept share drifts 0.318 → 0.142: it is a different filter on each block. |
| **`d_ema200` distance** | 0.693 / 0.648 / 0.685, lift 1.64–1.84 | partly (69% pass) | contributes negatively in S3 at both geometries | **not earned on this base.** `STUDY_V40`'s distance finding does not reproduce on a US30 morning window. |
| **`ema13>34>89` alignment** | 0.662 / 0.620 / 0.644, **lift 1.569 / 1.583 / 1.590** | partly (66% pass) | **positive in 6 of 6**, and the only cell to clear a control out of sample (B 30/150, p 0.018) | **the second candidate**, and the most stable base rate in the pool. |
| **`ema13x48 fresh<=5`** | highest lift in the table (2.054) | no | one of the two worst research cells | **high lift is not information.** Stacked with the other highest-lift rungs it leaves 24 trades of 1,115. |

### 7c. In one paragraph

**ADX, ATR and EMA are not the Donchian restated on this base — except `+DI > −DI`, which is,
at 97.8% of breakout bars.** That is the finding the base-rate check was for, and it is the first
time on this branch that a proposed filter pool has come through it largely intact: max cross-family
|rho| on the signal bars is 0.236, and ADX and ATR lifts sit between 1.01 and 1.16, meaning they can
genuinely refuse trades. **What they cannot do is earn anything measurable.** All 42 research cells,
all 24 drop-one arms and all 88 out-of-sample cells have effects smaller than their own MDE, and
4 of 88 out-of-sample cells clear a control against 4.4 expected by chance. The one durable
statement is a **direction, held across three blocks and two providers**: an ADX **ceiling** beats
the base in **12 of 12** cells while ADX **floors** beat it in **6 of 24**, and a **counter-trend**
EMA reading beats it in **0 of 18** — so on a US30 morning Donchian breakout the conventional `ADX>=25`
gate is on the **wrong side of its own axis**, and the conventional stack of all three
(`adx>=25 & atr/tod>=1.0 & ema13>48`) is the single worst object measured: −5.68 and −7.73 points a
trade on the holdout at PF 0.769 / 0.781, and removing ADX from it improves it at both geometries.
**ATR carries no direction that survives a block change**, and the reason is visible in its own base
rate rather than in its P&L: the kept share of `atrpct250<=0.5` runs 0.318 → 0.212 → 0.142, so it is
not the same filter twice, while `ema13>34>89`'s lift is 1.569 / 1.583 / 1.590.

### 7d. What would actually move this

* **1-minute US30 bars.** A 07:00–11:00 session is sixteen 15-minute bars; the exposure-matched
  test in `STUDY_MR30` is already the strongest form of this question at this resolution and it
  came back below chance.
* **More blocks, not more conditions.** The MDE at ±5 to ±20 points against edges of 2–6 points
  needs roughly 4–10× the trades. That is calendar, not search.
* **Nothing should be shipped from this study.** The two candidates (`adx<=20`, `ema13>34>89`) are
  sign-consistent 6 of 6 and significant nowhere; the correct status is *watch*, and the correct
  action on `adx>=25` is to remove it wherever it is currently switched on.

---

## 8. Discipline, trial count and what this study cannot say

**Trial count on A_research: 72 P&L evaluations.** 42 single-condition vetoes + 24 drop-one arms
(`run_b2.py`) + 4 unfiltered base reads (2 triggers × 2 geometries, `run_b1.py`) + 2 unfiltered
bases in `run_b2.py`. `run_b4.py` re-scored 12 already-counted cells with additional nulls and
introduced no new cells. The base-rate and correlation tables of §1–§2 involve no P&L and are not
counted. Reads of B_holdout and C_forward were one each, on cells declared in `run_b3.py`'s
docstring, with the usable-rung set frozen from A.

**Expected passes at p≤0.05 over the 66 controlled research cells: 3.3. Observed: 7** (6 singles,
1 drop-one arm). But the nominal count overstates the search: the 21 usable rungs are roughly
**12 independent axes** because every floor has its exact-complement ceiling in the pool, and the
two geometries are highly correlated. Reduced to distinct axes, the six single-cell passes are
**four**: `atrpct250<=0.5`, `adx<=20`, `ema13>34>89` and `ema13>48` — and the last two correlate
+0.596 on the signal bars, so it is nearer three. Against ~12 effective axes that is above chance,
which is why the direction finding is reported at all; it is not enough to be deflated into
significance, and no deflated Sharpe is quoted because nothing here reaches the point of needing one.

**The grid was deliberately small.** The mandate's arithmetic applies: over ~1,176 cells the
search's own E[max t | noise] is 3.301, which already exceeds the t ≈ 2.802 needed for
detectability, so a wide search here cannot separate an edge from its luckiest draw. 21 declared
rungs and 3 declared stacks were chosen for that reason, and every rung was declared as a floor
*and* a ceiling so no direction could be picked after the fact.

**Detectability is the binding constraint, not significance.** Per-trade sd runs 60–85 points at
30/150 and 75–105 at 50/150, so the minimum detectable effect at 80% power is ±5 to ±12 points on
research, ±8 to ±20 on the holdout and ±12 to ±20 on the forward block. **Not one cell in this
study — research, holdout or forward — has an effect larger than its own MDE.** Everything reported
as "held" or "inverted" is a *sign* agreeing or disagreeing across blocks, which is weaker evidence
than a measurement and is the only kind this sample supports.

**What is inherited and not re-derived.** `STUDY_DL50` already established that this exact base
decays across this exact split and that its failure is in the trigger (on the holdout a random entry
in the same window beats it while always-long in that window is positive). `STUDY_MR30` already
established that timing inside US30 is worth nothing an exposure-matched test can detect (1 of 60
declared conditions clearing where 3.0 are expected). This study does not overturn either; it
localises them to the three filter families.

**Known limits.**
* `US30_1m` is not on disk, so 15-minute bars are the finest available and a 07:00–11:00 session is
  sixteen bars. No true 1-minute exit path can be walked.
* A and B are heavily spent — six studies have read them — so every p-value on either is
  descriptive. C_forward is the only genuinely unread block and it is 492 breakout bars.
* Long side only, one trigger family, one market. The short mirror was not run.
* The ambiguous intrabar share is 0.006–0.007, so the tie-break convention is not load-bearing at
  these geometries. It would be at a tighter stop.
