# Hedging prop-firm evaluations across accounts: what 8, 9 or 10 accounts actually buy

The plan: buy N $25K Flex evaluations, go long in half and short in the other half, pass whichever
side wins, then hedge the funded accounts the same way and withdraw from the winners. The questions
as asked: *buy 8 accounts, get 4 funded, get 2 payouts or 1 max payout*; *risk the whole $1,000 on
every account to reach the $1,250 target*; and *what do 9 and 10 accounts do*.

Every example below is a **hedged** plan, in one of two forms:

- **exit-together** — both accounts close together when price has moved the day's bracket or either
  one touches its threshold, so no leg is ever left unhedged;
- **all-in** — each account's stop is its own threshold ($1,000 away) and its target is what it still
  needs, so the two legs exit separately (§2).

Everything is `research/propfirm_hedge.py` (stdlib only, no market data needed — see §1). Every trade
primitive and every headline closed form is asserted in `research/propfirm_hedge_test.py` (§8).
Headline tables are 20,000 runs (standard error ≤ $6 on E[net], ≤ 0.4 points on any probability);
the group-size sweep is 10,000, the rule and cost grids 5,000.

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
repo's standard figure). Funded accounts are hedged exit-together with a $250 bracket unless stated.

**Odd N.** With 9 accounts one has no partner. It sits out each day it is unpaired and, if it is the
last one left, trades alone. N = 9 against N = 10 (§2, §3) is therefore what a 10th account to pair it
with is worth.

## 1. The accounting identity

While two accounts hold opposite positions, the market is only a coin that decides *which* one
wins: their combined P&L is exactly minus the costs. An account can only lose until it touches its
threshold — at most $1,000. So a group that is hedged *the whole time* obeys

```
passes x $1,250  <=  busts x $1,000 - costs
passes           <=  N x 1,000 / 2,250  =  0.444 N          (3.56 for 8, 4.00 for 9, 4.44 for 10)
```

The same ceiling holds **on average** for any zero-edge plan: a driftless account is a martingale, so
P(pass) x 1,250 ≤ P(bust) x 1,000, i.e. P(pass) ≤ 1,000 / 2,250. Hedging cannot raise the average; what
it controls is the spread of outcomes and how much of the ceiling is wasted.

The funded phase obeys the same identity while hedged: every dollar withdrawn was lost by another
funded account, so gross withdrawals ≤ funded accounts x $1,000 − costs, and less in practice, because
once a threshold locks at start + $100 the profit below it is trapped.

Two things break the ceiling *in a single run* (never on average):

- **A leg left naked.** Once one account busts, its partner is unhedged and the market, not the
  group, pays it. This is exactly what the all-in plan does for the last $250.
- **A threshold checked only at the close.** "EOD" means the threshold is *recalculated* at the
  close; if the firm also only *checks* it then, a loser can sit $2,000 under water intraday and hand
  its partner $2,000. Ask the firm.

## 2. The all-in pair, and 8 / 9 / 10 accounts

Account A long and account B short, same size, same entry. Each leg's stop is its **own threshold**
and its target is the **$1,250 it needs**. At 2 NQ ($40/pt): a 25-point stop and 31.25-point target.

```
price moves 25 pts one way  ->  the losing account is closed at -$1,000
                                 the winner is at +$1,000, 6.25 pts from target, 50 pts from its stop
the winner, now naked        ->  reaches +$1,250 first with probability 50 / 56.25 = 88.9%
                                 (or falls 50 pts and busts too: 11.1%, both accounts gone)
```

For stop S and target T > S the pair produces one pass with probability **2S / (S + T)**: 0.889 at zero
cost and 2,000 / 2,269 = **0.881** once the target is grossed up by the $19 cost — 0.44 passes per
account, the ceiling itself. The loser donates all of its $1,000 and nothing is lost to partial wins,
trailing, or extra days of costs.

The target is reached on **one day**, and a $1,250 day is 100% of the profit. **If the 50%
consistency rule gates the pass, it does not pass** — the account then needs $2,500 of total profit.
Respecting the rule means two winning days of exactly $625 net, each still risking the whole cushion.

### Consistency rule off (a single $1,250 day passes)

