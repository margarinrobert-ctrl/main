# APM session-VWAP: out of sample and walk-forward, in dollars

Re-reads `STUDY_APM_VWAP` and `STUDY_APM_WFO` in account dollars with the matched control computed
**inside each block** rather than over all trades. Nothing is selected; the author's constants
throughout. One contract, costs in.

NQ splits 65/35 by session. US100 and US30 are nine-year CFD feeds split research (<2022) /
validation (2022-23) / **test (>=2024)** — their test block is the cleanest read this family has.

## Every block

| market | block | n | $/trade | $ total | PF | win | Sharpe | max DD | ret/DD | top 5% of net | control p |
|---|---|---|---|---|---|---|---|---|---|---|---|
| NQ | research | 70 | +48.03 | +3,362 | 1.62 | 58.6% | +1.12 | 1,128 | 2.98 | 71% | **0.050** |
| NQ | **locked** | 34 | +125.62 | **+4,271** | 4.12 | 67.6% | +2.77 | 487 | 8.78 | 27% | **0.040** |
| US100 | research | 176 | +10.77 | +1,895 | 1.53 | 57.4% | +0.80 | 638 | 2.97 | 94% | **0.033** |
| US100 | validation | 70 | +34.55 | +2,419 | 1.89 | 64.3% | +1.37 | 478 | 5.06 | 59% | **0.043** |
| US100 | **test** | 62 | +15.31 | **+949** | 1.31 | 58.1% | +0.45 | 1,324 | **0.72** | **126%** | 0.250 |
| US30 | research | 148 | -7.87 | **-1,165** | 0.88 | 48.7% | -0.22 | 2,168 | -0.54 | — | 0.593 |
| US30 | validation | 68 | +16.41 | +1,116 | 1.19 | 45.6% | +0.37 | 1,957 | 0.57 | 244% | 0.289 |
| US30 | **test** | 51 | +4.58 | **+234** | 1.06 | 51.0% | +0.13 | 1,150 | **0.20** | **527%** | 0.400 |

**Profitable on 7 of 8 blocks and it clears its control on 4 — every one of them a block the rule
was developed or validated on.** On the two genuine test blocks it fails: US100 test p 0.250,
US30 test p 0.400. NQ's locked block passes at p 0.040 on **34 trades**.

**READ THE `top 5%` COLUMN.** On US100's test block the best 5% of trades supply 126% of net, and on
US30's **527%** — that block's entire $234 is two or three trades. US30 is also NEGATIVE on the only
block long enough to say anything (148 trades, -$1,165).

## Walk-forward

Six cells, rolling and expanding, the six parameters re-chosen inside every training window:

| market | mode | re-chosen | given constants | WFE | folds positive |
|---|---|---|---|---|---|
| NQ | rolling 12m | +0.0684 | **+0.3123** | 0.22 | 5/7 vs **7/7** |
| NQ | expanding | +0.0592 | **+0.3123** | 0.19 | 5/7 vs **7/7** |
| US100 | rolling 24m | +0.0006 | **+0.2702** | 0.00 | 7/13 vs **11/13** |
| US100 | expanding | +0.0698 | **+0.2702** | 0.26 | 9/13 vs **11/13** |
| US30 | rolling 24m | -0.0241 | -0.0195 | n/a | 6/13 vs 3/13 |
| US30 | expanding | -0.0657 | -0.0195 | n/a | 3/13 vs 3/13 |

Two separate readings, and they say different things.

**The optimiser loses in 6 of 6 cells, mean WFE 0.17** — the sixth re-optimiser on this branch to
lose to the author's constants. It keeps the given value in only 1/13 to 8/13 of folds and agrees
with its own first fold **46-47%** of the time across six axes: a parameter set with no information
in it.

**But the `given` column is the strategy's own walk-forward, and it is the strongest thing here.**
Held completely fixed and rolled forward, the author's constants earn **+0.3123 %/trade on NQ with
7 of 7 folds positive** and **+0.2702 on US100 with 11 of 13**, against **-0.0195 on US30 with
3 of 13**. That is a genuinely good out-of-sample shape on two markets and a clear failure on the
third.

## Answer

**Out of sample: yes on NQ and US100, no on US30 — and the two clean test blocks do not clear their
control.** NQ locked +$4,271 on 34 trades and US100 test +$949 on 62; US30 test +$234 on 51 with the
top 5% of trades supplying 527% of it.

**Walk-forward: yes for the strategy, no for optimising it.** Fixed constants rolled forward are
7/7 and 11/13 folds positive on NQ and US100. Re-choosing the parameters each fold destroys that in
every cell.

The binding objections are unchanged from `STUDY_APM_VWAP`: **34 and 62 trades** on the reads that
matter, a US30 result that is negative over nine years, and MC p99 drawdown ~$2,400 per MNQ against
a research bootstrap P(mean<=0) of 0.052. Not live-ready; forward-test 40+ trades.

`research/apm/run_p1.py`, `results/apm/wfo.txt`.
