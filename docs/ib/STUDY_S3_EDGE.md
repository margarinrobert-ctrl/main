# Is there a real edge in S3? Four tests, and two of my own objections withdrawn

Written because I asserted there was no edge and was challenged on it. The challenge was partly
right. This records what changed, what did not, and the two errors of mine that produced the
overstatement.

Everything here is on NQ 5m, k3/w20, the shipped geometry, 07:00-11:00 New York, flat at 11:00.
**Nothing is selected anywhere in this study** -- the constants are fixed throughout, so there is
no new multiplicity and no holdout is spent.

## 1. What was already true

Locked block: 179 trades, +11.41 pts/trade, PF 1.467, Sharpe 1.75, day-block bootstrap
P(mean<=0) **0.032**, clears a matched random entry at p 0.018 and a coin-flip side at p 0.008.
Research block: 380 trades, +2.31, PF 1.118, Sharpe 0.55, bootstrap P(mean<=0) 0.256.

## 2. The split date does not decide the verdict -- objection weakened

I said the research/locked cut at 2024-11-27 happens to fall inside the good stretch. Swept over
twelve cut dates from 2023-11 to 2025-07, **both sides are profitable at 8 of 12**, and the first
block's per-trade result is positive at every cut from 0.55 onward. The verdict is not an artifact
of where the line falls, which is more robustness than I credited.

## 3. THE CONCENTRATION OBJECTION WAS MINE AND IT FAILS ITS OWN CONTROL

The raw numbers look damning: remove the best 5% of trades and the locked block goes
+11.41 -> **-0.10** pts/trade, research +2.31 -> -6.45. I offered that as evidence the result is a
handful of trades.

It is not evidence, because a no-target system with a 3xATR stop and a 1R trail is DESIGNED to earn
in the tail -- so heavy concentration is a property of the exits that ANY entry inherits. The test
is the same statistic on the matched random entry (same window, rate, side mix, geometry, lock):

| | rule research | control | rule LOCKED | control |
|---|---|---|---|---|
| mean pts/trade | +2.31 | -1.55 | +11.41 | -2.05 |
| **MEDIAN trade** | **+3.89** | -5.22 | **+11.82** | -5.22 |
| top 5% share of net | 365% | -202% | 101% | -109% |
| **ex-top-5% mean** | **-6.45** | -8.76 | **-0.10** | -12.38 |
| win rate | 52.4% | 48.2% | 60.3% | 48.4% |

**The rule's MEDIAN trade beats the control in 97.8% of research draws and 99.8% of locked draws.**
The median is immune to the tail by construction, so this cannot be a tail artifact. And the
**ex-top-5% mean beats the control in 85.2% and 99.5% of draws** -- with the tail surgically
removed the rule is still 2.3 and 12.3 points better than a random entry with identical geometry.
My "-0.10 is basically zero" compared the rule to ZERO when the right comparison is the control at
-12.38.

