# V18 — cointegration, correlation, and the Donchian 30/20 + EWMAC(16,64) spec

**Not one configuration beats its matched control on both blocks.** The two geometry choices in the
brief — a 1.5×ATR stop and a 2R target — are both on the wrong side of their own marginal curves,
and correcting them moves pooled EV from −0.083 to −0.052 R without making anything significant.

---

## 1. Data, and a cost error corrected

Five 15-minute series on a New York clock: US30 (2024-08→2026-08), US100 (same span), **US30L**
(2016-10→2025-07, 8.5 years, newly attached), XAU (2004→2026) and NQ. All four uploaded feeds are
now in `research/datasets.py` **with checksums** — XAU re-ingested to exactly 494,235 rows, matching
the count recorded before the recycle.

**The first run of this study charged MNQ's tick and fee stack in every market**, which on gold —
15-minute ATR ≈ 1.5 USD — made the round turn 54% of a 1.5×ATR stop and printed EV −1.55 R at
PF 0.13. That is this branch's own recorded mistake walked into again. With per-instrument tick,
point value and spread the round turn lands at 5–19% of the stop everywhere:

| | US30 | US100 | NQ | US30L | XAU |
| --- | --- | --- | --- | --- | --- |
| round turn (points) | 8.368 | 2.470 | 2.470 | 8.368 | 0.378 |
| as % of a 1.5×ATR stop | 13.9% | 5.2% | 7.6% | 19.2% | 16.6% |

---

## 2. Cointegration

Engle–Granger, both directions, against **MacKinnon's EG critical values** (−3.90 / −3.34 / −3.04),
not the ADF table (−3.43 / −2.86 / −2.57). Reading an *estimated* residual against the plain ADF
table is the commonest way a cointegration result is manufactured. A pair is only called
cointegrated if both directions reject.

**15-minute:**

| pair | bars | corr(ret) | ADF t | t rev | half-life | verdict |
| --- | --- | --- | --- | --- | --- | --- |
| US30/US30L | 21,023 | 0.9447 | −5.17 | −5.17 | **6 bars** | **cointegrated** |
| US30/NQ | 31,203 | 0.7747 | −3.49 | −3.37 | 677 | cointegrated |
| US30/US100 | 46,690 | 0.7675 | −3.05 | −3.04 | 1,510 | no |
| US100/NQ | 30,264 | 0.9546 | −1.97 | −2.08 | 683 | no |
| US30L/XAU | 193,705 | 0.0598 | −3.57 | −2.86 | 5,954 | one-way — distrust |
| XAU/NQ | 67,581 | 0.1039 | −2.03 | −2.95 | 6,571 | no |

**US30/US30L is the positive control and it works**: the same instrument from two providers, β 0.994,
half-life 6 bars. A test that could not find that would be broken.

**US100/NQ is the informative failure.** Daily return correlation is **0.9995** — they are the same
index — and the pair does **not** cointegrate (t −1.64 daily). That is the signature of a slowly
drifting level ratio, which is exactly the defect `STUDY_US100.md` records for our NQ file: its
levels are synthetic and the ratio decays smoothly 1.253 → 1.036. **Correlation near 1 with no
cointegration means the levels, not the returns, are wrong.**

**On daily closes nothing cointegrates at all** — not even US30/US30L, at 283 overlapping days. The
15-minute rejections are microstructure and sample size, not economics.

**Gold is the only genuinely independent series**: 15-minute return correlation 0.06–0.10 against
every index, and rolling 500-bar correlation sits below 0.5 in **97–99%** of windows.

**And index correlation is not stable.** US30/US100 15-minute return correlation ranges **0.019 to
0.971** across rolling 500-bar windows, below 0.5 in 21% of them. Any sizing that assumes a fixed
pairwise correlation is assuming something this data does not support.

*Note for a trend follower: a cointegrated pair is bad news, not good. Cointegration means the
spread reverts, so two cointegrated legs held the same way are one bet wearing two names.*

---

## 3. The strategy exactly as specified

