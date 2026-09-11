# V51 — One entry, one exit, four requested filters, 1,161,216 configurations

**One of the four earns its place, and it is INVERTED: the MA 200 works as an EXTENSION FLOOR
(price at least 1.5 ATR ABOVE it), not as support. It clears a same-selectivity control on all
three blocks at p 0.001 and survives 2× cost. The 13×48 cross, all six absorption readings and
every session and flatten setting fail on the market that had no part in the search.**

The full system clears a random-**entry** control on research (p 0.003) and on held-back US30
(p 0.001) and **fails on US100's own locked block (p 0.241)**. Two of three.

---

## What was built

A fresh single-entry / single-exit strategy, per request: a Donchian breakout in; an ATR stop or a
Donchian channel out, whichever is nearer the market; no System 2, no pyramid ladder, no take
profit. Then the four requested filters as swept selectors — MA 200 as a level, an EMA 13×48 cross,
absorption, and a session window with an optional flatten.

Fixed by declaration rather than swept: the MA type (EMA) and the 13/48 lengths, because
`STUDY_MA_LAG` measured MA type and MA length as non-degrees-of-freedom here (13/48 vs 12/48 vs
15/48 all land within 0.03 PF); no take profit, which has beaten every target ten times; and a
480-bar max hold.

**Grid:** 4 entry × 4 exit × 4 stop × 6 MA200 × 4 cross × 14 absorption × 9 session × 3 timeframes
× 2 markets = **1,161,216 configurations**.

**Split:** searched on US100L's first 70% only. US100L's last 30% and the whole of US30L held back.
US30 is the best available second test and **not an independent one** — its 15-minute returns
correlate 0.758 with US100's over an overlapping calendar.

## On vectorbt, since it was asked for

It was not used, and the reason is the same one that made the V46 cross-check inconclusive:
**vectorbt 1.1.0's `sl_stop` is a fraction of price, not a per-trade ATR multiple**, and `td_stop` /
`dt_stop` do not exist in it. The geometry here is an ATR-multiple stop maxed against a rolling
channel and capped at the prior close; vectorbt cannot express it, so a run would have measured a
different strategy.

What was used instead is the cached exit tensor: a trade's outcome depends only on its **signal bar**
and its **geometry**, never on which filter let it through, so the price is walked once per (bar,
geometry) and every configuration becomes an array lookup plus a position-lock pass.
**1,161,216 configurations in 17.7 seconds.** It was verified before it was trusted — diffed against
an independent plain-Python simulation on 15 cells across two markets and two timeframes, with trade
counts identical and mean R equal to 1e-9 on every one.

## Gate 3 — the population, before any row is named

```
248,172 of 1,161,216 cells carry >= 100 research trades (42.7%)
  positive mean R : 187,372 of 248,172 = 75.5%
  PF > 1.2        :  77,968           = 31.4%
  PF > 1.5        :  13,089           =  5.3%
  median mean R +0.0500   median PF 1.117   median n 298
```

Any single cell is the maximum of **~187,000 positive draws**. The top-1000 median is n 129 / PF
1.973 / R +0.5444 — a selection-bias signature, not a finding.

**Four of four geometry axes run to the edge of the declared grid.** The marginal average rises
monotonically to 60m (the slowest tested), to a 30-bar exit channel (the longest), to a 55-bar entry
channel (the longest), and *down* to a 1.5 ATR stop (the tightest). The optimum was never bracketed,
and the grid was not extended afterwards.

## The feature test — each filter against a random filter of the same selectivity

2,000 draws, same base signals, same geometry, same exits, same costs. p is the share of random
filters that did as well or better, so low is good. Base: 60m, Donchian 20 in / 30 out, 1.5N stop.

| feature | keep | research | US100 locked | US30 held back |
| --- | --- | --- | --- | --- |
| **MA200 ≥ 1.5 ATR ABOVE** | 77% | **+0.4720 p 0.001** | **+0.3475 p 0.001** | **+0.3534 p 0.001** |
| MA200 ≥ 3.0 ATR above | 68% | +0.3293 p 0.198 | +0.5018 p 0.000 | +0.3923 p 0.000 |
| MA200 above | 86% | +0.4170 p 0.000 | +0.2834 p 0.029 | +0.3003 p 0.147 |
| MA200 above & within 3.0 ATR | 18% | +0.5044 p 0.001 | +0.3142 p 0.241 | +0.1333 **p 0.999** |
| MA200 above & within 1.5 ATR | 8% | +0.4699 p 0.017 | +0.2781 p 0.390 | +0.2186 p 0.800 |
| EMA13 > EMA48 (state) | 84% | +0.4091 p 0.000 | +0.3626 p 0.000 | +0.2878 p 0.400 |
| EMA13×48 cross ≤ 20 bars | 32% | +0.4208 p 0.009 | +0.3986 p 0.023 | +0.1853 **p 0.995** |
| EMA13×48 cross ≤ 5 bars | 13% | +0.4185 p 0.037 | +0.2971 p 0.324 | +0.0777 **p 1.000** |
| require BUYER absorption ≤ 5 | 6% | +0.2061 p 0.518 | +0.3442 p 0.272 | +0.0946 p 0.883 |
| avoid SELLER absorption ≤ 20 | 86% | +0.3211 p 0.208 | +0.2866 p 0.021 | +0.3159 p 0.007 |
| require SELLER absorption ≤ 20 | 15% | +0.2403 p 0.548 | **−0.0995 p 0.996** | +0.0983 p 0.991 |
| session 08:00-12:00 | 32% | +0.2548 p 0.717 | +0.2282 p 0.501 | +0.3241 p 0.347 |
| session 09:30-16:00 | 42% | +0.3045 p 0.433 | +0.2524 p 0.334 | +0.3135 p 0.394 |
| *base, no filter* | 100% | *+0.3063* | *+0.2394* | *+0.2785* |

