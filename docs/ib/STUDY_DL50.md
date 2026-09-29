# Deep learning on a fixed 50-point stop with 50 / 100 / 150-point targets, US30

`research/dl50/`. `US30_LONG_15m`, Donchian 20 entry with the EMA200 state deciding the side, fixed
**50-point stop**, targets **50 / 100 / 150 points**, one-day hold cap, both sides, 2.29-point round
turn. 44 causal features in 7 declared families, truncation audit **0 mismatches of 264**.

## A fixed point barrier is not one geometry

This is the finding that outranks everything else here, and it is arithmetic rather than a result.
US30 went from ~16,000 to ~45,000 across the sample, so the *same* 50-point order is a different
trade every year:

| year | stop as % of price | stop in ATR |
|---|---|---|
| 2016 | 0.261 | **4.23** |
| 2018 | 0.200 | 1.85 |
| 2021 | 0.145 | 1.61 |
| 2023 | 0.147 | 1.85 |
| 2025 | 0.118 | **1.10** |

**A 3.85× change in ATR units.** Early in the sample this is a wide swing stop; late in it, a tight
scalp. Research runs to 2023 and the holdout is 2023–2025, so a model fitted on one geometry is
being tested on another. Nothing downstream can undo that, and it is why `geo.stop_in_atr` was put
in the feature pool as a first-class column rather than normalised away: a model that helps by
learning it is telling you the barrier is mis-specified, not that it found an edge.

## Cost is not the objection here, which is rare on this branch

Break-even win rate `(1 + c) / (1 + R)` with `c` = 2.29 / 50 = **4.58% of risk**:

| target | R | driftless bound | after cost | cost gap |
|---|---|---|---|---|
| 50 pt | 1.0 | 50.00% | 52.29% | **+2.29** |
| 100 pt | 2.0 | 33.33% | 34.86% | +1.53 |
| 150 pt | 3.0 | 25.00% | 26.15% | +1.15 |

Against 24% of risk for a 0.75×ATR scalping stop elsewhere here. Whatever fails at this geometry
fails on **direction**, not on execution.

## Base rates — the barriers are hit by noise

| target | block | n | win % | needs | gap | pts/trade | PF | median hold | ambiguous |
|---|---|---|---|---|---|---|---|---|---|
| 50 | research | 6031 | 50.42 | 52.29 | −1.87 | −1.894 | 0.927 | 30 min | 3.0% |
| 50 | HOLDOUT | 2283 | 48.09 | 52.29 | −4.20 | −4.195 | 0.845 | 15 min | 3.4% |
| 100 | research | 4965 | 34.60 | 34.86 | −0.26 | −1.001 | 0.971 | 45 min | 1.2% |
| 100 | HOLDOUT | 1884 | 33.76 | 34.86 | −1.10 | −1.592 | 0.954 | 45 min | 1.4% |
| 150 | research | 4365 | 27.84 | 26.15 | **+1.69** | **+1.237** | **1.033** | 75 min | 0.6% |
| 150 | HOLDOUT | 1657 | 25.89 | 26.15 | −0.25 | −0.718 | 0.981 | 60 min | 0.6% |

**Every win rate lands within 2 points of its own driftless bound** — fifth family on this branch to
do so after `STUDY_THE_STRAT`, `STUDY_IB25_RETRACEMENT`, `STUDY_VWAP_STOCH_ATR` and
`STUDY_V69_ORB`. Only the 150-point target clears its break-even, only on research, by 1.69 points.
The intrabar tie-break is not deciding it (0.6–3.4% ambiguous), and the hold cap almost never binds
(0.6–3.3% time exits), so these are genuine barrier outcomes.

## The deep-learning ladder — 86% twin wins

150-point target (the only one above break-even on research), 4,365 research events, 41 features
after removing three near-duplicates (`geo.stop_in_atr ≡ geo.tgt150_in_atr` at ρ 1.0000 — my own
construction, one is three times the other; plus the two `math.` pairs). Purged embargoed CV,
objective = the **points earned**, every model beside a shuffled-label twin.

