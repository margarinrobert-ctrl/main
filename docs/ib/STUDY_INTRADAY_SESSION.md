# Intraday only: 06:00 New York open, hard flat at 12:00

`research/vbt/intraday.py`, `run_intraday.py`. **No position can survive the window end** — there
is no code path that carries one past `win_end`.

## Why this study exists

The brief has been intraday from the start: open at 06:00 EST, flat by 12:00. The work drifted onto
1-hour charts holding for days, because that is where results survived. **That is the wrong reason
to change a requirement.** This is the constraint as specified, measured properly.

## The result

2,160 configurations per chart (entry channel including *none*, channel and ATR stops, targets
1–5R, 4H EMA 20/50/100, avoid-resistance tolerance, three side settings), selected in-sample and
read once out of sample.

**5-minute chart** (US30, NQ, XAUUSD — the feeds fine enough to support it):

| ent | stop | tp | ema | side | IS n | IS E[R] | IS PF | OOS n | OOS E[R] | OOS PF |
| ---: | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | ch20 | 5.0 | 50 | short | 2,144 | +0.033 | 1.06 | 1,118 | +0.009 | 1.02 |
| 30 | ch20 | 5.0 | 100 | short | 1,951 | +0.021 | 1.04 | 1,044 | +0.025 | 1.05 |

Population: IS mean −0.4004, OOS mean −0.3034, **1.0% of configurations positive out of sample.**

**15-minute chart** (adds US100 and BTC):

| ent | stop | tp | ema | side | IS n | IS E[R] | IS PF | OOS n | OOS E[R] | OOS PF |
| ---: | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 | ch20 | 5.0 | 20 | **long** | 2,763 | +0.078 | 1.22 | 1,651 | **+0.034** | 1.08 |
| 30 | ch20 | 5.0 | 50 | long | 2,630 | +0.062 | 1.17 | 1,577 | **+0.043** | 1.11 |

Population: IS mean −0.3294, OOS mean −0.6175, **5.5% positive out of sample.**

## What the constraint costs

The same family without the session constraint — 1-hour chart, positions held for days — scores
**+0.279 R out of sample at PF 1.35**. Held to 06:00–12:00 with a hard flatten it scores **+0.034 R
at PF 1.08**.

**The intraday constraint removes roughly 88% of the result.** That is the seventh independent time
it has done so on this branch, and it is not a cost artifact: it is that the exits fire on the clock
rather than on the trade, so the wide-target geometry that carries this family never gets to pay.
A 5R target with a hard 12:00 flat is a 5R target that mostly does not arrive.

## The one actionable finding: the 06:00 start is the worst part of the window

Same configuration, only the window moved. Everything still flat by the window's end.

| window (New York) | IS n | IS E[R] | IS PF | OOS n | OOS E[R] | OOS PF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **06:00–12:00** (as asked) | 2,763 | +0.078 | 1.22 | 1,651 | +0.034 | 1.08 |
| 07:00–12:00 | 2,564 | +0.078 | 1.23 | 1,547 | +0.032 | 1.08 |
| 08:00–12:00 | 2,290 | +0.066 | 1.20 | 1,408 | +0.031 | 1.08 |
| **09:30–12:00** | 1,651 | **+0.103** | **1.44** | 1,027 | **+0.046** | **1.17** |
| 09:30–11:30 | 1,532 | +0.087 | 1.38 | 966 | +0.039 | 1.15 |
| 09:30–11:00 | 1,371 | +0.091 | 1.44 | 868 | +0.033 | 1.13 |

**Starting at 09:30 instead of 06:00 raises out-of-sample expectancy 35% on 38% fewer trades**, and
in-sample profit factor from 1.22 to 1.44. The 06:00–09:30 block is not merely thin, it is
*subtractive*: dropping it improves the result on both blocks at once.

This replicates a finding already on the branch from a different family — `STUDY_TREND_PULLBACK.md`
measured 07:00–09:00 as the worst part of the day on all three indices (−0.18 to −0.43 R/trade) and
found 09:30–11:00 worth 4× the per-trade result of 07:00–11:00 on 44% fewer trades. Two independent
studies now say the pre-open hours cost money.

Note the cost model does not widen the pre-RTH spread, so the real 06:00–09:30 penalty is **larger
than measured here**, not smaller.

## Verdict

Intraday with a hard 12:00 flat is viable but thin: the best out-of-sample cell is **+0.046 R at
PF 1.17** on the 09:30–12:00 window, against +0.279 R for the same family allowed to hold. If the
intraday constraint is non-negotiable — and it is the stated brief — then **09:30 is the right open,
not 06:00**, and the expectation should be set at a profit factor near 1.2 rather than 1.4.
