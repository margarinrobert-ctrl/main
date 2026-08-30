# Donchian 07:00-11:00 scalps — the two Pine strategies

Two separate strategies, from the two designs in
[`docs/ib/SKILL_DONCHIAN_BVAR_UQ.md`](../../docs/ib/SKILL_DONCHIAN_BVAR_UQ.md) and
[`docs/ib/SKILL_DIRECTIONAL_ALPHA.md`](../../docs/ib/SKILL_DIRECTIONAL_ALPHA.md). What differs is
which layer picks the side.

| file | who picks the side | runs standalone | has a measured result |
| --- | --- | --- | --- |
| `DonchianTrendScalp_0700_1100.pine` | the Donchian rule | **yes** | yes — synthetic only, see below |
| `DonchianModelSide_0700_1100.pine` | a model you wire in | no — takes no trades until wired | **no strategy-level result exists** |

## 1. `DonchianTrendScalp_0700_1100.pine`

Donchian 20 breakout (channel excludes the current bar) + EMA 13 > 48 > 200 stacked + ADX(14) > 30,
stop 1.5 × ATR(14), target 3R, time stop 24 bars, entries 07:00–11:00 New York, flat at 11:00,
both sides. This is the configuration with the best **mean** out-of-sample R across twelve
independent simulated 50-year worlds — not the winner of any single world.

Measured **on synthetic data only** (`docs/ib/STUDY_SYNTH50_DONCHIAN.md` §4b): +0.0487R per trade,
Sharpe 0.41, profit factor 1.08, 35.7% win rate at a 1.95 payoff, 160 trades a year, max drawdown
54.7R. Three caveats live in the script's header and matter more than those numbers:

* a **matched control** — random entries, same barriers, same minute-of-day mix — earned +0.0355R
  in the same worlds, so about three quarters of the headline is not the rule;
* in a **martingale world** the same configuration earns −0.0266R and is beaten by its control in
  10 of 12 worlds: the EMA/ADX filter concentrates the book exactly where breakouts fail;
* the **3R target** is where a bar-discretisation artefact lives (+0.037R per trade at the
  simulation's resolution, 0.000R for a symmetric 1:1). TradingView fills intrabar and is not
  subject to it, so set the target to 1.0 if you want the geometry with no artefact in it.

## 2. `DonchianModelSide_0700_1100.pine`

The break is only the **event**; a model picks the side, sizes the trade and can veto it. Pine
cannot fit a Bayesian VAR or a deep ensemble, so the model's outputs are wired in through
`input.source` from a companion indicator plotted on the same chart:

| input | what it must be |
| --- | --- |
| `P(long wins)` | a **calibrated** probability, already **prior-shifted** so 0.5 means "nothing beyond the unconditional drift" |
| `epistemic sd` | optional — shrinks size toward the base rate and can veto unfamiliar states |
| `aleatoric sd` | optional — scales the stop so barrier probabilities stay stable across regimes |

**With nothing wired it takes no trades**, by design. On a sample where the index rose 89%,
"predicts direction" and "is long" are nearly the same statement, so a directional script that
silently defaults to long would look like an edge for years.

Sizing is fractional Kelly on the barrier bet (default ¼), shrunk toward the base rate in
proportion to the ensemble's disagreement, then capped by a hard per-trade dollar risk limit and a
contract cap — the formula in `research/dbu.py: kelly_size`.

## Before running either

* Both scripts pass `research/pine_lint.py`. **Neither has been compiled by TradingView** — a
  compiler error is a typo, not a changed strategy.
* Costs are set for NQ: $2.00 per side plus 2 ticks of slippage. The research modelled $4 per round
  turn plus one tick of spread each side plus one extra tick on stops, so Pine's flat slippage is
  slightly harsher on non-stop exits and slightly softer on stops.
* The three Pine traps this repository has shipped broken once each are handled: ATR is
  `ta.ema(ta.tr(true), 14)` and **not** `ta.atr`; the session goes through an explicit timezone
  because bare `hour`/`minute` are **exchange** time; and the Donchian channel excludes the current
  bar, without which `high >= highest(high, n)` is true on every bar that is its own n-bar high.
* Entries require `barstate.isconfirmed`, so the Strategy Tester's "Script execution" boxes cannot
  change the result.
