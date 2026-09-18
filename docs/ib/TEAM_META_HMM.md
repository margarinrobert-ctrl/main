# The meta layer on the §12 US30 primary: an HMM, fracdiff and the advanced quant families

Workstream: build the META LAYER on `STUDY_US30_SCALP_0711` §12's derived rule and find out whether
it raises profit factor by an amount **the sample can actually resolve**. The primary was fixed and
untouched: `research/us30scalp/s10lib.py` — Donchian 20 long, US30 07:00–11:00 New York, flat at the
11:00 open, 50-point stop / 150-point target. Code `research/us30meta/`, logs
`research/us30meta/logs/`, results `results/us30meta/`.

**Verdict in one line: the meta layer does not clear anything, and the interesting part is HOW it
fails — a fixed-width fractional difference is not level-free, its truncated weight sum drifts the
score by 3.2 research standard deviations onto a different provider's feed, and the "4 of 4 positive
uplifts out of sample" that reading produces is entirely the threshold silently becoming five times
more selective. Fix the selectivity and 0 of 4 survive.**

---

## 0. Architecture, and what was declared before anything ran

Phase 0 is in `m_core.py`'s docstring. The §12 rule names no counterparty — it was DERIVED from
three component readings (ADX inverted, EMA alignment carrying, ATR at chance), not from a
mechanism — so it carries the full deflation burden and no story protects it. What the meta layer
is allowed to claim is narrower: that some causal state at the SIGNAL BAR separates the breakouts
worth taking from the ones that are not.

**Two event streams, answering different questions.** LOCKED is what one account takes — one live
position, later signals swallowed — and is the ONLY stream Gate 1 and Gate 2 score. UNLOCKED labels
every eligible signal bar under the identical geometry with no position lock, and is used for
TRAINING ONLY: 2,240 research rows against 400 locked ones. `STUDY_S3_NEURAL_NET` established the
principle (the lock decides which events one account can act on, not which have a well-defined
outcome) and `STUDY_CONFORMAL` reached it from the other side. Every reported number is a locked
number.

**The arm the verdict is written about.** The coordinator's measurement in `research/us30rate/`
(§14–15) landed mid-study: over six channel rungs × three blocks `+adx<=20` beats its own
same-selectivity veto in 15 of 18 cells but only **3 of 6 on the reserved forward feed** (median
p 0.617), while the EMA condition is 18 of 18 including 6/6 forward — and the stack decomposes, so
`ema34>ema89` alone carries it. `+ema34>89` was therefore ADDED here (in `m_core`, not in the fixed
primary file) and is the arm the verdict is about; `+adx<=20` is reported beside it throughout,
because a meta layer measured on an arm that fails the reserved block inherits that failure.

---

## 1. Gate 1 — the primary alone, before a single feature exists

Research block, against a matched random ENTRY: same count, drawn from every eligible in-window
bar, **sorted** so the position lock rejects the same share (`STUDY_V59`), identical geometry,
exits, cost and flatten.

| arm | n | pts/trade | PF | sd | **MDE** | inside its MDE | control p | bootstrap p |
|---|---|---|---|---|---|---|---|---|
| base | 1,054 | +0.956 | 1.034 | 68.7 | 5.93 | **YES** | 0.083 | 0.311 |
| **+adx<=20** | 400 | **+6.260** | 1.236 | 73.2 | 10.26 | **YES** | **0.005** | **0.037** |
| +ema align | 668 | +2.794 | 1.106 | 67.4 | 7.30 | **YES** | 0.023 | 0.149 |
| **+ema34>89** | 697 | +2.512 | 1.094 | 67.6 | 7.17 | **YES** | 0.060 | 0.164 |
| +both | 227 | +6.613 | 1.253 | 71.3 | 13.26 | **YES** | 0.030 | 0.070 |
| conventional (`adx>=25`) | 368 | +1.419 | 1.054 | 65.4 | 9.56 | **YES** | 0.205 | 0.364 |

Reproduces §13 to the third decimal on every arm it shares. Three arms clear the entry null;
**all six are inside their own MDE**, which is §12's finding restated and the constraint the rest of
this study is written against. `+ema34>89` is the weaker arm IN SAMPLE (control p 0.060) — which is
the shape the coordinator's cross-block work predicts, since `+adx<=20` is the arm fitted at channel
20 and the EMA condition is the one that survives elsewhere.

