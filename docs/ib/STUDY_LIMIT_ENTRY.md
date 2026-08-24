# `BUYLEVEL = C - ATR(5) * 0.75` — the entry mechanic, and what it actually does

*The two formulas:*

    EMASTRETCH = 100 * (C / EMA(C,10) - 1)      percent stretch from the 10-EMA
    BUYLEVEL   = C - ATR(5) * 0.75              a resting limit 0.75 ATR below the close

*The finding, in one line:* **the limit entry is worth an enormous amount on an unsignalled entry
and destroys a signalled one.** It substitutes for a signal; it does not complement one. And the
mechanism is mean reversion at the execution level — the thing you asked me to avoid, working in
the one place it is not a strategy.

---

## 1. What was missing from the engine

Every entry on this branch until now filled at **the next bar's open**. A resting limit is a
different trade in three ways, and each had to be modelled:

1. **It may not fill.** Price has to come to you. Fill rates here run 27–72%.
2. **The fill is better when it happens.** You buy 0.75 ATR lower. That is the appeal.
3. **It selects the bars that went against you first.** Every filled trade is one where price moved
   adversely after the signal. Comparing that to a market-entry result without saying so is the
   mistake the module exists to avoid.

`research/limit_entry.py` implements it at bar level and, more importantly, on the **true 1-minute
path** — which settles a question the bar-level version cannot: within one chart bar, did price
reach the limit *before* or *after* it reached the stop? The bar version must assume the fill came
first, which is the optimistic branch. The 1-minute walk observes the order and takes the stop when
both are reachable inside the same minute.

## 2. Four ways it could have been an artifact, all tested

| test | result |
| --- | --- |
| bar-level ordering optimistic? | 1-minute path gives **$20.5/trade vs $21.1** — no |
| fill better than the limit on a gap? | forcing the fill to exactly the limit: **identical** |
| fill price too generous? | 1 tick of adverse fill: **identical** |
| **touch-fill trap** — an order at the exact low of a swing is the *least* likely to fill in reality | requiring price to trade **through** by 1, 2 and 4 ticks: $10.8 → $10.4 → $10.1 → $9.4 per trade. Fill rate 42% → 39%. **Survives** |

That fourth one is the standard way a limit-order backtest lies, and it is not what is happening
here.

## 3. Is it the fill, or just where the barriers end up?

A long filled 0.75 ATR lower has its stop *and* its target 0.75 ATR lower in absolute price. So
the same absolute levels were given to a **market** entry — stop 2.73×ATR wide, target 0.47R — with
no better fill:

| tf | window | variant | research $/trade | locked $/trade |
| --- | --- | --- | --- | --- |
| 5m | 09:30–16:00 | market, plain 2.0×ATR 1R | −0.6 | −2.3 |
| 5m | 09:30–16:00 | market, **barriers shifted to match** | −0.9 | −2.2 |
| 5m | 09:30–16:00 | **limit 0.75 ATR(5)** | **+10.1** | **+15.5** |
| 30m | 09:30–16:00 | market, plain | +8.5 | +1.7 |
| 30m | 09:30–16:00 | market, barriers shifted | +6.3 | +1.6 |
| 30m | 09:30–16:00 | **limit** | **+28.7** | **+35.6** |

**It is the fill price.** Barrier placement explains none of it.

## 4. It is symmetric, which rules out drift

If this were "buy dips in a market that rose 91%", it would help longs and hurt shorts. It does
not. Every bar as a signal, no rule at all:

| tf | window | side | market $/tr (res / lok) | limit $/tr (res / lok) |
| --- | --- | --- | --- | --- |
| 5m | 07:00–11:00 | long | −2.2 / −5.1 | **+8.8 / +7.3** |
| 5m | 07:00–11:00 | short | −5.7 / −2.8 | **+4.5 / +10.3** |
| 5m | 09:30–16:00 | long | −0.6 / −2.3 | **+10.8 / +16.6** |
| 5m | 09:30–16:00 | short | −6.3 / −4.4 | **+4.3 / +11.2** |
| 30m | 07:00–11:00 | long | +0.9 / −7.0 | **+14.5 / +12.3** |
| 30m | 07:00–11:00 | short | −11.7 / −2.5 | **+6.1 / +11.8** |
| 30m | 09:30–16:00 | long | +8.5 / +1.7 | **+30.2 / +37.7** |
| 30m | 09:30–16:00 | short | −16.8 / −8.7 | −1.4 / **+19.6** |