Donchian 30 entry / 20 exit, stop 1.5 × ATR(14), target 2R, gated by a **daily** EWMA(16) − EWMA(64)
crossover mapped onto 15-minute bars strictly after each session closes. Market order, one unit.
EV per trade in R and in USD at one contract.

| instrument | block | n | EV (R) | EV ($) | PF | win% | net R | maxDD | MAR | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| US30 | research | 658 | −0.1582 | −52.44 | 0.778 | 34.7 | −104.1 | 107.4 | −0.97 | −2.43 |
| US30 | locked | 402 | −0.0217 | −9.27 | 0.967 | 38.6 | −8.7 | 27.9 | −0.31 | −0.30 |
| US100 | research | 624 | **+0.0878** | +8.03 | **1.148** | 39.4 | +54.8 | 18.3 | 3.00 | 1.30 |
| US100 | locked | 306 | −0.0195 | −2.75 | 0.969 | 34.6 | −6.0 | 21.7 | −0.28 | −0.29 |
| NQ | research | 1053 | +0.0063 | +0.45 | 1.010 | 37.5 | +6.6 | 34.0 | 0.19 | 0.10 |
| NQ | locked | 515 | **+0.0509** | +4.83 | **1.084** | 38.6 | +26.2 | 16.6 | 1.58 | 0.76 |
| US30L | research | 2427 | −0.2002 | −43.63 | 0.739 | 35.2 | −485.8 | 486.9 | −1.00 | −2.61 |
| US30L | locked | 1383 | −0.1880 | −55.08 | 0.747 | 34.6 | −260.0 | 295.9 | −0.88 | −2.72 |
| XAU | research | 4768 | −0.2182 | −51.43 | 0.713 | 33.2 | −1040.3 | 1041.0 | −1.00 | −2.70 |
| XAU | locked | 3211 | −0.0550 | −26.91 | 0.918 | 35.3 | −176.7 | 248.1 | −0.71 | −0.78 |

**It loses on four of five instruments**, and on the longest history — US30L, 8.5 years, 3,810
trades — it loses decisively on both blocks. Only NQ is positive on both, at +0.006 R on research.
Short side is worse everywhere except US100.

**The EWMAC gate is a coin flip**: across ten instrument-block cells it helps four and hurts six.
On US30L it hurts on both blocks.

---

## 4. Robustness — 625 cells per instrument, read by marginal average

Donchian entry × exit × stop × target, 5 × 5 × 5 × 5, research block, long side.

**Share of the grid that is profitable, before any ranking:** US30 **0%**, US30L 2%, XAU 1%,
NQ 45%, US100 66%. On three of five markets there is no parameterisation of this family that works.

| ATR stop | US30 | US100 | NQ | US30L | XAU | **pooled** | % profitable |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1.0 | −0.2543 | −0.0399 | −0.0898 | −0.3160 | −0.3568 | −0.2280 | 7% |
| **1.5 (spec)** | −0.1584 | +0.0347 | −0.0100 | −0.1769 | −0.2222 | **−0.1423** | 22% |
| 2.0 | −0.1244 | +0.0232 | +0.0018 | −0.1094 | −0.1449 | −0.0897 | 26% |
| 2.5 | −0.0960 | +0.0196 | +0.0065 | −0.0822 | −0.1110 | −0.0634 | 27% |
| 3.0 | −0.0842 | +0.0346 | +0.0140 | −0.0629 | −0.0888 | **−0.0532** | 33% |

**Monotone toward a wider stop on every single instrument.** The specified 1.5N is second-worst.

| target | US30 | US100 | NQ | US30L | XAU | **pooled** | % profitable |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **none** | −0.1308 | **+0.1256** | +0.0120 | −0.0666 | −0.0917 | **−0.0521** | 37% |
| 1R | −0.1203 | −0.0170 | −0.0169 | −0.1359 | −0.1798 | −0.0993 | 10% |
| 1.5R | −0.1314 | +0.0015 | −0.0165 | −0.1242 | −0.1532 | −0.0962 | 17% |
| **2R (spec)** | −0.1376 | +0.0189 | −0.0040 | −0.1111 | −0.1465 | −0.0826 | 22% |
| 3R | −0.1217 | +0.0495 | +0.0019 | −0.1033 | −0.1286 | −0.0767 | 29% |