| model | OOF IC | shuffled twin | winner |
|---|---|---|---|
| ridge | **+0.0211** | +0.0170 | real |
| rf | −0.0085 | +0.0282 | TWIN |
| lgbm | −0.0175 | +0.0173 | TWIN |
| xgb d3 | −0.0114 | +0.0252 | TWIN |
| MLP 2×32 | +0.0037 | +0.0584 | TWIN |
| MLP 2×64 | −0.0151 | +0.0288 | TWIN |
| MLP 4×128 | +0.0054 | +0.0059 | TWIN |

**Twin wins 6 of 7 = 86%**, the highest rate measured on this branch (`STUDY_VWANOM` 71%,
`STUDY_S3_NEURAL_NET` 58%). Four of seven models have a **negative** IC — they rank the events
backwards. Above 50% the noise floor is higher than the signal; at 86% there is nothing to gate on,
so **Gate 2 was not run and the holdout was not opened for a model read**. Capacity is inert again:
the deepest net (+0.0054) is indistinguishable from the shallowest (+0.0037) and from ridge.

## ADX, added both ways

### The base rate is the surprise, and it inverts four prior findings

| reading | signal bars | all bars | lift |
|---|---|---|---|
| ADX(14) ≥ 20 | 0.660 | 0.652 | **1.01** |
| ADX(14) ≥ 25 | 0.454 | 0.455 | **1.00** |
| ADX(14) ≥ 30 | 0.307 | 0.305 | 1.01 |
| ADX(14) ≤ 20 | 0.340 | 0.348 | 0.98 |
| ADX(28) ≥ 20 | 0.344 | 0.401 | 0.86 |
| ADX(28) ≤ 20 | 0.656 | 0.599 | 1.09 |

**On this base ADX is not the trigger restated.** That is new. RSI ≥ 55 passes **94.7%** of a
long-only Donchian-55 breakout, Aroon 100.0%, MACD 99.8%, MFI 91.7% — four measurements of one
mechanism — and ADX(14) ≥ 25 passes 45.4% here against 45.5% of all bars. The reason is structural:
this primary takes **both sides** with a slow EMA200 state, so its signal bars are not concentrated
in high-ADX regimes the way a long-only breakout's are. ADX is therefore a genuinely independent
reading on this base and worth the test — which is exactly what the base-rate check is for.

### As a gate, the direction that works flips between blocks

Scored as a veto, re-simulated, against a random gate keeping the same share. `no gate` rows in bold.

| target | reading | research PF | research p | HOLDOUT PF | HOLDOUT p |
|---|---|---|---|---|---|
| 50 | **no gate** | **0.927** | — | **0.845** | — |
| 50 | ADX ≥ 25 | 0.906 | 0.845 | 0.869 | 0.278 |
| 50 | ADX ≤ 20 | **0.971** | 0.128 | 0.853 | 0.460 |
| 100 | **no gate** | **0.971** | — | **0.954** | — |
| 100 | ADX ≥ 25 | 0.949 | 0.830 | **1.023** | 0.115 |
| 100 | ADX ≤ 20 | **1.030** | **0.085** | 0.948 | 0.550 |
| 150 | **no gate** | **1.033** | — | **0.981** | — |
| 150 | ADX ≥ 25 | 1.012 | 0.710 | **1.017** | 0.273 |
| 150 | ADX ≤ 20 | **1.077** | 0.193 | 0.968 | 0.608 |

**On research every ADX floor is worse than no gate and the ceiling is the better direction; on the
holdout that reverses and the floor is the better one.** Both directions were run on both blocks, so
this is a clean sign-flip rather than a one-sided read — the **sixth** time ADX's sign has moved on
this branch (`STUDY_V39`, `V52`, `V60`, `SCALP_FILTERS`, `SCALP_REQUIREMENTS`, here). Nothing clears
p ≤ 0.05 anywhere; the best cell in the table is `ADX ≤ 20` on the 100-point target at **p 0.085**,
research only, and it is the direction the holdout likes least.

