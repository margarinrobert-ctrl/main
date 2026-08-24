# `vol rising AND midday AND dist EMA200>2 ATR`, long, 2.5×ATR / 3R

The full 57-test suite plus four targeted follow-ups. Reproduce with
`python3 research/vm_diagnose.py`; the suite itself with `research/test_suite.py`.

**Measured**: 230 trades, $31,516, PF 1.74, win 37.0% against a 25.0% driftless bound,
max drawdown $3,547, Sharpe 1.68, net/drawdown 8.89.

## Suite result

```
PASS 41   WARN 5   FAIL 4   INFO 6   N/A 4
```

That is the best result on this branch by a wide margin — the previous best survivor scored
PASS 30 / FAIL 6. What passed is worth stating because it is a lot, and it is the right things:

| | |
| --- | --- |
| Walk-forward | 7 forward folds, **0 negative**, stitched $24,483 |
| Rolling window | 13 windows of 180 sessions, **0 negative** |
| Time period | 6 equal periods, **0 negative** |
| Monte Carlo | 10,000 resampled orders, **P(net<0) = 0.0%**, p5 $16,298 |
| Bootstrap | stationary block, 95% CI on net **[$13,387, $49,810]** |
| Significance | per-trade t = **3.27**, p = 0.0013 |
| Parameter sensitivity | 92% of a 25-point stop × target grid profitable, neighbourhood 100% |
| Stop / target sweeps | **6 of 6** profitable each |
| Intrabar true path | **+0%** — this rule does not depend on the same-bar stop-vs-target assumption at all |
| Drawdown | $3,547, 11% of net, longest underwater stretch 90 sessions |
| Diversification | correlation to every book leg within ±0.05; Sharpe 1.68 alone → **2.80** combined |

## The follow-ups

### 1. Direction is not free, and it chose long

```
long     230 trades   net  $31,516    research  $24,811    locked  $6,706    win 37.0%
short    281 trades   net −$17,254    research −$12,233    locked −$5,021    win 20.6%
```

The short side wins 20.6% against the same 25.0% bound — it is *worse than random*. This is the
§4c signature the protocol document warns about, now seen an eighth separate way: on 2022-12 →
2025-12 NQ, which rose about 89%, any rule allowed to pick a direction picks long and is fitting
the index. Trading both directions on the same signal leaves $14,262, so the asymmetry is most
of the result.

### 2. But the entry timing is not nothing

Random entries drawn from the **same clock window**, same trade count, same exit geometry — the
null that holds drift, session and geometry fixed and varies only *which* midday bars are chosen:

```
observed                                            $31,516
400 random midday entry sets   median $9,942   p5 −$278   p95 $20,223
p = 0.0025      0 of 400 matched or beat it
```

This is the finding that separates this rule from everything else tested on this branch. The
previous best survivor scored p = 0.46 against its matched null — indistinguishable from random
entries. This one is not. The conditions are choosing better-than-random long windows.

Both results are true at once, and the honest reading is the uncomfortable one: **the entry has
demonstrable timing skill relative to random longs in the same window, and the strategy's
profitability is still inseparable from a market that rose throughout the sample.** This dataset
cannot separate them, because it contains one regime.

### 3. Two of the three conditions hurt out of sample

```
                                trades      net       research     locked
full rule                          230   $31,516      $24,811     $6,706
without 'dist EMA200>2 ATR'        278   $31,814      $18,377    $13,437
without 'vol rising'               242   $26,964      $17,046     $9,918
without 'midday'                   481   $25,621      $21,263     $4,357
'dist EMA200>2 ATR' alone          461   $21,944      $17,964     $3,981
```

Dropping `dist EMA200>2 ATR` earns *more* overall and **twice as much on the locked block**.
Dropping `vol rising` also improves the locked block. The three-condition rule beats its own
subsets on research and loses to them out of sample, which is what a fitted condition looks
like.

### 4. The edge halves out of sample

```
research   149 trades   $24,811   $167/trade   win 40.3%   PF 2.11
locked      81 trades    $6,706    $83/trade   win 30.9%   PF 1.33
```

Still above the 25.0% bound on the locked block, still profitable, at half the size.

## What is actually being traded

Strip the labels and the rule is: **buy a dip more than 2 ATR from the 200-period EMA, around
midday, on rising volume, and hold about two days.** Mean hold 96.8 bars, 62.3% of all bars spent
in the market, long only. The regime test shows the below-EMA200 trades earn $21,557 against
$9,959 above it — it is a dip-buy.

On 2022-12 → 2025-12 every dip recovered. That is the sample, and it is one regime.

## Verdict

Not established as profitable, and closer than anything else here has come.

The suite's four failures are Data-snooping (deflated Sharpe 0.000 against 16.2M trials searched
— unfixable by any amount of further testing on this data), SPA (p = 0.192), Information
Coefficient (≈ 0), and Residual analysis. The last one is weaker evidence than it looks: it
regresses P&L on the move over the *realised* holding window, which the exit itself determines,
so beta ≈ 1 is close to tautological. The first two are the real ones.

**The decisive test is not in this repository.** It is 2018–2021 — the Q4 2018 selloff, the 2020
crash, the 2022 bear — periods where "every dip recovers" was false. This repository's data
starts 2022-12-26. A TradingView chart with deeper history can run it, and that result outranks
every number above.

Run it short as well as long. If the short side is still −20% win rate on a period that fell,
the rule is a drift capture. If it holds up in both directions on a falling market, this is the
first thing on this branch worth a small live test.
