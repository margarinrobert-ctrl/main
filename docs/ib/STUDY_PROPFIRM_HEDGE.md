# Hedging prop-firm evaluations across accounts: what 8 accounts actually buy

The plan being tested: buy N $25K Flex evaluations, go long in half and short in the other half,
pass whichever side wins, then hedge the funded accounts the same way and withdraw from the
winners. The question as asked: *buy 8 accounts, get 4 funded, get 2 payouts or 1 max payout* —
and then: *risk the whole $1,000 on every account to reach the $1,250 target.*

Everything below is `research/propfirm_hedge.py` (stdlib only, no market data needed — see §1).
Every primitive and every headline closed form is asserted in `research/propfirm_hedge_test.py`
(§8). Headline tables are 20,000 runs (standard error ≤ $25 on E[net], ≤ 0.4 points on any
probability); sweeps are 10,000.

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

How they are implemented: the threshold is the highest **end-of-day** balance minus $1,000, recomputed
only at the close, and enforced **intraday** — an account dies the moment its equity touches it.
Commissions come out of the account balance, so a loss of $981 plus a $19 round turn is a $1,000
loss and a bust.

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

That ceiling also holds **on average** for any zero-edge trading, hedged or not. A driftless account
is a martingale, so its expected P&L is minus its costs; a pass is worth at least +$1,250 and a bust
costs at most $1,000; hence P(pass) x 1,250 ≤ P(bust) x 1,000, i.e. P(pass) ≤ 1,000 / 2,250. What
differs between plans is only the spread around the mean — and how much of the ceiling a plan wastes.

The same identity caps the funded phase while the funded accounts are hedged: every dollar
withdrawn was lost by another funded account, so gross withdrawals ≤ funded accounts x $1,000 − costs,
and less in practice, because once a threshold locks at start + $100 the profit below it is trapped.

Two things break the ceiling *in a single run* (never on average):

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
                                 (or falls 50 pts and busts too: 11.1%, both accounts gone)