### As features, it changes nothing

Six `adx.` columns added (ADX 14 and 28, the DI spread, DI alignment with the EMA state, the ADX
slope, and its 500-bar rank). `adx.di_aligned` is **degenerate on the trigger's own bars** and drops
out — the EMA200 state and the sign of the DI spread agree by construction on a directional break.
Pool 44 → 50 → 46 after the degenerate column and the same three near-duplicates. Truncation audit
**0 of 300**.

| model | IC without adx | IC with adx | twin (with) |
|---|---|---|---|
| ridge | +0.0211 | **+0.0100** | +0.0033 |
| rf | −0.0085 | −0.0124 | +0.0407 |
| lgbm | −0.0175 | −0.0265 | +0.0350 |
| xgb d3 | −0.0114 | −0.0098 | +0.0309 |
| MLP 2×32 | +0.0037 | −0.0207 | +0.0487 |
| MLP 2×64 | −0.0151 | −0.0088 | +0.0531 |
| MLP 4×128 | +0.0054 | −0.0125 | +0.0321 |

**Twin wins 6 of 7 = 86%, unchanged**, and six of seven ICs are now negative against four before.
Adding a family that is genuinely independent of the trigger did not move the noise floor at all,
which is the cleanest evidence in this study that the problem is the geometry and not the pool.

## Held to 07:00–11:00 New York with an 11:00 flatten

`US30_LONG_15m` is already New York time — the 09:30 mean-bar-range step was re-derived on this feed
— so the window is minutes 420–660 and the flatten fires at the 660 **open**, submitted on the bar
before, with any signal whose fill would land at or after the cutoff **refused** rather than opened
and closed at the same price (`STUDY_V60`).

| target | arm | research pts | PF | HOLDOUT pts | PF | closed on the clock |
|---|---|---|---|---|---|---|
| 50 | all hours | −1.894 | 0.927 | −4.195 | 0.845 | — |
| 50 | 07:00–11:00 entries | −2.111 | 0.919 | −4.695 | 0.829 | — |
| 50 | + flatten | −3.059 | 0.871 | −5.149 | 0.805 | 17.3% |
| 100 | all hours | −1.001 | 0.971 | −1.592 | 0.954 | — |
| 100 | 07:00–11:00 entries | **+0.907** | **1.027** | −0.708 | 0.979 | — |
| 100 | + flatten | −0.243 | 0.991 | −0.980 | 0.969 | 28.6% |
| 150 | all hours | +1.237 | 1.033 | −0.718 | 0.981 | — |
| 150 | 07:00–11:00 entries | **+1.513** | **1.041** | −1.722 | 0.956 | — |
| 150 | + flatten | −0.049 | 0.998 | −1.868 | 0.945 | 35.9% |

**The window and the flatten do opposite things.** Restricting *entries* to 07:00–11:00 improves the
100- and 150-point targets on research (+0.907 and +1.513 against −1.001 and +1.237) and worsens the
50-point one; on the holdout it worsens all three. The **flatten is destructive in all six cells** —
the sixteenth confirmation on this branch — and it binds hard despite a 30–75 minute median hold,
closing **17% to 36%** of trades on the clock.

### The win rate rises nine points while the strategy turns negative

This is the trap in the table and it is worth stating separately. At the 150-point target on
research the flatten takes the win rate **28.40% → 37.31%**, which reads as +11.16 points over the
break-even — and points per trade go **+1.513 → −0.049**.

`(1 + c) / (1 + R)` is a **two-outcome** formula. Once a third exit reason exists it is no longer the
right bar, because a clock exit books a small gain or loss that counts as a "win" without ever
reaching the target. `STUDY_V45` recorded exactly this bound — the formula is valid only where the
flatten share is small (1.4–5.0% there) — and here that share is **35.9%**. Any win-rate column
computed against a barrier break-even beside a flatten of that size is not comparable, and reading it
as an improvement inverts the actual result.

