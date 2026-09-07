# The AI Quant Brain

`python3 research/quant_brain.py` — one command, 74 seconds, end to end.

Four new modules sit under the existing engine:

| module | what it adds |
| --- | --- |
| `research/features.py` | 86 continuous features from OHLCV, every one verified causal by recomputation on truncated history |
| `research/regimes.py` | regime classification on 5 independent axes plus a Gaussian-mixture state, all labelled from bars that closed *before* the session they label |
| `research/metrics.py` | 34 performance metrics, a user constraint system, and the composite Quant Score |
| `research/quant_brain.py` | the orchestrator: leaderboard, signal intelligence, improvement engine, feature importance, portfolio intelligence |

## The Quant Score, and why win rate is not in it

Seven dimensions, each capped at its own weight so a perfect score on one cannot buy a poor
score on another:

```
alpha quality 20 · risk-adjusted return 20 · robustness 15 · statistical significance 15
stability 10 · diversification 10 · regime consistency 10
```

**Win rate is not a dimension.** It appears only inside expectancy, where it is multiplied by
what a win is worth, and inside the excess over the driftless barrier bound, where it is measured
against what the exit geometry produces with no edge at all. A 3R strategy winning 30% and a 1R
strategy winning 60% are the same edge; scoring win rate directly would rank them differently.

## Leaderboard

```
strategy                score      net $   locked $     PF  Sortino   maxDD $   null p  constraints
vol/midday/EMA200        86.2     31,516      6,706   1.74     3.84     3,547   0.0066     all pass
EMA10/body/momentum      80.4     35,157     15,151   1.53     3.56     4,937   0.0066       1 fail
VWAP/Stoch/ADX           78.7     33,830     15,482   1.39     4.60     3,750   0.0066     all pass
RSI/Williams/ADX         43.4     13,546      7,585   1.23     0.78     8,936   0.0861       2 fail
```

The ranking is not the net-profit ranking. `EMA10/body/momentum` earns the most and places
second; `RSI/Williams/ADX` is last on score and is also the only one whose matched-null p-value
fails to clear 0.05.

## The result that matters most

The improvement engine tried 64 variants of the leader — geometry moves, session flattens, and a
fourth condition drawn from the pool:

```
Variants improving RESEARCH: 1 of 64
Variants that ALSO improve the locked block, without a worse drawdown or Sortino: 0
   none. Every research gain here is a research gain only.
```

That is the engine working. An improvement engine that reports improvements on the data it
searched is a fitting engine with a nicer name. This one is allowed to return nothing, and does.

## Feature importance, reported honestly

```
Gradient boosting on the 32-bar forward move, purged split.
Out-of-sample R2 = -0.0801
   <- negative: the model does not generalise, and the ranking below is a description of
      the fit, not of the market
```

The ranking (skew 100, kurtosis 100, EMA50-EMA200/ATR …) is printed anyway, with that warning
attached. A negative out-of-sample R² on 86 features and 46,000 bars is the expected result for
OHLC-only prediction of a liquid index future, and it agrees with everything else on this branch.

Redundancy: **86 features collapse to 55 independent groups** at |ρ| > 0.9. `return 10b`,
`return 10b / vol`, `return 10b / ATR` and `ROC10` are one feature wearing four names — which is
why any "we tested 86 features" claim needs the clustering beside it.

## Signal intelligence

Each entry decomposes into eight named components graded by percentile against their own
trailing distribution, with a confidence from a model **fitted on research trades and scored on
locked trades**:

```
LONG SIGNAL   2024-08-05 13:00    outcome $+3,394
   Momentum                +++      89th percentile
   Volatility regime       ++       77th percentile
   VWAP relationship       ++       70th percentile
   ...
   Trend alignment         −        25th percentile
   Signal confidence: 72%   primary: Momentum, Volatility regime, VWAP relationship

LOCKED-BLOCK AUC = 0.576   (above chance out of sample)
```

The AUC travels with every confidence the system prints. 0.576 is above a coin and nowhere near
a trading signal on its own — which is what the number should say when it is true.

## Portfolio intelligence

Pearson, Spearman, partial, rolling and regime-dependent correlation; hierarchical clustering;
PCA.

```
largest pairwise Pearson          +0.29
largest rank correlation          +0.30
largest partial correlation       +0.19   (the direct link, others held constant)
rolling 120-session, worst pair   median +0.36, range [-0.10, +0.79]

high vol +0.42   low vol +0.38   trending +0.49   mean-reverting +0.35

clusters at |rho| > 0.4:  four singletons
PCA: 4 components for 90% of variance (45%, 20%, 18%, 17%)
equal-risk portfolio Sharpe 2.10 against best single 1.87
```

Two things only the fuller treatment shows. Partial correlation (+0.19) is well below pairwise
(+0.29), so most of what links these strategies is shared exposure rather than direct
duplication. And the rolling correlation reaches **+0.79** in places while its median is +0.36 —
a static matrix would have hidden the periods when the book stops being diversified, which are
exactly the periods diversification is for.

## Regime engine

Five axes, each cut into terciles against the trailing distribution, plus a 4-state Gaussian
mixture as a cross-check:

```
trend       mean-reverting 30%  choppy 42%  trending 28%
volatility  low 30%  normal 41%  high 29%
vol shape   compressing 30%  stable 39%  expanding 31%
liquidity   thin 30%  normal 40%  deep 30%
direction   down 29%  flat 41%  up 30%

state 0:  356 sessions   normal vol 50%, normal liquidity 54%, flat 50%
state 1:  164 sessions   low vol 73%, thin 66%
state 2:  155 sessions   high vol 76%, deep 86%, flat 52%
state 3:  246 sessions   normal vol 51%, compressing 47%, up 72%
```

Every label for session *s* is computed from bars that closed before session *s* begins. That is
not a detail — a regime label built from the session it labels makes every regime study
circular, and this repository has already published one look-ahead of exactly that shape.

For the leader, no regime bucket with 15+ trades loses money. The report says what that most
likely means rather than claiming regime independence: the sample contains one regime.

## What this brain cannot see

The brief asks for order flow, open interest, options, IV, Greeks, gamma exposure, market
breadth, intermarket relationships and futures basis. **The data file is `timestamp, open, high,
low, close, volume` for one instrument.** None of those inputs exist here, so none of them are
built. The report prints the list every run rather than shipping stubs that silently return
nothing.

The same applies to cross-asset and multiple-market validation: one instrument, so the suite
returns N/A with the reason rather than a number.
