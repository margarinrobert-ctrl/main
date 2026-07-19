# Intraday (flat-by-close) search — SAM-Best on 30m NAS100

2253 decision days, 46 session slots (01:00–23:30 server time, US cash ≈ 16:30–23:00), costs 2 bps/side (4 bps/round trip).

## Where does the SAM payoff live? (mean return per day, bps)

| strength bucket | days | intraday leg (fill→session close) | overnight leg (close→next fill) |
|---|---|---|---|
| 0 (flat) | 175 | +2.1 (t=0.3) | +2.2 (t=0.9) |
| (0, 1/3] | 498 | +3.7 (t=0.7) | +2.5 (t=0.7) |
| (1/3, 2/3] | 493 | +8.8 (t=1.9) | -1.6 (t=-1.2) |
| (2/3, 1] | 1087 | +9.8 (t=2.3) | +0.4 (t=0.3) |

## Full-sample grid (6210 configs) — read with deflation!

Expected best IS Sharpe from pure noise at N≈6,200 trials over 8.9y ≈ **1.24** (E[max Z]≈3.7 / √years). Any winner below that is presumed selection noise until it survives the walk-forward.

| rank | config (variant, entry→exit) | full-sample net Sharpe |
|---|---|---|
| 1 | BIN25 01:00→22:00 | 0.54 |
| 2 | BIN25 01:00→21:30 | 0.53 |
| 3 | BIN25 01:30→22:00 | 0.52 |
| 4 | BIN25 01:30→21:30 | 0.52 |
| 5 | BIN25 02:00→22:00 | 0.51 |
| 6 | BIN25 02:30→22:00 | 0.51 |
| 7 | BIN25 02:00→21:30 | 0.50 |
| 8 | BIN25 02:00→23:30 | 0.50 |
| 9 | BIN25 01:00→23:30 | 0.50 |
| 10 | GRAD 02:00→23:30 | 0.50 |
| best GRAD | 02:00→23:30 | 0.50 |
| best BIN25 | 01:00→22:00 | 0.54 |
| best BIN50 | 02:30→23:30 | 0.41 |
| best BIN75 | 02:00→23:30 | 0.44 |
| best ALWAYS | 01:00→23:30 | 0.38 |
| best MOM | 03:30→14:30 | 0.24 |

## Walk-forward of the selection process (rolling IS=756d, OOS=126d)

| universe | stitched OOS Sharpe | OOS CAGR | OOS maxDD | WFE | folds>0 |
|---|---|---|---|---|---|
| refit best of all 6,210 configs | -0.20 | -3.2% | -40.8% | -0.21 | 27% |
| refit best of signal configs only (no ALWAYS/MOM) | -0.08 | -2.1% | -36.9% | -0.10 | 45% |

## Pre-specified candidates (nothing fitted) on the identical walk-forward OOS days

| candidate | full-sample Sharpe | OOS-days Sharpe | OOS CAGR | OOS maxDD |
|---|---|---|---|---|
| C1 GRAD US session 16:30→23:00 | -0.04 | 0.00 | -0.9% | -28.9% |
| C2 GRAD full session 01:00→23:30 | 0.48 | 0.34 | 4.5% | -30.7% |
| C3 BIN50 US session 16:30→23:00 | -0.12 | -0.12 | -2.8% | -34.2% |
| B0 ALWAYS US session (control) | -0.24 | -0.21 | -4.8% | -41.5% |
| B1 ALWAYS full session (control) | 0.38 | 0.22 | 2.6% | -41.4% |

## Does the SAM signal add anything intraday? (paired vs ALWAYS, same window, exposure-matched, Newey-West t)

- C1 vs B0 (US session): spread +1.64%/yr, NW t = **1.12**
- C2 vs B1 (full session): spread +3.08%/yr, NW t = **1.45**

## Cost sensitivity (per-side commission multiples)

| candidate | 1x (2bps) | 2x | 3x |
|---|---|---|---|
| C1 GRAD US session 16:30→23:00 | -0.04 | -0.47 | -0.89 |
| C2 GRAD full session 01:00→23:30 | 0.48 | 0.16 | -0.17 |

## Per-fold picks — refit best of ALL configs

| fold | pick | IS SR | OOS SR |
|---|---|---|---|
| 1 | BIN25 01:00→19:00 | 1.00 | 1.79 |
| 2 | BIN25 01:30→09:30 | 1.20 | -0.96 |
| 3 | BIN25 01:30→16:30 | 1.15 | -0.02 |
| 4 | BIN50 01:00→21:30 | 1.11 | 2.60 |
| 5 | BIN50 02:30→21:30 | 1.42 | -2.54 |
| 6 | MOM 03:30→11:30 | 1.23 | -0.56 |
| 7 | MOM 04:30→09:30 | 1.16 | -3.62 |
| 8 | MOM 19:00→21:30 | 0.56 | -0.01 |
| 9 | MOM 19:00→21:30 | 0.55 | -0.93 |
| 10 | BIN75 17:30→23:30 | 0.67 | -1.14 |
| 11 | BIN75 17:30→23:30 | 0.46 | 0.41 |