### ADX inside the window: the low reading agrees across blocks, the high one does not

| target | reading | research pts | PF | p | HOLDOUT pts | PF | p |
|---|---|---|---|---|---|---|---|
| 50 | no gate | −3.059 | 0.871 | — | −5.149 | 0.805 | — |
| 50 | ADX ≥ 25 | −1.183 | 0.948 | **0.018** | −6.559 | **0.757** | 0.795 |
| 100 | no gate | −0.243 | 0.991 | — | −0.980 | 0.969 | — |
| 100 | ADX ≤ 20 | +1.252 | **1.047** | 0.247 | +1.082 | **1.035** | 0.280 |
| 150 | no gate | −0.049 | 0.998 | — | −1.868 | 0.945 | — |
| 150 | ADX ≤ 20 | +3.460 | **1.126** | 0.080 | +3.641 | **1.111** | 0.142 |
| 150 | ADX ≥ 25 | +0.953 | 1.033 | 0.318 | −5.367 | 0.846 | 0.877 |

**`ADX ≤ 20` is positive on both blocks at the 100- and 150-point targets** — the first ADX cell in
this study that agrees across the split, and the only arm anywhere in the study that is above break-
even out of sample. Its direction is consistent with `STUDY_V21` (every ADX floor fails while CHOP
clears) and with `STUDY_SCALP_REQUIREMENTS` (ADX ≥ 25 is negative at scalp geometry). The high
reading does the opposite: `ADX ≥ 25` is the one cell in the whole study to clear p ≤ 0.05
(**p 0.018**, 50-point target, research) and it is the **worst** row on that target's holdout,
PF 0.757 at p 0.795 — and its research PF is 0.948, so it beats a losing null while still losing.
One pass in ~30 window gate cells is what chance delivers at 1.5 expected.

### The ladder inside the window

1,694 research events, 41 features after five degenerate columns drop out (`tod.min`, `tod.sin`,
`tod.cos` are constant-ish inside a four-hour box by construction, plus `vol.rng_atr` and
`adx.di_aligned`).

| model | IC | twin | |
|---|---|---|---|
| ridge | +0.0035 | +0.0308 | TWIN |
| rf | +0.0275 | +0.0221 | real |
| lgbm | −0.0121 | +0.0378 | TWIN |
| xgb d3 | +0.0140 | +0.0082 | real |
| MLP 2×32 | +0.0062 | +0.0121 | TWIN |
| MLP 2×64 | +0.0058 | +0.0731 | TWIN |
| MLP 4×128 | **+0.0343** | −0.0164 | real |

**Twin wins 4 of 7 = 57%**, down from 86% all-hours — the noise floor is lower in the window, but
still at chance. Gate 2 on the best model: keep-70% reads +1.261 pts at PF 1.045 and **p 0.125**,
and both tighter rungs are *worse than the base* (keep-50% −0.321, keep-30% −1.619). A gate whose
best rung is its loosest is not selecting; it is trimming a tail.

## ATR barriers instead of points — the fix I proposed does not work

The hypothesis was explicit: a fixed 50-point stop is 4.23 ATR in 2016 and 1.10 ATR in 2025, so
research and holdout are different strategies, and sizing the stop as k × ATR at the signal bar with
the target at 3 × that stop should shrink the inversion. **It does not.** Same arm — 07:00–11:00
entries, no flatten, R = 3.

| barrier | research R | HOLDOUT R | research PF | HOLDOUT PF | entry-null p (res) |
|---|---|---|---|---|---|
| 50 / 150 points | +0.0303 | −0.0344 | 1.041 | 0.956 | 0.177 |
| 1.0 ATR / 3R | +0.0216 | −0.0694 | 1.044 | **0.913** | **0.010** |
| 1.25 ATR / 3R | **+0.0662** | −0.0768 | **1.068** | **0.877** | **0.007** |
| 1.5 ATR / 3R | +0.0266 | −0.0135 | 0.995 | 0.924 | 0.128 |
| 2.0 ATR / 3R | +0.0395 | +0.0010 | 1.034 | 0.896 | 0.142 |

