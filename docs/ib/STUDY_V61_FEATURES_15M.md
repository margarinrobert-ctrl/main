# STUDY: feature engineering on the V61 CVD rule at 15 minutes

**What this is.** A full feature-engineering pass on the V61 CVD exhausted-sellers rule on NQ
15-minute bars, built to the mechanism-first architecture: a primary that emits events, a meta layer
that only scores them, features confined to the meta layer, and two gates so neither features nor
sizing can be credited with an edge the primary does not have.

**Verdict: this is the strongest meta-layer result on this branch, and it does not clear its
out-of-sample null.** Gate 1 passes cleanly on both blocks. The screen is well above chance at every
stage. Gate 2 clears both nulls on research at p 0.006 / 0.007. The single locked read moves profit
factor **1.862 → 2.707** — and a random filter of the same size gives **p 0.145**, so it is
directionally right and not significant, on 56 events.

**Code.** `research/v61feat/v61feat.py` (51 features, fracdiff, causal HMM, truncation audit),
`run_feat1.py` (Gate 1, base rates, IC, redundancy, stability), `run_feat2.py` (models, Gate 2,
drop-one, one locked read, deflation), `plot_feat.py`. Output `results/v61feat/`.

## Gate 1 — before a single feature is written

Two 15-minute candidates. Whichever clears is the one a meta layer may be built on.

| primary | block | n | net %/event | 95% CI | p | PF |
| --- | --- | --- | --- | --- | --- | --- |
| **15m all hours (as shipped)** | research | 225 | +0.0697 | [+0.014, +0.123] | **0.006** | 1.570 |
| **15m all hours** | locked | 125 | +0.1022 | [+0.038, +0.173] | **0.005** | 1.869 |
| 15m 07:00–11:00 + flatten | research | 87 | +0.0171 | [−0.060, +0.096] | **0.330** | 1.151 |
| 15m 07:00–11:00 + flatten | locked | 45 | +0.0796 | [−0.001, +0.161] | 0.027 | 1.859 |

**The session+flatten configuration does not clear research.** Building a meta layer on it would be
exactly the move the two-gate structure exists to prevent, so the meta layer goes on the all-hours
primary. 350 events, 225 research / 125 locked.

## The features — 51 columns, 7 declared families, fixed before any scoring

`trend` (ADX, DI spread, EMA distance and slope, efficiency ratio at two horizons, linreg R², EMA
alignment, up-bar share) · `struct` (channel excess, channel width, position in channel, close
position, body, upper wick, range/ATR, gap, distance from the 55-bar high) · `mom` (ROC at 5/20/60/240,
RSI 14 and 48, MACD histogram, 96-bar tsmom) · `vol` (ATR/price, ATR percentile, ATR ratio, realised
vol, vol ratio, Parkinson, vol-of-vol) · `volu` (participation against an expanding **time-of-day**
baseline, not a raw mean — a raw volume mean is a clock feature) · `regime` (CHOP at two lengths,
three HMM posteriors, HMM confidence, time-of-day) · `ffd` (fixed-width fractional difference of log
price and of the CVD, plus z-scores).

**Fracdiff and the HMM are meta features and cannot fire a trade.** Fracdiff order **d = 0.8**
(64-bar fixed window), chosen by ADF **on the research block only**. HMM fitted by Baum-Welch **on
research only** and read **FILTERED** — `STUDY_V27_HMM` measured a fit-on-all + smoothed decode at
locked PF 1.351 against the causal version of the same model at 0.973, on nearly identical trade
counts, so the leak is invisible in the count. Filtered and smoothed labels agree on **96.8%** of
bars here, which is exactly why it is easy to miss.

**Truncation audit: 0 mismatches over 1,020 comparisons on 20 probe bars.**

## 1 — Base rates: does each feature bind at all?

Four indicator families have died on this branch by being the breakout restated (RSI 94.7%, Aroon
100.0%, MACD 99.8%, MFI 91.7%). Here **2 of 51 pass more than 95% of signal bars** — `struct.excess`
(by construction) and `struct.pos_in_ch` — and 6 are inert. The pool genuinely binds.

## 2 — Predictive power, each against its own shuffled twin

**9 of 51 clear p ≤ 0.05 against 2.6 expected by chance.**

