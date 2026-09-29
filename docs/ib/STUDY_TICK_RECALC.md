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

## Addendum — two things the US100 runs exposed that are not the checkbox

A follow-up pair of Deep Backtests on US100, offered as a checkbox comparison, turned out to have
**Script execution 3 on both** — so they are not that comparison at all. What they do show is worse,
and neither defect had anything to do with tick recalculation.

| | range | capital | trades | profitable | PF | total P&L | max DD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| run A | 2022-12-31 → 2025-12-26 | **100K** | **850** | 23.65% | 1.642 | +9,350.80 (+9.35%) | 890.50 (0.85%) |
| run B | 2022-12-19 → 2025-12-26 | **1M** | **4,806** | 35.00% | 1.551 | +52,017.10 (+5.20%) | 4,297.50 (0.42%) |

### Capital silently rewrites the strategy

The same script over the same range produced **850 trades at 100K and 4,806 at 1M — 5.65×**. Twelve
extra days of range cannot do that. Capital can: with `pyramiding = 4` the ladder needs four units of
notional, and when the account cannot fund the next unit TradingView's broker emulator **rejects the
order** rather than reporting an error. The run then trades a different, smaller subset of its own
signals and reports the result as though it were the strategy.

The rejections are not random, which is what makes this worse than a sample-size problem. They
cluster exactly where price is high and the position is already large — so the underfunded run is
systematically dropping the late units of extended trends, which is where a Turtle ladder either
makes its year or gives it back. Run A's 23.65% win rate against run B's 35.00% is that selection,
not a different edge.

`unitQty` is now an input, and the HUD carries a fourth row that turns red with the required notional
and the current equity when the full ladder does not fit. Size the units down; do not raise capital
until the warning clears and call the difference performance.

### The script was charging nothing

Run B's Performance analysis reads **Commission load 0.00%**, and it is correct: the `strategy()`
declaration set no `commission_type`, no `commission_value` and no `slippage`. The file header had
claimed all along that the research assumed ~1.0 point spread and 0.25 point slippage — the research
did, the **script did not**. Every Strategy Tester run of it, including both above and the ETH runs in
the main study, was a zero-cost backtest of a system taking thousands of trades.

Both are now set in the declaration and both are meant to be edited per instrument. This was my
omission: every other Pine shipped on this branch carries `commission_value` and `slippage`, and this
one was missed.

**The general point.** A backtest has three ways to be wrong before its rules are ever in question:
the engine can re-evaluate mid-bar (the main study), the account can be too small to take the trades
(above), and the fills can be free (above). All three flatter. None of them is visible in the equity
curve — they are visible in the **trade count** and in **Commission load**, which is why those two
numbers are worth reading before the P&L.

## Correction — the first fix was a half-fix, and half-fixing it made it worse

Guarding the two state blocks was not enough, and I said it was. Re-run on US100 at 100K over the
same range with the corrected script still showed:

| Script execution | trades | profitable | PF | total P&L | max DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| all three boxes | **850** | 23.65% | **1.642** | +9,350.80 | 890.50 (0.85%) |
| bar close only | **762** | 18.37% | **1.188** | +3,386.40 | 1,788.50 (1.76%) |

Still 88 extra trades and a 0.45 swing in profit factor from a checkbox. The remaining leak was
created *by* the first fix.

`strategy.exit` was left unguarded on purpose — the reasoning was that it must stay a live intrabar
order. That reasoning confused **when the level is set** with **when it can trigger**, and the two
are separate: a strategy order persists until filled or cancelled, so placing it at the close still
leaves it live intrabar on every later bar.

Meanwhile, guarding the state blocks while leaving the exit call open opened a window that had not
existed before. A fill lands mid-bar; "On order fill" re-runs the script; `flat` is already false —
but `stopLvl` is still `na`, because the block that anchors it now waits for the close. `exitLevel`
falls through its own `na` branch to `chanExit`, the **channel low**, and a stop goes to the broker
at a level the strategy never chose. The position is cut early and re-entered. That is the 88 extra
trades, and it is why the boxes-on run shows *less* drawdown (0.85% against 1.76%) — an accidental
tighter stop flatters exactly the way the original defect did.

The condition that actually expresses the requirement is `lastCount > 0`: the state machine has
anchored to the position that is currently open. With that plus `barstate.isconfirmed`, placement
happens once, at the close, from settled state.

**The lesson is narrower than "guard everything" and more useful.** Guarding *some* of a coupled set
of statements is not a partial improvement — it desynchronises them, and a reader who has just been
told the script is now deterministic has less reason to check than before. Either every statement
that touches a piece of state reads it at the same instant, or none of them do.

## A misreading of my own, corrected

I read the `ETH` badge in the Strategy Tester's top-right corner as the instrument and referred to
"the ETH runs". On a TradingView futures chart that badge sits beside the clock and the `B-ADJ`
contract-adjustment marker, and it is the **session**: `ETH` = Electronic/Extended Trading Hours,
`RTH` = Regular Trading Hours. It says nothing about the symbol.

The correction matters because it changed the advice attached to it. On the strength of "ETH" I
recommended switching commission to **percent** with a crypto taker rate. The runs are on CME index
futures simulated through a retail futures broker, where fees are **per contract per side** and
percent commission is simply the wrong model — MNQ is about $0.72 a side, NQ about $2.05, and with
`pyramiding = 4` a full ladder pays that eight times over its life.

Two habits follow. Read the badge row as *timezone / session / contract adjustment*, not as a
ticker. And when a cost model is being chosen, ask what the instrument is rather than inferring it
from chrome.
