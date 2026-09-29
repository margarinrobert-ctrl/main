# The submitted MA 13/48/200 rule, and the two additions asked for

A user-supplied Pine v6 strategy: EMA(13) crossing EMA(48) in either direction, entered at the next
bar's open, a fixed **100-point take profit and 100-point stop measured from the fill**, one
position at a time, no reversal on an opposite cross. The MA(200) is plotted and never traded on.

The ask was a **session window for trade selection, a session stop, and a breakeven in points**.
Each was measured before it shipped, because this branch has recorded a hard flatten as destructive
seventeen times and a breakeven as a subtractor once.

Feeds: `US30_LONG_15m` (2016–2025, split at 2023-01-01) and `US30_ISO_15m`, a **different
provider** whose post-2025-07-16 bars no search here has touched.

---

## 1. The arithmetic, before any rule

| feed | median ATR | 100 points is | round turn | driftless break-even at 1:1 |
|---|---|---|---|---|
| US30_LONG | 29.10 pts | **3.44 ATR** | 2.29 pts = 2.29% of the stop | **51.15%** |
| US30_ISO | 40.02 pts | **2.50 ATR** | 2.29 pts | 51.15% |

A point is not a geometry. The same 100 points is 3.44 ATR on one feed and 2.50 on the other, and
on US30 alone a fixed point stop was 4.23 ATR in 2016 against 1.10 in 2025 (`STUDY_DL50`) — so a
points barrier confounds geometry with market *and* with era. The shipped panel prints the live ATR
equivalent of whatever is set.

## 2. The rule as submitted

| block | n | pts/trade | PF | win rate | vs break-even |
|---|---|---|---|---|---|
| US30_LONG research | 1722 | +0.265 | 1.005 | 51.28% | +0.13 |
| US30_LONG holdout | 870 | **−11.026** | 0.802 | 45.63% | −5.52 |
| US30_ISO forward | 457 | +1.430 | 1.029 | 51.86% | +0.71 |

**The win rate is its own break-even.** Symmetric barriers with a 2.29-point cost need 51.15%, and
the rule delivers 51.28 / 45.63 / 51.86. The barriers are being hit by noise — the fifth strategy
family measured that way here, after `STUDY_THE_STRAT`, `STUDY_IB25_RETRACEMENT`,
`STUDY_VWAP_STOCH_ATR` and `STUDY_V69_ORB`.

## 3. The session window

42 declared cells: 7 windows × flatten on/off × 3 blocks. `E[max t | pure noise]` over that ladder
is **2.209** against the 2.802 detectability needs, so the table is readable and its top row is not.

Marginal average by window, points a trade:

| window | pts | PF | mean n |
|---|---|---|---|
| **13:00–16:00** | **+0.83** | **1.014** | 193 |
| 09:30–16:00 | −2.58 | 0.948 | 530 |
| 09:30–11:00 | −3.01 | 0.936 | 230 |
| all hours | −3.11 | 0.945 | 1016 |
| 09:30–12:00 | −5.18 | 0.885 | 315 |
| 07:00–11:00 | −6.11 | 0.876 | 404 |
| 08:00–12:00 | −9.04 | 0.815 | 421 |

13:00–16:00 is the only positive window, and it is the only one of the seven that is not a morning
window — the eighth time a session preference on this branch has failed to agree with the previous
one. **The session stop helps in 9 of 18 paired cells — exactly chance — at a mean of −0.67 points
a trade.**

## 4. The breakeven

21 effective cells. Rungs at or beyond the 100-point target are **inert** — the target resolves
first on the same bar — so 100 and 150 are excluded rather than counted as tests never run.
`E[max t | noise]` = 1.922.

| arms at | Δ pts vs OFF | Δ win rate | **Δ trade count** | cells won |
|---|---|---|---|---|
| 25 pt | **+4.35** | +0.020 | **+251** | 5/6 |
| 50 pt | +1.43 | +0.007 | +118 | 4/6 |
| 75 pt | −0.22 | −0.001 | +46 | 4/6 |

