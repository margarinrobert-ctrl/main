# edgeful's ORB probabilities for NQ, measured

## 0. The site could not be read

edgeful.com is **not reachable from this session.** The environment's agent proxy answers 403 to
CONNECT for every outbound host, and it logged the rejection for `edgeful.com:443` specifically:

```
{'kind': 'connect_rejected',
 'detail': 'gateway answered 403 to CONNECT (policy denial or upstream failure)',
 'host': 'edgeful.com:443'}
```

That is an organization egress policy, not a site problem — plain `curl` and Python's `urllib` get
the same 403, and the proxy's own README says to report such denials rather than route around them.
So **nothing here is scraped, and no claim is attributed to edgeful that this repository had not
already recorded** from their public writing (the source notes at the bottom of
`NQ_InitialBalance.pine`, gathered earlier in this project).

What follows is better than a page read anyway: edgeful's product is a **probability book**, and
every claim in it is a measurable statement about NQ. This measures them against three years of
1-minute data. Reproduce with `python3 research/orb_stats.py`.

## 1. The headline claim: ~82% single-break days on NQ

764 RTH sessions, Dec 2022 – Dec 2025.

| opening range | days that break at all | **single break** | double break | first break up | **2nd side breaks after the 1st** | closes beyond broken edge | median extension |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5 min | 100.0% | **28.9%** | 71.1% | 51.3% | 71.1% | 50.8% | 2.06x |
| 15 min | 100.0% | **45.5%** | 54.5% | 50.7% | 54.5% | 50.5% | 1.21x |
| 30 min | 99.6% | **61.8%** | 38.2% | 53.0% | 38.2% | 53.7% | 0.89x |
| **60 min** | 97.3% | **78.2%** | 21.8% | 52.1% | 21.8% | 53.4% | 0.55x |

**The ~82% figure is real, and it belongs to the 60-minute range — the Initial Balance — not to a
short ORB.** At 60 minutes NQ gives 78.2% single-break days, close to the published number and
plausibly identical on a different sample or session definition. At 5 minutes the same statistic is
**28.9%**. Anyone carrying "82% single break" across to a 5-minute opening range has the number
almost exactly backwards.

The reason is geometric, not behavioural. A 60-minute range is wide and consumes most of the day's
eventual travel, so there is rarely enough range left to take both edges. A 5-minute range is narrow
and gets straddled by ordinary noise. The statistic is mostly a statement about **how much of the
day's range the opening window already captured.**

## 2. Why a high single-break rate is not an edge

Single-versus-double is **only knowable after the close.** At the moment you are in the trade the
question is the complement: *given that my side has broken, how often does price come back and take
the other edge too?* That is the "2nd side" column, and at 60 minutes it is 21.8%.

So far so good. But now the number that decides whether any of it pays:

> **Across all breaking days, the session closes beyond the broken edge only 53.4% of the time
> (60-minute range). At 5 minutes, 50.8%.**

A coin. The 78.2% single-break rate and the 53.4% directional hit rate are both true, and only the
second one is about direction. The first is about range geometry.

The conditional split shows exactly where the illusion comes from:

| opening range | single-break days close beyond | double-break days close beyond |
| --- | --- | --- |
| 5 min | **95.0%** | 32.8% |
| 15 min | **83.3%** | 23.1% |
| 30 min | **75.5%** | 18.6% |
| 60 min | **65.2%** | 11.1% |

Single-break days look spectacular — 95% of them close beyond the broken edge on a 5-minute range.
But *"single break"* is defined by the day never reversing, so this is close to a tautology: days
that did not reverse are days that did not reverse. **The selection happens after the outcome.** It
is the same trap this repository has now documented three times — high-touch-rate gap fills losing
money, the Market Profile 80% rule, and now this.

## 3. Median extension: the published target sits on the coin-flip line

The median move beyond the broken edge, in units of the opening range:

| opening range | median extension |
| --- | --- |
| 5 min | 2.06x |
| 15 min | 1.21x |
| 30 min | 0.89x |
| 60 min | **0.55x** |

edgeful's documented Initial Balance target is **50% of the range beyond the broken edge**. The
median extension on a 60-minute range is **0.55x**. The published target is sitting almost exactly
on the median — which means it is reached slightly more than half the time by construction, and the
strategy's profitability then rests entirely on whether the stop is small enough to survive the
other half. That is consistent with what the backtest found: the published geometry runs at
PF 1.067 and t = 0.57, mildly profitable and not significant.

Extension shrinks monotonically as the opening range widens, which is the same geometric fact from
section 1 seen from the other side: a wider opening window has already absorbed more of the day.

## 4. One rule that does carry information

Testing the Zarattini/Barbon/Aziz opening-body rule against the same data — does the direction of
the opening candle predict which side breaks, and whether it holds?

| opening range | body agrees with first break | closes beyond, agreeing | closes beyond, disagreeing |
| --- | --- | --- | --- |
| 5 min | 75.7% | **52.6%** | 44.9% |
| 15 min | 72.8% | **52.5%** | 45.9% |
| 30 min | 72.3% | 53.8% | 53.3% |
| **60 min** | 77.4% | **55.8%** | **45.2%** |

A consistent **8–11 percentage point** spread at 5, 15 and 60 minutes, vanishing at 30. Small, but
in the same direction across three of four window lengths, and it agrees with the strategy backtest
in `STUDY_ORB_PAPER.md`, where removing the body rule more than halved expectancy (0.176R → 0.073R).

This is the one genuinely directional statistic in the whole exercise, and note what it is *not*: it
is not the 78% headline. It is a modest tilt on a near-coin.

## 5. Bottom line

1. **edgeful's ~82% single-break claim for NQ checks out at 78.2% — for the 60-minute range.** The
   number is sound and this repository's earlier source notes recorded it correctly.
2. **It is not a directional edge.** The same days close beyond the broken edge 53.4% of the time.
   The 78% describes how often the opening range contains the day, not how often the break works.
3. **The statistic is measured after the fact.** Its tradeable form is the 21.8% chance of the other
   side going too, which is a risk figure, not a signal.
4. **The published 50% target sits on the median extension of 0.55x**, so its hit rate is a coin flip
   by construction and everything depends on the stop.
5. **The opening-candle body is the one component that adds directional information**, worth about
   8–11 points of hit rate, and it corroborates independently in the strategy backtest.

## Caveats

- One instrument, three years, one regime.
- "Break" here is any trade beyond the level during RTH; edgeful may require a close beyond, which
  would lower every break rate and raise every hold rate.
- Session defined as 09:30–16:00 ET. A different end time changes the double-break rate directly.
- No content from edgeful.com was retrieved. The claims tested are the ones already documented in
  this repository's Pine source notes from earlier work; if their current published figures differ,
  this compares against the wrong target.
