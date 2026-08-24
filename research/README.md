# The Python research layer

A second engine, in a second language, checked against the first.

## Why it exists

Two reasons, and only one of them is speed.

**It is an independent implementation.** `ib_sim.py` was written from the stated rules and from
reading the TypeScript engine's semantics — not ported from it. Different language, different array
layout, different author-in-the-moment. When the two agree trade-for-trade, that is evidence the
rules are implemented correctly. When they disagree, one of them has a bug, and this repository has
a history of finding bugs exactly this way.

They currently agree **exactly**: 1,413 trades across five configurations, matching on every entry
index, exit index, side, entry price, exit price and P&L. The only difference is 5e-7 in R, which is
the six-decimal rounding of the CSV used to compare them.

That agreement validates more than the strategy. It validates the hand-rolled DST rule in `clock.ts`
against the IANA database, the resting-limit trade-through semantics, the pessimistic intrabar rule,
the cost model and the tick-snapping arithmetic — all at once.

**It is about 100x faster.** 0.89 ms per full backtest over 113,816 bars, roughly 1,100 backtests a
second, against a TypeScript engine that took minutes for a few thousand.

## What the speed is NOT for

vectorbt's headline feature is sweeping millions of parameter combinations. **This project has
already measured that as harmful.** `docs/ib/STUDY_SEARCH_CURVE.md` found a pre-specified
configuration earning 0.312R against a searched one's 0.278–0.343; the IB study found PBO 0.968 and
walk-forward re-optimisation turning $27,253 into $14,580.

A faster search does not fix an overfitting problem. It makes it cheaper to have.

## What it is for

Running the validation machinery that was previously too expensive to run properly:

- **CSCV / PBO at 16 blocks** — 12,870 train/test splits, against the 10 blocks that were affordable
  before.
- **Stationary block bootstrap at 10,000 resamples**, which preserves the serial dependence an
  i.i.d. bootstrap destroys.
- **The search-width curve at real resolution** — the repo's own central finding, measured with
  hundreds of draws per width instead of a handful.

## What it found

The curve is **non-monotonic**, and that is only visible when the objective is dollars. Selecting on
mean R, the holdout percentile climbs to 98.5 and stays there — search harder, apparently forever.
Selecting on dollars over the same configurations, it climbs to 88.5 and then **collapses to 45.0
with a median holdout of −$90** once the search is wide enough to converge on the global in-sample
optimum.

R divides by the stop distance, so a configuration with a tiny stop books large multiples on very few
trades; a search maximising mean R converges on exactly those (96% of its picks at the widest
setting) and never registers the failure, because the failure is in trade count and dollars rather
than in the ratio.

**Select on dollars.** Full write-up: `docs/ib/STUDY_VECTORBT.md`.

Then the same experiment at 225,792 configurations with a properly locked holdout removed the rising
section entirely: a random pick lands at the 51.5th percentile of locked-holdout P&L, the best of
143,536 lands at the **13.4th**, and every increase in search width moves the result down without a
single reversal. Rank correlation between research and locked P&L is **−0.079**. The pre-specified
geometry beat 57% of the grid on data nobody looked at. See `docs/ib/STUDY_MEGA_SEARCH.md`.

`vectorbt` itself is used for the analytics layer (`pf.py`): the returns accessor, drawdown
decomposition and risk ratios. Those are well-tested and easy to get subtly wrong by hand.

## Files

| file | what it does |
| --- | --- |
| `nqdata.py` | data loading, the New York session clock, session ids that survive midnight |
| `ib_sim.py` | the independent numba simulation of the strategy and the execution model |
| `crosscheck.py` | trade-for-trade comparison against the TypeScript engine |
| `grid.py` | the parameter grid and per-block performance matrices |
| `pf.py` | trades to a vectorbt Portfolio, and its statistics |
| `validate.py` | CSCV/PBO, block bootstrap, search-width curve |
| `mega_sweep.py` | the 225,792-configuration sweep, with a locked holdout |
| `mega_analyse.py` | what the sweep bought — search width against locked-holdout rank |
| `anomalies.py` | conditional edge by pre-entry condition, with Benjamini-Hochberg control |
| `purged_cv.py` | purged, embargoed K-fold (Lopez de Prado ch. 7) |
| `metalabel.py` | meta-labelling: learn which signals to skip, tested on locked data |
| `smc.py` | smart-money-concept features — swing pivots, BOS, CHoCH, FVG, order blocks, liquidity sweeps, premium/discount |
| `test_smc.py` | correctness and causality checks for those features (17 assertions) |
| `smc_ml.py` | triple-barrier labels + gradient boosting on the SMC features, purged CV, locked holdout |

## Running it