**No take profit beats every take profit — the sixth independent time on this branch.** Entry and
exit lengths are both mildly monotone toward longer (exit 30 > exit 10 on all five).

---

## 5. Drawdown optimisation

Ranking the same grid by MAR (net R / max drawdown) and reading what the **top decile agrees on**
rather than its best row:

| instrument | best MAR | median MAR | top-decile consensus |
| --- | --- | --- | --- |
| US100 | 4.77 | +0.46 | entry 30 (45%), exit 25, stop 1.5, **no TP (63%)** |
| NQ | 3.48 | −0.15 | entry 40 (50%), exit 30 (56%), stop 3.0, TP 3R |
| US30L | 1.37 | −0.99 | entry 55 (50%), exit 30 (44%), stop 2.5, **no TP (79%)** |
| XAU | 0.73 | −1.00 | entry 55, exit 20, stop 3.0, **no TP (79%)** |
| US30 | −0.14 | −0.97 | entry 55, exit 30 (47%), stop 3.0, **no TP (60%)** |

Against a population share of 20% per rung, **no take profit takes 60–79% of the top decile on four
of five instruments**. That is the most consistent signal in the entire study.

---

## 6. The marginal-implied configuration, read once on locked

Two changes only — stop 3.0N, no target — chosen from the marginal medians, not from a cell:

| instrument | spec locked EV / PF | marginals locked EV / PF |
| --- | --- | --- |
| US30 | −0.0217 / 0.967 | −0.0951 / 0.812 |
| US100 | −0.0195 / 0.969 | **+0.0837 / 1.212** |
| NQ | +0.0509 / 1.084 | **+0.0844 / 1.198** |
| US30L | −0.1880 / 0.747 | −0.1245 / 0.777 |
| XAU | −0.0550 / 0.918 | **+0.0510 / 1.111** |

Better on four of five, and it flips US100, NQ and XAU positive. Bootstrap P(mean daily R ≤ 0) on
locked: US100 0.216, NQ 0.155, XAU 0.072, US30 0.841, US30L 0.990. **Nothing reaches 5%.** Monte
Carlo p99 drawdowns run 1.5–2.5× the realised figure — size for the p99, not for what is visible.

---

## 7. The matched control, which settles it

Random entries, same side, same geometry, same minute-of-day mix, 1,500 draws:

| instrument | config | research p | locked p |
| --- | --- | --- | --- |
| US100 | 1.5N, 2R (spec) | **0.001** | 0.639 |
| US100 | 3N, no TP | 0.070 | 0.390 |
| NQ | 1.5N, 2R (spec) | 0.074 | **0.031** |
| NQ | 3N, no TP | 0.496 | 0.161 |
| XAU | 3N, no TP | 0.157 | **0.003** |
| US30L | 3N, no TP | 0.715 | 0.961 |

**Not one cell beats its control on both blocks.** US100's spec passes research at p 0.001 and dies
on the holdout — textbook decay. NQ and XAU pass *locked* while failing research, which this branch
treats as a **defect, not a result**: a rule chosen on research should look better there.

---

## 8. What would change the answer

1. **A second contemporaneous instrument for pair trading**, if the cointegration is to be traded
   rather than diagnosed. The only cointegrated pair found is the same instrument twice.
2. **Bid/ask.** Every spread here is assumed, and on US30 the round turn is already 19% of the stop.
3. The family itself is exhausted at this geometry — 3,125 cells across five markets, 0–66%
   profitable, nothing clearing a control twice.

## Files

`research/v18/v18diag.py` (ADF, half-life, Hurst, Lo–MacKinlay VR, Newey–West correlation — all
validated against simulated processes) · `v18coint.py` · `v18multi.py` · `v18results.py` ·
`v18control.py`.
