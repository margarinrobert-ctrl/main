# Breaker block — research log

Every configuration evaluated, including the ones that failed. Nothing here was chosen after
seeing a result: the spec was frozen by the user in two rounds (instrument/bar/M/K/N/sides/exits,
then EXPIRY and the primary-B cap) before the first P&L was computed.

## Frozen spec

| | |
|---|---|
| instrument | NQ 1-minute, `data/NQ_1m.csv`, 1,048,575 bars |
| sample | 2022-12-26 18:01 → 2025-12-11 20:52 New York |
| M (impulse, ATR20) | 2.0 |
| K (impulse bars) | 5 |
| N (swing lookback) | 20 |
| EXPIRY (zone lifetime) | 240 bars |
| buffer | 0.25 × ATR(20) at the order block |
| sides | both |
| primary A | fixed 2R target |
| primary B | no target, 240-bar cap |
| execution | detect on completed bar, fill at `open[trig+1]`, never same-bar |
| costs | 1.72 index points round turn (MNQ, `STUDY_COSTS`), charged from the first run |
| position lock | one live position across both sides |
| **holdout** | **last 25% of trading days: 2025-03-17 → 2025-12-11, opened once in `run_b4.py`** |

Derived, not invented: the impulse direction. The spec does not state it, and it is forced by
steps 2 and 3 being mutually consistent — a bullish trade sweeps a swing low and then closes a body
above the block, so the block must be the last **up** candle before a **down** impulse. Any other
pairing makes step 3 unreachable from step 2.

## Configurations evaluated (21 counted trials, all on the research block)

| # | configuration | n | %/trade | PF | note |
|---|---|---|---|---|---|
| 1–6 | EXPIRY 30/60/120/240/480/1440, detection only | 18,655–85,041 setups | — | — | `run_b1`, no P&L read |
| 7 | **primary A**, expiry 240, rr 2.0 | 27,237 | −0.00999 | 0.596 | declared primary |
| 8 | **primary B**, expiry 240, rr 0.0 | 15,405 | −0.00834 | 0.752 | declared primary |
| 9–18 | expiry 30/60/120/480/1440 × rr {2.0, 0.0} | 1,655–24,600 | −0.0126 … −0.0043 | 0.41–0.86 | all negative |
| 19 | fill at `open[trig+2]` | 30,138 | −0.00931 | 0.690 | alignment probe |
| 20 | fill at `open[trig+3]` | 26,538 | −0.00921 | 0.725 | alignment probe |
| 21 | fill at `open[trig+6]` | 20,575 | −0.00854 | 0.790 | alignment probe |
| — | cost × {0, 2, 4} × 2 primaries | — | see B2.2 | — | folded into the trial variance |
| — | same-bar close fill | 33,624 | −0.00600 | 0.744 | leak counterfactual, not a candidate |
| — | 50-seed random-entry control × 2 | matched | −0.00989 / −0.00779 | 0.594 / 0.755 | null, not a candidate |

No configuration evaluated at any point in this study was profitable net of costs on any block.

## Failures and fixes during the build

1. **Truncation audit reported 0/3 clean and it was my own harness bug.** Counts matched and
   `trig` mismatched on 0 rows; the differing rows were the same setups swapped pairwise, because
   several distinct order blocks can be triggered by the same bar (10,866 bars carry more than one
   setup, up to 11) and `sort_values("trig")` is not a total order. Fixed by sorting on
   `["trig", "side", "ob"]` with a stable kind — the audit, not the test, was weakened by the bug.
   Now 3/3 clean at bars 200k / 500k / 800k, with max |ATR diff| exactly 0.0.
2. Order-block backward search capped at 50 bars as a computational bound; measured binding rate
   **0.0000** at every expiry, so the cap never decided anything.
