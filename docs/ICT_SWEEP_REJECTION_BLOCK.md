# ICT Sweep → Rejection Block — NQ1! backtest

`ICTSweepRejectionBlock.pine` — a Pine v6 **strategy** (not an indicator) that mechanises the
liquidity-sweep → rejection-block model on NQ futures. Paste it into TradingView's Pine editor,
"Add to chart" on `NQ1!`, and read the Strategy Tester.

The stop is placed beyond the **rejection block's wick tip** and the target is **resting liquidity**,
filtered so only setups paying **≥ 2R** are ever taken.

---

## The five steps, and where each one lives in the code

| # | Step | Implementation |
|---|------|----------------|
| 1 | **Mark POI / liquidity pools** | Every confirmed `ta.pivothigh`/`ta.pivotlow` becomes a pool: BSL above highs, SSL below lows. Each is tagged `engineered` (equal high/low within a tick tolerance), `weak` (a failed swing — a lower high or higher low), or `HTF` (a swing from the higher-timeframe PD array). Pools are drawn as rays and retired the moment price trades through them. |
| 2 | **Manipulation sweeping a key zone** | A bar whose *wick* pierces a qualifying pool but whose *close* returns inside it. The level was respected, not broken. The wick that did it becomes the rejection block: `[wick tip … farthest body edge]` across a small candle cluster, exactly as the ICT definition draws it. |
| 3 | **New internal level + retracement** | Within `mssBars` the close must break the last internal swing in the opposite direction, with displacement (`bar range ≥ ATR × mult`) and an FVG inside the leg. That break is the new internal level. The script then waits for the leg to *extend* — so an inducement actually forms below/above the POI — before arming anything. |
| 4 | **OB / RB inside the POI** | The order block is the last opposing candle inside the displacement leg; the rejection block is the sweep wick. A limit order is placed at the POI's proximal edge (or 50% / distal). No market entries — price must come back. |
| 5 | **Target liquidity, ≥ 2R** | The target scan walks the opposite pool book for the *nearest* level that still pays `minR`, preferring failed swings, engineered liquidity and HTF PD arrays. If nothing qualifies the setup is discarded rather than downgraded. |

**Stop:** `rejection block wick tip ± buffer`. Because the RB sits at the 80–90% retracement of the
setup leg, this stop is materially tighter than the equivalent order-block stop — which is the only
reason a nearby liquidity target can clear 2R at all. A `POI extreme (tighter)` option is available if
you want the classic OB stop instead.

---

## Defaults

Tuned for **NQ1! on the 5-minute chart**:

- HTF PD arrays from the **1H**, longs only in HTF discount / shorts only in HTF premium.
- Sweeps only count on **HTF PD arrays + engineered liquidity** — not on every internal pivot.
- NY AM (09:30–11:00) and NY PM (13:30–16:00) killzones, flat at the RTH close.
- Risk **1% of equity** per trade, max 3 entries/day, position size derived from the actual stop distance
  (`riskCash / (stopPoints × pointvalue)`), so a wide stop buys fewer contracts rather than more risk.
- $2.25/contract commission and 1 tick of slippage.

## Reading the funnel table

The bottom-right table is the tuning instrument:

```
sweeps          how many qualifying sweeps fired
MSS confirmed   how many survived displacement + FVG
limits armed    how many produced a valid POI, stop and ≥2R target
filled          how many the retracement actually reached
no 2.0R target  killed because no liquidity paid the minimum
risk too large  killed because one contract exceeded the risk budget
```

If `sweeps` is healthy but `MSS confirmed` is near zero, loosen `dispMult` or raise `mssBars`.
If `limits armed` collapses into `no 2.0R target`, your stop is too wide for the nearby pools — try the
`POI extreme` stop reference, or a larger `pvLen` so pools sit further apart.
If `filled` is a small fraction of `limits armed`, move the entry to the proximal edge and raise `fillBars`.

## Suggested loosening order

The defaults are deliberately strict — expect a handful of A+ setups per month, not per day. To widen:

1. `sweepSrc` → `Any untapped pool`
2. killzones → add London, or turn `useKZ` off
3. `needFVG` → off
4. `dispMult` → 1.0
5. `usePD` → off

Change one at a time and watch the funnel, not just net profit.

## Honest limitations

- **Intrabar sequencing.** TradingView fills from OHLC only. When a bar contains both the limit and the
  stop, the tester guesses the order. Exits are attached to the *pending* entry so same-bar stop-outs are
  at least modelled, but enable **Bar Magnifier** (paid plans) for trustworthy fill sequencing.
- **`NQ1!` is a continuous contract.** Roll gaps sit in the series; levels mapped before a roll refer to a
  different contract's prices. For a clean sample, backtest a single quarter between rolls, or run on a
  back-adjusted continuous symbol.
- **HTF pivots are confirmed, not predicted.** `request.security` uses `lookahead_off` and the pivot only
  publishes `htfPv` HTF bars after the fact, so nothing repaints — but an HTF level appears on the chart
  later than a human would have drawn it.
- **Pool book is capped** at `maxPool` levels per side; the oldest untapped levels are dropped.
- Backtest results are not forward results. Size the sample by the funnel's `filled` count — a strategy
  with 20 trades has told you nothing.
