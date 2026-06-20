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
- **Daily 50% as support/resistance**: the midpoint of the prior daily candle is a
  directional bias gate — price *above* it ⇒ longs only (50% = support), *below* ⇒
  shorts only (50% = resistance). Set via `use_pd`.

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

## Data caveat (read this)

This environment has **no market-data network access** (Yahoo & co. are not
allowlisted), so by default the backtest runs on a **synthetic** 1-minute series.
The generator deliberately manufactures the patterns the strategy hunts for
(overnight drift, an 08:30 displacement leg that sweeps prior highs/lows and
reverses, fair-value gaps, a quiet afternoon) so the *whole pipeline is exercised
end-to-end* — but it is random noise with no genuine edge. **Negative expectancy on
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
