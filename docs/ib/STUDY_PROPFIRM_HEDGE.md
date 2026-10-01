# Hedging prop-firm evaluations across accounts: what 8 accounts actually buy

The plan being tested: buy N $25K Flex evaluations, go long in half and short in the other half,
pass whichever side wins, then hedge the funded accounts the same way and withdraw from the
winners. The question as asked: *buy 8 accounts, get 4 funded, get 2 payouts or 1 max payout* —
and then: *risk the whole $1,000 on every account to reach the $1,250 target.*

Everything below is `research/propfirm_hedge.py` (stdlib only, no market data needed — see §1),
8,000–10,000 Monte Carlo runs per row.

## 0. The rules modelled

From the two screenshots, verbatim:

| | eval | funded |
| --- | --- | --- |
| profit target | $1,250 | — |
| max loss limit | $1,000, EOD trailing | $1,000 (assumed EOD trailing) |
| daily loss limit | off | none |
| consistency | 50% (best day ≤ half of total profit) | none |
| max size | 2 NQ or 20 MNQ | 2 NQ or 20 MNQ, scaling plan |
| price | $65.30 one-time (coupon), $65 reset | — |
| days to payout | — | 5 |

**Not on the screenshots, so assumed and exposed as flags:** threshold locks at start + $100; "5 days
to payout" means 5 winning days of ≥ $100; each payout request withdraws up to 50% of profit, capped at
$1,000, and cannot take the balance below max(start, threshold) + $100; 90/10 split; no activation
fee. Whether the 50% consistency rule gates the *pass* or only a later payout is the single biggest
unknown, so every headline is given both ways (`--consistency 1.0` switches it off). Costs: **$19 per
account per trading day** (one NQ round turn — $4 commission, one tick spread, one tick slippage, the
repo's standard figure).

## 1. The accounting identity

While two accounts hold opposite positions, the market is only a coin that decides *which* one
wins: their combined P&L is exactly minus the costs. An account can only lose until it touches its
threshold — at most $1,000. So a group that is hedged *the whole time* obeys

```
passes x $1,250  <=  busts x $1,000 - costs
passes           <=  N x 1,000 / 2,250  =  0.444 N          (= 3.56 for 8 accounts)
```

That ceiling also holds **on average** for any zero-edge trading, hedged or not: a driftless account
is a martingale, so P(pass) x $1,250 = P(bust) x $1,000 at best. What differs between plans is only
the spread around it — and how much of the ceiling a plan wastes.

The same identity caps the funded phase while the funded accounts are hedged: every dollar
withdrawn was lost by another funded account, so gross withdrawals ≤ funded accounts x $1,000 − costs,
and less in practice, because once a threshold locks at start + $100 the profit below it is trapped.

Two things break the ceiling *for a single run* (never on average):

- **A leg left naked.** Once one account busts, its partner is unhedged and the market, not the
  group, pays it. This is exactly what §2's all-in plan does for the last $250.
- **A threshold checked only at the close.** "EOD" means the threshold is *recalculated* at the
  close; if the firm also only *checks* it then, a loser can sit $2,000 under water intraday and hand
  its partner $2,000. Ask the firm.

## 2. Risk the whole $1,000 on every account: the all-in pair

Account A long and account B short, same size, same entry. Each leg's stop is its **own threshold**
($1,000 away) and its target is the **$1,250 it needs** — so the two legs do *not* exit together.
At 2 NQ ($40/pt) that is a 25-point stop and a 31.25-point target on both.

```
price moves 25 pts one way  ->  the losing account is closed at -$1,000
                                 the winner is at +$1,000, 6.25 pts from target, 50 pts from its stop
the winner, now naked        ->  reaches +$1,250 first with probability 50 / 56.25 = 88.9%
```

**One pass from every pair 88.9% of the time** (before costs), with both accounts gone 11.1% of the
time. That is 0.889 passes per pair — exactly the 0.444-per-account ceiling. It is the efficient way
to spend the drawdown: the loser donates all of its $1,000, and nothing is lost to partial wins
or trailing. Checked against theory in the code: 0.8887 simulated vs 0.8889.

But the target is reached on **one day**, and a $1,250 day is 100% of the profit. **If the 50%
consistency rule gates the pass, this does not pass** — the account then needs $2,500 of total
profit. Respecting the rule means two days of $625, each still risking the whole cushion, which is
less efficient. Both readings, 8 accounts, $522 invested:

| plan | consistency | E[funded] | 4+ funded | E[payouts] | E[$ to you] | E[net] | P(net > 0) | 5th pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **all-in pairs** | **off** | **3.53** | **60.4%** | 2.90 | $901 | **+$378** | **68.9%** | −$316 |
| exit-together hedge | off | 3.06 | 6.2% | 2.45 | $781 | +$259 | 53.6% | −$328 |
| independent, unhedged | off | 3.54 | 50.1% | 1.67 | $1,024 | +$501 | 43.1% | −$522 |
| copy-traded, same side | off | 3.55 | 44.4% | 1.68 | $1,023 | +$501 | 14.8% | −$522 |
| **all-in pairs** | **50%** | **2.88** | **21.6%** | 2.30 | $753 | **+$230** | **50.5%** | −$453 |
| exit-together hedge | 50% | 2.58 | 0.0% | 2.04 | $685 | +$162 | 42.1% | −$426 |
| independent, unhedged | 50% | 2.90 | 31.8% | 1.38 | $849 | +$326 | 35.2% | −$522 |
| copy-traded, same side | 50% | 2.88 | 36.0% | 1.41 | $871 | +$349 | 12.0% | −$522 |

Funded accounts out of 8, all-in, consistency off: 4 in 60.4%, 3 in 32.2%, 2 in 6.9%, 1 in 0.5% —
the binomial of four pairs at 88.9%. With consistency on: 5 in 3.9%, 4 in 17.7%, 3 in 42.0%, 2 in 32.8%.

**So the original target — 8 accounts, 4 funded — is reachable, 60% of the time, if consistency does
not gate the pass, and 22% if it does.** It is never reachable by the exit-together hedge with the
rule on (0.0%), because that plan never leaves a leg naked.

"Independent" and "copy" are the same accounts with **no edge at all**: driftless price, same
brackets, same costs. All-in pairs match them on E[funded] — as the martingale argument says they
must — but with far less spread: P(net > 0) 68.9% against 43.1%, and no run in which all eight die.
Hedging buys a narrower distribution, not a higher mean. (Independent shows a higher E[net] because
its funded accounts are also unhedged, so their payouts are paid by the market rather than by each
other.)

## 3. Across group size

E[funded] / E[net] / P(net > 0); hedge = exit together, all-in = §2, indep = unhedged zero edge.

Consistency rule **off**:

| N | invested | ceiling | hedge | all-in | indep | | hedge | all-in | indep | | hedge | all-in | indep |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | $131 | 0.89 | 0.78 | 0.88 | 0.88 | | +$99 | +$128 | +$122 | | 25.6% | 29.1% | 26.9% |
| 3 | $196 | 1.33 | 1.09 | 1.32 | 1.32 | | +$113 | +$159 | +$193 | | 35.7% | 42.6% | 37.4% |
| 4 | $261 | 1.78 | 1.53 | 1.77 | 1.76 | | +$148 | +$204 | +$264 | | 46.2% | 51.7% | 46.5% |
| 6 | $392 | 2.67 | 2.27 | 2.65 | 2.68 | | +$197 | +$306 | +$387 | | 45.7% | 60.8% | 61.2% |
| 8 | $522 | 3.56 | 3.06 | 3.53 | 3.54 | | +$259 | +$374 | +$501 | | 53.9% | 69.1% | 42.9% |
| 12 | $784 | 5.33 | 4.56 | 5.29 | 5.29 | | +$367 | +$548 | +$748 | | 68.0% | 81.5% | 62.1% |
| 16 | $1,045 | 7.11 | 6.11 | 7.07 | 7.09 | | +$492 | +$708 | +$1,020 | | 78.5% | 89.3% | 60.8% |
| 20 | $1,306 | 8.89 | 7.59 | 8.83 | 8.82 | | +$568 | +$885 | +$1,252 | | 83.7% | 92.8% | 69.4% |

Consistency rule **on (50%)**:

| N | invested | ceiling | hedge | all-in | indep | | hedge | all-in | indep | | hedge | all-in | indep |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | $131 | 0.89 | 0.64 | 0.71 | 0.72 | | +$63 | +$65 | +$78 | | 21.2% | 23.5% | 22.3% |
| 3 | $196 | 1.33 | 0.99 | 1.08 | 1.08 | | +$79 | +$97 | +$133 | | 31.3% | 35.2% | 31.8% |
| 4 | $261 | 1.78 | 1.35 | 1.44 | 1.45 | | +$112 | +$140 | +$170 | | 41.4% | 44.9% | 40.3% |
| 6 | $392 | 2.67 | 1.92 | 2.14 | 2.17 | | +$125 | +$178 | +$237 | | 38.9% | 47.1% | 52.6% |
| 8 | $522 | 3.56 | 2.58 | 2.88 | 2.88 | | +$159 | +$228 | +$319 | | 42.1% | 50.3% | 35.1% |
| 12 | $784 | 5.33 | 3.96 | 4.32 | 4.34 | | +$220 | +$324 | +$488 | | 53.2% | 61.0% | 51.6% |
| 16 | $1,045 | 7.11 | 5.23 | 5.77 | 5.78 | | +$279 | +$391 | +$622 | | 57.1% | 65.9% | 50.2% |
| 20 | $1,306 | 8.89 | 6.64 | 7.21 | 7.24 | | +$358 | +$478 | +$790 | | 64.5% | 71.3% | 57.3% |

All-in beats exit-together at every N on every column. With consistency off it sits within 1% of the
ceiling throughout; the rule costs it about 18% of its passes.

## 4. The unstated payout rules

N = 8, exit-together hedge, consistency on (the funded phase is the same for both hedges):

| payout cap | withdraw per request | split | E[payouts] | E[$ to you] | E[net] |
| --- | --- | --- | --- | --- | --- |
| $500 | 50% | 90% | 2.20 | $635 | +$112 |
| $1,000 | 50% | 80% | 2.01 | $590 | +$67 |
| **$1,000** | **50%** | **90%** | **2.01** | **$664** | **+$141** |
| $1,000 | 100% | 90% | 1.77 | $772 | +$250 |
| $1,000 | 100% | 100% | 1.77 | $858 | +$335 |
| none | 100% | 90% | 1.76 | $783 | +$260 |

The cap barely binds; the **fraction of profit you may withdraw per request** is what matters,
because what is left in the account is what the lock traps.

## 5. Costs and bracket size

N = 8, exit-together hedge, consistency on:

| $/leg/day | eval step | funded step | E[funded] | E[$ to you] | E[net] |
| --- | --- | --- | --- | --- | --- |
| 0 | 625 | 250 | 2.97 | $1,099 | +$576 |
| 10 | 625 | 500 | 2.74 | $911 | +$389 |
| **19** | **625** | **250** | **2.57** | **$664** | **+$141** |
| 19 | 625 | 500 | 2.60 | $754 | +$232 |
| 19 | 400 | 150 | 2.34 | $502 | −$21 |
| 38 | 625 | 500 | 2.42 | $581 | +$59 |

Costs are paid per day, so bigger, fewer days win, which is the other reason all-in does well.
Trade the fewest contracts that resolve the bracket intraday: 1 NQ is a 50-point stop and 62.5-point
target for all-in, $19 a leg; 20 MNQ for the same dollars costs ~$57 a leg.

## 6. Firm terms

Opposite positions across one person's accounts are prohibited by most futures prop firms and are
easy to detect; the usual remedy is closing the accounts and voiding payouts. `--void` prices it:
with the exit-together hedge (consistency on) break-even is a 24% chance of voiding. The user asked
to set this aside for the numbers above, which all assume it never happens.

## 7. Bottom line

- **Risking the whole $1,000 on every account is the best way to run the hedge.** Each pair produces
  one pass 88.9% of the time, which is the theoretical ceiling; every other hedge wastes some of it.
- **8 accounts → 4 funded: 60% if the consistency rule does not gate the pass, 22% if it does.**
  Expected 3.53 / 2.88 funded. The 4th pass is paid by the market during the naked last $250, not by
  the other accounts — in the closed, exit-together hedge 4 is out of reach.
- **Payouts: ~2.3–2.9, worth ~$750–$900 to you for $522**, so +$230 to +$378 expected, a 50–69% chance
  of finishing ahead — under the assumed payout rules, which §4 shows matter a great deal.
- No hedge raises the *average*: unhedged zero-edge accounts pass at the same rate. Hedging trades
  the lottery for a narrower range of outcomes. A real edge is the only thing that moves the mean.

```bash
python research/propfirm_hedge.py --n 8 --consistency 1.0     # all four plans, rule off
python research/propfirm_hedge.py --sweep                     # N = 2..20, payout and cost grids
```

## Correction

The first version of this study scored the unhedged single-account trade as a 50/50 coin even when
its target and stop differed (e.g. +$1,269 vs −$1,000), which is a hidden edge. It inflated the
"independent" and "copy" baselines and the last unhedged leg of every hedge, and produced the claim
that unhedged accounts beat the hedge on average. Solo legs now use the exact first-passage
probability (stop / (stop + target)); every table above is from the corrected code.

## Caveats

- **No market data.** Only which side wins matters to a hedged pair, so a driftless price is the right
  model. It ignores bust slippage past the threshold, NQ's drift (NQ rose 89% on this sample — which
  side wins is not a fair coin in a trending month, though the pair does not care), and brackets that
  do not resolve by the close. All-in's naked leg can need 50 more points at 1 NQ; most sessions cover
  that, not all.
- Unhedged baselines assume zero edge, not negative edge.
- The payout rules marked as assumptions are guesses; §4 shows they matter.
- The funded scaling plan is not modelled.
