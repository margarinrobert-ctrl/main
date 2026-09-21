# `research/nineam/` — the 09:00 range breakout on 30-second US30

Written to answer one question: can feature engineering and a timeframe sweep take this rule to
profit factor 2? The answer, and every number behind it, is in
[`docs/ib/STUDY_NINE_AM_1M.md`](../../docs/ib/STUDY_NINE_AM_1M.md).

| module | what it does |
| --- | --- |
| `bars.py` | loads the 30-second file, resamples to N minutes keeping each bar's 30s slice, sessions, the 65/35 split, `ema(tr,n)` ATR |
| `sim.py` | the Pine's rule as a numba state machine; exits walk the **30-second** array so a bar holding both barriers is resolved, not assumed. Also the fixed-entry walk used by controls, the points breakeven with a through-the-market fill model, and the MA gate |
| `sim_test.py` | a slow, obvious reference walker; asserts the fast path trade-for-trade over 5 configurations |
| `features.py` | 22 causal features in 5 families, all read at the **signal** bar, plus `audit()` which truncates the series at each probe row and requires the feature to reproduce |
| `control.py` | matched random entries (same side, geometry, minute-of-day) and the minimum detectable effect |
| `run_grid.py` | the declared 960-cell grid, research only, every cell kept for the reality check |
| `run_meta.py` | Gate 1 and Gate 2 — purged/embargoed CV, gates applied to triggers and re-simulated, scored against a same-size random filter |
| `run_deflate.py` | White reality check, deflated Sharpe, effective trials, PBO |
| `run_locked.py` | the locked read, multiplicity printed first, plus cost sweep and exit split |
| `run_userconfig.py` | the settings from the screenshots, decomposed one mechanic at a time |

Run in that order. `sim_test.py` first — nothing below it means anything if the engine disagrees
with its own reference.

The data path is set at the top of `bars.py`. The first call caches a parquet in `.cache/`.