---

## 2. Features: 55 declared, 8 inert on the trigger's own bars, 9 collapsed as duplicates

Seven declared families (`m_feat.py`): `vol` (level, ratio, Parkinson, Garman-Klass, vol-of-vol, and
the same quantities against a **causal time-of-day baseline** — never a trailing mean, per
`STUDY_VWAP_STOCH_ATR`), `hmm` (filtered posteriors only), `ffd`, `str`, `mom`, `par`
(participation against the same causal baseline), `ctx` (the session clock, declared separately and
flagged because inside a fixed window it is near-categorical).

**TRUNCATION AUDIT: 0 mismatches of 1,100 value comparisons over 20 probes** — every feature
recomputed on history ENDING at bar i and required to match the full-run value at i.

**Base rates on the trigger's own bars.** For a continuous feature the analogue of a >95% pass rate
is the share of signal bars above the POPULATION median. Eight of 55 are inert and were removed
before any P&L:

| feature | share above population median | what it is |
|---|---|---|
| `mom.roc4` | **1.0000** | a Donchian break IS a 4-bar advance |
| `str.pos_in_ch` | **1.0000** | the break bar is at the top of its own channel, by construction |
| `str.excess` | **1.0000** | same, expressed in ATR |
| `mom.roc16` | 0.9995 | |
| `mom.rsi14` | **0.9963** | RSI restated for the **fifth** time on this branch (94.7% in `STUDY_V16`) |
| `mom.di_diff` | 0.9765 | `+DI > -DI` again — the team measured 97.8% on this exact base |
| `ffd.z250` | 0.9691 | |
| `mom.d_ema50` | 0.9604 | |

**And the pool duplicated — my own, caught by the check.** `par.z_tod` vs `par.vs_tod` reads
**rho +1.0000** on the signal bars: one is `log1p(v) − log1p(baseline)` and the other is
`v / baseline`, a monotone transform, so Spearman cannot tell them apart. That is the ninth
pool-duplication catch on this branch and the first where the duplicate was written in the same
file, two lines apart. Also collapsed at |rho| ≥ 0.90: `hmm.entropy`/`hmm.conf` (−0.9998),
`vol.garman_klass`/`vol.parkinson` (+0.9977), `hmm.edge`/`hmm.fwd12` (+0.9942),
`str.close_pos`/`str.upper_wick` (−0.9842), **`hmm.side`/`vol.rv96` (−0.9693)**.

55 declared → 47 after inert → **38 after collapsing**.

---

## 3. The HMM: causal, and then interrogated

Hand-rolled Baum-Welch (`research/v27/v27hmm.py`), K=3, fitted on the **research block only**, read
through the **FILTERED** posterior only. States after ordering by drift, with self-transitions:
bear μ −0.00000 at rolling vol 0.107 (0.9735), sideways μ +0.00154 at **0.0504** (0.9864), bull
μ +0.00404 at 0.2439 (0.9574). The persistent state is the calm one, as on NQ.

**3.1 Filtered vs smoothed — 0.9682 on all bars, 0.9626 on the signal bars.** Third instrument to
land in the branch's 96–97% band, which is exactly the regime where `STUDY_V27`'s leak is invisible.
Priced directly, as a bull-state gate on the primary at matched selectivity:

| keep | filtered (causal) PF | smoothed (LEAKY) PF | trade counts |
|---|---|---|---|
| 0.75 | 1.299 | 1.275 | 340 / 344 |
| 0.50 | 1.360 | **1.427** | 259 / 251 |
| 0.25 | 1.855 | **2.010** | 141 / 138 |

Mean advantage of the leaky decode **+0.067 PF on trade counts that move by −1.3%** — the count is
blind to it, as recorded. **But note the direction is NOT uniform**: at keep 0.75 the leaky decode
is WORSE. On 400 trades the leak is smaller than the noise, so on a sample this size the leak
diagnostic is a reason to be causal by construction, not a test you can pass.