It beats its own OFF twin in 13 of 18 paired cells and the ladder is monotone. **Read the trade
count first.** It rises by 251 trades at the 25-point rung, because a breakeven closes positions
sooner, frees the one-position lock and admits later crosses the base never saw. That is a
*different strategy with more trades*, not a filter on the same ones — `STUDY_V56`'s mechanism,
where an ATR target did the same thing.

### Secured points: the largest win-rate illusion measured on this branch

| secure | Δ pts vs OFF | Δ win rate |
|---|---|---|
| 0 | +1.65 | **−0.156** |
| 5 | +2.06 | **+0.173** |

At breakeven 25 on the research block the *same trades* read a **26.07% win rate securing 0 and
79.35% securing 5 — fifty-three points** — while the money moves +3.099 → +3.472 points a trade.
A stop at the fill books minus the round turn and is a loss; five points beyond it books +2.71 and
is a win. The threshold is the round turn, not zero, and the panel computes it live from the run's
own closed trades (`(gross − net) / trades / point value + 2 × tick`, because slippage is charged
in ticks on both sides and never appears in the commission figure).

The nineam study measured this at 31 points on a different rule; here it is 53, because a 1:1
geometry puts far more mass on the moved stop.

## 5. The nulls

Nine declared cells against a **random entry** with the identical window, side mix, barriers,
breakeven and cost — only the entry bar moves. `E[max t | noise]` = 1.521.

| arm | block | n | pts | PF | control | p | bootstrap |
|---|---|---|---|---|---|---|---|
| as submitted | research | 1722 | +0.265 | 1.005 | −0.009% | 0.068 | 0.416 |
| as submitted | holdout | 870 | −11.026 | 0.802 | −0.009% | 0.996 | 1.000 |
| as submitted | forward | 457 | +1.430 | 1.029 | −0.006% | 0.108 | 0.337 |
| + 13:00–16:00 | research | 353 | +5.925 | 1.126 | −0.008% | **0.024** | 0.150 |
| + 13:00–16:00 | holdout | 167 | +0.704 | 1.014 | −0.012% | 0.308 | 0.470 |
| + 13:00–16:00 | forward | 49 | +3.832 | 1.080 | −0.006% | 0.288 | 0.408 |
| + breakeven 25/5 | research | 2184 | +3.472 | 1.164 | −0.002% | **0.004** | **0.008** |
| + breakeven 25/5 | holdout | 1097 | −0.357 | 0.983 | −0.002% | 0.500 | 0.640 |
| + breakeven 25/5 | forward | 528 | +1.772 | 1.079 | +0.000% | 0.268 | 0.267 |

**2 of 9 clear p ≤ 0.05 where 0.5 are expected — and both are US30_LONG research cells**, which
then read p 0.308 / 0.500 on the holdout and 0.288 / 0.268 on the different-provider forward feed.
**1 of 9 exceeds its own minimum detectable effect.** Clears where it was chosen, fails everywhere
it was not: the shape this file has now recorded fifteen times.

## 6. What ships

All three additions, **default OFF**, so the script with the new inputs untouched is the submitted
strategy unchanged:

- `Only take entries inside a window` — start and end declared in **minutes past New York
  midnight**, pre-filled at 780/960 (13:00–16:00, the one positive window)
- `Session stop: flatten at the window end` — filled at the cutoff minute's **open**, so the order
  is submitted on the bar before
- `Auto breakeven` — arms at 25 points, secures 5, the ratchet re-issued as an absolute stop once
  the position exists and binding only from the bar after it arms

Each tooltip carries its own measured numbers. Parity with the shipped order model: **14 of 14
configurations at trade count 1.000**, same exit bar 0.996–1.000, correlation 0.997–1.000, gap
+0.000 to +0.284 points a trade.

---

### Files
`research/ma13/m13core.py` (the rule, the barrier walker with session / flatten / breakeven, and a
sorted matched control) · `run_s1.py` (the arithmetic first, then both declared ladders read by
marginal average with the trade count beside the win rate) · `run_s2.py` (nine cells against a
matched random entry, with each cell's own MDE) · `m13_parity.py` ·
`pine/ma13/US30_MA_13_48_200_SESSION_BE_strategy.pine`