### The MA 200 is a floor, not support — the third inversion on this branch

Requiring price to be **at least 1.5 ATR above** the average clears on all three blocks at p 0.001
and decays from research to holdout, which is the right shape. Requiring price to be **near** the
average — the support reading that was asked for — clears research at p 0.001 and then reads
p 0.241 and **p 0.999**, where a random filter of the same selectivity earns more than double
(+0.3066 against +0.1333). `STUDY_TURTLE_15M` took PF 0.94 → 1.58 by making exactly this inversion
on EMA100; this replicates it on the MA 200 and on a third market.

The ≥ 3.0 ATR rung scores *better* on both holdouts than on research (p 0.198 → 0.000 → 0.000).
That is the wrong shape and it is recorded as a defect, not as a stronger result.

### The cross does not transfer

`EMA13 > EMA48` clears both US100 blocks at p 0.000 and reads **p 0.400** on the market that had no
part in the search; the recency variants read p 0.995 and p 1.000, with the random filter earning
+0.3059 against the cross's +0.1853. Two blocks of one index over an overlapping calendar are not
two tests — `STUDY_TREND_LONG`'s rule, and here it decides the answer.

### Absorption: nothing clears, and the sign is the usable part

The definition came from the user's own chart: a large-volume **up** bar whose close sits in the
lower 40% of its own range — sellers absorbing the buying. Its mirror is buyers absorbing selling.
**It is a proxy and it is labelled one**: real absorption needs bid/ask volume at price and no feed
on this branch carries it.

*Requiring* seller absorption fails all three blocks and **loses money on locked** (−0.0995 R, PF
0.866). In the sweep it appears in **0.00% of the top 1000 in five of its six variants** against a
2.2–4.3% population share, and it gets monotonically worse as the volume threshold rises (1.5×:
+0.031, +0.022; 2.0×: −0.015, +0.001). That is `STUDY_DIVERGENCE_CONFIRM`'s volume-spike result
reproducing from a different direction — −2.45 points at 1.5× the baseline and −17.88 at 2.0× there.
A spike marks maximum participation, which is where a short-horizon move is most likely already over.

*Avoiding* it clears locked (p 0.021) and US30 (p 0.007) and fails research (p 0.208) — the wrong
shape — so it ships OFF. The sign is right; the effect is not established.

### The flatten is destructive, on every window measured

| window | no flatten | with flatten |
| --- | --- | --- |
| 07:00-11:00 | +0.0778 | **−0.0347** |
| 08:00-12:00 | +0.1111 | +0.0049 |
| 09:30-12:00 | +0.1062 | −0.0011 |
| 09:30-16:00 | +0.1251 | +0.0434 |

At the shipped geometry it takes 08:00-12:00 from +0.2548 to **−0.0239** (PF 0.950) on research and
from +0.3241 to −0.0099 (PF 0.977) on US30. It truncates exactly the trades a channel exit exists to
hold — the eighth confirmation of the intraday-constraint finding on this branch. Provided because
it was asked for, defaulted off, and it fills at the **next bar's open** because
`strategy.close_all()` cannot sell the close of the bar that triggers it.

No session window clears its control on any block (p 0.33–0.72).

## The shipped default against a random ENTRY

The harder null: a random entry with the identical stop, exits, max hold and costs, matched on trade
count against eligible bars and on minute-of-day. The R denominator is an ATR stop, not a channel
stop, so it cannot collapse the way `STUDY_TURTLE_YOUTUBE`'s first control did.

| block | n | R | PF | Sharpe | random entry | p |
| --- | --- | --- | --- | --- | --- | --- |
| US100 research | 434 | +0.4720 | 1.724 | 1.08 | +0.2642 | **0.003** |
| US100 LOCKED | 206 | +0.3475 | 1.496 | 0.55 | +0.2751 | **0.241** |
| US30 held back | 616 | +0.3534 | 1.513 | 0.92 | +0.1879 | **0.001** |

Sharpe is over **every trading day in the block**, zero-filled on days that did not trade. Cost
stress: p 0.003 / 0.232 / 0.003 at 1.5× and 0.004 / 0.232 / 0.003 at 2×. **This is the first
candidate on this branch to survive 2× the assumed spread** — every previous one died at 1.5×.

The base with no filter fails the same null on US100 (p 0.140 research, 0.596 locked) and clears on
US30 (p 0.001), so the breakout trigger is close to a coin flip and the MA200 floor is what moves it.

## Caveats that stay attached

Two markets, one of them not independent of the other. US100 locked does not clear the random-entry
control, so the result rests on the search block and on US30. Absorption is a proxy, not a
measurement. Spread is assumed in both feeds. Four of four geometry axes sit at the edge of the
grid, so the geometry is not a bracketed optimum. And the population is 75.5% profitable, which
means a positive cell is the default outcome here and only the control readings carry information.

## Files

`research/v51/v51feat.py` (feeds, the four filter families, the absorption proxy) ·
`v51tensor.py` (the cached exit tensor and the scoring kernel) · `v51_verify.py` (the tensor diffed
against an independent reference) · `run_v51.py` (the 1.16M sweep) · `analyse_v51.py` (population and
marginal averages) · `run_v51b.py` (random-entry control, daily Sharpe, cost stress) ·
`run_v51c.py` (the same-selectivity feature test) · `results/v51/` ·
`pine/v51/V51_DONCHIAN_MA_ABSORPTION_strategy.pine`.