| N | invested | plan | E[funded] | 4+ funded | E[payouts] | E[$ to you] | E[net] | P(net > 0) | 5th pct | 95th pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 8 | $522 | **all-in** | **3.52** | **59.7%** | 2.80 | $936 | **+$414** | **69.5%** | −$322 | +$1,917 |
| 8 | $522 | exit-together | 3.07 | 6.6% | 2.39 | $821 | +$299 | 54.8% | −$331 | +$1,685 |
| 9 | $588 | **all-in** | **3.97** | **74.8%** | 3.21 | $1,050 | **+$463** | **73.9%** | −$316 | +$1,950 |
| 9 | $588 | exit-together | 3.48 | 47.8% | 2.79 | $945 | +$357 | 63.2% | −$336 | +$1,862 |
| 10 | $653 | **all-in** | **4.41** | **88.7%** | 3.60 | $1,160 | **+$507** | **78.0%** | −$279 | +$2,049 |
| 10 | $653 | exit-together | 3.78 | 78.0% | 3.03 | $997 | +$344 | 63.4% | −$364 | +$1,801 |

### Consistency rule on (50%: two $625 days)

| N | invested | plan | E[funded] | 4+ funded | E[payouts] | E[$ to you] | E[net] | P(net > 0) | 5th pct | 95th pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 8 | $522 | **all-in** | **2.96** | **23.9%** | 2.31 | $798 | **+$275** | **52.8%** | −$409 | +$1,713 |
| 8 | $522 | exit-together | 2.79 | 0.0% | 2.14 | $745 | +$223 | 47.7% | −$391 | +$1,586 |
| 9 | $588 | **all-in** | **3.33** | **39.2%** | 2.64 | $895 | **+$307** | **57.9%** | −$448 | +$1,820 |
| 9 | $588 | exit-together | 3.13 | 18.8% | 2.47 | $851 | +$264 | 52.7% | −$431 | +$1,757 |
| 10 | $653 | **all-in** | **3.69** | **53.9%** | 2.98 | $991 | **+$338** | **60.6%** | −$434 | +$1,896 |
| 10 | $653 | exit-together | 3.44 | 44.9% | 2.75 | $931 | +$278 | 55.9% | −$401 | +$1,818 |

### Funded accounts out of N

| N | plan | consistency | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 8 | all-in | off | 0.6% | 6.6% | 33.0% | **59.7%** | — | — | — |
| 8 | exit-together | off | — | — | 93.4% | 6.6% | — | — | — |
| 8 | all-in | 50% | — | 33.0% | 43.1% | 19.5% | 4.0% | 0.4% | — |
| 8 | exit-together | 50% | — | 20.8% | 79.2% | — | — | — | — |
| 9 | all-in | off | 0.4% | 4.2% | 20.6% | 47.4% | **27.4%** | — | — |
| 9 | exit-together | off | — | — | 52.2% | 47.8% | — | — | — |
| 9 | all-in | 50% | — | 18.6% | 42.1% | 28.9% | 8.6% | 1.6% | 0.1% |
| 9 | exit-together | 50% | — | 5.9% | 75.3% | 18.8% | — | — | — |
| 10 | all-in | off | 0.1% | 1.3% | 9.9% | 35.3% | **53.4%** | — | — |
| 10 | exit-together | off | — | — | 22.0% | 78.0% | — | — | — |
| 10 | all-in | 50% | — | 7.2% | 38.8% | 35.6% | 14.3% | 3.5% | 0.4% |
| 10 | exit-together | 50% | — | 0.5% | 54.6% | 44.9% | — | — | — |

With the rule off the all-in rows are exact binomials of the pairs at 0.881: for 8 accounts
P(4) = 0.881⁴ = 60.4%; for 10, P(5) = 0.881⁵ = 53.2%; for 9, the four pairs plus the unpaired account
trading alone at 1,000 / 2,269 = 0.441, so P(5) = 0.881⁴ x 0.441 = 26.6% and
E[funded] = 4 x 0.881 + 0.441 = 3.97. The 8- and 9-account forms are asserted in the tests.

### Payouts, all-in

| N | consistency | 0 | 1 | 2 | 3 | 4 | 5+ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 8 | off | 0.9% | 11.5% | 32.0% | 32.3% | 15.1% | 8.2% |
| 9 | off | 0.5% | 7.0% | 23.7% | 32.6% | 21.7% | 14.5% |
| 10 | off | 0.1% | 3.2% | 15.8% | 32.2% | 27.8% | 20.9% |
| 8 | 50% | 2.0% | 28.9% | 32.0% | 21.4% | 9.1% | 6.6% |
| 9 | 50% | 1.2% | 19.5% | 31.9% | 25.1% | 13.0% | 9.3% |
| 10 | 50% | 0.4% | 11.9% | 29.4% | 28.2% | 16.9% | 13.2% |