Every ATR cell is research-positive and holdout-negative, and at 1.0 and 1.25 ATR the profit-factor
gap is **wider** than the point version's. Making the geometry scale-free did not remove the
inversion, so **the inversion is not a geometry artifact** — it is decay or regime. One thing did
improve: the trigger now clears its random-entry control on research (p 0.007–0.010 against the
point version's 0.177), and fails it on the holdout (0.585–0.720). That is the right *shape* for
decay and it does not rescue a negative holdout.

## ADX ≤ 20 on the ATR barriers

| barrier | gate | research R | PF | p | HOLDOUT R | PF | p |
|---|---|---|---|---|---|---|---|
| 1.25 ATR | ADX ≥ 25 | **+0.1738** | 1.138 | **0.010** | −0.0526 | 0.946 | 0.345 |
| 1.25 ATR | ADX ≤ 20 | +0.0188 | 1.079 | 0.787 | −0.0119 | 0.952 | 0.282 |
| 1.5 ATR | ADX ≤ 20 | +0.0547 | 1.069 | 0.323 | **+0.1340** | **1.206** | 0.090 |
| 2.0 ATR | ADX ≥ 25 | +0.1118 | 1.112 | 0.065 | −0.0361 | 0.922 | 0.705 |
| 2.0 ATR | ADX ≤ 20 | +0.0077 | 1.032 | 0.685 | **+0.1497** | **1.222** | 0.090 |

**The same flip reproduces on ATR barriers**: research prefers `ADX ≥ 25` (p 0.007–0.065) and the
holdout prefers `ADX ≤ 20` (p 0.090 at both wide stops). At 1.5 and 2.0 ATR the low reading is
holdout-positive at PF 1.21–1.22 on 168–172 trades — but it is **better on the holdout than on
research** (p 0.323 / 0.685 there), the wrong shape, and it fails on the block permitted to choose.

## Why it inverts — year by year

| year | 50/150 pts PF | 1.25 ATR PF | 2.0 ATR PF | ADX winner (1.5 ATR) |
|---|---|---|---|---|
| 2017 | 1.080 | 1.019 | 1.071 | high |
| 2018 | 0.980 | 1.104 | 1.080 | low |
| 2019 | 1.130 | **1.305** | 1.173 | low |
| 2020 | 0.896 | 0.943 | 1.129 | low |
| 2021 | **1.253** | 1.155 | 1.123 | high |
| 2022 | 1.012 | 1.092 | 0.910 | high |
| 2023 | 0.970 | 0.933 | 0.917 | low |
| 2024 | **0.875** | **0.818** | 0.987 | low |
| 2025 | 1.041 | 0.870 | **0.683** | low |

**This is not a decay curve — it is year-to-year sign noise with a bad run at the end.** 2018–2022
is five mostly-positive years across all three geometries; 2023–2025 is three mostly-negative ones,
and the split date (2023-05) sits exactly on that boundary. The three barrier versions **disagree
about which years were good** (2020: 0.896 / 0.943 / 1.129; 2022: 1.012 / 1.092 / 0.910), which is
what noise looks like rather than a shared underlying signal.

The ADX winner flips **five times** across ten years with no persistence — high in 2017, low
2018–2020, high 2021–2022, low 2023–2025. The market statistics do not explain it: median ADX is
flat at 21.8–24.5 all sample and the share of bars under 20 moves only 0.31–0.43. **So neither block
is telling the truth about ADX; the direction that "wins" is whichever one happened to catch that
block's years.**

## Decay, or a badly-placed cut? Three tests, and they agree

The year table above admits two readings that call for different decisions. Either the mechanism
worked and stopped — in which case the holdout is informative and the research block is stale — or
the annual sign is noise and the 2023-05 cut happened to land on a bad run, in which case
"research positive, holdout negative" is not evidence of anything. `run_d9.py` and `run_d10.py`
separate them without introducing a single new parameter.

### 1. The cut is not the explanation

Slide the split across the sample and read both halves at each position (1.25 ATR / 3R,
07:00–11:00 entries, no flatten, n = 2,495):

| cut | date | R research | R holdout | gap |
|---|---|---|---|---|
| 0.40 | 2020-06-11 | +0.0437 | +0.0178 | +0.0259 |
| 0.50 | 2021-05-27 | +0.0498 | +0.0066 | +0.0432 |
| 0.60 | 2022-04-14 | +0.0640 | −0.0255 | +0.0895 |
| 0.70 | 2023-02-02 | +0.0747 | −0.0803 | +0.1550 |
| **0.75** | **2023-07-06** | **+0.0724** | **−0.1043** | **+0.1767** |
| 0.85 | 2024-04-29 | +0.0482 | −0.0852 | +0.1334 |
| 0.90 | 2024-09-19 | +0.0390 | −0.0688 | +0.1078 |

**The gap is positive at all eleven cut points** (min +0.0259, median +0.1078), and the research
half is positive at every one of them. What moves is the holdout half, which is positive at the two
earliest cuts and turns negative only once it is confined to 2023 and later. So the sample genuinely
got worse late; the date was not chosen to make it look that way. The point-barrier arm is weaker
evidence for the same thing — 8 of 11 gaps positive, and **negative at the 0.85 and 0.90 cuts**
(−0.0401, −0.0148), so the two barrier versions do not even agree that there is decay.

### 2. On the folds that post-date the cut, everything loses and a random cell loses least

Walk-forward with the 12-cell barrier × ADX grid re-chosen inside every training window, one
calendar year per test fold, beside the fixed arm, the point arm, and a random cell from the same
grid (mean R per trade):

| scheme | folds | re-chosen | fixed 1.25 ATR | 50/150 pts | random cell |
|---|---|---|---|---|---|
| rolling, pre-cut | 5 | +0.0568 | +0.0918 | +0.0379 | +0.0486 |
| rolling, **post-cut** | 3 | **−0.0695** | **−0.0789** | −0.0307 | −0.0289 |
| expanding, pre-cut | 5 | **+0.1713** | +0.0918 | +0.0379 | +0.0486 |
| expanding, **post-cut** | 3 | **−0.0712** | **−0.0789** | −0.0307 | −0.0289 |
| post-cut folds positive | | 1/3 | **0/3** | 1/3 | 1/3 |

The expanding re-optimiser looks like the rare optimiser win — +0.1713 against the constants'
+0.0918 — and **the whole advantage is pre-cut**, exactly the shape `STUDY_VWAP_EMA_GOLD` and
`STUDY_VWAP_EMA_INDICES` recorded. On the three honest folds it is the second-worst arm and loses
to a **random cell**; thirteenth re-optimiser on this branch to lose to the author's constants and
the third to also lose to a coin flip. And the selection is *stable* — expanding picks
`1.25 ATR, ADX ≥ 25` in six of eight folds — so this is not an optimiser that cannot make up its
mind. It settles on one cell and that cell stops working.

### 3. The framing test: it is the trigger, not the window and not the market

Same block, same geometry (1.25 ATR / 3R), same position lock:

| arm | research | | holdout | |
|---|---|---|---|---|
| | R | PF | R | PF |
| **the arm, 07:00–11:00** | **+0.0673** | 1.088 | **−0.0761** | 0.903 |
| random entry in the window, same geometry | −0.0458 | — | −0.0303 | — |
| → control p | **0.000** | | **0.815** | |
| always-long in the window, same geometry | −0.0116 | 0.985 | **+0.0280** | 1.037 |
| the arm, all hours | +0.0365 | 1.047 | −0.0589 | 0.925 |

Three readings, and they point one way:

- **On the holdout a random entry in the same window with the same geometry beats the arm**
  (−0.0303 against −0.0761, p 0.815). The trigger is worth less than nothing there.
- **Always-long in that window is *positive* on the holdout** (+0.0280) while the arm is −0.0761.
  So 2023–2025 is not a bad market for being long between 07:00 and 11:00 — it is a bad market for
  this breakout. The window is not the cause.
- **Removing the window entirely reproduces the inversion** (+0.0365 → −0.0589). So the session
  constraint is not the cause either.
- Note the research pass's own null: the control there earns **−0.0458**, i.e. random entries in
  this window *lose money*, so part of the p 0.000 is the window being hostile rather than the
  trigger being good. `STUDY_V15_BOOK`'s distinction, again — clearing a matched control and
  clearing zero are different questions.

### 4. Ten years cannot separate this arm from zero anyway

| arm | mean R | day-block 95% CI | P(mean ≤ 0) | sd across years |
|---|---|---|---|---|
| 1.25 ATR / 3R | +0.0282 | [−0.0431, +0.1021] | 0.223 | 0.1075 |
| 50 / 150 points | +0.0120 | [−0.0583, +0.0860] | 0.369 | 0.0829 |

Annual means on the ATR arm run **−0.160 to +0.147**. The trade-weighted mean is +0.0282 and the
**year-weighted mean is +0.0108** — and the disagreement runs the *opposite* way to
`STUDY_TREND_LONG`'s: here `corr(trades in a year, that year's mean R) = +0.527`, so the busy years
are the good ones and the trade-weighted figure is the flattering one. At an annual spread of 0.1075
around +0.0108, a two-standard-deviation separation from zero needs roughly **380 years**. Neither
block was ever going to answer this.

## Verdict

**No edge, and now for a stated reason rather than a failed test.** The arm under work
(07:00–11:00 entries, no flatten, R = 3, in either the point or the ATR parameterisation) is closed:

1. The research-minus-holdout gap is positive at **every one of eleven cut points**, so the split
   date is not the explanation.
2. On the three walk-forward folds that post-date the research cut the fixed arm is **0/3** and every
   arm is negative, with a **random cell least bad**.
3. On the holdout a **random entry** in the same window with the same geometry **beats it**
   (p 0.815) while **always-long in that window is positive** — so the failure is in the trigger,
   not in the session and not in the market direction.
4. And the whole-sample edge does not separate from zero on ten years (P(mean ≤ 0) 0.223, annual
   sd 0.1075 against a year-weighted mean of +0.0108).

The two proposed repairs both failed and both failed informatively. **ATR barriers** made the
geometry scale-free and left the inversion *wider* at 1.0 and 1.25 ATR — so the fixed-point drift
was real but was not what was wrong. **ADX in either direction** flips winner five times in ten
years while the market's own ADX distribution barely moves, so neither block was telling the truth
about it.

What is left of the work, as findings rather than a strategy:

- **A 50-point stop on US30 is not a cost problem** (round turn 4.58% of risk, and the win rates sit
  within two points of their own driftless bounds) — so this family fails on direction, which is
  the rarer and more useful diagnosis on this branch.
- **A fixed point barrier is not one geometry** across a 2.8× move in the index (4.23 ATR in 2016,
  1.10 ATR in 2025). Any multi-year study on a point barrier is a mixture of strategies.
- **Six of seven models lost to their shuffled twins**, before and after the window was added — the
  noise floor is above the signal, so capacity and features are not the constraint.
- The `run_d9` / `run_d10` battery — slide the cut, split the walk-forward at it, then ask whether a
  random entry and an always-in position in the *same block* also failed — is the cheapest way to
  tell decay from a bad draw, and it is three short scripts.

Do not re-run this family on US30 at these barriers.
