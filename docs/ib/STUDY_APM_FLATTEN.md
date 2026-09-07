# APM with a hard flatten at 11:00 New York: out of sample and walk-forward

11:00 is where the **entry window ends**, so a flatten there caps every trade at 90 minutes and
turns a hold-to-the-cash-close rule into a morning scalp. Four arms throughout so the flatten and
the stop are never confounded:

| arm | stop | flatten |
|---|---|---|
| **A source** | none | none (cash close / opposite cross) |
| **B flat 11:00** | none | 11:00 |
| **C stop 3N** | 3.0 × ATR | none (the shipped default) |
| **D stop+flat** | 3.0 × ATR | 11:00 |

## Out of sample, $/trade, one contract, costs in

| arm | NQ locked | NQ res | US100 res | US100 test | US100 val | US30 res | US30 test | US30 val |
|---|---|---|---|---|---|---|---|---|
| A source | **125.62** | 48.03 | 10.77 | 15.31 | 34.55 | -7.87 | 4.58 | 16.41 |
| B flat 11:00 | 31.09 | 36.48 | 6.73 | 2.20 | 12.12 | **2.47** | -3.73 | **-21.46** |
| C stop 3N | 70.73 | 44.46 | 13.67 | **28.56** | 42.21 | 0.29 | -8.13 | 18.97 |
| D stop+flat | 6.42 | 28.96 | 6.38 | 1.84 | 12.45 | 2.99 | -7.27 | -16.39 |

Averaged over all eight market-blocks:

| arm | $/trade | PF | win | Sharpe | max DD | ret/DD | worst trade | median hold |
|---|---|---|---|---|---|---|---|---|
| A source | **30.93** | **1.700** | 56.4% | 0.849 | 1,166 | 2.592 | -614 | **354 min** |
| B flat 11:00 | 8.24 | 1.380 | 51.8% | 0.513 | 643 | 2.202 | -226 | **57 min** |
| C stop 3N | 26.35 | 1.602 | 49.5% | **0.923** | 942 | **3.213** | -296 | 314 min |
| D stop+flat | **4.42** | 1.244 | 51.1% | 0.345 | 645 | 1.686 | -214 | **48 min** |

**THE FLATTEN COSTS 73% OF THE PER-TRADE RESULT** (30.93 -> 8.24) and, stacked on the stop, 83%
(26.35 -> 4.42). It cuts the median hold from 354 minutes to 57 — that is the mechanism, and it is
the seventeenth confirmation of the intraday-constraint finding on this branch.

It is not free-standing bad: drawdown halves (1,166 -> 643) and the worst trade improves
-614 -> -226. But **the stop buys the same protection more cheaply** — 942 drawdown and -296 worst
at a cost of only $4.58 a trade, with Sharpe and return/drawdown both RISING. On every risk-adjusted
measure the stop dominates the flatten:

| | $/trade cost | drawdown | worst trade | Sharpe | ret/DD |
|---|---|---|---|---|---|
| stop 3N | -$4.58 | -19% | -52% | **+0.074** | **+0.62** |
| flatten 11:00 | **-$22.69** | -45% | -63% | **-0.336** | -0.39 |

Blocks profitable: A 7 of 8, B 6, C 7, D 6. **The flatten turns US100's test block from +$15.31 to
+$2.20 and US30's validation block from +$16.41 to -$21.46.** The one place it helps is US30's
research block (-$7.87 -> +$2.47), which is the block that loses without it.

## Walk-forward, fixed constants, nothing re-selected

Rolling folds — NQ 12m train / 3m test, US100 and US30 24m / 6m — with the configuration held
completely fixed:

| market | arm | folds | positive | mean %/trade | worst fold | best fold |
|---|---|---|---|---|---|---|
| NQ | A source | 6 | 4 | +0.2330 | -0.0508 | +0.6292 |
| NQ | B flat 11:00 | 6 | 4 | +0.0616 | -0.0736 | +0.1958 |
| NQ | C stop 3N | 6 | **5** | +0.1977 | -0.0458 | +0.4935 |
| NQ | D stop+flat | 6 | 4 | +0.0599 | -0.1282 | +0.1958 |
| US100 | A source | 13 | 10 | +0.1316 | -0.1840 | +0.4358 |
| US100 | B flat 11:00 | 13 | **12** | +0.0807 | **-0.0169** | +0.1632 |
| US100 | C stop 3N | 13 | 11 | **+0.1850** | -0.0629 | +0.5947 |
| US100 | D stop+flat | 13 | 11 | +0.0748 | -0.0468 | +0.1582 |
| US30 | A source | 13 | 5 | +0.0159 | -0.3109 | +0.6368 |
| US30 | B flat 11:00 | 13 | 6 | **-0.0166** | -0.1129 | +0.0773 |
| US30 | C stop 3N | 13 | 5 | +0.0207 | -0.1708 | +0.4692 |
| US30 | D stop+flat | 13 | 5 | **-0.0147** | -0.1141 | +0.0844 |

Pooled across the three markets:

| arm | folds positive | mean %/trade |
|---|---|---|
| A source | 19/32 | +0.1268 |
| **B flat 11:00** | **22/32** | +0.0419 |
| **C stop 3N** | 21/32 | **+0.1344** |
| D stop+flat | 20/32 | +0.0400 |

**THE FLATTEN BUYS CONSISTENCY AND SELLS RETURN.** It is the only arm to reach 22 of 32 folds
positive and it compresses the fold distribution hard on US100 (worst fold -0.184 -> -0.017, best
+0.436 -> +0.163) — but its mean is a third of the source's and it turns US30 negative. The stop
gets 21 of 32 folds at the **highest** mean of any arm.

## The control

Reported with a caveat that must stay attached: `apm_core.control` walks the RULE's exits and has
no flatten, so for arms B and D **the control is being given a longer hold than the rule** and its
p-values are a lower bound on the rule. On that reading nothing changes qualitatively — the two
genuine test blocks (US100 p 0.260, US30 p 0.395) fail in every arm, and the blocks that pass are
the ones the rule was developed or validated on.

## Answer

**Out of sample: the flatten makes it worse on 6 of 8 blocks and costs 73% of the per-trade result.**
It halves drawdown, but the 3N stop already halves it for a fifth of the cost while *raising*
Sharpe and return/drawdown.

**Walk-forward: the flatten is the most consistent arm (22/32 folds) and the least profitable
(+0.042 %/trade against the source's +0.127 and the stop's +0.134).** If fold consistency is what
you are buying, it delivers; if return is, it does not.

**Recommendation: leave the flatten OFF and keep the 3N stop ON.** The stop dominates it on every
risk measure at a fifth of the cost. If you want a flatten anyway, `STUDY_APM_VWAP`'s marginal says
use a LATE one — 15:30 costs ~$1.20 a trade against 11:00's ~$22.69.

`research/apm/run_p3.py`, `research/apm/apm_exits.py`.
