# IFVG + Liquidity Sweep (ICT) — VectorBT strategy & backtest

A Python/VectorBT port of the Pine v6 strategy *"IFVG + Liquidity Sweep Model
(Dodgy DD / ICT)"*. It reproduces the ICT smart-money workflow as a mechanical,
backtestable model and adds a grid-search optimiser.

```
liquidity sweep (ERL)  →  displacement  →  FVG inversion (IFVG)  →  entry
```

with the same context filters as the Pine source: market-structure bias (BOS/MSS),
killzones + ICT macros, displacement (`body ≥ ATR × mult`), the singular-FVG ("reject
double FVG") rule, an FVG size band, and prop-firm daily limits (max trades/day,
two-losses-and-done).

### Trade management (current defaults)

- **Sweep → IFVG must form short-term**: the inversion has to print within
  `sweep_lookback` bars of the liquidity sweep (default 5 ≈ 1–5 min on 1-min data).
- **TP1 at 1:1 R:R**: scale `scale_pct`% (default 50%) off at +1R (`rr = 1.0`).
- **Break-even at the internal high/low**: once price takes the nearest internal
  swing (ITH/ITL), the runner's stop moves to entry (`use_be`).
- **Runner targets the external swing high/low** (opposing liquidity draw); if no
  external pool is available it falls back to `runner_rr` (default 2R).
- **Pure 1:1 mode** (`full_tp_1r=True`): take 100% off at the 1R target with a
  symmetric hard stop — no partial/BE/runner/IFVG-early-exit. Use this when you want a
  clean, readable win rate (≈ P(price reaches 1R before the stop), ~50%+ on data that
  actually delivers). The default scale+runner style instead front-loads a 1R partial
  and lets a runner chase external liquidity, which trades win rate for tail upside.
- **Daily 50% as support/resistance**: the midpoint of the prior daily candle is a
  directional bias gate — price *above* it ⇒ longs only (50% = support), *below* ⇒
  shorts only (50% = resistance). Set via `use_pd`.

### Liquidity sweep set (ERL)

A sweep (wick beyond a level, body rejects back) off **any** enabled level satisfies
the "sweep before IFVG" requirement, and the same levels seed the runner's external
draw-on-liquidity target. Covered: old swing highs/lows (BSL/SSL), equal highs/lows,
PDH/PDL, and **session ranges** — Asian (20:00–00:00), London (02:00–05:00) and NY AM
(08:30–12:00) NY. Each session's high/low freezes when the session ends and stays
sweepable for the rest of the ICT day (so London can raid Asian, NY can raid London),
resetting at the 18:00 NY ICT-day open. Toggles: `use_sessions`, `use_asian_range`,
`use_london_range`, `use_ny_range`. (PWH/PWL and trendline liquidity are not yet
implemented.)

## Layout

| file | what it does |
|------|--------------|
| `strategy.py` | Event-driven port of the Pine logic. Emits long/short entry+exit signals and exact fill prices. `Params` mirrors every Pine input. |
| `backtest.py` | Feeds the signals into `vbt.Portfolio.from_signals` with NQ futures economics ($20/pt, $2.04/order, 2-tick slippage). Returns the portfolio + a compact stats dict. |
| `data.py` | Loads a real 1-minute OHLCV CSV if present; otherwise generates a reproducible synthetic NQ-like series with intraday ICT structure. |
| `optimize.py` | Grid search over the highest-impact parameters, ranked by a return/drawdown + profit-factor objective with a trade-count floor. |
| `main.py` | CLI tying it together. |

## Run it

```bash
# single backtest on synthetic data (default params)
python -m vectorbt_ifvg.main

# grid search, then backtest the winning configuration
python -m vectorbt_ifvg.main --optimize           # full grid (slower)
python -m vectorbt_ifvg.main --optimize --quick    # small grid (fast)

# use your own data
python -m vectorbt_ifvg.main --csv mydata/nq_1min.csv --optimize
```

CSV columns: `datetime, open, high, low, close, volume` (tz-naive datetimes are
treated as America/New_York). Drop a `.csv` in `vectorbt_ifvg/data/` and it is
picked up automatically.

## Real data: Nasdaq-100 1-minute (free, works in-sandbox)

Market-data APIs (Yahoo etc.) are blocked here, but `raw.githubusercontent.com` is
reachable, so `fetch_nas100.py` pulls **real OANDA Nasdaq-100 (`NAS100_USD`) 1-minute
data** (2005–2020) — the same underlying the NQ future tracks — from the public
`FutureSharks/financial-data` repo, cleans it, and drops a CSV in `data/`:

```bash
python -m vectorbt_ifvg.fetch_nas100 --years 2019
python -m vectorbt_ifvg.main                 # auto-picks up the CSV
```

