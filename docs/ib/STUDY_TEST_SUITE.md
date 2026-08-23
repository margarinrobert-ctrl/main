# The 57-test suite, and what it does to the generator's best find

`research/test_suite.py`. One command, one strategy, fifty-seven tests:

```
python3 research/test_suite.py
```

Every test reads the same object — per-trade P&L, the bar and session each trade entered and
exited, the side, and the bars it was measured on — plus optional hooks: a re-simulation
closure, the condition pool, the trigger vector, and a sample of the searched family. A test
that is missing a hook it needs says so and returns INFO. It never guesses.

Verdicts are PASS / WARN / FAIL / INFO / N/A.

## The subject

The strategy under test is the strongest survivor of the cross-timeframe transfer study: the
rule that stayed profitable in both directions on all three research blocks and all three
locked blocks at 15m, 30m and 60m.

```
RSI14<30 AND Williams%R<-80 AND ADX>25      long, 2.5xATR stop, 3.0R target, 30m bars
253 trades over 922 sessions, research/locked split at session 599
```

## The result

```
PASS 28   WARN 13   FAIL 6   INFO 6   N/A 4
```

Six failures, and they are the six that decide whether a strategy is real:

| test | number |
|---|---|
| Walk-forward test | 7 forward folds, 3 negative |
| Statistical significance | per-trade t = 1.49, p = 0.139; matched-null p = 0.46 |
| Data-snooping | 16,228,800 trials searched; deflated Sharpe probability 0.000 |
| P&L distribution | the best 5% of trades carry 161% of net |
| Sharpe stability | Sharpe by sixth +1.68 +1.06 −0.62 −0.35 +1.27 +1.76 |
| Information Coefficient | rank IC −0.021, positive in 1 of 6 periods |

The single number that ends the discussion is the matched null. Hold the trade count fixed at
253, put the entries on random bars, and 46% of those random strategies earn at least the
$15,587 this one does. The conditions are not what produced the money; the exit geometry and
the instrument's drift are. The deflated Sharpe says the same thing from the other side: with
16.2 million strategies searched, the best one *by luck alone* would show an annualised Sharpe
near 5.3. This one shows 0.81.

That is the suite working. A battery that never fails its author's favourite strategy is
decoration.

## What passed, and why that is not a rescue

The passes are real but they are the wrong kind of evidence:

* **Robustness** — 40 half-tick noise draws, 100% profitable, CV 0.03. Conditions and ATR are
  recomputed on the perturbed prices, not held fixed, so this is the strong version of the test.
* **Leakage** and **look-ahead** — every condition recomputed on history truncated at 40% and
  70% takes the identical value at every earlier bar; every trade that closed before the cut
  comes out identical on truncated data. There is no peeking. (This is the test that would have
  caught the IVB `session_index` bug in 2022.)
* **Execution, cost, slippage, latency, capacity** — profitable at 4x modelled cost, at +4 ticks
  of extra slippage, and with the fill delayed a whole 30-minute bar; p5 capacity 22 lots at 1%
  of bar volume.
* **Selection bias (PBO)** — 0.03 over 70 CPCV splits.

None of these say the edge is real. They say that *if* it were real, it would survive costs and
is not an artefact of the code. A strategy can be perfectly implemented, perfectly robust to
noise, and still be noise.

Note the two resampling tests that disagree: White's Reality Check returns p = 0.044 and
Hansen's SPA returns p = 0.147 on the same family sample. SPA is the one to believe — it
studentises and recentres the poor models, and RC is known to be dragged toward significance
by the bad candidates in the family. Both are computed over a 250-strategy random sample of the
16.2M enumerated, which makes each p-value a *lower* bound on what the full family would give.

## The four that cannot be run here

Not approximated, not faked:

| test | why not |
|---|---|
| Cross-asset | the repository holds one instrument. Running the rule on MNQ instead of NQ is the same series with a different multiplier and would pass by construction. |
| Cross-sectional | there is no cross-section — this is single-instrument timing, not a ranking of names. |
| Cointegration | a property of two or more price series. One instrument, no pair. |
| Survivorship bias | a continuous front-month series has no universe and no delisting. The related risk is roll bias, which is a data-construction question, not a test. |

## The tests

**Performance** — Backtest, Profitability, Risk-adjusted performance, Benchmark.

**Out of sample** — Out-of-sample, Time-period, Rolling-window, Expanding-window, Walk-forward.

**Robustness** — Parameter sensitivity (25-point stop x target grid), Robustness (price noise),
Stress (worst 60-session stretch, top-quintile volatility, ten worst days), Regime, Volatility.

**Resampling and significance** — Monte Carlo (10,000 resampled trade orders), Bootstrap
(stationary block bootstrap of daily P&L), Statistical significance (t-test plus matched null),
Data-snooping (deflated Sharpe), Reality Check (White), SPA (Hansen), Selection bias (PBO
via CPCV).

**Execution** — Transaction cost, Slippage, Execution latency, Market impact, Liquidity,
Capacity, Execution (exit mix, hold time, gap-through rate).

**Risk** — Drawdown, Tail risk, VaR, Expected Shortfall, P&L distribution, Sharpe stability,
Residual analysis, Autocorrelation (Ljung-Box), Stationarity (ADF on equity and on increments).

**Exposure** — Factor exposure, Factor stability, Correlation, Information Coefficient, Signal
decay, Turnover.

**Features and bias** — Feature importance (drop-one), Feature selection (add a fourth
condition, measure the lift on research and on the locked block), Leakage, Look-ahead bias.

**Portfolio** — Position sizing (flat, fixed-fractional, volatility-targeted), Stop-loss sweep,
Take-profit sweep, Concentration, Diversification against the book, Risk budget.

## Two results worth keeping regardless

**Signal decay.** The mean gross move after the signal is *negative* for the first 16 bars
(−$3.0 at 1 bar, −$4.4 at 16) and only turns at 32 bars, reaching +$86 at 64. Whatever this rule
finds, it is not a short-horizon effect — the entry is early and the trade is carried by the
stop being far enough away to survive the first eight hours.

**Feature importance.** Dropping `ADX>25` *improves* net by $1,196 while adding 34 trades. It is
in the rule because the search put it there, not because it does anything.

## Using it on another strategy

```python
from test_suite import build, sample_family, run_all

s = build(["close>EMA200", "vol>1.5x mean"], side=1, atr_mult=2.0, tp_r=2.0,
          flat_min=960, tf=60, n_trials=1)
s.family = sample_family(s, k=250)
run_all(s)
```

`build()` takes any subset of the 115 conditions in `research/alpha_factory2.py`, either
direction, any stop and target, any flatten time, and any of the timeframes `prep()` can build.
Every keyword it takes is something a test can turn, which is the whole design: the tests do not
re-implement the strategy, they re-run it.
