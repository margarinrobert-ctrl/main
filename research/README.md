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

## Running it

```bash
pip3 install -r research/requirements.txt

# export the TypeScript engine's trades, then check the Python engine against them
npx tsx scripts/quant-export-trades.ts /tmp/ts_trades.csv 50 80 2
python3 research/crosscheck.py /tmp/ts_trades.csv 50 80 2

# the validation suite
python3 research/validate.py
```

Data files are git-ignored; see `data/README.md` for the ingest command.