### What the 9th and 10th accounts buy

- **The 9th has no partner.** With the rule off, every pair resolves on day 1, so the 9th trades alone
  on day 2 at 44% — unhedged. It still adds +0.45 funded and +$49 E[net] over 8 accounts, because a
  zero-edge account is worth more than its $65.30 fee under these payout terms. With the rule on, the
  two-day path leaves survivors for it to pair with, so it is partly hedged.
- **The 10th gives the 9th a partner.** All-in, rule off: 4.41 funded against 3.97, **5 funded in 53%**
  of runs, P(net > 0) 78.0% against 73.9%, and a better 5th percentile (−$279 against −$316). E[net]
  rises +$44 for the extra $65.30.
- **Getting 4+ funded:** all-in, rule off, needs 8 accounts for 60%, 9 for 75%, 10 for 89%. With the
  rule on: 24% / 39% / 54%.

## 3. Across group size

Hedged plans only; ex = exit-together, all-in = §2.

### Consistency rule off

| N | invested | ceiling | E[funded] ex | all-in | 4+ funded ex | all-in | E[payouts] ex | all-in | E[$ to you] ex | all-in | E[net] ex | all-in | P(net>0) ex | all-in |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | $131 | 0.89 | 0.78 | 0.88 | — | — | 0.38 | 0.42 | $234 | $259 | +$103 | +$128 | 25.8% | 29.0% |
| 3 | $196 | 1.33 | 1.09 | 1.33 | — | — | 0.59 | 0.81 | $311 | $365 | +$115 | +$169 | 35.4% | 43.1% |
| 4 | $261 | 1.78 | 1.54 | 1.77 | — | — | 0.98 | 1.22 | $416 | $481 | +$155 | +$220 | 46.3% | 53.0% |
| 5 | $326 | 2.22 | 1.87 | 2.21 | — | — | 1.31 | 1.61 | $521 | $600 | +$194 | +$274 | 48.7% | 58.1% |
| 6 | $392 | 2.67 | 2.27 | 2.64 | — | — | 1.67 | 2.01 | $607 | $715 | +$215 | +$324 | 47.0% | 61.7% |
| 7 | $457 | 3.11 | 2.66 | 3.09 | 0.4% | 30.2% | 2.03 | 2.40 | $713 | $825 | +$256 | +$368 | 54.1% | 65.6% |
| 8 | $522 | 3.56 | 3.07 | 3.52 | 6.8% | 59.5% | 2.39 | 2.80 | $819 | $935 | +$296 | +$413 | 55.2% | 70.0% |
| **9** | **$588** | **4.00** | **3.48** | **3.97** | **47.9%** | **74.2%** | **2.78** | **3.22** | **$948** | **$1,052** | **+$361** | **+$464** | **63.0%** | **73.9%** |
| **10** | **$653** | **4.44** | **3.78** | **4.41** | **77.6%** | **89.1%** | **3.03** | **3.60** | **$998** | **$1,155** | **+$345** | **+$502** | **63.3%** | **77.8%** |
| 12 | $784 | 5.33 | 4.58 | 5.29 | 100.0% | 97.7% | 3.74 | 4.40 | $1,191 | $1,378 | +$407 | +$594 | 69.9% | 83.5% |
| 16 | $1,045 | 7.11 | 6.11 | 7.05 | 100.0% | 100.0% | 5.15 | 5.98 | $1,592 | $1,824 | +$547 | +$779 | 81.3% | 90.5% |
| 20 | $1,306 | 8.89 | 7.63 | 8.82 | 100.0% | 100.0% | 6.50 | 7.54 | $1,969 | $2,254 | +$663 | +$948 | 86.6% | 94.4% |

### Consistency rule on (50%)

