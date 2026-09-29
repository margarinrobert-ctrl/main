# EMA 13/48 × VWAP × ATR-trail × deep learning — research log

| # | What | Cells | Locked reads |
| --- | --- | ---: | ---: |
| 1 | declared grid: cross {fresh, state} × VWAP {off, state, touch} × trail {on, off} × flatten {on, off}, NQ 5m | 24 | 0 |
| 2 | the ask as stated + 8 ablations (no trail, no VWAP, no flatten, both off, longs, shorts, touch, zero cost) | 9 | 0 |
| 3 | stop ladder (5) and trail arm/offset ladder (5) | 10 | 0 |
| 4 | random-entry controls, as asked and no-trail | 2 | 0 |
| 5 | NQ 15m and US100 15m, as asked and no-trail, both blocks — reads, not selections | 4 configs | **4** |
| 6 | 37 causal features in 8 families, truncation-audited (0 leaks on 30 probes); 36 survive a 98% coverage floor | — | 0 |
| 7 | ML ladder on the as-asked base: 10 model-objective cells × 2 keep rungs, each with a shuffled twin, purged + embargoed 6-fold | 20 (+20 twins) | **1** (best research IC) |
| 8 | the same ladder on the no-trail base | 20 (+20 twins) | **1** |

**Research-block configurations: ~90 plus 40 shuffled twins. Locked reads: 6, all pre-declared.**
The model read on locked is chosen by a rule fixed before the read (best research OOF IC), once
per base.

## Decisions

- Bar size 5m (unstated in the ask; the 15m reads are cross-checks).
- "VWAP as support and resistance" implemented two ways and both swept: STATE (side of the VWAP)
  and TOUCH (bounce off it). Neither was chosen after seeing results; both are in the grid.
- The trail is ATR-scaled (arm 1.0 / offset 1.0 ATR), not fixed points, because the fixed-point
  trail was just measured destroying the previous strategy by arithmetic. The ATR trail is
  measured here to be destructive too.
- The ML label is the R of the base trade, read at the signal bar. Two bases: as asked (with
  the trail) and without it. Ridge and logistic are the baselines every deep net must beat.
