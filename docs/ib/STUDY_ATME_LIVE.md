# The NQ ATME configuration on the true 1-minute path

The ATME sweep selected its NQ configuration on 5-minute bars. Two of that engine's decisions are
assumptions rather than observations, and a limit-entry strategy is built entirely out of both:

* whether a resting limit was **reached inside a bar**, and
* once filled, whether the **stop or the target came first** when one bar touched both.

`research/atme/livesim.py` removes both. The signal is still computed on the 5-minute close —
nothing about the decision changes — and every fill and exit is then resolved against the real
1-minute path in the order it happened. What 1-minute bars still cannot resolve (both barriers
inside one minute) is resolved stop-first and **counted**, so the residual is reported rather than
hidden.

## The configuration

Long only, NQ 5-minute, window 09:00–13:00 New York, an order armed on every 4th eligible bar.
Resting limit **1.0×ATR(14, EMA of TR)** below the signal close, valid **3 bars**; stop
**1.0×ATR** from the fill; target **1R**; max hold **24 bars**; flat at 13:00.
Costs: MNQ, $0.72/order commission, half-spread by session, 0.75 pt of stop slippage.

## What the true path does to it

| block | 5-minute engine | **true 1-minute path** | ambiguous |
| --- | --- | --- | --- |
| research (n 2131) | 68.2% win, **+0.3312 R**, PF 1.99 | 53.1% win, **−0.0029 R**, PF 0.994 | 1.64% |
| validation (n 1204) | 67.6% win, **+0.3402 R**, PF 2.03 | 54.6% win, **+0.0697 R**, PF 1.157 | 1.33% |

**The fills agree exactly** — 35.7% of signals fill on both engines. The whole of the difference
is exit ordering: on 5-minute bars a stop and a target inside one bar were resolved by a rule, and
on the minute path they are resolved by the sequence. The 5-minute engine was overstating this
configuration by a factor of five.

Sequencing the trades so only one position is open at a time — which is what a Pine strategy with
`pyramiding=0` actually trades — changes almost nothing: research 1926 trades at −0.0110 R,
validation 1107 trades at +0.0687 R. The overlap was not carrying the result.

Out-of-sample detail: median 6 minutes to fill, median 5 minutes held. Exits split
stop 40.3% (mean −1.066 R), target 50.2% (+1.003), flat at 13:00 9.6% (−0.038).

## Two flags, both of which this branch treats as defects

1. **It is worse on research than out-of-sample.** A rule chosen on research should look better
   there; the holdout is where an edge decays, not where it appears. That is the third time this
   shape has shown up here.
2. **`top5pct_share` = 0.98.** Effectively all of the out-of-sample profit is in the top 5% of
   trades.

## The mechanic itself does survive

Same bars, same barriers, same costs, market entry at the next open instead of the resting limit:

| block | market entry | limit entry | limit − market |
| --- | --- | --- | --- |
| research | −0.0745 R (PF 0.860) | −0.0029 R | **+0.072** |
| validation | −0.0876 R (PF 0.827) | +0.0697 R | **+0.157** |

So `STUDY_LIMIT_ENTRY.md`'s finding holds on the true path and on both blocks. What the true path
changes is the *level*: the mechanic is worth about what it was measured to be worth, but it is
buying an unconditional market whose expectancy is negative by roughly the same amount. Net of
that, the configuration is at its cost floor on research and marginally above it out-of-sample.

## Perturbation Monte Carlo (validation trades, true path)

Not a reshuffle. Three shocks applied together, per path: a per-trade fill shock in R units, a
cost multiplier drawn per path, and a randomly dropped fraction of trades standing for fills that
never happened. 20,000 paths each.

| shock set | fill sd | cost × | dropped | mean p05 | p50 | p95 | P(mean ≤ 0) | dd p50 | dd p95 | dd worst |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mild | 0.05 R | 0.75–1.5 | 5% | +0.0340 | +0.0472 | +0.0603 | 0.0000 | 23.3 R | 37.1 R | 71.6 R |
| harsh | 0.10 R | 0.5–2.5 | 10% | +0.0145 | +0.0398 | +0.0645 | 0.0029 | 24.5 R | 40.1 R | 79.3 R |
| harsh, sequential | 0.10 R | 0.5–2.5 | 10% | +0.0129 | +0.0387 | +0.0642 | 0.0039 | 23.9 R | 39.4 R | 74.8 R |

**Read `P(mean ≤ 0) = 0` for exactly what it is.** It says the out-of-sample sample mean is stable
under execution noise. It says nothing about whether that sample mean is real — the Monte Carlo
resamples the trades this configuration was selected to produce, so it cannot price the selection,
and the selection is the thing the research block is warning about. A drawdown of 24 R at the
median and 40 R at the 95th percentile against +0.07 R per trade is the number that matters for
sizing: the configuration needs roughly 600 trades to earn back a median drawdown.

## Verdict

Ship it as an **execution study**, not as a validated edge. The entry mechanic is a real,
reproducible, monotone effect and it belongs in the fill logic of any long trade this branch
takes. On its own, with no signal underneath it, it lands at break-even.

Pine: `pine/atme/ATME_NQ_LIMIT_strategy.pine` (session start/stop left as free inputs).
Runner: `research/atme/run_live.py`.
