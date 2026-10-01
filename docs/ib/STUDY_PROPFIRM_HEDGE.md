# Hedging prop-firm evaluations across accounts: what 8 accounts actually buy

The plan being tested: buy N $25K Flex evaluations, go long in half and short in the other half with
the same bracket, pass whichever side wins, then hedge the funded accounts the same way and withdraw
from the winners. The question as asked: *buy 8 accounts, get 4 funded, get 2 payouts or 1 max payout.*

Everything below is `research/propfirm_hedge.py` (stdlib + numpy, no market data needed — see §1),
20,000 Monte Carlo runs per row.

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
fee. §4 shows how much these move the answer. Costs: **$19 per account per trading day** (one NQ round
turn — $4 commission, one tick spread, one tick slippage, the repo's standard figure).

## 1. It is an accounting identity before it is a simulation

A hedged pair has no market exposure, so the market is only a coin that decides *which* account
wins. Summed over every account in the group, P&L is exactly **minus the costs**. Every dollar an
account gains was lost by its partner, and an account can only lose until it hits its threshold —
at most $1,000. So:

```
passes x $1,250  <=  busts x $1,000 - costs
passes           <=  N x 1,000 / 2,250  =  0.444 N          (zero costs, perfect play)
```

**8 accounts hedged only against each other cannot produce 4 funded accounts.** The ceiling is
3.56 with zero costs; four passes need $5,000 of gains, and the other four accounts only hold
$4,000 of drawdown between them. This is a statement about the *closed* group, and it rests on two
things worth checking with the firm:

- **The threshold is enforced in real time.** "EOD" here means the threshold is *recalculated* at
  the close; if the firm only *checks* it at the close, a loser can sit $2,000 under water intraday
  and hand its partner $2,000, and the ceiling no longer holds.
- **Nothing outside the group pays.** Unhedged accounts are paid by the market, so 4 of 8 is
  possible — the same 8 accounts traded independently with zero edge get 4+ funded in **42.9%** of
  runs (copy-traded, 41.4%, but 0 funded in 58.6%). The ceiling still holds *on average* — a
  zero-edge account is a martingale — but not in any one run. Hedging is exactly what removes that
  upside: hedged, 4+ funded happens in 0.0% of runs.

The same identity caps the funded phase: every dollar withdrawn was lost by another funded account, so

```
gross withdrawn  <=  funded accounts x $1,000 - costs       (3 funded -> <= $2,700 to you at 90%)
```

and in practice well under that, because once an account's threshold locks at start + $100 the
profit below it is trapped: it can no longer be donated to a partner or withdrawn.

## 2. The 8-account plan, simulated

Policy: pair live accounts in similar states each day; bracket = the move that passes one of them
today with consistency intact, else $625 (half the target, the largest day the 50% rule allows);
the pair exits together when the winner makes the bracket or the loser touches its threshold, so no
leg is ever left naked. An odd account sits the day out; the last survivor trades alone. Funded:
same, $250 bracket (§5 has $500). Adjacent pairing beat strongest-vs-weakest and random pairing
(3.01 / 2.82 / 2.90 passes at zero cost).

8 accounts, $522 invested:

| mode | E[funded] | E[payouts] | E[$ to you] | E[net] | P(net > 0) | 5th pct | 95th pct | median days |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **hedge** | **2.63** | **2.57** | **$686** | **+$164** | **49.8%** | −$399 | +$1,280 | 38 |
| independent, unhedged | 3.28 | 3.39 | $959 | +$437 | 59.3% | −$522 | +$2,272 | 33 |
| copy-traded, all same side | 3.31 | 3.42 | $962 | +$439 | 21.9% | −$522 | +$5,515 | 7 |

- Funded accounts out of 8, hedged: **3 in 63%** of runs, **2 in 37%**, never 4.
- Payouts, hedged: 0 in 1%, 1 in 22%, 2 in 33%, 3 in 23%, 4+ in 21%. Average payout ≈ $265 to you
  under the assumed 50%-of-profit rule — this is not a "max payout" plan.

"Independent" and "copy" are the same accounts with **no edge at all**: random direction, same
bracket, same costs. That row is the baseline the hedge has to beat, and it does not beat it.

## 3. Hedging creates no edge — it gives some back

The same rule this repo found for sizing (§9 of the protocol) applies across accounts. A zero-edge
unhedged account is a martingale, so it obeys the same 0.444 ceiling *in expectation*; the hedge
only makes the count nearly deterministic. What the hedge costs on top:

1. **Waste in the pairing.** The winner only banks what the loser actually had left, so a win
   against a partner with $356 of cushion is a $356 win, not a $625 one.
2. **Both legs pay costs every day.** An unhedged account that busts early stops paying; a hedged
   one is paying to be the other side of its partner's progress.
3. **The lock traps profit on both sides of the pair.**

Result at 8 accounts: 2.63 funded against 3.28 unhedged, and +$164 expected against +$437. The
hedge's only win is a milder bad case (5th percentile −$399 vs −$522). Across group size:

| N | invested | ceiling | hedge E[funded] | E[payouts] | E[$ to you] | hedge E[net] | P(net>0) | unhedged E[net] | P(net>0) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | $131 | 0.89 | 0.67 | 0.69 | $195 | +$64 | 32.5% | +$109 | 35.9% |
| 4 | $261 | 1.78 | 1.42 | 1.43 | $395 | +$133 | 48.7% | +$222 | 49.9% |
| 6 | $392 | 2.67 | 1.98 | 1.97 | $530 | +$139 | 46.5% | +$329 | 56.1% |
| 8 | $522 | 3.56 | 2.63 | 2.57 | $686 | +$164 | 49.8% | +$437 | 59.3% |
| 10 | $653 | 4.44 | 3.35 | 3.25 | $862 | +$209 | 56.8% | +$544 | 62.9% |
| 12 | $784 | 5.33 | 4.03 | 3.85 | $1,021 | +$237 | 60.1% | +$651 | 65.9% |
| 16 | $1,045 | 7.11 | 5.32 | 5.05 | $1,339 | +$294 | 64.8% | +$870 | 70.6% |
| 20 | $1,306 | 8.89 | 6.70 | 6.31 | $1,667 | +$361 | 71.2% | +$1,101 | 74.8% |

Unhedged beats hedged at every N. Note what the unhedged column is saying: at a $65 fee and these
(assumed) payout terms, a **zero-edge** trader has positive expectation. That is the structure of the
product — losses cost you the fee, gains are paid in real money — and it is the only source of
positive expectation anywhere in this study. The firm prices it with rules the screenshots do not
show (payout caps, buffers, winning-day definitions, discretionary review), so treat that column as
an upper bound, not an opportunity.

## 4. The unstated payout rules move the answer more than anything you control

N = 8, hedged:

| payout cap | withdraw per request | split | E[payouts] | E[$ to you] | E[net] |
| --- | --- | --- | --- | --- | --- |
| $500 | 50% | 90% | 2.71 | $694 | +$172 |
| $1,000 | 50% | 80% | 2.61 | $613 | +$90 |
| **$1,000** | **50%** | **90%** | **2.61** | **$689** | **+$167** |
| $1,000 | 100% | 90% | 2.24 | $834 | +$312 |
| $1,000 | 100% | 100% | 2.24 | $927 | +$405 |
| none | 100% | 90% | 2.22 | $832 | +$310 |

The cap barely binds (profits rarely reach it before a bust); the **fraction of profit you may
withdraw per request** is what matters, because what is left in the account is what the lock traps.
Read the firm's actual payout policy before believing any row.

## 5. Costs and bracket size

N = 8, hedged:

| $/leg/day | eval step | funded step | E[funded] | E[$ to you] | E[net] |
| --- | --- | --- | --- | --- | --- |
| 0 | 625 | 250 | 3.02 | $1,255 | +$733 |
| 10 | 625 | 500 | 2.79 | $1,074 | +$551 |
| **19** | **625** | **250** | **2.64** | **$689** | **+$167** |
| 19 | 625 | 500 | 2.64 | $909 | +$387 |
| 19 | 400 | 150 | 2.35 | $410 | −$112 |
| 38 | 625 | 250 | 2.46 | $390 | −$133 |
| 38 | 625 | 500 | 2.47 | $685 | +$162 |

Costs are paid per day, so **bigger, fewer days** wins: small brackets lose money. $38/leg is 2 NQ
or ~13 MNQ — using 20 micros to hit a bracket costs more than one mini, so trade the fewest
contracts that resolve the bracket intraday (1 NQ = 31 points for $625). A $500 funded bracket
lifts E[net] to +$387 but makes it lumpier: **29.5% of runs get no payout at all**, 42% get one.

## 6. The risk that is not in the market

Opposite positions across accounts are prohibited by essentially every futures prop firm, and they
are easy to detect: one identity, same instrument, opposite sides, same timestamps. The usual
remedy is closing every account and voiding payouts. With E[$ to you] = $686 and $522 invested:

| P(firm voids hedged payouts) | E[net] |
| --- | --- |
| 0% | +$164 |
| 25% | −$8 |
| 50% | −$179 |
| 90% | −$454 |

**Break-even is a 24% chance of being caught.** Check this firm's terms directly — if cross-account
hedging is prohibited there, the realistic row is the bottom one.

## 7. Bottom line

- **8 accounts → 4 funded is impossible if the 8 are only hedged against each other**, not
  unlikely: the ceiling is 3.56 at zero cost, and the simulated hedge gets 3 funded 63% of the time
  and 2 the rest. Unhedged, 4+ happens 43% of the time — by luck, which is what hedging removes.
- **2 payouts is about right; they are small.** ~2.6 payouts worth ~$690 in total for $522 in fees:
  +$164 expected, a coin flip to finish ahead, before any ban risk. Not a max payout.
- **Hedging is strictly worse than not hedging** on expected value at every group size tested. It
  converts a lottery into a near-certain small number and pays for that in costs and trapped profit.
- The only positive expectation here comes from the fee being small relative to the payout — which
  an unhedged, zero-edge trader also collects, without the terms-of-service risk. A real edge is the
  only thing that moves these numbers materially; see `STUDY_PROP_FIRM.md` for what one is worth.

Re-run with the firm's real payout terms:

```bash
python research/propfirm_hedge.py --n 8 --payout-frac 1.0 --payout-cap 1500 --split 0.9 --void 0 0.25 0.5
python research/propfirm_hedge.py --sweep
```

## Caveats

- **No market data.** A hedged pair's outcome does not depend on the market's path, only on which
  side wins, so a fair coin is the right model. It ignores bust slippage past the threshold (costs
  absorb it), and brackets that do not resolve by the close (at 31 NQ points this is rare).
- Unhedged baselines use a fair coin: they assume no edge and no negative edge. A trader with worse
  than zero edge does worse than that row; one with a real edge does better.
- The payout rules in §0 marked as assumptions are guesses, and §4 shows they matter.
- The funded scaling plan is not modelled; it only restricts size early, which a $19/day, 1-NQ
  bracket already respects.
