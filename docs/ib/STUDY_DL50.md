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

## Verdict

**No edge found, and the reason is stated rather than implied.** The direction call at this geometry
is worth less than the two-point cost gap; the win rates sit on their own driftless bounds; six of
seven models lose to random labels; and the spec's fixed-point barrier is itself a moving target
across the sample.

What would change the answer, in order of expected value:

1. **Express the barrier in ATR, not points.** A 1.5 ATR stop with 1.5 / 3 / 4.5 ATR targets is the
   same *intent* and is scale-free across the 2.8× move in the index — and it makes research and
   holdout the same strategy for the first time.
2. **More events at the tight end.** 1,657 holdout events at a 27% base rate is ~430 winners; a
   1.7-point win-rate edge needs several thousand to separate.
3. Not more capacity and not more features — both were swept, and both are at the noise floor.