Selling into a bounce is worth as much as buying a dip.

**And note what is not here: a rule.** Every bar is a signal. Nothing was selected, so there is no
multiplicity problem to correct for — which makes this the most credible result in the session and
also the reason to be suspicious of everything in §5.

## 5. Now the reversal

The same mechanic applied to the nine validated strategies, same rule, same barrier multiples:

| book | trades | net $ | research $ | locked $ |
| --- | --- | --- | --- | --- |
| market entry | 1,212 | **55,424** | 29,896 | 25,528 |
| limit 0.75 ATR(5) | 656 | **13,415** | 6,768 | 6,647 |

**Every single strategy is worse.** V1 $8,935 → $474. V4 $2,975 → −$1,416. M1 $3,331 → −$105.

The reason is exactly the conditional-sample property from §1.3: a validated rule's edge is in the
**immediacy** of the move. Waiting for a 0.75 ATR adverse excursion throws away 40–60% of the
trades, and the ones thrown away are the ones where the edge materialised straight away.

## 6. What this means

1. **The limit mechanic is an alternative to a signal, not an addition to one.** On a random entry
   the better price is worth more than the missed moves. On a good entry it is worth less. Both
   halves of that are measured above.
2. **What is working is short-horizon mean reversion, at the execution layer.** A limit only fills
   on an adverse excursion, and adverse excursions partially revert. That is the same effect
   `STUDY_FEATURES.md` measured as `close position in bar` (IC −0.02 to −0.03) and dismissed as
   worth 0.28 ticks against a 6-tick round turn. It is worth far more here because you are **not
   paying a round turn to harvest it** — you were entering anyway, and the reversion buys you a
   better price on a trade you were going to make.
3. **You told me to avoid mean reversion.** The honest report is that mean reversion is the only
   thing in this document that works, and it works in the one place where it is not a strategy —
   it is an execution improvement. Whether to use it is your call; I am not going to bury the
   result because of the label on it.
4. **EMASTRETCH added nothing.** `EMASTRETCH < −0.2%` inside 07:00–11:00 gives $8.4/trade on
   research against $14.5 for taking *every* bar. It is a negative filter. Adding the daily uptrend
   on top takes it to −$0.0. Both were tested because they were asked for; neither survived.

## 7. What I would not yet trust

* **Order-to-trade ratio.** This places a limit on essentially every bar and fills 27–72% of them.
  Thousands of resting orders, most cancelled. Exchange messaging fees and queue priority are not
  modelled, and some venues penalise exactly this pattern.
* **Queue position.** `through_ticks` tests whether price traded past the level, not whether *your*
  order was near the front of the queue when it did.
* **No regime control.** The posture is "always trying to fade the last move". The short side
  working is reassuring, but the sample contains one large uptrend and no 2022.

The next step, if you want to pursue it, is not more rule searching — it is a fill model with queue
position, and a live paper test where the fill rate can be compared against the 40% this assumes.

## Files

| | |
| --- | --- |
| `research/limit_entry.py` | bar-level and true-1-minute limit-entry simulators, `emastretch`, the `through_ticks` / `fill_at_limit` / `adverse_ticks` pessimism knobs |

Measured on MNQ, 2022-12-27 → 2025-12-11, one contract, $1.00 commission per round turn, one tick
spread plus one tick slippage each side, one extra tick on stops. The entry cost is charged at the
**full market rate** even for the limit entry, which is conservative. Research tooling for
education and analysis, not financial advice.

---

# Addendum — is it more profitable *with* EMASTRETCH, and what the tests say

Asked directly. Two formulas:

```
EMASTRETCH = 100 * (C / EMA(C, 10) - 1)      // % distance from the 10-EMA
BUYLEVEL   = C - ATR(5) * 0.75               // the resting limit price
```