| N | invested | ceiling | E[funded] ex | all-in | 4+ funded ex | all-in | E[payouts] ex | all-in | E[$ to you] ex | all-in | E[net] ex | all-in | P(net>0) ex | all-in |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | $131 | 0.89 | 0.68 | 0.74 | — | — | 0.32 | 0.37 | $200 | $209 | +$69 | +$79 | 22.2% | 25.0% |
| 3 | $196 | 1.33 | 1.04 | 1.11 | — | — | 0.54 | 0.64 | $290 | $315 | +$94 | +$119 | 33.4% | 36.3% |
| 4 | $261 | 1.78 | 1.43 | 1.48 | — | 0.2% | 0.88 | 0.94 | $400 | $421 | +$139 | +$159 | 44.2% | 46.2% |
| 5 | $326 | 2.22 | 1.72 | 1.86 | — | 1.6% | 1.15 | 1.30 | $469 | $526 | +$142 | +$199 | 45.2% | 50.5% |
| 6 | $392 | 2.67 | 2.05 | 2.22 | — | 5.3% | 1.49 | 1.61 | $569 | $603 | +$177 | +$211 | 42.4% | 48.7% |
| 7 | $457 | 3.11 | 2.43 | 2.59 | — | 13.6% | 1.83 | 1.98 | $670 | $713 | +$213 | +$255 | 49.0% | 54.0% |
| 8 | $522 | 3.56 | 2.79 | 2.96 | — | 24.0% | 2.14 | 2.31 | $739 | $794 | +$217 | +$272 | 47.8% | 52.9% |
| **9** | **$588** | **4.00** | **3.13** | **3.34** | **18.9%** | **39.8%** | **2.46** | **2.64** | **$847** | **$894** | **+$259** | **+$307** | **52.6%** | **58.1%** |
| **10** | **$653** | **4.44** | **3.44** | **3.70** | **44.6%** | **54.0%** | **2.75** | **2.99** | **$931** | **$992** | **+$278** | **+$339** | **56.3%** | **60.7%** |
| 12 | $784 | 5.33 | 4.19 | 4.43 | 95.9% | 81.0% | 3.42 | 3.63 | $1,111 | $1,173 | +$328 | +$389 | 61.3% | 65.7% |
| 16 | $1,045 | 7.11 | 5.58 | 5.91 | 100.0% | 100.0% | 4.66 | 4.95 | $1,448 | $1,538 | +$404 | +$493 | 69.4% | 72.6% |
| 20 | $1,306 | 8.89 | 6.96 | 7.41 | 100.0% | 100.0% | 5.89 | 6.33 | $1,809 | $1,933 | +$503 | +$627 | 75.4% | 78.0% |

All-in beats exit-together on E[funded], E[net] and P(net > 0) at every N under both readings. With the
rule off it sits within about 1% of the ceiling at every even N; the rule costs it about 16% of its
passes. The one place exit-together wins is *4+ funded at N = 12, rule on* (95.9% against 81.0%): it
rarely strays far from its mean, so once the mean clears 4 it almost always gets there.

## 4. The unstated payout rules

N = 8, both hedges (5,000 runs per cell):

| payout cap | withdraw per request | split | rule off: ex E[$] | ex E[net] | all-in E[$] | all-in E[net] | rule on: ex E[$] | ex E[net] | all-in E[$] | all-in E[net] |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| $500 | 50% | 90% | $775 | +$252 | $883 | +$360 | $727 | +$205 | $772 | +$250 |
| $1,000 | 50% | 80% | $717 | +$195 | $813 | +$290 | $668 | +$145 | $714 | +$192 |
| **$1,000** | **50%** | **90%** | **$807** | **+$284** | **$914** | **+$392** | **$751** | **+$229** | **$804** | **+$281** |
| $1,000 | 100% | 90% | $930 | +$408 | $1,067 | +$545 | $846 | +$324 | $901 | +$378 |
| $1,000 | 100% | 100% | $1,033 | +$511 | $1,186 | +$663 | $940 | +$418 | $1,001 | +$479 |
| none | 100% | 90% | $931 | +$409 | $1,070 | +$547 | $848 | +$325 | $907 | +$385 |

The cap barely binds; the **fraction of profit you may withdraw per request** is what matters,
because what is left in the account is what the lock traps.

## 5. Costs and the funded bracket

N = 8, both hedges (5,000 runs per cell):

| $/leg/day | funded bracket | rule off: ex E[net] | all-in E[net] | rule on: ex E[net] | all-in E[net] |
| --- | --- | --- | --- | --- | --- |
| 0 | $250 | +$697 | +$831 | +$611 | +$606 |
| 0 | $500 | +$593 | +$698 | +$502 | +$547 |
| 10 | $250 | +$465 | +$596 | +$380 | +$405 |
| 10 | $500 | +$510 | +$638 | +$445 | +$505 |
| **19** | **$250** | **+$284** | **+$392** | **+$229** | **+$281** |
| 19 | $500 | +$437 | +$554 | +$317 | +$420 |
| 38 | $250 | +$37 | +$124 | −$12 | +$29 |
| 38 | $500 | +$244 | +$324 | +$176 | +$252 |