**3.2 The HMM's states ARE volatility states, and this is the strongest measurement of it here.**
On the signal bars `hmm.side` vs `vol.rv96` reads **−0.9755**, against `STUDY_V61_FEATURES_15M`'s
0.945 and `STUDY_V67`'s −0.478. `hmm.bull` vs `vol.atr_pct` +0.8517. Mean |rho| of an HMM column to
its nearest volatility feature is 0.3818, but the two columns that carry the model's signal are the
two that are volatility.

**3.3 The Markov apparatus collapses to the state label — a third time, on the largest signal yet.**
`hmm.fwd12` (the twelve-step matrix power) takes **187,293 distinct values** and:

| set A | set B | Jaccard |
|---|---|---|
| state == bull | `hmm.bull > 0.50` | 0.9986 |
| state == bull | `hmm.edge > 0.30` | 0.9630 |
| state == bull | **`hmm.fwd12 > 0`** | **0.9524** |

with rho(`fwd12`, `edge`) = **+0.9952** on the signal bars. `STUDY_V27` measured 1.0000 on a
three-valued signal (dismissible), `STUDY_V67` 0.9757 on a 25,044-valued one, and this is 0.9524 on
a 187,293-valued one. **Matrix powers add nothing to the state label. Do not compute them again.**

**3.4 And it loses to volatility at the actual job.** Best |IC| against the label among HMM columns
**0.1166** (`hmm.side`); among volatility columns **0.1303** (`vol.garman_klass`). Ratio 0.896.
`STUDY_V67` found 0 of 32 cells where the HMM won; this is one more.

---

## 4. The model ladder — and the split between the two statistics

Objective is the POINTS EARNED, purged and embargoed folds, day-level uniqueness weights (effective
n 1,566 of 2,229), every rung beside a SHUFFLED-LABEL TWIN.

| model | real IC | twin IC | twin wins | top-30% pts | twin top-30% |
|---|---|---|---|---|---|
| ridge | **−0.0351** | +0.0075 | **YES** | −1.085 | +2.235 |
| rf | +0.0084 | −0.0535 | no | −3.510 | +1.326 |
| lgbm | +0.0227 | −0.0308 | no | −3.327 | +1.442 |
| **xgb_d3** | **+0.0505** | −0.0306 | no | +0.783 | +3.728 |
| xgb_d6 | +0.0456 | +0.0074 | no | +0.697 | +2.465 |
| mlp_2x32 | −0.0241 | +0.0059 | **YES** | −0.502 | +1.846 |
| mlp_2x64 | +0.0044 | −0.0196 | no | −0.226 | +0.836 |
| mlp_4x128 | +0.0108 | −0.0092 | no | −1.280 | +2.232 |

**The twin wins 2 of 8 on IC (25%) and 8 of 8 on the top-30% mean (100%).** Both are true and they
answer different questions: the models rank slightly better than permuted labels, and **the trades
they select earn less than the trades a permuted-label model selects, in every single cell**. The
second statistic is the one a gate is made of. `STUDY_V32` found the twin above 50% on IC and called
it a noise floor; here the noise floor is above the signal on the statistic that matters while
sitting below it on the statistic that does not.

**Capacity is inert.** MLP 2x32 / 2x64 / 4x128 read −0.0241 / +0.0044 / +0.0108 and XGBoost d3 → d6
+0.0505 → +0.0456: neither "deeper is worse" (`STUDY_V28`) nor "deeper is better", which is what a
swept architecture axis looks like when there is nothing there. **Ridge is the worst rung**, which
breaks the branch's run of six families where the linear model won — and the reason is visible in
§5: the surviving structure is not linear in the features that survive.

---

## 5. The seeded family ablation — and it does NOT say what the last five studies said

