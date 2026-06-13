# IFVG + Liquidity Sweep Model (Dodgy DD style) — TradingView Pine v6

Two Pine Script v6 files implementing the **Dodgy DD Inversion Fair Value Gap (IFVG)**
model for **Nasdaq‑100 futures (NQ/MNQ)** on the **1‑minute** chart, distilled from the
strategy guide PDF.

| File | Type | Purpose |
|------|------|---------|
| `IFVG_LiquiditySweep_Indicator.pine` | `indicator` | Draws FVGs, marks inversions (IFVGs), liquidity sweeps, PDH/PDL, EMA, and prints A+ long/short signals with the suggested limit‑retest entry edge. Includes `alertcondition`s. |
| `IFVG_LiquiditySweep_Strategy.pine` | `strategy` | Backtests the model end‑to‑end: entry, stop, 1:2 target, optional break‑even, killzone + EOD flatten. |

## The model (exactly as in the guide)

A valid setup follows a strict chronological sequence:

1. **Liquidity Sweep** — price purges a key level (Previous Day High/Low or a swing
   high/low) and *rejects back through it* (wick beyond, body closes back inside). This
   is the "manipulation leg" that traps breakout traders.
2. **Displacement** — an aggressive reversal candle (body ≥ `dispMult × ATR`).
3. **FVG + Inversion** — an opposing 3‑candle Fair Value Gap is **closed through by a
   candle body** (a wick is *not* enough):
   - Bullish FVG closed *below* → flips to a **Bearish IFVG** → short bias.
   - Bearish FVG closed *above* → flips to a **Bullish IFVG** → long bias.
4. **Entry** — limit at the inverted gap edge (the retest), or market on the inversion
   close. **Stop** beyond the swept swing; **target** a fixed 1:2 R:R (default), with an
   optional move to break‑even after +1R.

### A+ confluences (all toggleable)
- **50‑EMA trend filter** — longs only above EMA, shorts only below.
- **Killzones** — NY `08:30–11:00` and London `02:00–05:00` (New York time by default).
- **Sweep requirement** — an external‑liquidity sweep must have happened within
  `sweepLookback` bars before the inversion (the "fuel").
- **Displacement** — rejects weak inversion candles.
- **Double‑FVG reject** — skips stacked same‑direction gaps ("gapping sack" / over‑extension).

## How to use

1. Open TradingView → **Pine Editor**.
2. Paste a file's contents → **Add to chart**.
3. Set the chart to **NQ1!/MNQ1!**, **1‑minute**. For the strategy, open the
   **Strategy Tester** tab to see the report.
4. Tune inputs in the settings gear (grouped: Fair Value Gap, Liquidity Sweep,
   Displacement, Trend, Time, Execution, Risk Management).

## Notes on "making it profitable"

The defaults are deliberately **selective** — they encode the guide's "A+" filters so the
strategy only fires high‑quality setups rather than every gap. Realised performance
depends entirely on the **symbol, date range, session and broker fills** you load, so
treat the numbers in the Strategy Tester as your own backtest, and walk‑forward before
risking capital. Practical tuning levers, in order of impact:

- **`rr`** (Reward:Risk): 1.5–2.0 trades more often / wins more often; 2.0–3.0 fewer wins,
  bigger winners.
- **`minGapTicks`** / **`dispMult`**: raise to take fewer, cleaner setups.
- **Killzones** + **EOD flatten**: keep trading inside high‑volatility windows and avoid
  overnight gap risk.
- **`useBE` / `beTrigger`**: the guide's defensive break‑even rule — protects prop‑firm
  trailing drawdown at the cost of more scratch trades.
- Commission/slippage are pre‑set to realistic micro‑futures values; adjust for your
  account and the contract you trade.

This is an educational implementation of a publicly described discretionary model. It is
**not financial advice**, and **past backtest performance does not guarantee future
results.**
