# Reverse-engineering the IB strategy for the Asia session

The question was whether the Initial Balance breakout-retracement — validated on the New York
morning at E = 0.325R, t = 3.84 — can be adapted to the Asia session, and what the best version
looks like.

**The answer is that there is no version worth trading, and the reason is structural rather than a
matter of tuning.** This document is the falsification trail.

Reproduce with `npx tsx scripts/quant-asia-study.ts`.

## 0. What had to be built first

The session machinery could not express an Asia session at all. Two bugs would have appeared
silently as bad numbers rather than as errors:

- **`dayIndex` rolls at local midnight**, so an 18:00–03:00 session was two sessions. The initial
  balance would have been rebuilt at midnight and the one-trade-per-session state reset halfway
  through the night.
- **The IB window test compared raw minute-of-day against `start + length`.** For a 120-minute IB
  from 23:00 that sum is 1500, past the end of the day, so every post-midnight bar reads as being
  *before* the open and the window silently collapses.

Fixed with two additions to `clock.ts`: `minutesSinceOpen()` gives a session-relative coordinate that
wraps correctly, and `sessionIndex()` moves the day boundary to the session open so an overnight
session is one session. Six tests cover them, including the exact wrap cases above.

`initialBalance.ts` now uses both. **The RTH numbers are bit-identical after the change** — n = 349 /
E = 0.096 / t = 2.46 / $37,409 and n = 167 / E = 0.325 / t = 3.84 / $29,657, exactly as before —
which is the check that matters, because a refactor that quietly moved the baseline would have
invalidated every comparison below.

## 1. Transplant the RTH winner unchanged

Nothing searched. The validated geometry (IB 60, 50% retracement, 80% stop, fixed 1:2, both sides)
pointed at five different Asia session definitions.

| session | n | win | E | PF | t | research | holdout |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **09:30–11:59 RTH (baseline)** | 167 | 55.7% | **+0.325R** | 1.66 | 3.84 | +0.414 | +0.116 |
| 18:00–03:00 Globex reopen | 432 | 35.0% | −0.096R | 0.88 | −1.10 | −0.093 | −0.106 |
| 19:00–03:00 | 488 | 33.2% | −0.094R | 1.00 | −0.67 | −0.062 | −0.169 |
| 20:00–03:00 Tokyo open | 393 | 40.2% | −0.162R | 0.80 | −1.53 | −0.237 | +0.023 |
| 20:00–02:00 | 383 | 38.9% | −0.115R | 0.82 | −1.46 | −0.169 | +0.021 |
| 18:00–23:59 | 426 | 34.0% | −0.155R | 0.82 | −2.27 | −0.179 | −0.099 |

Every definition loses. The win rate collapses from 55.7% to 33–40%. And those rows use **RTH cost
assumptions** — one tick of spread — which is optimistic for a book running at 5% of RTH volume. At a
realistic overnight assumption (2 tick spread, 2 tick slippage) the Globex session goes to −0.182R
(t = −2.06) and Tokyo to −0.252R (t = −2.34).

## 2. Why: the cost hurdle is four to seven times larger

This is the whole finding. Asia's ranges are a quarter of RTH's; the round turn costs the same
dollars either way.

| session | IB length | median IB range | median risk | cost as R @1 tick | @2 tick |
| --- | --- | --- | --- | --- | --- |
| 09:30 RTH | 60 | 123.3 pts | 37.0 pts | **0.026R** | 0.046R |
| 18:00 Globex | 60 | 31.8 pts | 9.5 pts | **0.100R** | 0.178R |
| 20:00 Tokyo | 60 | 29.5 pts | 8.8 pts | **0.107R** | 0.192R |
| 18:00 Globex | 120 | 41.8 pts | 12.5 pts | 0.076R | 0.136R |
| 20:00 Tokyo | 120 | 39.8 pts | 11.9 pts | 0.080R | 0.143R |

A New York trade starts 0.026R underwater. An Asia trade starts 0.100R underwater on optimistic
assumptions and 0.19R on realistic ones — **four to seven times the hurdle, for a session with less
information flow, not more.** Lengthening the IB to 120 minutes helps (the range grows faster than
nothing) but does not close the gap.

That is a fact about the instrument and the clock, not about the geometry, so no parameter can fix
it. The only lever would be a product whose cost scales down with Asia's range, and NQ is not one.