Eight seeds per arm, paired t across the same eight seeds, workhorse `xgb_d3` (the ladder's best
rung, decided in M3 before this file ran; `rf` reads +0.0096 on all 38 and an ablation run on a rung
whose own IC is near zero measures the model's bootstrap noise).

**Drop one family** (all 38 features: IC +0.0422, seed sd 0.0059):

| dropped | n left | IC | delta | paired t | |
|---|---|---|---|---|---|
| mom | 30 | +0.0474 | **+0.0051** | +1.20 | HARMFUL |
| vol | 29 | +0.0400 | −0.0023 | −0.54 | load-bearing |
| ctx | 36 | +0.0390 | −0.0032 | −1.35 | load-bearing |
| str | 29 | +0.0366 | −0.0056 | −2.35 | load-bearing |
| hmm | 34 | +0.0330 | −0.0092 | −1.87 | load-bearing |
| ffd | 36 | +0.0300 | −0.0123 | −3.57 | load-bearing |
| **par** | 34 | +0.0254 | **−0.0168** | **−6.26** | load-bearing |

Only ONE of seven families is harmful, against `STUDY_V66_DL_META`'s six of eight and
`STUDY_VP_DONCHIAN_US30`'s four. **Keep-one-family says why**, and it is the sharper table:

| family alone | n | IC |
|---|---|---|
| **par** | 4 | **+0.0791** |
| vol | 9 | +0.0132 |
| str | 9 | +0.0041 |
| ctx | 2 | −0.0107 |
| hmm | 4 | −0.0158 |
| ffd | 2 | −0.0317 |
| mom | 8 | **−0.0566** |

**Participation alone, four features, scores +0.0791 — nearly double all thirty-eight.** Greedy
forward selection over FAMILIES (seven ordered looks, not 2^38): `par` → +0.0791 (4 features),
`+ffd` → +0.0802 (6), `+hmm` → **+0.0821 (10)**, stop. Ten features beat thirty-eight at a paired
t of **+15.53**, and 28 of 38 inputs are deleted. So the branch's "feature engineering is
subtractive" finding reproduces for the sixth time — it just arrives through keep-one rather than
drop-one, because with 38 columns on 2,240 rows every family is load-bearing for a model that is
mostly fitting noise.

**And ONE feature is not enough here**, unlike V66. `vol.garman_klass` has the strongest univariate
IC in the pool (**−0.1286** on the modelled rows, −0.1303 over the full unlocked stream) and as a one-column model scores **−0.0212**: the relationship is
strong in rank and unstable across purged folds, which is also why ridge lost the ladder.

**The surviving family is the one two other studies already flagged.** `par.*` is volume against a
causal time-of-day baseline, and its sign is NEGATIVE (`par.z_tod` IC −0.1091) — more participation
than usual at the breakout, worse trade. That agrees with `STUDY_VWANOM` (`vlm.tod_ratio` −0.219
and `vol.atr_tod` −0.214 as the two strongest single features) and with
`STUDY_DIVERGENCE_CONFIRM` (volume spikes hurt longs monotonically). It is the third independent
route to the same statement.

---

## 6. Gate 2 — the VETO, re-simulated, against a same-selectivity random gate

The gate decides which BARS may open a trade, so refusing one frees the position lock and admits a
later breakout the ungated run never saw (`STUDY_AUCTION`; the two framings have disagreed twice on
this branch). The null is a random gate keeping the same NUMBER OF SIGNAL BARS, re-simulated end to
end with the lock re-applied — not a subset of realised trades, and matched on signal bars rather
than on post-lock trades because §6 of the parent study measured that handing a control the rule's
post-lock count and re-locking settles ~34% below it.

**`+ema34>89` — the arm the verdict is about:**

| keep | n | pts/trade | uplift | MDE | MDE split | PF | total | rand p | boot p |
|---|---|---|---|---|---|---|---|---|---|
| off | 697 | +2.512 | | 7.17 | | 1.094 | +1,751 | | |
| 0.70 | 540 | +1.634 | **−0.878** | 7.86 | 15.45 | 1.063 | +882 | 0.693 | 0.617 |
| 0.60 | 480 | +1.633 | −0.879 | 8.18 | 14.37 | 1.064 | +784 | 0.610 | 0.633 |
| 0.50 | 409 | +2.025 | −0.487 | 8.82 | 13.44 | 1.081 | +828 | 0.530 | 0.565 |
| 0.40 | 343 | +1.267 | −1.245 | 9.46 | 13.15 | 1.051 | +435 | 0.605 | 0.645 |
| 0.30 | 264 | +0.380 | −2.132 | 10.58 | 13.52 | 1.015 | +100 | 0.672 | 0.692 |

**Every rung subtracts.** The meta layer makes the arm the coordinator's cross-block work identifies
as the durable one strictly worse, at every selectivity.

**`+adx<=20`:**

| keep | n | pts/trade | uplift | MDE | MDE split | PF | total | rand p | boot p |
|---|---|---|---|---|---|---|---|---|---|
| off | 400 | +6.260 | | 10.26 | | 1.236 | +2,504 | | |
| **0.70** | 291 | **+9.243** | **+2.983** | 12.02 | **21.92** | **1.374** | +2,690 | **0.043** | 0.250 |
| 0.60 | 264 | +7.737 | +1.477 | 12.38 | 21.08 | 1.313 | +2,042 | 0.150 | 0.374 |
| 0.50 | 227 | +6.415 | +0.155 | 13.32 | 20.03 | 1.254 | +1,456 | 0.355 | 0.500 |
| 0.40 | 187 | +6.715 | +0.455 | 14.98 | 20.05 | 1.263 | +1,256 | 0.292 | 0.485 |
| 0.30 | 146 | +3.450 | −2.810 | 17.10 | 21.00 | 1.125 | +504 | 0.610 | 0.671 |

**0 of 10 cells clear both nulls. 0 of 10 uplifts exceed their own kept-vs-rejected MDE.** The one
cell that clears the random gate (+adx<=20 at keep 0.70, p 0.043) delivers **+2.98 points against a
resolution of 21.92** — an eighth of what the sample can see — and fails the day-block bootstrap at
0.250. And the gate raises PF in 4 of 10 cells while raising total points in **1 of 10**: the branch's
standing finding that a filter buys ratio with count, one more time.

---

## 7. The one read, and the calibration failure that explains it

Rung keep = 0.70 (best research random-gate p, a pre-declared selection rule), both arms, one read
of B_holdout and one of C_forward (`US30_ISO_15m`, a different provider, rebuilt with the FROZEN
d and HMM parameters).

| block | arm | n off | off pts | n on | **kept** | on pts | uplift | MDE split | on PF | tot off | tot on | rand p |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A research | +ema34>89 | 697 | +2.512 | 540 | 0.701 | +1.634 | −0.878 | 15.45 | 1.063 | +1,751 | +882 | 0.698 |
| A research | +adx<=20 | 400 | +6.260 | 291 | 0.730 | +9.243 | +2.983 | 21.92 | 1.374 | +2,504 | +2,690 | 0.028 |
| B holdout | +ema34>89 | 330 | +2.178 | 125 | **0.338** | +3.848 | +1.670 | 24.56 | 1.126 | +719 | +481 | 0.263 |
| B holdout | +adx<=20 | 157 | +4.596 | 57 | **0.386** | +5.870 | +1.274 | 36.65 | 1.202 | +722 | +335 | 0.427 |
| C forward | +ema34>89 | 183 | +6.546 | 42 | **0.124** | +14.970 | +8.423 | 43.86 | 1.472 | +1,198 | +629 | 0.393 |
| C forward | +adx<=20 | 76 | +6.382 | 26 | **0.188** | +15.083 | +8.701 | 61.15 | 1.469 | +485 | +392 | 0.263 |

Read naively this is encouraging: **4 of 4 out-of-sample uplifts positive**, PF 1.07→1.13, 1.15→1.20,
1.19→1.47, 1.18→1.47. It is not, and the kept-fraction column is why.

**THE THRESHOLD WAS SET TO KEEP 0.70 AND KEEPS 0.12 ON THE FORWARD FEED.** Largest deviation
**0.576**. That is `STUDY_AUTOBNN`'s defect (a research cut that kept 105 of 105 locked events) with
the opposite sign, and it means the out-of-sample cells are not the test that was declared — they
are a far more restrictive filter, on 26–125 trades, whose "uplift" is inseparable from having
become five times more selective. All four still fail their random gate (best p 0.263), 0 of 6 cells
exceed their MDE split, and **total points fall in every out-of-sample cell** (719→481, 722→335,
1,198→629, 485→392).

---

## 8. The post-mortem: a fixed-width fractional difference is NOT level-free

Two things produce a broken threshold and they have different verdicts — the score RANKS correctly
and the threshold drifts (fixable by cutting on rank), or the score's INPUTS drift (not fixable).
Block drift of every input on the signal bars, in RESEARCH standard deviations:

| input | A | B | C | B−A (sd) | **C−A (sd)** |
|---|---|---|---|---|---|
| **SCORE** | −0.122 | −12.616 | −19.007 | −0.82 | **−1.24** |
| **`ffd.price`** | 0.721 | 0.745 | 0.761 | +1.90 | **+3.23** |
| `par.z_tod` | 0.251 | −0.787 | 0.096 | −1.86 | −0.28 |
| `par.per_range` | 0.894 | 0.538 | 1.052 | −1.30 | +0.58 |
| `hmm.sojourn` | 4.146 | 3.669 | 3.524 | −0.30 | −0.39 |
| (the other six) | | | | ≤0.20 | ≤0.28 |

**The mechanism is arithmetic and it is measured, not inferred.** Fractional differencing weights
sum to zero only in the infinite limit; truncated at a practical tolerance they do not:

| d | window | **sum(w)** | level term over this file's log-price range (0.944) |
|---|---|---|---|
| 0.2 | 497 | +0.248196 | 0.2344 |
| **0.4** (chosen by ADF) | 282 | **+0.070369** | **0.0665** |
| 0.6 | 140 | +0.023325 | 0.0220 |
| 0.8 | 64 | +0.007908 | 0.0075 |
| 1.0 | 2 | +0.000000 | 0.0000 |

At d = 0.4 the weights sum to **+0.0704**, so `ffd.price` carries 7% of the log price level. US30's
log price rises 0.944 across this file; the predicted level shift is 0.0665 and the measured block
means are **+0.7214 / +0.7448 / +0.7612** — a rise of 0.0398 from A to C, the right sign and the
right order of magnitude, on a feature whose research sd is 0.0123. **A truncated fixed-width
fracdiff is a level feature with a small coefficient, and any THRESHOLD on a model containing one
is non-transferable across a trending sample.** The ADF test does not catch it: the residual level
term is a slow drift, and ADF on 34,000 research bars passes it at d = 0.4. This applies to every
study on this branch that has used `ffd` in a thresholded score — `STUDY_V61_FEATURES_15M`,
`STUDY_XAU_TWO_LAYER`, `STUDY_IB_US30_OPTUNA`, `STUDY_VP_DONCHIAN_US30`. The cheap repairs are to
report `sum(w)` beside `d`, subtract it (`ffd − sum(w) × log price`), or use a rolling z-score of
the fracdiff rather than its level. Note `ffd.z1000`, which is exactly that, drifts **−0.01 sd**
onto the forward block while `ffd.price` drifts +3.23.

**The rank cut settles which failure it is.** Same score, same model, threshold taken as each
block's OWN 30th percentile over its own signal bars, so selectivity is fixed by construction:

| block | arm | n on | kept | on pts | **uplift** | MDE split | PF | tot off | tot on | rand p |
|---|---|---|---|---|---|---|---|---|---|---|
| A research | +ema34>89 | 540 | 0.700 | +1.512 | −1.000 | 15.40 | 1.058 | +1,751 | +816 | 0.760 |
| A research | +adx<=20 | 283 | 0.700 | +9.226 | +2.966 | 21.69 | 1.372 | +2,504 | +2,611 | 0.035 |
| B holdout | +ema34>89 | 254 | 0.700 | +1.343 | −0.835 | 28.42 | 1.043 | +719 | +341 | 0.630 |
| B holdout | **+adx<=20** | 120 | 0.699 | **−1.009** | **−5.605** | 45.97 | **0.969** | +722 | **−121** | 0.943 |
| C forward | +ema34>89 | 145 | 0.700 | +5.109 | −1.437 | 41.77 | 1.147 | +1,198 | +741 | 0.792 |
| C forward | +adx<=20 | 57 | 0.699 | +4.778 | −1.604 | 64.47 | 1.136 | +485 | +272 | 0.480 |

**0 of 4 out-of-sample uplifts are positive** and `+adx<=20` on the holdout goes to −5.605 points at
PF 0.969 and −121 total. So §7's "4 of 4 positive" was the drifting threshold, entirely. And the
ranking itself is not there either — IC on the unlocked labelled stream, with the threshold taken
out of the question:

| block | n | IC | top-30% pts | bottom-70% pts | all |
|---|---|---|---|---|---|
| A research (**in-sample** for the full-fit model; the honest OOF figure is **+0.0821**) | 2,240 | +0.4997 | +42.342 | −19.020 | −0.611 |
| B holdout | 865 | **−0.0076** | −1.885 | −1.000 | −1.266 |
| C forward | 444 | +0.1057 | +11.469 | +5.877 | +7.552 |

**+0.50 where it was fitted, −0.01 on the holdout, +0.11 on a different provider.** Failure type (b),
with (a) sitting on top of it.

---

## 9. Deflation

104 looks counted in `m_run5` (6 Gate-1 arms, 11 fracdiff d rungs, 1 HMM K, 6 leak cells, 19 HMM/vol
IC columns, 8 ladder models, 7 drop-one, 7 keep-one, 28 greedy steps, 1 single-feature, 10 Gate-2
research cells) plus **9 more in the post-mortem** (6 rank-cut cells, 3 IC reads) = **113**.

- per-event Sharpe across the Gate-2 research cells: mean +0.05711, **var 0.001815**, best **+0.12631**
- **E[max Sharpe | pure noise] at N = 104: +0.10841.** Best achieved is 1.165× that — barely above
  the noise floor of its own search, and at N = 113 the floor rises again.
- **Deflated Sharpe of the best research cell: 0.6230 — FAIL.**
- **White's reality check** over the 10 Gate-2 candidate daily streams (1,915 sessions):
  **p 0.0655 — FAIL.** The DSR deflates one Sharpe; the reality check bootstraps the MAXIMUM over
  the candidate set, which is the right statistic for a ten-candidate search, and they agree.

---

## Verdict

**No meta layer built here raises the §12 primary's profit factor by an amount this sample can
resolve, and on the arm that survives a different provider it lowers it at every selectivity.**

- Gate 1 reproduces §12/§13 exactly. All six arms sit **inside their own MDE** — direction, not size.
- Gate 2: **0 of 10 research cells clear both nulls; 0 of 10 uplifts exceed their kept-vs-rejected
  MDE.** The single random-gate pass delivers +2.98 points against a resolution of 21.92 on the arm
  the coordinator's work says fails the reserved feed.
- The one read looks positive (4 of 4) and is not: the score keeps 0.70 / 0.34 / 0.12 across the
  three blocks. **Fix the selectivity and 0 of 4 survive, and the holdout goes negative.**
- The out-of-sample ranking is **−0.0076** on the holdout.
- DSR 0.6230 and White's p 0.0655 at 113 counted looks — the best thing found is at its own noise
  floor.

**Three things worth carrying beyond this workstream.**

1. **A truncated fixed-width fracdiff is not level-free.** `sum(w) = +0.0704` at d = 0.4 and it
   drifts the feature 3.23 research sd onto a different provider. Print `sum(w)` beside `d`; prefer
   a rolling z-score of the fracdiff to its level; and never threshold a score that contains one.
2. **The kept fraction is the first thing to read on any out-of-sample meta-layer result.** A
   positive uplift at a kept fraction that has silently fallen from 0.70 to 0.12 is a report about
   selectivity, not about the model — and the rank cut is the two-minute diagnostic that separates
   them.
3. **The HMM is finished on this branch.** Its states are volatility states (`hmm.side` vs
   `vol.rv96` **−0.9755**, the strongest reading yet), the twelve-step matrix power reproduces the
   bare state label at Jaccard **0.9524** on 187,293 distinct values, and its best column loses to
   `vol.garman_klass` at predicting the label. Three instruments, three studies, the same answer.

**What would move it.** Nothing in the feature layer. The MDE split on the best out-of-sample cell
is 36.65 points against an uplift of +1.27, and the arm carries 57 trades — a filter would have to
be worth a quarter of a stop per trade before this sample could see it. The parent study's list
stands unchanged: pool the window across US100 and NQ, then 1-minute US30 bars. A meta layer is the
last thing this primary needs.