| feature | family | IC | twin \|IC\| p95 | p |
| --- | --- | --- | --- | --- |
| `mom.roc240` | mom | **+0.1870** | 0.1080 | 0.000 |
| `struct.range_atr` | struct | −0.1471 | 0.1103 | 0.000 |
| `ffd.cvd_z` | ffd | −0.1542 | 0.1143 | 0.020 |
| `trend.slope200` | trend | +0.1339 | 0.1025 | 0.020 |
| `volu.trend20` | volu | −0.1456 | 0.1239 | 0.020 |
| `vol.atr_pct` | vol | −0.1668 | 0.1570 | 0.040 |
| `regime.hmm_bear` | regime | −0.1448 | 0.1418 | 0.040 |

Every family produced at least one hit. Note the **fracdiff z-scores are both negative** — a high
fractionally-differenced price predicts a worse event — which is the twelfth independent route to
mean reversion on this branch.

## 3 — Redundancy, measured on the signal bars

A feature only ever acts where the base fires, so correlation is measured **on the 225 signal bars**,
not on all 70,685 (`STUDY_V40` found two exact duplicates in this branch's own pool that way).

**0 exact duplicates.** The most redundant pairs are `volu.vs_ma50` / `volu.z50` at 0.974,
`trend.d_ema200` / `trend.slope200` at 0.950, and `vol.rv96` / `regime.hmm_side` at **0.945** — the
HMM's sideways state is very nearly realised volatility, which is worth knowing before crediting the
Markov apparatus with anything.

**Family-first selection** at |ρ| ≤ 0.65 (family first, because five picks that all passed a
correlation ceiling were once all volatility level) gives **10 features**, worst pairwise |ρ| 0.634.

## 4 — Stability

| test | passing |
| --- | --- |
| sign holds across both halves of research | 31 of 51 |
| sign holds across all three volatility regimes | 22 of 51 |
| **both** | **18 of 51** |

Chance for a null feature is about 0.5 × 0.25 ≈ 12.5%, so 18 against ~6.4 expected is meaningfully
above noise. **8 of the 10 selected features are stable**; `struct.range_atr` and `volu.z50` flip
sign in the mid-volatility regime and are dropped. **Kept: 8.**

## 5 — Gate 2

Purged, embargoed 5-fold inside research. Objective is the event's own **return**, not win/lose —
`STUDY_V28`/`V32` measured what a win/lose objective does to a breakout system (raises win rate,
cuts p90 of R, which is the tail it earns in).

| model | OOF IC | shuffled twin |
| --- | --- | --- |
| ridge | +0.0559 | −0.1332 |
| logit | −0.0359 | −0.2037 |
| **random forest** | **+0.1637** | −0.0460 |
| LightGBM | +0.1517 | +0.0157 |

**4 of 20 declared cells clear both nulls at p ≤ 0.10:**

| model | keep | n | base | filtered | uplift | bootstrap p | random-filter p |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **rf** | **40%** | 90 | 0.0697 | 0.1798 | **+0.1101** | **0.006** | **0.007** |
| lgbm | 40% | 90 | 0.0697 | 0.1562 | +0.0865 | 0.017 | 0.027 |
| lgbm | 50% | 113 | 0.0697 | 0.1227 | +0.0530 | 0.042 | 0.050 |
| ridge | 80% | 180 | 0.0697 | 0.0905 | +0.0208 | 0.091 | 0.097 |

**Drop-one: all 8 features contribute.** Removing any one lowers the uplift — `mom.roc240` by
**−0.150**, `ffd.cvd_z` by −0.045, `vol.atr_pct` by −0.028. None is decoration with a correlation.

## 6 — One locked read

Threshold taken from the research score distribution, model refitted once on all of research.

| arm | n | %/event | PF | total % |
| --- | --- | --- | --- | --- |
| locked, unfiltered | 125 | 0.1022 | 1.862 | 12.78 |
| **locked + the meta filter** | 56 | **0.1560** | **2.707** | 8.74 |

**Uplift +0.0538 %/event — and a random filter of the same size gives p 0.145.** It does not clear
out of sample. Three things stay attached:

- **It kept 45% against the 40% it was set for**, so the score *is* calibrated across the split —
  unlike `STUDY_AUTOBNN`, where a research threshold kept 105 of 105 locked events and was therefore
  meaningless.
- **Total return falls 12.78% → 8.74%**, because the filter removes 55% of the trades. It buys ratio
  with count, which is the same trade-off `STUDY_V61` recorded for the CVD gate itself.
- **p90 of R in the kept set is below baseline for all four models** (0.68–0.71 against 0.72). Even
  with a return objective the tail is being trimmed slightly — worth watching, not yet a problem.

## Deflation

136 counted looks (51 features screened, 51 IC tests, 4 models, 20 keep-fractions, 8 drop-one runs,
2 primaries); 68 effective at ρ 0.5.

**Deflated Sharpe 0.750** against an expected best-of-null of 0.218. **White's reality check
p 0.011 — PASS.** `var_trials` is the variance of the 51 feature ICs, which is the population the
screen actually searched; the same input estimated two other ways on earlier studies gave 0.571 and
0.9919, both wrong, so stating what it is measured over is the point.

## What ships, and in what form

A random forest cannot go into Pine. Two forms can, and **both were measured before the script was
written**, so the header numbers are the script's and not the forest's.

**RIDGE SCORE — the only portable form positive on both blocks.** Standardise each feature with its
research mean and sd, multiply by a fixed coefficient, add:

| keep | research %/ev | PF | locked n | locked %/ev | PF | vs a random filter |
| --- | --- | --- | --- | --- | --- | --- |
| 70% | 0.1140 | 1.967 | 91 | 0.1267 | 2.057 | p 0.187 |
| 60% | 0.1391 | 2.216 | 82 | 0.1266 | 2.008 | p 0.257 |
| 50% | 0.1096 | 1.924 | 70 | 0.1281 | 1.977 | p 0.285 |
| 40% | 0.1480 | 2.332 | 61 | 0.1233 | 1.886 | p 0.334 |

against a base of research 0.0697 / PF 1.546 and locked 0.1022 / PF 1.862. Positive everywhere,
significant nowhere.

**COUNT 0–8 — monotone on research and it INVERTS on locked.** Spearman +0.667 across the rungs on
research; every locked rung falls *below* the unfiltered base:

| T | research %/ev | PF | p | locked %/ev | PF | p |
| --- | --- | --- | --- | --- | --- | --- |
| ≥3 | 0.0914 | 1.836 | 0.075 | 0.0889 | 1.785 | 0.746 |
| ≥5 | 0.1078 | 2.450 | 0.190 | 0.0547 | 1.591 | 0.836 |
| ≥6 | 0.1228 | 2.867 | 0.216 | 0.0263 | 1.323 | 0.806 |

It ships **visible but not recommended**, so the inversion can be seen rather than described.

**Three of the eight ridge coefficients have the opposite sign to their univariate IC** —
`vol.atr_pct` (IC −0.167, coef +0.035), `regime.hmm_side` (+0.141, −0.038), `trend.er60` (+0.119,
−0.012). That is multicollinearity exploited conditionally and it is the least stable part of the
model; the script therefore also exposes each feature as a standalone univariate switch.

## Parity — the script's feature math diffed against the research

`research/v61feat/feat_parity.py`. Two features are not ordinary indicators and could silently
differ:

| check | result |
| --- | --- |
| fracdiff weights (Pine recursion vs numpy) | max diff **0.000e+00** on all 64 |
| FFD series, bar 300 onward | max diff **8.9e-15**, correlation **1.000000000000** |
| HMM filtered posterior, matched ddof | max diff **1.0e-06**, correlation **1.0000000000** |
| HMM as `ta.stdev` actually computes it | correlation 0.9986 — the residual is the ddof convention alone |
| the six ordinary features | max diff **0.000e+00**, correlation 1.0 on all six |
| ridge score on the 350 events | correlation **0.99990**; take/skip agrees on **99.4–99.7%** |

Two conventions are recorded rather than hidden. Pine's `ta.stdev` is population (ddof 0) where
pandas is sample (ddof 1) — a factor of 1.0052 at n=96 that flows into the HMM's second observation
channel and into `f_cvdZ`, and changes no decision. And the **research shifted the CVD by a
full-sample minimum before the log**; that minimum sits at bar 177, before any event, so it never
binds — but it is not causal by construction, so **the script uses an expanding minimum instead**.
The FFD warm-up correlation of 0.51 over all bars is entirely those first 240 bars and no event
lives there.

## Verdict

**Research: the meta layer works.** Gate 1 clean, base rates clean, 9 hits against 2.6 expected,
0 duplicates, 18 stable against ~6.4 expected, models beating their shuffled twins, Gate 2 clearing
both nulls, every kept feature contributing incrementally, DSR and reality check both passing.

**Locked: it does not clear.** p 0.145 against a random filter on 56 events, and it costs a third of
the total return. That is a directionally correct, underpowered read — not a result.

**Ship nothing yet.** What would settle it is more events: 125 locked events is too few to separate
a +0.05 %/event uplift from noise. The primary generates about 120 trades a year at 15 minutes, so
another year of forward data roughly doubles the locked sample. Nothing here needs re-searching.

**Do not re-run:** the 43 features that failed the screen, and any win/lose meta objective on this
base — both are recorded as tested.
