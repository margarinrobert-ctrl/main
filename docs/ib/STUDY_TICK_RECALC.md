# `barstate.isconfirmed` on the entries is not enough — the state machine needs it too

A Deep Backtest of `pine/turtle/TURTLE_LONG_strategy.pine`, same chart, same range, same preset.
The only thing changed between the two runs is the Strategy Tester's **Script execution** checkboxes:

| Script execution | total P&L | max drawdown | profitable | trades | PF |
| --- | ---: | ---: | ---: | ---: | ---: |
| bar close + order fill + realtime tick | **+62,278.50 (+62.28%)** | 3,325.50 (3.16%) | 36.34% | **14,462** | **1.416** |
| bar close only | **−913.50 (−0.91%)** | 9,217.00 (8.88%) | 29.50% | **11,398** | **0.994** |

**The bar-close run is the correct one.** The other is an artifact, and the trade count says so before
any of the money does: the rules did not change, yet 3,064 more fills appeared — 27% more trades out
of the same bars.

## Where it comes from

The script already guarded its **entries** with `barstate.isconfirmed`, which is the trap this
repository documented once before. That is necessary and it is not sufficient. Two blocks of
mutable state were left unguarded:

```pine
if strategy.position_size == 0 and lastCount > 0
    lastWin := close > firstFill        // <- `close` mid-bar is the CURRENT PRICE
...
if strategy.opentrades > lastCount
    anchorAtr = na(pendAtr) ? atrN : pendAtr
    stopLvl  := fillPx - atrMult * anchorAtr
```

When "On order fill" or "On realtime bar tick" is ticked, the entire script re-executes *inside* the
bar. On such a pass `close` is the price at that instant, not the bar's close. `lastWin` is computed
from `close`, and **`lastWin` drives the System 1 skip rule** — the rule that decides whether a
20-bar breakout is taken at all. So the unguarded version chooses which breakouts to trade using a
price the bar-close version cannot see. That is the 27%.

`anchorAtr` has the same defect one level down: a mid-bar `atrN` is a partly-formed ATR, so every
stop and every pyramid step gets anchored to a number that does not exist yet at that point in the
bar. It shows up as the drawdown difference — 3.16% against 8.88%.

## The shape of the tell

Note which direction the artifact runs. More frequent re-evaluation produced a **higher** win rate
(36.34% against 29.50%) and **less than half** the drawdown. Extra recalculation cannot legitimately
improve a fill — `strategy.exit(stop=)` is already an intrabar order regardless of the checkboxes —
so a strategy that gets *better* as the engine looks at it more often is a strategy reading
something it should not have. **If a checkbox changes the report, the report is about the checkbox.**

## The fix

Guard every block that writes `var` state, not just the ones that place orders:

```pine
if barstate.isconfirmed and strategy.position_size == 0 and lastCount > 0
if barstate.isconfirmed and strategy.opentrades > lastCount
```

`strategy.exit` itself stays unguarded — it must remain an intrabar order — but the level it is
handed now derives only from confirmed data. With the guards in place all three checkbox
combinations produce the identical report, which is the property that makes a backtest worth reading
at all.

## The general rule

In Pine, the question is not "does this line place an order". It is **"does this line read a series
that differs mid-bar, and does anything durable depend on the answer"**. `close`, `high`, `low`,
`ta.atr`, `ta.dmi`, `strategy.opentrades` and everything derived from them all differ mid-bar. A
`var` written from any of them is a decision frozen at an arbitrary instant inside the bar. Guard it.
