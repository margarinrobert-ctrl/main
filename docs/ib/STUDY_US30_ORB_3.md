# US30 09:00 range, third pass: exits, daily direction, overnight position — still nothing

*Follow-up to [`STUDY_US30_ORB.md`](STUDY_US30_ORB.md) and [`STUDY_US30_ORB_2.md`](STUDY_US30_ORB_2.md).
The instruction was to keep working until maximum performance. Passes one and two exhausted the
rule's parameters, the entry mechanics and the intraday filters. This pass holds the time window
and the entry at the line, and asks the three questions that had not been asked on this file:
does exit management change anything, does the DAILY trend dictate a better direction than the
15-minute EMA 200, and does it matter where the 09:00 range sits inside the overnight range.*

*Result:* **720 cells, 0 beat the matched control at z > 2 where 11 would by chance. No exit
variant — trailing, time exit, partial, gap-fill target, 100/200 — beats the plain 100/100 on
the user's rule. Direction from the daily trend is the least-bad axis and is still negative. The
best plateau cell is a coin flip on research (−1.0 pt/trade, z 0.44) and loses 19.4 pt/trade on
the holdout. Three passes, 29,337 cells, one file. There is no configuration of this structure
on this data that is profitable out of sample, and the search should stop here.**

> Reproducible: `python3 research/us30_orb3.py`. Same data, split and cost model as before.
> Research output, not financial advice.

---

## 1. What was asked this time

| axis | values | the question |
| --- | --- | --- |
| exits | fixed 100/100; 75/75; 100/200; 100/100 flat 11:00; chandelier trail at 1.5× and 2.5× ATR(14) from the best excursion, initial stop 100; time exit (stop 100, no target) flat 11:00 and 12:00; half off at +100 and the rest trailed 2× ATR; a gap-fill target at the prior session's 16:00 close | is the loss in the exit rather than the entry |
| direction | none (the EMA state decides); 15-minute EMA 200 (passes one and two); daily 5-session momentum; daily 20-session EMA of closes | can a slower trend dictate the side (`daily_trend.py` protocol) |
| position | any; the 09:00 range high/low must also be the overnight (18:00 → 08:45) extreme, so the break is a new session high/low; or the range must sit inside the overnight range | is a break of the whole night's range different from a break of two pre-open bars |
| momentum | EMA 13/48 state; none | |
| entry | stop at the line (the Pine default); limit at the line on the retest; close | |

3 × 2 × 4 × 3 × 10 = 720 cells, 465 with at least 60 research trades. Same gates as pass two.
The trailing exit is a chandelier: after each bar the stop is the larger of the initial stop and
the best excursion so far minus k × ATR, and the next bar exits at that level if it trades there.
Verified by hand on a trade.

Facts about the file that bear on the direction gates: 71% of sessions are in a daily uptrend by
the 20-session EMA and 55% by 5-session momentum; the 09:00 range high is also the overnight high
on 20% of sessions and the low is the overnight low on 14%.

## 2. The user's rule at the line under every exit, research

Stop at the 09:00 line, EMA 13/48 state, EMA 200 gate, 263 research trades in every row:

| exit | win | per trade | control z |
| --- | --- | --- | --- |
| **fixed 100/100, flat 16:00** | 49.0% | **−5.5** | 0.09 |
| fixed 75/75 | 41.4% | −16.5 | −2.04 |
| trail 1.5× ATR, stop 100 | 42.2% | −5.8 | −0.47 |
| trail 2.5× ATR, stop 100 | 33.5% | −8.3 | −0.67 |
| time exit at 11:00, stop 100 | 35.7% | −6.2 | −0.69 |
| time exit at 12:00, stop 100 | 30.4% | −8.6 | −1.03 |
| half at +100, rest trailed 2× ATR | 45.6% | −5.9 | −0.27 |
| fixed 100/100, flat 11:00 | 47.5% | −6.6 | −0.18 |
| fixed 100/200 | 31.6% | −14.1 | −1.87 |
| gap-fill target | 13 trades | too few | |

The exit is not where the loss is. Every alternative is worse than or equal to the plain
100-point stop and target, and the time exits — the pure direction bet — are the clearest
statement that the break does not pick a direction: 30–36% of them are still open at the flat
time with a negative mean.

## 3. The sweep

| statistic | value |
| --- | --- |
| median z over 465 cells | −0.54 |
| 90th percentile z | 0.30 |
| cells with z > 2 | **0**, against 11 expected from noise |

Median z by axis value:

| axis | values → median z |
| --- | --- |
| entry | close −0.50 · limit −0.53 · stop −0.59 |
| momentum | 13/48 −0.46 · none −0.58 |
| direction | **daily EMA −0.13 · daily momentum −0.23** · EMA 200 −0.79 · none −0.85 |
| position | any −0.54 · inside overnight −0.46 · new extreme **−0.84** |
| exits | 100/100 flat 16:00 **−0.02** · 100/100 flat 11:00 −0.29 · trail 2.5× −0.38 · partial −0.43 · 75/75 −0.44 · time 12:00 −0.59 · time 11:00 −0.68 · 100/200 −0.72 · trail 1.5× −0.97 · gap-fill −1.34 |

Two readings. The daily trend is a better direction gate than the 15-minute EMA 200 by about
0.7 z, which is the `daily_trend.py` lesson repeating on a new instrument, and it still does not
get the family to zero. And a break that is also a new overnight extreme is *worse* than one
inside the overnight range, which is the opposite of the breakout story and consistent with the
gap-fill regularity pass two found: on this file the open's first move is more often reversed
than continued.

Top of the table, none of it significant:

| entry | mom | direction | position | exit | n | win | per trade | L / S | z |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| limit | 13/48 | daily EMA | any | 75/75 | 65 | 60.0% | 11.3 | 42 / 23 | 1.77 |
| limit | 13/48 | daily momentum | any | 75/75 | 67 | 56.7% | 7.5 | 33 / 34 | 1.40 |
| limit | 13/48 | none | inside overnight | 75/75 | 104 | 54.8% | 3.8 | 45 / 59 | 1.32 |
| limit | 13/48 | none | any | 75/75 | 147 | 54.4% | 3.2 | 69 / 78 | 1.31 |
| limit | 13/48 | EMA 200 | any | 75/75 | 123 | 55.3% | 3.9 | 59 / 64 | 1.30 |

The limit retest with a 75-point barrier is again the top of the list, on 65–147 trades, at z
1.3–1.8. It is the same execution effect pass two identified and it does not reach the gate.

## 4. The one cell read on the locked block

Nothing passed, so per the pre-registered fallback the best plateau cell was read once: close
entry, EMA 13/48, direction from the daily 20-session EMA, 100/100, flat 16:00 — research z 0.44,
stability 1.50.

| block | n | win | per trade | PF | L / S | control z | bare mechanic, same exit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| research | 127 | 52.0% | −1.0 | 0.98 | 86 / 41 | 0.42 | −6.1 |
| locked | 77 | 41.6% | **−19.4** | 0.68 | 63 / 14 | −1.53 | −11.7 |

On research it is a coin: bootstrap P(net ≤ 0) is 0.55. On locked it loses 19.4 a trade, 1.5
standard deviations worse than random, in 1 of 4 quarters profitable. The daily gate made it
82% long on the holdout, and the longs lost 16.5 a trade in a period when the index rose.

## 5. Where this leaves the question

| pass | what was searched | cells | z > 2 | expected by chance | survived |
| --- | --- | --- | --- | --- | --- |
| one | the rule's own parameters | 16,200 | 0 | 373 | 0 |
| two | entry mechanics, filters, exits, gap, volume, width | 12,672 | 13 | 41 | 0 |
| three | exit management, daily direction, overnight position | 720 | 0 | 11 | 0 |
| **total** | | **29,337** | 13 | 425 | **0** |

Thirteen cells at z > 2 across 29,337 is far fewer than noise alone produces. The structure —
mark the 09:00–09:30 range, trade its break between 09:30 and 10:30 with an EMA cross and a
100-point barrier, on 15-minute US30 bars — has no configuration that is profitable out of
sample on this file, and no axis where the surface even reaches zero. The honest answer to "keep
working until maximum performance" is that maximum performance on this data is a coin flip minus
costs, and the tooling has measured that from every side it can be measured from.

What would change the question is unchanged and is not a rule search:

1. **One-minute bars of the same period.** The 09:30 15-minute bar alone spans more than the
   barrier; the idea is a one-minute idea and has never been tested at its own resolution.
2. **More history or a second instrument.** Both blocks are one regime.
3. **The instrument's real cost.** Irrelevant to this verdict, decisive for anything that passes.

## Files

| file | what |
| --- | --- |
| `research/us30_orb3.py` | pass three: daily-trend and overnight-range facts, direction and position gates, chandelier trail / time / partial / gap-fill exits, matched control with the same exit, bare-mechanic gate, one locked read |
| `pine/us30/US30_OpenRangeEmaCross.pine` | defaults unchanged: nothing earned a change. Header records this pass |
