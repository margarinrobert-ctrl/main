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
