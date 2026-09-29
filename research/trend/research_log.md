# Diversified Trend Ensemble — research log

The spec forbids parameter optimisation, so the trial count is small and consists of the design as
given plus the validation perturbations it mandates. Every one is listed so `N` in the deflated
Sharpe is a fact, not a guess.

| # | What | Chosen on | Notes |
| --- | --- | --- | --- |
| 1 | The design as specified: 5 sleeves (4/16 … 64/256) with the hard-coded scalars, FDM from the spec's matrix, vol blend 0.70/0.30 over span 32 / 2560, IDM from a rolling 1280-day correlation capped 2.5, τ 0.20, buffer 0.10, t+1-open execution, 2 bps a side | nothing | the one configuration |
| 2 | Per-instrument sleeve set by the drag rule (turnover × cost / σ_ann ≤ 0.10) | training σ_ann only | mechanical, not a choice |
| 3 | Calibration constant c = τ / realised training vol | training | set once, written to config |
| 4–10 | §8 step 8 perturbations: vol span 24 / 40, long window 1920 / 3200, sleeve speeds ×0.75 / ×1.25, buffering off | none — validation only, nothing is adopted from them | counted honestly |
| 11 | walk-forward folds (in-fold c only rescales; Sharpe is scale-free) | — | evaluation |
| 12 | CPCV 15 splits / 5 paths | — | evaluation |

**N = 12** for the deflated Sharpe. Nothing was adopted from any perturbation.

## Data reality, stated before any result

The spec's engine is breadth: 15–30 instruments across equities, bonds, FX and commodities. On
disk there are two equity index feeds with nine years each — US100 and US30. NQ is the same index
as US100 (daily return correlation 0.9995) and three years long, so it is not a third instrument.
**N = 2, one asset class.** The spec calls a single market a coin flip; two correlated equity
indices are not much more. The result below is a test of the *implementation*, not of the
*design* — the design cannot be tested without the universe it was written for.

Holdout: the most recent 25% of the common sample, split date written to `config.yaml` by the
first build and not moved.