Costs are paid per day, so bigger, fewer days win: at any nonzero cost the $500 funded bracket beats
$250 in every column. Trade the fewest contracts that resolve the bracket intraday: 1 NQ is a 50-point
stop and 62.5-point target for all-in at $19 a leg; 20 MNQ for the same dollars costs ~$57 a leg.

## 6. Firm terms

Opposite positions across one person's accounts are prohibited by most futures prop firms and are
easy to detect; the usual remedy is closing the accounts and voiding payouts. Break-even probability
of voiding, from `--void`:

| N | rule off: ex | all-in | rule on: ex | all-in |
| --- | --- | --- | --- | --- |
| 8 | 36% | 44% | 30% | 35% |
| 9 | 38% | 44% | 31% | 34% |
| 10 | 35% | 44% | 30% | 34% |

At the user's request every other number here assumes voiding never happens.

## 7. Bottom line

- **Risk the whole $1,000 on every account (all-in).** Each pair produces one pass 88.1% of the time
  after costs, which is the theoretical ceiling; exit-together wastes some of it at every N.
- **4+ funded, all-in:** 8 accounts 60% / 24% (rule off / on), 9 accounts 75% / 39%, 10 accounts
  89% / 54%. Expected funded 3.52 / 3.97 / 4.41 with the rule off.
- **Prefer an even N.** The 9th account has no partner and, with the rule off, trades alone. The 10th
  fixes that: 5 funded in 53% of runs and P(net > 0) 78%.
- **Money, all-in, rule off:** 8 accounts +$414 on $522, 9 +$463 on $588, 10 +$507 on $653; a 70–78%
  chance of finishing ahead — under the assumed payout rules, which §4 shows matter a great deal.
- Hedging does not raise the average (§1): it narrows the range of outcomes. A real edge is the only
  thing that moves the mean.

```bash
python research/propfirm_hedge.py --n 10 --consistency 1.0     # both hedges, rule off
python research/propfirm_hedge.py --sweep                      # N = 2..10, 12, 16, 20 and both grids
python research/propfirm_hedge.py --baselines                  # add unhedged zero-edge comparisons
python research/propfirm_hedge_test.py                         # 67 checks
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
3. **The whole simulation against closed forms.** All-in rule-off: 8 accounts give 4 x 2S / (S + T)
   passes and P(4 funded) = (2S / (S + T))⁴; 9 accounts give 4 x 2S / (S + T) + S / (S + T) and
   P(5 funded) = (2S / (S + T))⁴ x S / (S + T) — each at zero cost and at $19. The unhedged and
   copy-traded baselines match their closed forms; no plan beats the ceiling in expectation; an
   exit-together group's total P&L is exactly zero every day.

Earlier versions of this study had three bugs. The first two had the same shape — a trade whose two
outcomes were unequal in size, scored as a 50/50 coin, which is a hidden edge:

- **Solo legs**: +$1,269 / −$1,000 at even odds. It inflated the unhedged baselines and produced the
  false claim that unhedged accounts beat the hedge on average.
- **Exit-together pairs**: with unequal cushions the pair's barriers are min(bracket, each side's
  cushion), so an account with $375 left and a $625 bracket wins 37.5% of the time, not 50%; at 50% it
  carried a +$126 per-trade edge.
- **The eval's daily step** was a gross $625, so a winning day booked $606 and the consistency path
  needed three wins instead of two. It is now $625 **net**.

Every number in this document comes from the corrected code.

## Caveats

- **No market data.** Only which side wins matters to a hedged pair, so a driftless price is the right
  model. It ignores bust slippage past the threshold, NQ's drift (NQ rose 89% on this sample, so the
  long side wins more often in a trending month, though the pair does not care which side wins), and
  brackets that do not resolve by the close. All-in's naked leg can need 50 more points at 2 NQ, or
  100 at 1 NQ; most sessions cover that, not all.
- The payout rules marked as assumptions are guesses; §4 shows they matter.
- The funded scaling plan is not modelled. Funded accounts still alive after 250 trading days keep
  their unwithdrawn profit, which is not counted as money to you.
