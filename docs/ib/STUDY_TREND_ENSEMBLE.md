# Diversified Trend Ensemble — evaluation

`research/trend/` (the spec's §7 layout), `results/trend/`. Spec: `trend_ensemble_SPEC.md` as uploaded.

## Verdict

**The implementation passes every implementation test the spec sets; the strategy on the universe
available here has no demonstrable edge — and the spec itself predicts that outcome.** Its engine
is breadth: 15–30 instruments across equities, bonds, FX and commodities. What is on disk is two
equity index feeds. N = 2, one asset class, which the spec calls a coin flip. The result is
therefore a test of the *code*, not of the *design*; the design cannot be tested without the
universe it was written for.

On the numbers: training net Sharpe **−0.037**, deflated Sharpe **0.039** against N = 12 trials,
breakeven cost **negative** (the gross strategy already loses), random-strategy null percentile
**47**, block-bootstrap P(Sharpe < 0) **0.54**. The parameter surface is a flat plateau — at zero.
The holdout reads **+0.54**, better than training, which is the wrong shape and fails the spec's
own "within 0.3 of walk-forward" criterion. None of the kill conditions fire; nothing leaked.

What would change the verdict: the universe. The registry already knows feeds that would take
N from 2 to 5 across three asset classes — XAUUSD 5m (2004–2026), EURUSD 30m (2003–2022),
BTC 15m (2017–2026) — and they are absent from disk and need re-attaching.

## Setup

| | |
| --- | --- |
| Universe | US100 and US30, 15m CFD feeds resampled to daily. NQ is the same index as US100 (ρ 0.9995) and three years long — not a third instrument. |
| Sample | 2016-11-15 → 2025-07-14, 2,238 common days |
| Holdout | most recent 25%: split **2023-05-22**, written to `config.yaml` by the first build, read once at the end |
| Execution | signal at close *t*, filled at open *t+1*, held to open *t+2*; explicit `shift(1)`, asserted by `tests/test_alignment.py` |
| Costs | 2 bps a side (liquid index future), paid on |Δposition| at the execution open; no financing (futures convention — the CFD venue would add it) |
| Year | 256 days throughout |
| Trials | **N = 12**: the design as given, the mechanical sleeve rule, one calibration, seven mandated perturbations, two evaluation schemes. Nothing adopted from any perturbation. |

## The three tests the spec requires

| Test | Result |
| --- | --- |
| `test_alignment` — no same-bar execution | **pass.** corr(position_t, return_t) = 0.023 / 0.015. The skill's own diagnostic shows what the bug would have been worth: Sharpe **1.13 / 0.82 if executed same-bar** against 0.19 / −0.22 next-bar. |
| `test_scalars` — E\|F_k\| ≈ 10 with the hard-coded scalars | **pass**, no refit: 10.30 / 10.78 / 11.22 / 12.04 / 12.21 on US100, 9.80–10.27 on US30. The scalars are properties of the filter, as the spec says. |
| `test_vol_target` — realised training vol within 10% of τ after one calibration | **pass**: c = **0.7885**, realised 0.2000 vs τ 0.20. Note the sign: the uncalibrated system ran *hotter* than target (0.254), not cooler as the spec's 20-instrument simulation did (0.133), because two correlated equity indices do not offset. |

Sleeve sets by the drag rule at 2 bps: **all five kept** on both instruments (drag 0.007–0.078,
all under 0.10). Realised turnover after buffering: **7.9 / 9.4** position turns a year — the
buffer earns its place.

## The §8 battery, in order

| Step | Result |
| --- | --- |
| 1. Execution alignment | clean (above) |
| 2. Walk-forward rolling 1260/252 | **one fold** on 1,679 training days: Sharpe **−0.797**. The spec's window needs ≥10 years for a distribution. Supplement, 756/252 (a deviation, labelled): **+0.879, +0.524, −0.797** — mean +0.20, sd **0.88**, 2 of 3 positive. That spread is the finding, not the mean. |
| 3. CPCV 6×2 → 15 splits, 5 paths | all five paths **−0.056**, sd 0.000. Degenerate by construction: the strategy has no fitted parameter, so every path reassembles the same fixed return series. CPCV measures selection variance and there is no selection. |
| 4. Deflated Sharpe, N = 12 | observed −0.037; expected best-of-12 from noise **+0.65** annualised; **DSR 0.039** — "not distinguishable from the best of 12 random tries" |
| 5. Breakeven cost | **−2.4 bps** — gross is already negative. Sensitivity: 0 bps −0.020 → 50 bps −0.434, monotone. |
| 6. Random-strategy null | sign randomised per holding run, same \|exposure\| path and flip count: null 5–95% [−0.45, +0.37], real strategy at the **47th percentile** |
| 7. Block bootstrap (block 40) | P(Sharpe < 0) **0.541**, P(Sharpe < 0.5) 0.939 |
| 8. Perturbation ±25% | vol span 24 / 40: −0.012 / −0.059; long window 1920 / 3200: −0.037 / −0.037; speeds ×0.75 / ×1.25: −0.060 / +0.001; buffering off: −0.036. **A flat plateau at zero** — the implementation is not fitted to noise, and there is nothing under it. |
| 9. Regimes | by year: 2017 +1.09, 2018 −0.55, 2019 +0.03, 2020 +0.48, 2021 +0.46, **2022 −1.15**, 2023H1 −0.40. By vol tercile: **low +0.96, mid +0.14, high −1.06**. Per instrument (gross): US100 +13.9% (Sharpe +0.20), US30 −16.6% (−0.22). |
| 10. Holdout, once | 2023-05-22 → 2025-07-14: net Sharpe **+0.537**, CAGR +8.6%, vol 18.5%, maxDD −16.0%. 2023H2 +1.79, 2024 +0.33, 2025 −0.02. **Not within 0.3 of walk-forward.** |

## The 2022 question

Trend following's best year on a diversified book was **−20.1%, Sharpe −1.15** here. The system
was short US100 on **83%** of 2022's days while US100 fell 33.8% — and lost anyway, whipsawed by
the bear rallies (January–March, June–August, October–November) that a five-sleeve ensemble on a
single asset class cannot avoid. That is precisely what bonds, energy and FX exist to offset in
this design, and the vol-tercile row says the same thing from the other side: the book earns in
calm regimes and loses in volatile ones, the opposite of the crisis convexity the spec promises.
Both are the breadth deficit, not an implementation fault.

## Acceptance criteria (§9)

| Test | Pass? |
| --- | --- |
| Execution alignment | **pass** |
| Realised vol vs τ | **pass** (ratio 1.000) |
| Walk-forward Sharpe 0.25–0.70 | fail: −0.80 on the one spec fold; +0.20 ± 0.88 on the supplement |
| Holdout within 0.3 of walk-forward | fail: +0.54 against −0.80 / +0.20 — the wrong direction |
| Deflated Sharpe > 0.95 | fail: 0.039 |
| PBO < 0.30 | not computable: PBO needs a matrix of configurations and there is one |
| Breakeven cost > 3× modelled | fail: negative |
| Random null > 95th percentile | fail: 47th |
| Parameter surface a plateau | **pass** |

**Kill conditions:** none fire. Sharpe < 1, drawdown 50.6% ≫ vol, multi-year flat stretches
(2018–19, 2022–23), no cost collapse between 2 and 5 bps (there is nothing to collapse), and the
single-instrument share cannot be judged on a book of two.

## What this establishes

1. **The machinery is correct.** Alignment, scalars and vol target all pass on first run without
   any refit, the plateau is flat, buffering cuts turnover to 8–9 turns a year. `research/trend/`
   is ready for a real universe.
2. **The spec's warning was accurate.** On N = 2 in one asset class the design has no edge, and
   the spec said a single market is a coin flip. The 47th-percentile null and the 0.54 bootstrap
   are what "coin flip" looks like when measured.
3. **The holdout's +0.54 is not evidence.** It is one 25-month window in which the 2023 rally was
   caught long (2023H2 Sharpe +1.79); it was better than training, which on this branch has been
   the defect every time; and the design's own acceptance test rejects it.

## Two notes on the repository

`research/metrics.py`, the branch's own file, has an `IndentationError` at line 178 and cannot be
imported; it surfaced here because the skill's `metrics.py` was briefly shadowed by it. Not
touched. And the import order in `validate.py` matters: the pipeline modules push `research/` to
the front of `sys.path`, so the skill directory has to be inserted *after* them — the fourth
name-shadowing bug this session.
