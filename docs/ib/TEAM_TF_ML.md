# TEAM_TF_ML — feature engineering and a model ladder on the 09:00-range meta layer, timeframe as a parameter

Workstream: the user's TradingView configuration (`na_live.TV`, unchanged) on `US30_30s`, resampled to
30s / 1m / 2m / 3m / 4m / 5m / 15m. Question asked: can a meta layer take this system to PF >= 1.50
on each timeframe? Code `research/nineam/tfml/` (`tfcore.py` features + unlocked labeller + audit,
`tfmodels.py` folds/weights/ladder, `run_t0..t5.py`), CSVs and logs beside it.

**Answer, before the tables: no timeframe supports it resolvably.** The primary fails Gate 1 on every
timeframe's research half, so no meta layer is eligible anywhere; the ladder was run anyway (as asked)
and Gate 2 clears **0 of 14** cells on either null with **0 of 14** uplifts outside their own MDE.
The binding constraint is arithmetic, and it is stated first because it was computable first.

**Label caveat for every 30s number below:** they are the **14-bar research reading** of the
fresh-cross reach (`cross_min=7` / 0.5 min). The shipped Pine clamps `tfMin = max(1, seconds/60)`,
so TradingView runs **7 bars = 3.5 minutes** on a 30s chart (86.0% entry match against the user's
export vs 70.4%). One Gate-1 row at that reading is in §1; nothing else was re-run. At 1m+ the clamp
is a no-op.

## 0. Power first

92 tradeable sessions (the 09:00-09:05 range exists only from 2026-04-30); research half = first 46
sessions (to 2026-07-14), holdout = last 46. Volume is non-zero on all 92 (corr(volume, range) +0.700).

| tf | locked trades | gated signals | ungated breaks (unlocked labels) | locked %/trade | PF | MDE (locked) |
|---|---|---|---|---|---|---|
| 30s | 54 | 56 | 161 | +0.0250 | 1.601 | 0.0523 (0.48x) |
| 1m | 24 | 28 | 161 | -0.0261 | 0.644 | 0.0841 |
| 2m | 22 | 27 | 160 | -0.0318 | 0.530 | 0.0807 |
| 3m | 11 | 13 | 161 | -0.0094 | 0.846 | 0.1275 |
| 4m | 15 | 16 | 159 | -0.0340 | 0.527 | 0.1001 |
| 5m | 16 | 18 | 153 | -0.0161 | 0.749 | 0.1026 |
| 15m | 8 | 10 | 145 | +0.1021 | 3.697 | 0.1579 |

The ungated universe walked unlocked is negative on every timeframe (PF 0.69-0.98). So the meta layer
is being asked to find a subset of a losing universe, not to sharpen a winning one.

**MDE of a meta-layer uplift** (a veto keeping k of n moves the mean by a random-subset sd
`sd*sqrt((1-k)/(k n))` under the null; t 2.802), on the gated primary's RESEARCH half:

| tf | keep 0.7 | keep 0.5 |
|---|---|---|
| 30s | 0.0479 | 0.0732 |
| 1m | 0.0757 | 0.1156 |
| 2m | 0.0618 | 0.0943 |
| 3m | 0.1063 | 0.1625 |
| 4m | 0.0906 | 0.1384 |
| 5m | 0.0882 | 0.1347 |
| 15m | 0.1548 | 0.2364 |

The 30s primary's WHOLE per-trade edge is +0.0250. The smallest resolvable uplift on research is
1.9x (keep 0.7) to 2.9x (keep 0.5) the entire edge of the thing being filtered.

**Overlap across timeframes.** They are views of one set of breaks: Jaccard on (session, side) break
events **0.90-1.00** for every pair, and the break lands in the same bar-time window 97.9-100% of the
time. What differs is the LABEL (entry one bar later, and the 13x48 opposite-cross exit fires on
very different clocks): same-break label correlation +0.81 (30s/1m), +0.63 (30s/2m), +0.20 (30s/4m),
-0.00 (30s/5m), -0.06 (30s/15m); mean over pairs **rho +0.293**. Gated sets overlap far less
(Jaccard on gated sessions 0.05-0.59) because the cross gate reads different EMAs at each bar size.