It's the index (NQ *proxy*), so dollar figures use NQ economics ($20/pt) as an
approximation; the win rate / profit factor / % return are the real-market numbers.

### What the real data says (honest result)

Walk-forward (optimise on 2018, test untouched 2017 & 2019), pure-1:1 exit:

| | 2018 (in-sample best) | 2017 (OOS) | 2019 (OOS) |
|---|---|---|---|
| return | +1.23% | −0.93% | −0.18% |
| win rate | 63% | 11% | 50% |
| profit factor | 1.63 | 0.30 | 0.91 |

The win rate now reads sensibly (~50–63%), but the in-sample edge **does not survive
out-of-sample** — the strategy is roughly break-even on real Nasdaq-100 and has no
edge that generalises after costs. That is the truthful outcome for this mechanical
ICT model; treat any single-period positive as overfitting until walk-forward says
otherwise.

### Rolling walk-forward (the rigorous test)

`walk_forward.py` optimises on each year and tests the winner on the *next, untouched*
year, then pools every out-of-sample year (real Nasdaq-100 1-min, 2015→2020):

| train→test | OOS return | win% | PF |
|---|---|---|---|
| 2015→2016 | −0.75% | 41% | 0.64 |
| 2016→2017 | −1.23% | 17% | 0.33 |
| 2017→2018 | −0.94% | 54% | 0.89 |
| 2018→2019 | −0.18% | 50% | 0.91 |
| 2019→2020 | −0.66% | 64% | 0.93 |
| **pooled (163 trades)** | **−3.76%** | **50.3%** | **0.84** |

**Every out-of-sample year loses.** Win rate is a healthy ~50%, but profit factor < 1
— losers outweigh winners after costs. Run it yourself:

```bash
python -m vectorbt_ifvg.fetch_nas100 --years 2015 2016 2017 2018 2019 2020 \
    --out vectorbt_ifvg/data/nas100_2015_2020.csv
python -m vectorbt_ifvg.walk_forward
```

**Conclusion:** on real Nasdaq-100 data this mechanical IFVG/liquidity-sweep model has
no durable edge. The framework (signals, VectorBT accounting, optimiser, walk-forward)
is correct and reusable; the *strategy* doesn't make money out-of-sample. Plug in
genuine NQ-futures 1-min data to confirm on the exact contract, but expect the same.

### Law-of-large-numbers test (~1,000,000 synthetic trades)

`big_sample.py` accumulates ~1e6 trades across many synthetic seeds with filters open
(pure 1:1, the raw IFVG-inversion entry) to converge the distribution:

| (1,002,694 trades) | win rate | profit factor | mean/trade | t-stat |
|---|---|---|---|---|
| GROSS (no costs) | 40.98% | 0.796 | −$18.57 | −101.97 |
| NET (commission+slippage) | 40.91% | 0.595 | −$42.65 | −234.19 |

Even **before costs** the raw entry is significantly **negative** (t ≈ −102): on a
million trades the IFVG-inversion entry has no positive edge — it's slightly
anti-predictive on this data and strongly negative after costs. This agrees with the
real-data walk-forward. (The filtered "robust" preset reads ~50–60% win because the
filters *select* a subset; the entry itself carries no edge.) Repro:

```bash
python -m vectorbt_ifvg.big_sample --target 1000000   # ~33 min
```

## Synthetic-data caveat (read this)

This environment has **no market-data network access** (Yahoo & co. are not
allowlisted), so by default the backtest runs on a **synthetic** 1-minute series.
The generator now spans the **full Globex day (18:00 → 16:00 NY)** so every ICT
session (Asian, London, NY) builds a range a later session can raid, and it
manufactures the patterns the strategy hunts for (session drifts, an 08:30
displacement leg that sweeps prior highs/lows and reverses, fair-value gaps) so the
*whole pipeline is exercised end-to-end* — but it is random noise with no genuine edge. **Negative expectancy on
synthetic data is the expected, honest result and says nothing about the real
strategy.** Point the tool at real NQ/MNQ 1-minute data (via `--csv`) for any
conclusion about performance.

## Fidelity notes vs. the Pine source

- Entries fill at the **next bar's open** (market) or when price trades the inverted
  gap edge within the limit-expiry window (limit retrace) — no same-bar lookahead.
- Exits are resolved by walking bars forward, taking the first of: hard stop, take
  profit, "IFVG-close" invalidation, or end-of-session flatten. A stop is assumed to
  fill before the TP on the same bar (worst case).
- Partial scaling at ITH/ITL is approximated by break-even handling on a single
  runner exit (`use_scale`/`use_be` toggle the BE-after-ITH behaviour).
- SMT divergence needs a correlated feed and is **off by default** (matches the Pine
  default); it would require a second 1-minute series (ES/YM/DXY).
```
