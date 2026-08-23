# Lower-timeframe "sniper" entries after an HTF signal — they cost money, and here is why

The idea: let the 30m or 60m BOS/CHoCH fire the setup, then drop to 1m, 5m or 15m and wait for a
Stochastic or ADX trigger to time a better entry. 1,011 configurations across two HTFs, three LTFs,
five trigger families, wait windows of 5–120 minutes, four Stochastic thresholds, four retrace
depths, three Stochastic periods, two ADX periods, and skip-vs-market on timeout.

This is a genuinely different question from `STUDY_ADX_STOCH.md`. There, a Stochastic veto on the
*signal bar* was contradictory by construction — a break of structure prints %K near 100 because a
break IS a new range extreme. Here the oscillator is read *after* the HTF bar closes, on a faster
series, where it has room to pull back. The objection does not apply. The idea deserved the test.

## The control had a bug, and finding it validated the engine

The first run showed the control — no trigger, just take the next LTF bar — returning **$7,094** on
the locked block against the HTF-only engine's **$8,932**, and varying by LTF (1m $7,094, 5m
$2,649, 15m $3,253). A control that differs from the thing it is controlling for is not a control.

Cause: `run_mtf` filled at `fire + 1` unconditionally. For a *trigger*, that is right — the trigger
is evaluated on bar `fire`'s close, so the fill is the next bar's open. For the *control* there is
nothing to wait for: the HTF signal is already known at the HTF close, so the fill is bar `s0`'s
own open. Using `fire + 1` for both inserted a one-LTF-bar delay into the control alone, which is
why it got worse as the LTF got slower.

Corrected, the control reproduces the HTF engine **exactly** — 141 trades, research $2,747, locked
$8,932, 44.0% win — and is **identical across 1m, 5m and 15m**. That identity is worth keeping:
the stop sits at 2×ATR and the target at 4×ATR, so no single bar ever spans both barriers. The
pessimistic ambiguous-bar rule never fires, and **exit resolution is a non-issue for this
strategy**. One class of backtest doubt closed.

## Every trigger family loses to doing nothing

Best cell of each family selected on research, then its locked result:

| trigger | HTF/LTF | wait | research | **LOCKED** |
| --- | --- | --- | --- | --- |
| **none — take the next open** | 30/any | — | $2,747 | **$8,932** |
| stochastic pullback then turn | 60/1 | 30m | $4,190 | **$245** |
| stochastic %K × %D | 60/1 | 5m | $4,302 | $3,307 |
| ADX(ltf) rising | 60/15 | 30m | $3,781 | **$597** |
| price retrace | 30/15 | 30m | $4,184 | $4,692 |

Every trigger beats the control **on research** — $4,190 to $4,302 against $2,747 — and none comes
close on the locked block. The best cell of all 1,011 on research returns $3,307 out of sample.
Median locked across every configuration: **$1,486**.

## The mechanism: waiting is adverse selection, not price improvement

| entry method | trades | net | win % | **$/trade** |
| --- | --- | --- | --- | --- |
| **every signal at the next open** | 141 | **$11,679** | 44.0% | **$83** |
| wait for a stochastic pullback | 122 | $5,768 | 43.4% | $47 |
| wait for %K × %D | 143 | $9,346 | 41.3% | $65 |
| wait for ADX to rise | 141 | $10,933 | 43.3% | $78 |
| wait for a 0.25 ATR retrace | 97 | $7,088 | 45.4% | $73 |

**If waiting bought a better price, $/trade would rise as n fell. It falls in every case.**

The retrace row is the most instructive: it *does* raise the win rate (45.4% vs 44.0%) while
lowering $/trade to $73. You win slightly more often, for less — which is what a filter that
removes the biggest winners looks like from the inside.

The reason is the same one already recorded twice in this work under "fill rate points the wrong
way" (gap fills, the Market Profile 80% rule). A breakout that never retraces is a breakout with
demand behind it. Requiring a pullback before entry is a rule that **systematically discards
exactly those**, and keeps the ones that stalled. The better fill on the trades you do get is worth
less than the trades you no longer get.

This also explains why the effect is strongest for the strictest trigger: the stochastic pullback
discards 19 of 141 signals and loses half the P&L.

## Verdict

Do not add a lower-timeframe entry trigger. The 30m signal should be taken at the next 30m open,
as specified. The "sniper entry" intuition is real — the fills genuinely are better — but it is
paid for out of trade selection at a worse rate than it earns.

Reproduce with `python research/mtf_sniper.py`.
