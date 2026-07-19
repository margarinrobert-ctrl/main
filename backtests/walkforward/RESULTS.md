# Walk-forward results — SAM-Best v2 on user 30m NAS100 data

Data: `110577d2-30m_data.csv` — 2283 sessions (2016-11-15 → 2025-10-01), 2279 valid (≥20 bars), decisions from 2016-12-28.

## Full-sample replication check (study claims: ens Sharpe 0.83, CAGR 15.1%, maxDD -24.9%, t 2.51, exposure 0.58x; W8 1.02; B&H 0.73)

| Series | Sharpe | CAGR | maxDD | t | days |
|---|---|---|---|---|---|
| Ensemble W2-30 (2bps, gross of financing) | 0.86 | 14.0% | -24.6% | 2.58 | 2252 |
| Single W=8 (2bps) | 0.97 | 16.9% | -27.0% | 2.90 | 2252 |
| Buy & hold | 0.90 | 19.6% | -35.7% | 2.68 | 2252 |
| Ensemble net of 6.5% financing | 0.64 | 9.8% | -26.0% | 1.91 | 2252 |
| Ensemble, +1-bar delayed fills | 0.87 | 14.1% | -24.6% | 2.59 | 2252 |

Average ensemble exposure: **0.58x**

## Paired alpha vs exposure-matched buy & hold (VALIDATION.md Gap 3)

- gross spread: mean 2.52%/yr, NW t = **0.95**
- net-of-financing spread: mean -1.24%/yr, NW t = **-0.47**

## Walk-forward — Rolling (IS=756d), OOS=126d, 11 folds

| Process | stitched OOS Sharpe | OOS CAGR | OOS maxDD | WFE | folds>0 |
|---|---|---|---|---|---|
| A: refit best single W | 0.34 | 4.9% | -31.3% | 0.29 | 64% |
| B: fixed ensemble W2-30 | 0.73 | 12.8% | -24.6% | 0.83 | 91% |
| C: meta-select {W's, ENS} | 0.34 | 4.9% | -31.3% | 0.29 | 64% |
| (benchmark) B&H on same OOS days | 0.72 | 16.8% | -35.7% | — | — |

Process A picks per fold: W8, W13, W13, W13, W29, W6, W4, W27, W5, W4, W2
Process C picks per fold: W8, W13, W13, W13, W29, W6, W4, W27, W5, W4, W2

## Walk-forward — Anchored (expanding IS), OOS=126d, 11 folds

| Process | stitched OOS Sharpe | OOS CAGR | OOS maxDD | WFE | folds>0 |
|---|---|---|---|---|---|
| A: refit best single W | 0.58 | 10.2% | -31.8% | 0.48 | 82% |
| B: fixed ensemble W2-30 | 0.73 | 12.8% | -24.6% | 0.70 | 91% |
| C: meta-select {W's, ENS} | 0.58 | 10.2% | -31.8% | 0.48 | 82% |
| (benchmark) B&H on same OOS days | 0.72 | 16.8% | -35.7% | — | — |

Process A picks per fold: W8, W13, W13, W13, W29, W8, W8, W8, W8, W8, W8
Process C picks per fold: W8, W13, W13, W13, W29, W8, W8, W8, W8, W8, W8

## Per-fold detail (rolling)

| fold | OOS start | A pick | A IS SR | A OOS SR | B (ENS) OOS SR | C pick | C OOS SR |
|---|---|---|---|---|---|---|---|
| 1 | 2019-12-05 | W8 | 1.28 | 1.93 | 1.75 | W8 | 1.93 |
| 2 | 2020-06-12 | W13 | 1.40 | 1.83 | 1.91 | W13 | 1.83 |
| 3 | 2020-12-08 | W13 | 1.42 | 0.40 | 0.81 | W13 | 0.40 |
| 4 | 2021-06-04 | W13 | 1.36 | 0.40 | 1.92 | W13 | 0.40 |
| 5 | 2021-11-29 | W29 | 1.70 | -1.80 | -1.71 | W29 | -1.80 |
| 6 | 2022-05-26 | W6 | 0.97 | 0.53 | 0.71 | W6 | 0.53 |
| 7 | 2022-11-18 | W4 | 0.90 | 2.00 | 2.49 | W4 | 2.00 |
| 8 | 2023-05-17 | W27 | 0.95 | -0.06 | 0.71 | W27 | -0.06 |
| 9 | 2023-11-09 | W5 | 0.93 | 1.55 | 2.01 | W5 | 1.55 |
| 10 | 2024-05-08 | W4 | 1.03 | -0.30 | 0.75 | W4 | -0.30 |
| 11 | 2024-10-31 | W2 | 0.87 | -1.24 | 0.01 | W2 | -1.24 |