```bash
pip3 install -r research/requirements.txt

# export the TypeScript engine's trades, then check the Python engine against them
npx tsx scripts/quant-export-trades.ts /tmp/ts_trades.csv 50 80 2
python3 research/crosscheck.py /tmp/ts_trades.csv 50 80 2

# the validation suite
python3 research/validate.py

# the maximum-width experiment (about 11 minutes), then its analysis
python3 research/mega_sweep.py --out /tmp/mega.npz
python3 research/mega_analyse.py /tmp/mega.npz

# conditional anomalies, and meta-labelling
python3 research/anomalies.py
python3 research/metalabel.py
```

Data files are git-ignored; see `data/README.md` for the ingest command.

---

# The model layer (`research/ml/`) and platform adapters (`research/platforms/`)

Added on request: LightGBM, XGBoost, CatBoost, PyTorch, scikit-learn, Optuna, MLflow, Ray, plus
Qlib, LEAN and NautilusTrader.

## The problem with adding these

Every library in that list makes it cheaper to search, and this repository has *measured* search as
harmful on this data. On 225,792 initial-balance configurations a **random** pick landed at the
51.5th percentile of locked-holdout P&L and the **best-of-143,536** landed at the **13.4th**, with
in-sample/out-of-sample rank correlation of **−0.079**. Optuna with 500 trials is that experiment
with a nicer API.

So the discipline is inside the API rather than beside it. The things easiest to skip are the
things that are not optional:

| built in | why |
| --- | --- |
| purged + embargoed folds | triple-barrier labels overlap; plain K-fold leaks the answer |
| scoring in **dollars after costs** | AUC 0.51 is worth money or nothing depending on the round turn |
| **within-session paired lift**, not level | on 2023–25 NQ the unconditional long earns +$9.17/trade, so any long-biased rule clears zero |
| **day-clustered t** | bars inside a session share an outcome; ignoring that turned −$95 at t=−2.70 into +$201 at t=+5.60 |
| an automatic **shuffled-label control** | the reader always sees what the same pipeline produces on noise |
| **trial count logged with every tuned metric** | `track.log_result` *raises* on a tuned score with no denominator |
| a **locked holdout** split on sessions | opened once, never straddling a day |

`deflate(t, n_trials)` reports the hurdle a searched result must clear — E[max z] ≈ √(2 ln n) — so
a t of 2.0 clears a 1-trial hurdle and fails a 500-trial one, and the table says so rather than
leaving it to the reader.

## Modules

```
research/ml/
  dataset.py   causal features + the barrier label, with presence flags for optional signals
  splits.py    PurgedKFold, session-aware locked_split, session_folds
  zoo.py       one interface over 7 model families incl. a PyTorch MLP
  metrics.py   auc, day_paired_lift, evaluate, deflate
  tune.py      Optuna search with the search cost priced; study_pbo via CSCV
  track.py     MLflow to a local SQLite store
  runner.py    the driver: all families in parallel via Ray, then tuning, then the holdout
  test_ml.py   26 checks on the properties that fail silently
```

Run it:

```bash
python3 research/ml/runner.py --trials 20 --splits 5     # full experiment
python3 research/ml/runner.py --no-ray --no-mlflow       # same numbers, no infrastructure
python3 research/ml/test_ml.py                           # 26 checks
mlflow ui --backend-store-uri sqlite:///research/mlruns.db
```

### One trap worth naming

`dataset.py` gives every optional feature a **presence flag and a sentinel** instead of a NaN. A
fair-value gap exists on ~30% of bars and an opening-range position does not exist before 10:00;
dropping incomplete rows requires an unfilled gap on *both* sides at once and cuts 292,908 bars to
**4,347** — 1.5% of the sample, and a badly biased 1.5%. This is the identical mistake that cut the
SMC study to 6,091 bars, made twice, six hours apart. Absence is information.

## Platforms

| platform | status here |
| --- | --- |
| **NautilusTrader** 1.221 | **runs.** Real order lifecycle and nanosecond clock; NQ RTH bars load into its matching engine. Worth having because it resolves a same-bar stop-and-target from its own rules, where this repo books the stop — a genuine cross-check. |
| **Qlib** 0.9.7 | **runs**, narrowly. Qlib's unit is (instrument, date) for cross-sectional daily equity work; this is one instrument on a minute calendar. Its model layer is used; its handler and splits are **not** — the default splits on a daily calendar and would mis-purge a minute-bar barrier label. |
| **LEAN** | **does not run in this container.** The `lean` CLI installs, but the engine runs in Docker and this container has the Docker *client* with no daemon, and no dotnet/mono. `lean_export.py` writes correctly formatted minute data and `lean_algorithm.py` is a complete algorithm; both are untested against the engine and nothing here claims a LEAN result. |

## Two environment facts

- **`download.pytorch.org` is blocked** by the egress policy (403 on CONNECT). Install torch from
  PyPI; `--index-url https://download.pytorch.org/whl/cpu` fails here.
- **NautilusTrader requires pandas < 3**, which downgrades pandas from 3.0.5 to 2.3.3 and makes
  vectorbt print an incompatibility warning. Verified harmless: vectorbt imports, and the studies in
  `docs/ib/` reproduce to the digit.