Effective n: 1,100 nominal ungated events pooled = **161 distinct (session, side) breaks on 92
sessions**; sum_k k/(1+(k-1)rho) = **405.6** (an upper bound — the 92 sessions, 46 in research, are
the real ceiling on anything a feature measures at session level). Gated: 168 nominal, 89 distinct,
122 effective. Pooled uplift MDE at n_eff 406: 0.0123 (keep 0.7) / 0.0188 (keep 0.5) on all data,
0.0174 / 0.0266 on the research half — resolvable only for effects on the UNGATED universe, whose
mean is -0.0008 to -0.0236.

## 1. Gate 1 per timeframe (matched random entry, 400 draws, sorted, same lock)

| tf | block | n | %/trade | PF | target-hit | null median | p | MDE | x MDE | boot P(<=0) |
|---|---|---|---|---|---|---|---|---|---|---|
| 30s | ALL | 54 | +0.0250 | 1.601 | 0.352 | +0.0001 | 0.063 | 0.0523 | 0.48 | 0.101 |
| 30s | research | 29 | +0.0201 | 1.510 | 0.310 | +0.0013 | **0.253** | 0.0696 | 0.29 | 0.213 |
| 30s | holdout | 25 | +0.0305 | 1.696 | 0.400 | +0.0013 | 0.080 | 0.0806 | 0.38 | 0.149 |
| 1m | research | 12 | -0.0194 | 0.711 | 0.250 | -0.0196 | 0.500 | 0.1192 | — | 0.673 |
| 2m | research | 13 | +0.0156 | 1.348 | 0.308 | -0.0227 | 0.113 | 0.1105 | 0.14 | 0.335 |
| 3m | research | 2 | — | — | — | — | — | — | — | — |
| 4m | research | 6 | +0.0118 | 1.578 | 0.167 | +0.0282 | 0.570 | 0.1097 | 0.11 | 0.432 |
| 5m | research | 10 | -0.0060 | 0.905 | 0.300 | -0.0438 | 0.238 | 0.1412 | — | 0.601 |
| 15m | research | 3 | -0.0387 | 0.617 | 0.333 | -0.0073 | 0.678 | 0.3287 | — | 0.740 |
| 15m | holdout | 5 | +0.1866 | inf | 1.000 | +0.1362 | 0.098 | — | — | — |

(ALL / holdout rows for 1m-5m in `t1_gate1.csv`: every one negative and p 0.47-0.99.)
**0 of 7 timeframes pass Gate 1 on research.** The 15m "PF 3.70" is 8 trades, 3 of them in research
at PF 0.62; its holdout 5/5 target hits give a degenerate sd (MDE 0.0025 is an artefact, not power).

**30s at the TradingView reading (7 bars = 3.5 min, `run_t1b.py`):** ALL 39 trades +0.0593 %/trade
PF 3.149, matched-entry p **0.013**, 0.996x its MDE, day-block bootstrap P(<=0) 0.004; research 20
trades PF 3.280 p **0.100** (fails Gate 1 at 0.05), holdout 19 trades PF 3.068 p 0.008. Better than
the 14-bar reading on every row, not chosen on performance (reconciled to the export) — but still
fails research, still at 1.0x MDE on all data, and the meta layer below was NOT re-run on it.

## 2. Features (29 kept of 30), causal at the signal bar