The tail itself is also not just luck: the rule produces **more** big winners (24.6% of locked
trades over +50 pts against the control's 17.0%) and **bigger** ones (p90 +95.6 against +79.8).

Objection withdrawn. Concentration is the geometry.

## 4. MY DEFLATION WAS WRONG IN TWO WAYS, BOTH TOO HARSH

`STUDY_S3_10M` reported E[max Sharpe | noise] = 0.2159 at N = 1,295 and concluded that not even the
5-minute version clears the noise floor. Two errors:

1. **It counted VALIDATION looks as SEARCH looks.** 1,260 of the 1,295 cells were the 10-minute
   geometry grid, run to falsify the 5m result -- a test performed on a finished result is not a
   trial that produced it. Honest search count: **N = 805**.
2. **`var_trials` came from the wrong population** -- the 10-minute family, which is worse and more
   dispersed. The 5-minute family's variance is **0.001607 against 0.004208**, and a larger
   variance inflates E[max].

Redone with the 5m variance, as a curve because the N assumption does the work:

| N | E[max \| noise] | research DSR | LOCKED DSR |
|---|---|---|---|
| 100 | 0.1014 | 0.105 | 0.688 |
| **805** | **0.1280** | **0.037** | **0.550** |
| 5,000 | 0.1478 | 0.014 | 0.442 |

Per-trade Sharpe is +0.0393 research and **+0.1372 locked**. At the honest N the **locked cell
clears the noise floor (0.137 > 0.128)** and stays above it out to about N = 2,000. Not significant
-- DSR 0.55 -- but "clears the floor" and "fails it" are different claims and I published the wrong
one. Non-parametric check, best-of-30 matched random entries: locked **p 0.346**, research p 0.958.

## 5. What still stands against it

- **The research block does not separate from zero.** Bootstrap P(mean<=0) 0.256, DSR 0.037 at
  N=805, best-of-30 p 0.958. The block permitted to choose it says "maybe"; the block read once
  says "yes". That is the wrong order and it has never been the good kind of surprise here.
- **The magnitude is regime-dependent.** By quarter, fixed constants, nothing selected: 8 of 12
  positive overall, but **3 of 6 in the first half at a mean of -1.82 pts** against **5 of 6 in the
  second half at +13.22**. The direction call looks present throughout; the money is not.
- **At 10 minutes it is negative on research at every one of 630 geometry cells** (`STUDY_S3_10M`),
  and the two timeframes catch largely different trades (daily corr +0.107).
- **One market, never confirmed elsewhere.** The CVD needs sub-bars and NQ is the only feed here
  with 1-minute data.

## 6. The dollar answer, with the synthetic-level deflator applied

`STUDY_US100.md` records that the stored NQ series carries levels above the real index and that the
ratio decays across the sample, so DOLLAR magnitudes are inflated and inflated MOST EARLY -- which
is the research block. Measured here against US100 over **862 overlapping sessions**, the ratio runs
0.801 to 0.971; the mean deflator is **0.8804 on research and 0.9641 on locked**, i.e. raw points
overstate by 13.6% and 3.7%. Applied per trade:

| year | trades | raw pts | real pts | $ (1 MNQ) | PF | win |
|---|---|---|---|---|---|---|
| 2023 | 205 | -372.4 | -305.5 | **-611** | 0.908 | 52.7% |
| 2024 | 192 | +1,621.5 | +1,500.1 | **+3,000** | 1.445 | 53.1% |
| 2025 | 162 | +1,671.2 | +1,626.7 | **+3,253** | 1.404 | 59.9% |
| **total** | **559** | +2,920.3 | +2,821.3 | **+5,643** | 1.263 | 55.1% |

**$1,924 a year on one contract**, 191 trades a year, **$10.09 a trade**, worst drawdown **$1,670**,
return/drawdown **3.38**. By block: research $4.44/trade, locked $22.10/trade.

Cost sensitivity -- the one axis where this candidate is unusually comfortable, because a 3xATR stop
on 5m NQ is ~45 points and the round turn is under 4% of it: zero cost $13.92/trade, as modelled
$10.09, 2x $5.77, **4x -$2.63**. It survives double the assumed spread, which most candidates on
this branch do not.

Month by month: 37 months, **23 positive (62%)**, best +$1,966, worst -$724, longest losing run
**3 months**. First 12 months **-$512**, next 12 +$2,262, rest +$3,893.

## 6b. The out-of-sample block on its own

The locked block is the only stretch that had no say in choosing the rule. Read once, deflated,
one MNQ contract, costs included:

| | |
|---|---|
| period | 2024-11-27 to 2025-12-11 (269 sessions, 1.07 years) |
| trades | 179 (168 a year) |
| **net** | **+$3,956** |
| per trade | **$22.10** (median $23.08) |
| profit factor | 1.470 |
| win rate | 60.3% (108W / 71L) |
| Sharpe | **+1.76** (over every session, zero-filled) |
| max drawdown | $1,670, return/drawdown 2.37 |
| avg win / avg loss | $114 / -$118 |
| best / worst trade | +$677 / -$576 |

Month by month: **13 of 14 positive**, best +$1,161, worst -$724 (March 2025), longest losing run
**one month**. Note the shape -- the average win and average loss are almost identical ($114 vs
-$118), so the whole result is the 60.3% win rate, not asymmetric payoffs.

That is a clean year. What it is not: it is ONE year, ONE market, and the rule's best calendar year
in the sample. The research block earns $4.44 a trade against this block's $22.10, and a forward
expectation is somewhere in that range -- nearer the low end, because the research block is three
times longer and contains the only regime in which the rule lost.

## 7. Verdict, updated

**There is a real and repeatedly measurable EFFECT.** The rule selects better bars and better sides
than a random entry with identical geometry, on both blocks, on statistics that are immune to the
tail (median trade, ex-tail mean, win rate) -- 97.8-99.8% of draws on the median. That is more than
"no edge", and my earlier statement overstated the case against it.

**It is not an established edge of the size the P&L suggests.** The research block does not clear
zero, the money is concentrated in the second half of one sample, it fails at a different bar size,
and it has one market. The effect being real and the P&L being repeatable are different claims and
only the first has support.

What would settle it: **1-minute US100 or US30 data.** That is the only thing that turns one market
into two, and no amount of further work on the data here substitutes for it.

`research/s310/run_w1.py`, `run_w2.py`, `run_w3.py`.
