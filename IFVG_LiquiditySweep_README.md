# IFVG + Liquidity Sweep Model (Dodgy DD / ICT) — TradingView Pine v6

Two Pine Script v6 files implementing the **Dodgy DD Inversion Fair Value Gap (IFVG)**
model for **Nasdaq‑100 futures (NQ/MNQ)** on the **1‑minute** chart. Built purely on the
**ICT / Smart‑Money concepts** from the two source documents (the IFVG strategy guide and
*Dodgy's Ultimate Trading Course*) — **no moving‑average filter**.

| File | Type | Purpose |
|------|------|---------|
| `IFVG_LiquiditySweep_Indicator.pine` | `indicator` | Draws FVGs, marks inversions (IFVGs), liquidity sweeps, EQH/EQL, PDH/PDL, structure bias, and prints A+ long/short signals + the limit‑retest edge. Has `alertcondition`s. |
| `IFVG_LiquiditySweep_Strategy.pine` | `strategy` | Backtests the model end‑to‑end: entry, stop, target, ITH/ITL break‑even, killzone + EOD flatten. |

## The model (chronological sequence)

1. **Liquidity Sweep** — price purges a key pool and *rejects back through it* (the
   "manipulation leg" that stops out retail). Pools used, in the course's order of
   preference: **Equal Highs/Lows (EQH/EQL)** → **PDH/PDL** → **swing highs/lows**.
2. **Displacement** — an aggressive reversal candle (body ≥ `dispMult × ATR`).
3. **FVG + Inversion** — an opposing 3‑candle FVG is **closed through by a candle body**
   (a wick is *not* enough):
   - Bullish FVG closed *below* → **Bearish IFVG** → short bias.
   - Bearish FVG closed *above* → **Bullish IFVG** → long bias.
4. **Entry** — market on the inversion close (the course's default) or a limit at the
   inverted gap edge for better R:R.

## ICT context filters (these replace the EMA)

- **Market‑Structure Bias (BOS / MSS)** — directional context from body‑close breaks of
  swing points. Longs only while structure is bullish, shorts only while bearish.
- **SMT Divergence (NQ vs ES)** — confirms a sweep is genuine distribution/accumulation,
  not continuation. Optional (off by default; needs the correlated symbol's data).
- **Killzones + ICT Macros** — NY AM / Lunch / PM and London windows, plus the optional
  20‑minute macro windows (incl. the 10:00 reversal the course highlights).
- **Singular‑FVG filter** — rejects consecutive ("double") FVGs / over‑extension.

## Risk management (from the course)

- **Stop** — two modes:
  - `IFVG close` *(default, preferred)* — invalidate when a candle **closes back through
    the inverted gap**; a hard stop just beyond the gap is kept as a safety net.
  - `Swing high/low` — hard stop beyond the swept swing (easier to size, worse R:R).
- **Take‑profit** — fixed R:R (default **1:2**) toward the opposing liquidity draw.
- **Break‑even** — stop is moved to BE once the nearest **Internal Trading High/Low
  (ITH/ITL)** is taken (the course's "free trade" rule).
- **Premature‑liquidity‑take invalidation** — a pending limit is cancelled if price
  reaches the target before the entry fills (the objective is already met).
- **EOD flatten** — closes anything left at session end.

## Futures & Deep Backtesting

**Why a futures backtest can show zero trades ("This report requires trade data").**
A TradingView strategy will not enter a position it cannot afford, and futures have a
**Point Value / contract multiplier** (NQ = **$20/point**), so one NQ contract at ~20,000
costs ~**$400,000** of notional. If `initial_capital` (with full margin) can't cover that,
the tester places **no trades at all** — which is exactly why a strategy can work on an
index (point value ≈ 1) but be empty on NQ. This is configured in the `strategy()` header:

- `initial_capital = 100000`
- `margin_long = 5`, `margin_short = 5` → simulates ~5% futures leverage, giving
  `100000 / 0.05 = $2,000,000` of buying power, so 1 NQ/MNQ contract is always affordable.

If you increase position size, raise `initial_capital` or lower the margin further.

The SMT‑divergence filter compares the chart symbol against a **Correlated symbol**
(default `CME_MINI:ES1!`). That was **not** the cause of the empty futures report — the
capital/Point‑Value issue above was — so it is left as the original ES comparison.

## How to use

1. TradingView → **Pine Editor** → paste a file → **Add to chart**.
2. Chart = **NQ1!/MNQ1!**, **1‑minute**. For the strategy, open the **Strategy Tester**.
3. Tune inputs via the gear (grouped: FVG, Liquidity Sweep, Market Structure, SMT,
   Displacement, Time, Execution, Risk).

## Notes on profitability

The defaults encode the course's selective "A+" criteria so the system trades quality
setups, not every gap. Realised performance depends entirely on the **symbol, date range,
session and fills** you load. Dodgy himself stresses that inversions are best **forward‑
tested live** (instant backtest candles miss the discretionary daily‑bias read), so treat
the Strategy Tester numbers as your own sample and walk‑forward before risking capital.
Highest‑impact tuning levers: `rr`, `minGapTicks`/`dispMult`, the killzone toggles, the
stop method, and the EQH/EQL tolerance.

Educational implementation of a publicly described discretionary model. **Not financial
advice; past backtest performance does not guarantee future results.**
