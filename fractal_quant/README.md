# fractal_quant

A fractal-based quant model for the **S&P 500 / Nasdaq-100 complex**
(SPY, ^GSPC, ES=F, QQQ, ^NDX, NQ=F). It is the production Python port of the
browser reference (`fractal_engine.html`), built per `FRACTAL_QUANT_HANDOFF.md`.

What it does, end to end:

1. **Measures the market's memory** with the **Hurst exponent** (rescaled-range
   *and* DFA estimators).
2. **Classifies the regime** — trending (H>0.55), mean-reverting (H<0.45), or
   random.
3. **Trades the matching tool** — **FRAMA** momentum in trends, a **z-score
   fade** in mean-reverting stretches, flat in noise.
4. **Backtests honestly** — no lookahead (decide at close *t*, execute *t+1*),
   net of transaction costs, with **walk-forward out-of-sample** validation.
5. **Forecasts volatility** for the options angle with a **Calvet–Fisher
   Markov-Switching Multifractal (MSM)** model, benchmarked against GARCH(1,1).

> ⚠️ **Educational tool, NOT investment advice.** An H ≠ 0.5 does *not* prove a
> tradable edge — it is statistically compatible with a random walk. A backtest
> is hindsight. Size small, paper-trade first. The honest caveats print at the
> bottom of every run.

---

## Install (one time)

```bash
pip install -r fractal_quant/requirements.txt
```

That installs numpy, pandas, scipy, matplotlib, yfinance, and (recommended)
`arch` (the GARCH benchmark), `pyarrow` (fast cache), and `pytest`.

## Run it right now (no setup beyond the install)

```bash
# Try it offline with realistic SIMULATED data — works with no network at all
python -m fractal_quant.cli --symbol QQQ --demo
python -m fractal_quant.cli --symbol SPY --demo --walk-forward --msm
```

`--demo` uses a deterministic regime-switching simulator (clearly labelled
`⚠ SIMULATED DEMO`, not real prices) so you can see the whole engine work
immediately. If you run **without** `--demo` and the live feed is blocked or
you're offline, it auto-falls back to the same demo with a warning rather than
crashing.

## Run it on real data

From the repository root:

```bash
# Basic backtest on QQQ (downloads 5y of data, caches it, prints stats + charts)
python -m fractal_quant.cli --symbol QQQ

# S&P 500 ETF, allow shorts, 1.5 bps/side costs
python -m fractal_quant.cli --symbol SPY --shorts --cost-bps 1.5

# Add honest out-of-sample validation + a parameter-sweep overfit check
python -m fractal_quant.cli --symbol QQQ --walk-forward

# Fit the MSM volatility model and benchmark it against GARCH(1,1)
python -m fractal_quant.cli --symbol SPY --msm --msm-k 5

# Use your own data instead of yfinance (CSV with Date,Close[,Open,High,Low])
python -m fractal_quant.cli --csv my_prices.csv --walk-forward --msm
```

Charts are written to `charts/<symbol>/` (price+FRAMA+regime, Hurst over time,
equity vs buy & hold, walk-forward OOS curve, parameter heatmap, vol forecast).

### Offline / restricted networks

If `query1.finance.yahoo.com` is blocked (yfinance returns 0 rows), you have
two options: `--demo` to run on simulated data immediately, or `--csv` with
data exported from Yahoo Finance, Stooq, or your broker (CSV needs a header row
with at least `Date,Close`; OHLC optional, improves FRAMA).

## Useful flags

| Flag | Meaning | Default |
|------|---------|---------|
| `--symbol` | SPY ^GSPC ES=F QQQ ^NDX NQ=F | QQQ |
| `--demo` | use SIMULATED data, no network needed | off |
| `--csv PATH` | load a CSV instead of yfinance | — |
| `--start` / `--period` | history start date / yfinance period | 5y |
| `--hwin` | Hurst rolling window | 120 |
| `--framaN` | FRAMA period (forced even) | 16 |
| `--zlook` | z-score lookback for the fade | 20 |
| `--shorts` | allow short positions in the fade | off |
| `--hurst rs\|dfa` | Hurst estimator (DFA is less biased) | rs |
| `--cost-bps` | transaction cost per side, basis points | 1.0 |
| `--walk-forward` | rolling OOS validation + param sweep | off |
| `--msm` / `--msm-k` | fit MSM vol model / number of components | off / 4 |
| `--no-charts` | skip saving PNGs | off |

## Project layout

```
fractal_quant/
  data.py        yfinance loader + parquet/CSV cache; CSV import; random-walk gen
  fractal.py     hurst_rs(), hurst_dfa(), frama(), fractal_dimension(), rolling_hurst()
  regime.py      regime classification with configurable thresholds
  strategy.py    regime-switching signal generation (trend/revert/random)
  backtest.py    vectorized no-lookahead backtest, costs, performance stats
  validation.py  walk-forward OOS validation + parameter sweep
  msm.py         Calvet-Fisher MSM vol model (MLE Hamilton filter) + GARCH benchmark
  report.py      matplotlib charts + printed stats table
  cli.py         `python -m fractal_quant.cli ...`
  tests/         random-walk H≈0.5, no-lookahead, MSM recovery, costs, ...
```

## Tests

```bash
python -m pytest fractal_quant/tests -q
```

Covers the acceptance criteria: random walk → H ∈ [0.45, 0.55]; the backtest
provably has no lookahead (shifting signals one more bar changes results);
costs reduce returns; and the MSM estimator recovers known parameters from
simulated data.

## Faithfulness to the reference

`fractal.py` reproduces `fractal_engine.html` to machine precision on identical
input data (Hurst and FRAMA agree to ~1e-14). To stay faithful, standard
deviations use *population* std (ddof=0), matching the JavaScript.