Families: `rng.` width (ATR, % of price), break distance (ATR, %), extreme beyond level, minutes since
range end; `mom.` EMA13-48 gap, cross age and opposite-cross age in MINUTES, 5-minute slope, the
gate flag, 30-min return, side; `vol.` Parkinson and realised vol over 30 minutes from the 30s base,
ATR and 30-minute mean range against a CAUSAL time-of-day baseline (prior sessions, same minute),
ATR % of price; `pre.` overnight gap to the 09:00 open, 08:00-09:00 direction and range (activity
count dropped: modal share 0.975); `vlm.` signal-bar volume and 10-minute volume against a causal
time-of-day baseline (real only from 2026-04-27, so 3.6-6.5% NaN in the first sessions); `flow.`
close position in bar, CVD proxy (each 30s sub-bar's volume signed by its own direction) over 10 and
30 minutes and over the signal bar's own sub-bars, up-bar share; `tf.min`.

- **Truncation audit: 0 mismatches of 1,260** (6 probes x 30 features x 7 timeframes; frames cut at
  the signal bar's END, ATR recomputed from the truncated TR).
- **Base rates on the gated primary's own bars:** `mom.gate` 100% (it IS the gate), `mom.gap` > 0 on
  **97.0%** (the loose fresh-cross gate restated as the EMA state — the ninth trigger-restated catch
  here), `pre.h8act` modal 98.8% (dropped). Nothing else flagged; `flow.cvd10` > 0 on 83.3% of gated
  bars against 67.3% of all breaks, `mom.ret30` 92.3% vs 79.3%.
- **Correlation collapse on the signal bars:** no exact duplicate (max |rho| 0.948, park30 vs rv30;
  break-pct vs ret30 0.909; ATR% vs tf.min 0.812).

## 3. Ladder — research half, OOF Spearman IC vs %-of-price, 5 chronological session folds, 1-session embargo

547 pooled events (7 TFs) / 70-80 per TF, uniqueness weights x 1/k for a break seen at k timeframes.
Each model beside a shuffled twin (5 permutations; twin mean and sd shown for the pooled column).

| model | pooled IC | pooled twin (sd) | 30s | 1m | 2m | 3m | 4m | 5m | 15m |
|---|---|---|---|---|---|---|---|---|---|
| ridge | +0.009 | -0.025 (0.064) | +0.287 | +0.071 | -0.015 | -0.264 | -0.006 | +0.227 | +0.361 |
| rf | **+0.077** | -0.048 (0.047) | +0.234 | -0.034 | -0.051 | -0.179 | +0.142 | +0.255 | +0.117 |
| lgbm | +0.037 | -0.019 (0.046) | +0.233 | +0.148 | -0.046 | -0.169 | -0.011 | +0.251 | +0.189 |
| xgb d3 | +0.055 | -0.021 (0.055) | +0.244 | +0.167 | +0.054 | -0.120 | -0.032 | +0.248 | +0.206 |
| mlp 2x32 | +0.022 | -0.028 (0.056) | +0.190 | +0.135 | +0.200 | +0.202 | +0.129 | +0.054 | +0.170 |
| mlp 2x64 | +0.065 | -0.009 (0.050) | -0.191 | -0.138 | +0.059 | -0.046 | -0.105 | +0.165 | -0.022 |
| mlp 4x128 | +0.029 | -0.036 (0.043) | +0.092 | +0.052 | +0.060 | +0.090 | -0.082 | +0.140 | -0.024 |

- **Twin mean >= real IC in 10 of 56 cells (18%)** — better than S3 (58%) and VWANOM (71%). But the
  noise floor is wide: twin IC sd median **0.107** per-TF (up to 0.27 at 5m) and 0.050 pooled, and
  the per-TF ICs flip sign across neighbouring timeframes (ridge +0.287 at 30s, -0.264 at 3m, +0.361
  at 15m). The best pooled IC, rf +0.077, is **1.6 twin-sd** above zero, one cell of 56.
- Capacity is inert again: mlp 2x32 / 2x64 / 4x128 = +0.022 / +0.065 / +0.029 pooled, no gradient.
- The pooled models' OOF IC broken out by timeframe is positive at **15m for all 7 models
  (+0.13 to +0.31)** and near zero or negative at 2m/3m — on 70 events per TF, i.e. inside a twin sd of
  ~0.17, and the models share features so these are not 7 confirmations.
- Pre-declared Gate-2 score: the best REAL pooled IC = **rf**.

**Family ablation (pooled, rf, 5 seeds; ALL = +0.0855):**

| family | keep-one (k) | drop-one | drop delta |
|---|---|---|---|
| rng | **+0.1717** (6) | -0.0244 | -0.110 |
| vol | +0.0518 (5) | +0.0781 | -0.007 |
| mom | +0.0044 (7) | +0.0703 | -0.015 |
| flow | -0.0045 (5) | +0.0750 | -0.011 |
| tf | -0.0804 (1) | +0.0851 | -0.001 |
| pre | -0.0745 (3) | **+0.1507** | +0.065 |
| vlm | -0.1456 (2) | +0.0940 | +0.008 |

STUDY_V66's shape again: the SIX range-geometry features alone (+0.172) double all 29 (+0.086); `pre`
and `vlm` are subtractive; `tf.min` carries nothing (dropping it -0.0005). Keep-one found it,
drop-one would have called only `pre` harmful. Not acted on (the Gate-2 model was declared first),
and one ablation on 46 sessions is a lead, not a result.

## 4. Gate 2 per timeframe — rf OOF score as a VETO on the gated primary, re-simulated end to end

Research half; random-gate null 400 draws (same keep count, re-simulated); paired day-block bootstrap
(sessions resampled with base and kept trades attached); uplift MDE = 2.802 x the null's sd.

| tf | keep | base n | PF | hit | kept n | PF | hit | uplift | p gate | p boot | MDE uplift | twin-score uplift |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 30s | 0.7 | 29 | 1.510 | 0.310 | 21 | 1.651 | 0.286 | +0.0015 | 0.533 | 0.470 | 0.0504 | -0.0036 |
| 30s | 0.5 | 29 | 1.510 | 0.310 | 15 | 1.105 | 0.200 | -0.0164 | 0.785 | 0.745 | 0.0708 | +0.0167 |
| 1m | 0.7 | 12 | 0.711 | 0.250 | 9 | 0.726 | 0.222 | +0.0031 | 0.535 | 0.481 | 0.0847 | +0.0161 |
| 1m | 0.5 | 12 | 0.711 | 0.250 | 6 | 0.005 | 0.000 | -0.0693 | 0.970 | 0.958 | 0.1290 | +0.0327 |
| 2m | 0.7 | 13 | 1.348 | 0.308 | 9 | 0.706 | 0.222 | -0.0340 | 0.868 | 0.926 | 0.0677 | -0.0084 |
| 2m | 0.5 | 13 | 1.348 | 0.308 | 6 | 0.572 | 0.167 | -0.0407 | 0.820 | 0.852 | 0.1017 | -0.0122 |
| 3m | 0.7/0.5 | 2 | 0.928 | 0.500 | 1 | 0.000 | 0.000 | -0.1986 | 1.000 | — | 0.557 | -0.1986 |
| 4m | 0.7 | 6 | 1.578 | 0.167 | 4 | 0.023 | 0.000 | -0.0418 | 0.883 | 0.981 | 0.0767 | -0.0418 |
| 4m | 0.5 | 6 | 1.578 | 0.167 | 3 | 0.012 | 0.000 | -0.0523 | 0.905 | 0.980 | 0.1077 | -0.0523 |
| 5m | 0.7 | 10 | 0.905 | 0.300 | 7 | 0.426 | 0.143 | -0.0303 | 0.868 | 0.759 | 0.0866 | -0.0034 |
| 5m | 0.5 | 10 | 0.905 | 0.300 | 5 | 0.420 | 0.200 | -0.0454 | 0.870 | 0.769 | 0.1245 | -0.0454 |
| 15m | 0.7 | 3 | 0.617 | 0.333 | 2 | 1.952 | 0.500 | +0.0843 | 0.245 | 0.288 | 0.2194 | +0.0843 |
| 15m | 0.5 | 3 | 0.617 | 0.333 | 2 | 1.952 | 0.500 | +0.0843 | 0.328 | 0.288 | 0.3701 | +0.2257 |

**0 of 14 cells clear either null at 0.05; 0 of 14 uplifts exceed their MDE; the real score beats
its own shuffled-twin score in 2 of 14.** 9 of 14 uplifts are NEGATIVE. The score ranks events
(pooled IC +0.077) and still subtracts when applied as a veto to the locked primary — the released
position lock and 3-29 research trades per timeframe leave nothing for a ranking to act on.

**A win-rate illusion in the only cell with a sample:** 30s keep 0.5 raises the WIN RATE 0.690 ->
0.800 while PF falls 1.510 -> 1.105 and the target-hit rate falls 0.310 -> 0.200 — the veto keeps
breakeven scratches (+3 - 2.29 = +0.71 points, booked as wins). p90 of R is degenerate here (the
100-point target caps winners), so target-hit rate is printed instead.

## 5. One read of the holdout (second 46 sessions)

Declared rule (in `run_t4.py`, before the table): lowest research random-gate p, ties by uplift.
It selected **15m keep 0.7 — a cell with 3 research trades**. That rule should have carried a trade
floor; it did not, and the cell was read as declared rather than swapped after seeing the table.
rf refitted on all 547 research events, threshold = the research OOF cut (-0.01052):

- holdout gated signals 6, **kept 2 = 0.333 against a target of 0.70 — not calibrated**;
- base 5 trades, all 5 target hits (PF inf, +0.1866 %/trade); kept 2, both target hits (+0.1857);
- **uplift -0.0009**, random-gate p 0.508, bootstrap P(<=0) 0.757, uplift MDE 0.243.

The holdout says nothing either way; it was spent on 6 events.

## 6. Deflation and the PF-1.5 arithmetic

Looks counted: Gate 1 21 + ladder 56 + ablation 15 + Gate 2 14 + twin-score reference 14 + holdout 1
= **121**. E[max t | noise] over 121 looks = **2.597** (detection needs 2.802). Deflated Sharpe of the
chosen cell: per-trade SR 0.228 against SR0 1.006 (sd of per-trade SR across 12 Gate-2 arms 0.387)
-> **DSR 0.218, FAIL** — and on 2 research trades the statistic is itself degenerate.

PF-1.5 arithmetic on each primary's own realised win/loss sizes, w* = 1.5L/(W+1.5L):

| tf | n | win | avg win % | avg loss % | PF | win needed for PF 1.5 | lift needed | best Gate-2 kept win / PF |
|---|---|---|---|---|---|---|---|---|
| 30s | 54 | 0.685 | 0.097 | 0.132 | 1.601 | 0.671 | -0.014 | 0.800 / 1.651 |
| 1m | 24 | 0.500 | 0.094 | 0.146 | 0.644 | 0.700 | +0.200 | 0.556 / 0.726 |
| 2m | 22 | 0.500 | 0.072 | 0.135 | 0.530 | 0.739 | +0.239 | 0.667 / 0.706 |
| 3m | 11 | 0.636 | 0.081 | 0.168 | 0.846 | 0.756 | +0.120 | — |
| 4m | 15 | 0.467 | 0.081 | 0.135 | 0.527 | 0.714 | +0.247 | 0.500 / 0.023 |
| 5m | 16 | 0.563 | 0.085 | 0.146 | 0.749 | 0.720 | +0.158 | 0.571 / 0.426 |
| 15m | 8 | 0.750 | 0.187 | 0.152 | 3.697 | 0.549 | -0.201 | 0.500 / 1.952 |

At 1m-5m PF 1.5 needs **+12 to +25 points of win rate** at the realised payoff; no Gate-2 cell
delivered a positive lift at those timeframes. At 30s and 15m the point estimate already exceeds 1.5
with no meta layer — on 54 and 8 trades, inside the MDE, failing Gate 1 on research.

## Per-timeframe answer: does a meta layer reach PF >= 1.5 resolvably?

- **30s:** No. The primary is PF 1.60 unfiltered (14-bar reading; 3.15 at TradingView's 7-bar reading)
  without any meta layer, fails Gate 1 on research (p 0.253 / 0.100), and the best veto moves it
  +0.0015 against an MDE of 0.0504. The 7-bar primary sits at 0.996x its own MDE on 39 trades over
  all 92 sessions (0.63x on the 20 research trades) — resolving THAT is the forward test's job, and
  the meta layer was not re-run on it.
- **1m, 2m, 4m, 5m:** No. The primary loses (PF 0.53-0.75), needs +16 to +25 points of win rate, and
  every veto made it worse (uplift -0.030 to -0.069 at keep 0.5).
- **3m:** Not measurable: 2 research trades.
- **15m:** No. PF 3.70 on 8 trades (3 research at PF 0.62); the holdout read kept 2 of 6 against a
  0.70 target, uplift -0.0009.

What the study DOES leave: range geometry (`rng.`, 6 features) is the only family that carries on its
own (keep-one IC +0.172 vs +0.086 for all 29); the overnight/pre-open and volume families subtract;
`tf.min` carries nothing; capacity is inert. What would move it is EVENTS — 92 sessions is the
ceiling on every timeframe, and pooling timeframes multiplies rows (1,100) without multiplying breaks
(161) or sessions (92).

**Bugs / defects hit:** (1) my first base-rate flag counted magnitude features (widths, vol) as
"> 0 on 100%" — positive by construction, not information; fixed to flag directional features on
sign and magnitudes on modal share only. (2) the bootstrap returned p 0.000 when a veto kept a single
trade; now NaN below 2 kept trades. (3) the holdout-cell rule lacked a trade floor (above).
(4) `na_core.boot_edge` without `_day` is a per-trade bootstrap (coordinator's note); every bootstrap
here passes `_day=eday` or uses the paired session bootstrap in `tfcore.day_boot_uplift`.
