# ICT Sweep → Rejection Block — NQ1!

`ICTSweepRejectionBlock.pine` — a Pine v6 **strategy**. Paste into TradingView's Pine editor,
add to chart on `NQ1!`, read the Strategy Tester.

The script implements five steps and nothing else. Every input below maps to one of them.

## The five steps

**1. Mark out POI / liquidity pools.** Confirmed swing highs are buy-side liquidity, swing lows are
sell-side. Each pool is tagged as it forms:

- **failed swing** — a lower high or higher low, i.e. a swing that failed to take the previous one
- **engineered** — equal highs/lows within `eqTicks`
- **HTF PD array** — a swing from the higher timeframe (`htfTf`, default 1H)

Pools are drawn as rays and retired the moment price trades through them.

**2. Manipulation sweeps a key zone.** A bar whose *wick* pierces a pool but whose *close* returns
inside it — the level was respected, not broken. That candle becomes the **rejection block**: wick tip
to body edge. Set `keyOnly` to restrict sweeps to HTF PD arrays and engineered liquidity only.

**3. New internal level, then the retracement.** Within `mssBars`, a close must break the last internal
swing in the opposite direction (the MSS). That break is the new internal level. The script then waits
up to `fillBars` for price to retrace back into the POI. Entries are limit orders only — price has to
come back.

**4. Inside the POI: an OB or the RB.** If an order block (the last opposing candle in the leg) sits
*inside* the rejection block, the limit goes there for a tighter entry. Otherwise it goes at the
rejection block's body edge. Turn off with `useOB`.

**5. Target liquidity, ≥ 2R.** The target is the nearest untapped pool paying at least `minR`,
preferring failed swings, engineered liquidity and HTF PD arrays. If no pool qualifies it falls back to
a clean `minR` target.

## Stop and target

- **Stop** — beyond the rejection block's wick tip: above it on shorts (the "top of the RB"), below it
  on longs. Risk is therefore the height of the sweep wick plus `slBuf`, which is what keeps 2R
  reachable from nearby liquidity.
- **Target** — the liquidity pool, minimum 2R.

## Inputs

| Input | Step | Meaning |
|---|---|---|
| `pvLen` | 1 | Swing strength — larger = fewer, more significant pools |
| `eqTicks` | 1 | Tolerance for calling two swings equal (engineered) |
| `htfTf`, `htfPv` | 1 | Higher timeframe and swing strength for PD arrays |
| `keyOnly` | 2 | Only sweeps of HTF PD arrays / engineered liquidity count |
| `mssBars` | 3 | Max bars from the sweep to the structure shift |
| `fillBars` | 3 | Max bars to wait for the retracement to fill |
| `useOB` | 4 | Refine the entry to an order block inside the rejection block |
| `slBuf` | — | Ticks past the rejection block wick tip for the stop |
| `minR` | 5 | Minimum reward:risk |
| `qtyC` | — | Contracts per trade |

## If the report is empty

Work back through the chain — the chart shows where it breaks:

1. No `sweep` labels → pools are never swept with a close back inside. Lower `pvLen`, or turn `keyOnly` off.
2. `sweep` but no `MSS` labels → structure never shifts in time. Raise `mssBars`.
3. `MSS` but no fills → the retracement never reaches the POI. Raise `fillBars`.

## Limitations

- TradingView fills from OHLC only. Exits are attached to the pending entry so a same-bar stop-out is
  modelled, but enable **Bar Magnifier** for trustworthy fill sequencing.
- `NQ1!` is continuous — roll gaps sit in the series. Backtest inside a single quarter for a clean sample.
- HTF pivots publish `htfPv` HTF bars after the fact (`lookahead_off`, so nothing repaints, but levels
  appear later than a human would draw them).
- With Deep Backtesting on, trades appear only in the Strategy report, not on the chart. The pool rays,
  zone boxes and sweep/MSS labels still draw.

A fuller version with killzones, displacement/FVG filters, HTF premium-discount gating, risk-based
sizing and a setup funnel table is in this branch's git history (commit `0bc1968`).