```

In general, for stop S and target T > S the pair produces one pass with probability **2S / (S + T)**:
0.889 at zero cost, and 2,000 / 2,269 = **0.881** once the target is grossed up by the $19 cost. That
is 0.44 passes per account — the ceiling itself. The loser donates all of its $1,000 and nothing is
lost to partial wins, trailing, or extra days of costs. Asserted in the tests: simulated
0.8876 / 0.8819 against 0.8889 / 0.8814.

The target is reached on **one day**, and a $1,250 day is 100% of the profit. **If the 50%
consistency rule gates the pass, it does not pass** — the account then needs $2,500 of total profit.
Respecting the rule means two winning days of exactly $625 net, each still risking the whole cushion.
Both readings, 8 accounts, $522 invested:

| plan | consistency | E[funded] | 4+ funded | E[payouts] | E[$ to you] | E[net] | P(net > 0) | 5th pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **all-in pairs** | **off** | **3.52** | **59.7%** | 2.80 | $936 | **+$414** | **69.5%** | −$322 |
| exit-together hedge | off | 3.07 | 6.6% | 2.39 | $821 | +$299 | 54.8% | −$331 |
| independent, unhedged | off | 3.54 | 50.2% | 1.67 | $1,025 | +$503 | 43.1% | −$522 |
| copy-traded, same side | off | 3.52 | 44.0% | 1.66 | $1,020 | +$498 | 14.5% | −$522 |
| **all-in pairs** | **50%** | **2.96** | **23.9%** | 2.31 | $798 | **+$275** | **52.8%** | −$409 |
| exit-together hedge | 50% | 2.79 | 0.0% | 2.14 | $745 | +$223 | 47.7% | −$391 |
| independent, unhedged | 50% | 2.97 | 33.8% | 1.41 | $867 | +$344 | 35.8% | −$522 |
| copy-traded, same side | 50% | 2.95 | 36.9% | 1.42 | $876 | +$353 | 12.2% | −$522 |

Funded accounts out of 8:

| plan | consistency | 1 | 2 | 3 | 4 | 5 | 6+ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all-in | off | 0.6% | 6.6% | 33.0% | 59.7% | — | — |
| all-in | 50% | — | 33.0% | 43.1% | 19.5% | 4.0% | 0.4% |
| exit-together | 50% | — | 20.8% | 79.2% | — | — | — |

With the rule off this is exactly the binomial of four pairs at 0.881: P(4) = 0.881⁴ = 60.4%,
simulated 59.7–60.7% across seeds. Payouts, all-in, rule off: 0 in 0.9% of runs, 1 in 11.5%, 2 in
32.0%, 3 in 32.3%, 4+ in 23.3%.

**So the original target — 8 accounts, 4 funded — is reachable 60% of the time if consistency does not
gate the pass, and 24% if it does.** The exit-together hedge never leaves a leg naked, so with the rule
on it never reaches 4 at all.

"Independent" and "copy" are the same accounts with **no edge at all**: driftless price, same
brackets, same costs. All-in pairs match them on E[funded] — as the martingale argument says they
must — with far less spread: P(net > 0) 69.5% against 43.1%, and all eight die in 0.04% of runs
(7 of 20,000; 0.119⁴ = 0.02% from the pairs alone) against 0.9% unhedged.
Hedging buys a narrower distribution, not a higher mean. (Independent shows a higher E[net] because
its *funded* accounts are also unhedged, so their payouts are paid by the market rather than by each
other.)

## 3. Across group size

E[funded] / E[net] / P(net > 0); hedge = exit together, all-in = §2, indep = unhedged zero edge.

Consistency rule **off**:

| N | invested | ceiling | hedge | all-in | indep | | hedge | all-in | indep | | hedge | all-in | indep |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | $131 | 0.89 | 0.78 | 0.88 | 0.88 | | +$103 | +$128 | +$123 | | 25.8% | 29.0% | 26.9% |
| 3 | $196 | 1.33 | 1.09 | 1.33 | 1.32 | | +$115 | +$169 | +$195 | | 35.4% | 43.1% | 37.5% |
| 4 | $261 | 1.78 | 1.54 | 1.77 | 1.76 | | +$155 | +$220 | +$262 | | 46.3% | 53.0% | 46.4% |
| 6 | $392 | 2.67 | 2.27 | 2.64 | 2.68 | | +$215 | +$324 | +$384 | | 47.0% | 61.7% | 61.3% |
| 8 | $522 | 3.56 | 3.07 | 3.52 | 3.54 | | +$296 | +$413 | +$501 | | 55.2% | 70.0% | 43.1% |
| 12 | $784 | 5.33 | 4.58 | 5.29 | 5.29 | | +$407 | +$594 | +$758 | | 69.9% | 83.5% | 62.1% |
| 16 | $1,045 | 7.11 | 6.11 | 7.05 | 7.08 | | +$547 | +$779 | +$1,018 | | 81.3% | 90.5% | 60.7% |
| 20 | $1,306 | 8.89 | 7.63 | 8.82 | 8.83 | | +$663 | +$948 | +$1,250 | | 86.6% | 94.4% | 69.4% |

Consistency rule **on (50%)**:

| N | invested | ceiling | hedge | all-in | indep | | hedge | all-in | indep | | hedge | all-in | indep |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | $131 | 0.89 | 0.68 | 0.74 | 0.74 | | +$69 | +$79 | +$85 | | 22.2% | 25.0% | 23.0% |
| 3 | $196 | 1.33 | 1.04 | 1.11 | 1.12 | | +$94 | +$119 | +$134 | | 33.4% | 36.3% | 31.9% |
| 4 | $261 | 1.78 | 1.43 | 1.48 | 1.50 | | +$139 | +$159 | +$178 | | 44.2% | 46.2% | 40.5% |
| 6 | $392 | 2.67 | 2.05 | 2.22 | 2.22 | | +$177 | +$211 | +$260 | | 42.4% | 48.7% | 54.4% |
| 8 | $522 | 3.56 | 2.79 | 2.96 | 2.98 | | +$217 | +$272 | +$340 | | 47.8% | 52.9% | 35.8% |
| 12 | $784 | 5.33 | 4.19 | 4.43 | 4.47 | | +$328 | +$389 | +$513 | | 61.3% | 65.7% | 53.0% |
| 16 | $1,045 | 7.11 | 5.58 | 5.91 | 5.93 | | +$404 | +$493 | +$702 | | 69.4% | 72.6% | 51.8% |
| 20 | $1,306 | 8.89 | 6.96 | 7.41 | 7.40 | | +$503 | +$627 | +$851 | | 75.4% | 78.0% | 58.9% |

All-in beats exit-together at every N on every column, under both readings. With the rule off it
sits within 1% of the ceiling throughout; the rule costs it about 16% of its passes.

## 4. The unstated payout rules

N = 8, exit-together hedge, consistency on (the funded phase is the same for both hedges):

| payout cap | withdraw per request | split | E[payouts] | E[$ to you] | E[net] |
| --- | --- | --- | --- | --- | --- |
| $500 | 50% | 90% | 2.40 | $725 | +$202 |
| $1,000 | 50% | 80% | 2.14 | $657 | +$135 |
| **$1,000** | **50%** | **90%** | **2.14** | **$740** | **+$217** |
| $1,000 | 100% | 90% | 1.85 | $844 | +$321 |
| $1,000 | 100% | 100% | 1.85 | $937 | +$415 |
| none | 100% | 90% | 1.83 | $842 | +$320 |

The cap barely binds; the **fraction of profit you may withdraw per request** is what matters,
because what is left in the account is what the lock traps.

## 5. Costs and bracket size

N = 8, exit-together hedge, consistency on (eval step = net winning day; funded step = bracket):

| $/leg/day | eval step | funded step | E[funded] | E[$ to you] | E[net] |
| --- | --- | --- | --- | --- | --- |
| 0 | 625 | 250 | 2.96 | $1,113 | +$591 |
| 10 | 625 | 500 | 2.86 | $1,028 | +$505 |
| **19** | **625** | **250** | **2.78** | **$740** | **+$217** |
| 19 | 625 | 500 | 2.79 | $825 | +$302 |
| 19 | 400 | 150 | 2.38 | $532 | +$10 |
| 38 | 625 | 500 | 2.64 | $702 | +$179 |

Costs are paid per day, so bigger, fewer days win, which is the other reason all-in does well.
Trade the fewest contracts that resolve the bracket intraday: 1 NQ is a 50-point stop and 62.5-point
target for all-in at $19 a leg; 20 MNQ for the same dollars costs ~$57 a leg.

## 6. Firm terms

Opposite positions across one person's accounts are prohibited by most futures prop firms and are
easy to detect; the usual remedy is closing the accounts and voiding payouts. `--void` prices it:
with the exit-together hedge, break-even is a 30% chance of voiding (consistency on) or 36% (off).
At the user's request every other number here assumes it never happens.

## 7. Bottom line

- **Risking the whole $1,000 on every account is the best way to run the hedge.** Each pair produces
  one pass 88.1% of the time after costs (88.9% before), which is the theoretical ceiling; every other
  hedge wastes some of it.
- **8 accounts → 4 funded: 60% if the consistency rule does not gate the pass, 24% if it does.**
  Expected 3.52 / 2.96 funded. The 4th pass is paid by the market during the naked last $250, not by
  the other accounts — in the closed, exit-together hedge 4 is out of reach with the rule on.
- **Payouts: ~2.3–2.8, worth ~$800–$940 to you for $522**, so +$275 to +$414 expected, a 53–70% chance
  of finishing ahead — under the assumed payout rules, which §4 shows matter a great deal.
- No hedge raises the *average*: unhedged zero-edge accounts pass at the same rate. Hedging trades
  the lottery for a narrower range of outcomes. A real edge is the only thing that moves the mean.

```bash
python research/propfirm_hedge.py --n 8 --consistency 1.0     # all four plans, rule off
python research/propfirm_hedge.py --sweep                     # N = 2..20, payout and cost grids
python research/propfirm_hedge_test.py                        # 63 checks, ~35 s
```

## 8. Verification, and three corrections

`research/propfirm_hedge_test.py` asserts, with a 4-standard-error band on every Monte Carlo check:

1. **Fairness of every trade primitive.** A solo leg hits its target with probability
   stop / (stop + target) and has expected move zero, for five stop/target pairs; the all-in pair
   produces one pass with probability 2S / (S + T); the exit-together pair, *including unequal
   cushions*, wins with probability down / (up + down) and has expected move zero; every pair is
   exactly zero-sum before costs, and each leg pays its cost once.
2. **The rules, case by case.** Threshold 24,000 → trails to 24,600 on a 25,600 close → does not move
   back on a losing day → locks at 25,100 and stays; exact-cushion loss is a bust, cost counts toward
   it, $1 inside survives; a single $1,250 day fails 50% consistency and passes with it off; two $625
   days pass; after a $900 day the pass-today move is $900; payouts respect the 5-day count, cap,
   fraction and floor, and never come from a losing account.
3. **The whole simulation against closed forms.** Independent rule-off passes = 8 x 1,000 / (1,000 + T);
   all-in rule-off passes = 4 x 2S / (S + T) and P(4 funded) = (2S / (S + T))⁴, at zero cost and at $19;
   copy-trading is all-or-nothing; no plan beats the 3.556 ceiling in expectation; an exit-together
   group's total P&L is exactly zero every day.

Earlier versions of this study had three bugs. The first two had the same shape — a trade whose two
outcomes were unequal in size, scored as a 50/50 coin, which is a hidden edge:

- **Solo legs** (fixed in the second version): +$1,269 / −$1,000 at even odds. It inflated the
  unhedged baselines and produced the false claim that unhedged accounts beat the hedge on average.
- **Exit-together pairs** (fixed here): with unequal cushions the pair's barriers are
  min(bracket, each side's cushion), so an account with $375 left and a $625 bracket wins 37.5% of the
  time, not 50%; at 50% it carried a +$126 per-trade edge.
- **The eval's daily step** (fixed here) was a gross $625, so a winning day booked $606 and the
  consistency path needed three wins instead of two. It is now $625 **net**.

Together the last two moved the exit-together hedge from 2.58 to 2.79 funded (N = 8, rule on):
2.58 → 2.67 from the pair fix alone, → 2.79 from the step. Every number in this document comes from
the corrected code.

## Caveats

- **No market data.** Only which side wins matters to a hedged pair, so a driftless price is the right
  model. It ignores bust slippage past the threshold, NQ's drift (NQ rose 89% on this sample, so the
  long side wins more often in a trending month, though the pair does not care which side wins), and
  brackets that do not resolve by the close. All-in's naked leg can need 50 more points at 2 NQ, or
  100 at 1 NQ; most sessions cover that, not all.
- Unhedged baselines assume zero edge, not negative edge.
- The payout rules marked as assumptions are guesses; §4 shows they matter.
- The funded scaling plan is not modelled. Funded accounts still alive after 250 trading days keep
  their unwithdrawn profit, which is not counted as money to you.