They were tested separately, because they do different jobs: `BUYLEVEL` is an **execution** change
(where the order rests), `EMASTRETCH` is an **entry filter** (whether an order rests at all).

## A. The threshold sweep — market vs limit, 2 x 2

Long, 2.0xATR stop, 1R target, 6-bar expiry, `BUYLEVEL` = C − ATR(5)*0.75, 2-tick through-fill
required, resolved on the true 1-minute path. Total net dollars, full sample.

| EMASTRETCH gate | 30m, 07:00–11:00 ET, limit | 5m, 09:30–16:00 ET, limit |
| --- | ---: | ---: |
| none (every bar) | 17,759 | 49,927 |
| < −0.5% | 1,433 | −947 |
| < −0.3% | 2,743 | 1,624 |
| < −0.2% | 6,294 | −3,560 |
| < −0.1% | 4,721 | −1,798 |
| < 0 | −2,969 | 7,581 |
| **> 0** | **17,960** | **44,272** |
| **> +0.2%** | **9,058** | **17,888** |

Market-entry baselines, no EMASTRETCH: 30m **−3,599**, 5m **−6,526**.

Two things fall straight out.

1. **`BUYLEVEL` is where all the money is.** −3,599 → 17,759 on 30m and −6,526 → 49,927 on 5m,
   from changing nothing but the fill price. The same flip is in §3–§5 above with the pessimism
   knobs turned up.
2. **`EMASTRETCH` in the direction the formula intends (negative — price stretched *below* the
   10-EMA) makes it worse at every rung, on both configurations.** The only side of zero that
   helps per-trade is the *positive* one: price **above** the 10-EMA. That inverts the formula's
   reading. It is trend-following, not stretch-fading.

## B. The random-filter test, on the locked block, for the survivors

Total dollars reward big samples, so a filter that keeps everything always "wins". The informative
test is `research/dropone.filter_null`: compare a filter's per-trade dollars against **random
subsets of the same size** drawn from the unfiltered limit-entry trades. Read on the locked block
(the last 35% of sessions), which none of this was selected on.

| config | gate | n | $/trade | random control | p |
| --- | --- | ---: | ---: | ---: | ---: |
| 30m 07:00–11:00 | > +0.2% | 117 | 41.8 | 12.2 | **0.056** |
| 30m 07:00–11:00 | > 0 | 309 | 17.0 | 12.3 | 0.263 |
| 30m 07:00–11:00 | < −0.2% | 134 | 36.7 | 12.1 | 0.083 |
| 5m 09:30–16:00 | > +0.2% | 319 | 32.2 | 15.6 | **0.022** |
| 5m 09:30–16:00 | > 0 | 1,069 | 22.0 | 15.5 | **0.006** |
| 5m 09:30–16:00 | < −0.2% | 296 | −4.3 | 15.4 | 0.985 |

Multiplicity: 7 thresholds x 2 configurations = **14 comparisons**, so ~0.7 expected at p<0.05 by
chance. Two land there, both on the positive side.

`< −0.2%` is the honest caution in this table. On 30m it reads p 0.083 and looks like something;
on 5m the *same* gate is the worst cell in the study (p 0.985, negative per-trade). A gate that
reverses sign between two configurations of the same idea is noise, not a mechanism — the rule from
`STUDY_1R_MORE.md`, that an edge existing at one setting only is not an edge.

## C. Verdict

* **With `BUYLEVEL`: yes, and it is not close** — on unsignalled entries. Losing to solidly
  profitable, symmetric across sides, surviving 4-tick through-fill.
* **With `EMASTRETCH` as written (negative): no.** Worse at every rung, both configurations.
* **With `EMASTRETCH` inverted (> +0.2%, price above the 10-EMA): yes, modestly**, and it is the
  only filter here that holds against a size-matched random control on the block it was not
  selected on. Note what that combination is: enter *with* the trend, fill on the pullback. It is
  the trend-plus-pullback structure, with the pullback moved out of the signal and into the fill.
* **On a validated signal, `BUYLEVEL` still hurts** (§6: the shipped book falls 55,424 → 13,415).
  It substitutes for an edge; it does not stack with one.
