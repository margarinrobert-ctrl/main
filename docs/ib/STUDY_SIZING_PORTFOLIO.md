# 173,340 sizing combinations and 252 portfolio constructions, and what they bought

`research/sizing_sweep.py` → `sizing_report.py`, and `research/portfolio_sweep.py`.

Both answers are "no improvement", arrived at differently, and both are more useful than a
number that went up.

## Sizing creates no edge

It reshapes one. Net dollars are therefore meaningless as a ranking — more leverage buys more
dollars for free — so everything is ranked on Sharpe and MAR (net ÷ max drawdown), both
scale-invariant, and the locked block is read once after choosing.

**57,780 sizing configurations × 3 stop widths = 173,340.** Six schemes: fixed lot, fixed dollar
risk, fixed fractional (compounding), inverse ATR, volatility targeting, and Kelly — crossed with
risk per trade, volatility lookback, volatility multiplier, lot cap, account size, and an
equity-curve filter.

### The baseline wins

Median across every configuration of each scheme, at a 2.5×ATR stop:

| scheme | configs | med Sharpe | med MAR | med locked $ | % locked +ve |
| --- | --- | --- | --- | --- | --- |
| **fixed one contract** | 180 | **1.31** | **6.69** | **$1,357** | **60%** |
| fixed dollar risk | 1,800 | 1.13 | 4.54 | $0 | 45% |
| inverse ATR | 1,800 | 1.13 | 4.54 | $0 | 45% |
| fixed fractional | 1,800 | 1.07 | 3.97 | $0 | 45% |
| volatility target | 50,400 | 0.97 | 3.54 | $0 | 37% |
| Kelly | 1,800 | 0.79 | 3.44 | $0 | 30% |

Fixed one contract has the best median Sharpe, the best median MAR, and the highest share of
configurations that stay positive out of sample. Every scheme that scales position size does
worse on the median, and Kelly — the most aggressive — does worst.

### Selecting a sizing rule made it worse

```
baseline, one contract:   research $6,271   locked $1,831   Sharpe 1.45   MAR 8.47
best on research Sharpe:  research $9,845   locked $1,718   Sharpe 1.63   MAR 5.82
```

Choosing the best of 57,780 on the research block produced *less* money and a worse MAR on the
holdout than doing nothing. The pattern from the entry-rule searches repeats exactly.

Only **0.6%** of the 52,596 configurations that actually trade beat fixed-one-lot on research
MAR. Of those, 83% also beat it on the locked block — so the survivors are real, they are just
0.6% of the grid, and picking them out required knowing the answer.

### The finding a small account should read first

**9% of risk-based configurations never place a single contract.** At a 2.5×ATR stop on 60-minute
MNQ the risk per contract is roughly $250–400, so:

| account | risk-based configs that cannot afford one contract |
| --- | --- |
| $10,000 | **31%** |
| $25,000 | 10% |
| $50,000 | 3% |
| $100,000 | 1% |

Below about $25,000 most textbook sizing rules round to zero lots and the strategy simply does
not trade. Sizing theory assumes divisible positions; futures are not divisible.

### Robustness: the order of the trades

A compounding scheme is path dependent — the same trades in a different order give a different
equity curve, a different drawdown and a different survival outcome. The top 5,000 configurations
by research Sharpe were each re-run over **400 random orderings**. Ranking by the 5th percentile
across those orderings rather than by the single ordering history dealt selects completely
different configurations, and none of them beats the baseline on MAR either. Ruin (equity below
half) occurred in **0.0%** of the grid, which is the one comfortable number here.

## Portfolio construction made it actively worse

201 candidate legs, six weighting schemes — equal lots, equal risk, inverse variance, minimum
variance, maximum Sharpe, risk parity — crossed with six correlation caps and seven leg counts.
252 portfolios, each choosing its legs by **research** Sharpe and read once on locked.

| weighting | med research Sharpe | **med LOCKED Sharpe** | med locked $ | % locked +ve |
| --- | --- | --- | --- | --- |
| equal lots | 4.65 | **−0.78** | −$9,503 | 38% |
| equal risk | 5.16 | **−0.82** | −$5,159 | 36% |
| inverse variance | 4.87 | **−0.59** | −$4,122 | 38% |
| minimum variance | 4.53 | **−0.49** | −$3,327 | 31% |
| maximum Sharpe | 5.29 | **−0.88** | −$6,579 | 31% |
| risk parity | 5.23 | **−0.93** | −$5,551 | 33% |

Every scheme. Research Sharpe between 4.5 and 5.3, locked Sharpe **negative**.

The chosen configuration — maximum Sharpe, 18 legs, correlation cap 0.15 — scored **7.75 on
research and −0.62 on the locked block**, losing $4,360. The best single leg on locked scored
2.25 on its own.

**Portfolio construction does not rescue a selected pool; it amplifies the selection.** Choosing
18 legs from 201 by research Sharpe is a second search on top of the first, and the correlation
cap makes it worse rather than better by forcing the selection to reach further down the list.

This does not contradict the 14-leg 1R book, which still holds at +$8,456 on the locked block —
that one selected on research *win rate* with the calendar ban and subset coherence, then
decorrelated greedily. The difference is what the legs were chosen by. Sharpe over 599 sessions
with sparse trades is far more overfittable than a win rate against a known base.

## The conclusion

For this strategy: **trade one contract.** No sizing rule among 173,340 improved its
risk-adjusted result out of sample, and no portfolio construction among 252 improved on the legs
themselves. Both sweeps were run properly and both came back negative, which is information.