## 3. Is there any signal at all, before costs?

If a gross edge existed, a cheaper execution might one day capture it. So: 81 geometries
(IB 60/120/180 × retracement 10/25/50 × stop 60/80/100 × R:R 1/1.5/2), run at **zero cost**.

| session | mean gross E over 81 geometries | best gross | largest \|t\| gross | positive after costs |
| --- | --- | --- | --- | --- |
| 18:00 Globex | **+0.029R** | +0.217R (t = 0.88) | 2.19 | 9 / 81 |
| 20:00 Tokyo | **+0.012R** | +0.484R (t = 1.33) | 2.42 | 15 / 81 |

Mean gross expectancy is **approximately zero**, and no geometry with a positive gross edge reaches
t = 1.5 — the best is t = 1.48. The largest \|t\| values in each grid, 2.19 and 2.42, belong to
*negative* cells, and even those are unremarkable: the expected maximum \|t\| across 81 draws from a
zero-mean distribution is around 2.6. Nothing here stands out from noise in either direction.

This also rules out the obvious alternative hypothesis. Asia is a rotational, low-volume session, so
the natural guess is that **fading** the IB break should work where continuation does not. If that
were true the gross edge would be strongly *negative* and we could simply trade the other side. It
is not: the worst cells reach −0.17R and −0.70R at t = −1.9 to −2.4, which is exactly the tail an
81-cell grid produces with no effect present. There is no edge in either direction to invert.

## 4. The best-looking cells, on a split they were not chosen on

Taking the five strongest candidates from stage 3 and splitting them 70/30:

| candidate | full | research | holdout |
| --- | --- | --- | --- |
| Tokyo ib180 retr25 stop60 1:2 | +0.351R (t 0.96) | **+0.690R** | **−0.539R** |
| Tokyo ib180 retr25 stop60 1:1 | +0.243R (t 0.91) | **+0.456R** | **−0.316R** |
| Tokyo ib120 retr25 stop60 1:2 | +0.195R (t 0.79) | **+0.329R** | **−0.120R** |
| Globex ib180 retr25 stop60 1:2 | +0.085R (t 0.45) | **+0.200R** | **−0.254R** |
| Globex ib120 retr25 stop60 1:1.5 | +0.026R (t 0.21) | **+0.114R** | **−0.228R** |

**Five out of five are positive in the research half and negative in the holdout half.** Not one
survives. This is the cleanest overfitting signature produced anywhere in this repository.

### One number worth stopping on

The top candidate shows **E = +0.351R and total P&L of −$707.**

A positive expectancy in R with negative dollars is not a contradiction — it is what happens when R
is normalised by a very small denominator. Entry at 25% and stop at 60% of a 40-point Asia range is a
14-point risk, so a handful of large winners produce impressive R multiples while the many small
losses, each carrying a fixed dollar cost, quietly drain the account. **In a low-range session,
R-multiples flatter and dollars tell the truth.** Any Asia backtest quoted in R without the dollar
figure beside it should be treated as unreported.

## 5. Bottom line

There is no best Asia version. The strategy does not transfer, and the reason is that the IB
breakout-retracement needs a range large enough for a fixed dollar cost to be a rounding error.
New York's first hour provides that; Tokyo's does not.

What would actually be worth testing instead, in order:

1. **A different instrument.** The requirement is a product whose Asia-session range is large
   relative to its round-turn cost — a Nikkei future during Tokyo hours, or FX. NQ trades in Asia,
   but its information arrives in New York.
2. **A different mechanism.** Asia's structure is rotational: it builds the range that the London and
   New York sessions then break. That makes Asia most useful as a *reference level generator* for
   later sessions — the Asia high/low as a level to trade against at the London or New York open —
   rather than as a session to trade inside.
3. **Nothing else on NQ overnight.** The cost arithmetic in section 2 applies to any intraday
   strategy on this instrument in these hours, not only to this one.

## Caveats

- Overnight cost assumptions are modelled, not measured: 1 tick spread is optimistic and 2 ticks is
  a judgement. Real NQ Asia spreads vary a lot by hour, and 03:00 ET is not 23:00 ET. Tick data would
  settle it, and the conclusion does not depend on which of the two assumptions is used — the
  transplant loses at both.
- Three years, one instrument, one regime, as everywhere else in this repo.
