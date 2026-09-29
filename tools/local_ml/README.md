# Running the breakout ML on your own machine

One file, no dependency on this repo: `breakout_ml.py`. It reproduces the pipeline behind
`STUDY_V28_ML_CAPACITY` — same label, same purged cross-validation, same shuffled-label null, same
selectivity gate.

## Setup

```bash
pip install -r requirements.txt          # numpy pandas scipy scikit-learn xgboost lightgbm
python breakout_ml.py --csv YOUR_BARS.csv --stage inspect
```

Start with `--stage inspect`. It prints what the loader understood — bar count, span, spacing, and
the first three parsed rows — so you can catch a misread timestamp or a reversed file before
spending twenty minutes on models.

## Your data

Any OHLC(V) export with a timestamp column. The loader auto-detects the **delimiter** (comma, tab,
semicolon, pipe), the **row order** (newest-first files are flipped), and the **timestamp format**,
including day-first dates. Seven different export formats have been through this project and those
three are the differences that actually bite.

Column names are matched case- and space-insensitively: `Date`/`DateTime`/`Time`/`Timestamp`, then
`Open`/`High`/`Low`/`Close` (or `O`/`H`/`L`/`C`), and optionally `Volume`/`TickVolume`.

**Check the clock.** Broker exports are rarely in your session's timezone. `--tz-shift 7` adds seven
hours; use whatever puts the cash-open volume spike where you expect it. This matters because two of
the features are minute-of-day and day-of-week.

## Running it

```bash
# the shipped configuration
python breakout_ml.py --csv NQ.csv --tf 30 --chop-max 40

# faster — skip the neural nets, which are the slow part and the worst performers
python breakout_ml.py --csv NQ.csv --tf 30 --chop-max 40 --no-deep

# just the strategy, no ML
python breakout_ml.py --csv NQ.csv --tf 30 --stage baseline

# shorts
python breakout_ml.py --csv NQ.csv --tf 30 --side -1

# export every trade with its features, to model elsewhere
python breakout_ml.py --csv NQ.csv --tf 30 --out trades.csv
```

**Set your costs.** `--cost-points` is the round-turn fee **in points of the instrument you are
running**, which is the single easiest thing to get wrong. MNQ on a discount broker is `0.72`. A
number borrowed from another instrument is meaningless: 1.72 points is 3.7% of NQ's 2×ATR stop and
**54% of gold's**, and charging one in the other once turned a profit factor of 0.94 into 0.35.

## What each stage prints, and how to read it

**`baseline`** — the strategy alone. Signals, trades after the position lock, R per trade, profit
factor, drawdown in R, and the p90 of R. Note the gap between signals and trades: the position lock
enforces one trade at a time, and without it a backtest silently holds a dozen overlapping
positions.

**`ladder`** — a capacity ladder from a constant through logistic regression, forests and gradient
boosting to deep networks, on identical purged folds. Every row has a **shuffled-label twin** beside
it. That twin is the floor the pipeline produces from pure noise — leakage, class imbalance, fold
luck, the optimisation itself. On the reference run the deepest network's shuffled twin scored
**+0.2633 R** on top-decile P&L, higher than any model managed on real labels, which is how you
learn that column is noise rather than signal.

Read the AUC column top to bottom. If it falls as capacity rises, the constraint is signal-to-noise
and no architecture fixes that.

**`locked`** — trained on the first 65% of trades, the rest read once, then the **selectivity gate**:
the model's preferred half against 400 random halves of the same size. A filter that keeps half the
signals raises profit factor by being restrictive; beating a random half is the only honest bar.
`p` is the share of random halves that did better, so **low is good**.

Then the tail table. If **win% rises while p90 R falls**, the model bought its win rate by
discarding the big winners. A breakout system earns in the tail, so that trade is usually a losing
one — and it is invisible in AUC.

## Why your numbers won't match the study exactly

The reference figures come from the full research harness. This file differs in three ways, all
deliberate simplifications for portability:

1. **Slippage is flat**, not scaled by bar speed. The harness charges more in fast bars, which is
   where a stop system exits — so this version is slightly optimistic on stopped trades.
2. **The research/locked split is by trade count**, not by session. Close, not identical.
3. **Fewer features** — about 60 here against 141 there. The volatility block is the same; the
   momentum pool is trimmed.

The *shape* reproduces: AUC falling with depth, shuffled twins near 0.48, p90 R dropping in every
selected set. The absolute R values will differ by a few hundredths.

## The honest prior

On this data, across 110,250-configuration sweeps, 16.2M generated strategies and this ladder, model
capacity has never been the binding constraint — signal-to-noise has. The two best models in the
reference run were a **regularised random forest** and **logistic regression**; the deepest network
scored 0.5060, which is chance.

That is a statement about the data, not about your machine or your library versions. If you feed it
a different instrument and capacity suddenly starts paying, check the shuffled twin and the
selectivity gate before believing it — in that order.
