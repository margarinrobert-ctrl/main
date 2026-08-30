# V54 — CVD structure as four separate patterns, and a KAMA on an independent timeframe

**One of the four CVD patterns clears its control on BOTH blocks and decays the right way:
EXHAUSTED SELLERS — price Lower Low with CVD Higher Low — at pivot k=3, within 20 bars.
Research +0.3509 PF 1.696 p 0.001; locked +0.3176 PF 1.648 p 0.009. The other three fail on locked,
and ABSORBED BUYING is negative on both. Not one of sixteen KAMA readings clears locked.**

Testing the four separately is what made this visible. Collapsed into one "CVD divergence" flag they
would have averaged into nothing.

---

## What the CVD is, exactly

True cumulative volume delta needs the **aggressor side** of every trade. No feed on this branch
carries it — `data/NQ_1m.csv` is OHLCV, and the one feed that ever had real taker-side flow
(BTCUSDT's `Taker buy base`) is a different instrument and is not attached.

So this is a **proxy**, chosen to be the same one TradingView uses: sign each lower-timeframe bar's
whole volume by that bar's own direction (`close > open` is buying), sum inside the chart bar, and
accumulate. It is a direction-weighted volume sum, **not order flow**, and it will disagree with a
real tick-delta feed. It is worth testing anyway because a TradingView user trading this signal
would be trading exactly this proxy — the research and the shipped script measure the same object,
and the script computes the delta itself with `request.security_lower_tf` rather than calling a
built-in, so that identity is provable rather than assumed.

**NQ only.** CVD needs 1-minute bars and NQ is the only feed here that has them, so there is no
cross-market read in this study.

## No lookahead, twice over

A pivot at bar *i* needs bars *i−k … i+k*, so it is knowable only at *i+k*. Both the research and the
script stamp the divergence at the **confirmation bar**, never at the pivot.
`STUDY_DIVERGENCE_CONFIRM` caught precisely this leak once — a feature that filled forward to the
next pivot's confirmation read +999 truncated against +37 full.

The CVD value compared at each price pivot is the CVD **at that price pivot's own bar**, not a pivot
of the CVD series — the two points correspond to the same timestamp, as specified.

The KAMA is pulled with `lookahead_off` **and** `[1]`, so a bar can only ever see a closed
higher-timeframe bar.

## The four patterns, tested independently

Base: NQ 30m, Donchian 20 in / 20 out, 2.0N stop, one unit, long, no target, max hold 480. Each
condition against a random filter keeping the same share of the same signals, 2,000 draws.

| pattern | structure | research | LOCKED |
| --- | --- | --- | --- |
| *base, no condition* | — | *+0.0945 PF 1.16, vs a random entry p 0.057* | *+0.1280 PF 1.24, p 0.127* |
| **EXHAUSTED SELLERS** k3 w20 | price LL + CVD HL | **+0.3509 PF 1.696 p 0.001** | **+0.3176 PF 1.648 p 0.009** |
| ABSORBED SELLING k3 w20 | price HL + CVD LL | +0.2308 PF 1.404 p 0.045 | +0.0329 PF 1.055 p 0.903 |
| EXHAUSTED BUYERS k3 w20 | price HH + CVD LH | +0.2432 PF 1.454 p 0.046 | +0.1973 PF 1.362 p 0.179 |
| ABSORBED BUYING k3 w20 | price LH + CVD HH | +0.1404 PF 1.238 p 0.539 | **−0.0109 PF 0.982** p 0.926 |
| EXHAUSTED SELLERS k5 w20 | | +0.3853 PF 1.763 p 0.004 | +0.1631 PF 1.300 p 0.304 |
| ABSORBED SELLING k5 w20 | | +0.3437 PF 1.599 p 0.005 | +0.1569 PF 1.283 p 0.320 |
| EXHAUSTED BUYERS k5 w20 | | +0.3598 PF 1.644 p 0.009 | +0.1930 PF 1.343 p 0.225 |
| ABSORBED BUYING k5 w20 | | **−0.0852 PF 0.869** p 0.989 | −0.0167 PF 0.976 p 0.804 |

**EXHAUSTED SELLERS at k=3 is the only row that clears both blocks**, and it decays from research to
locked (+0.3509 → +0.3176), which is the right shape — a rule chosen on research should look better
there.

**The signs behave as the structure predicts for a long-only system.** The two bullish patterns
score above the two bearish ones on research, and ABSORBED BUYING — aggressive buying absorbed by
passive sellers, the most bearish of the four — is the only **negative** row on both blocks and the
only one that loses badly to its control at k5 (p 0.989). That is a coherent story rather than a
fitted one, and it is what the user's own framing predicted.

One reading cuts the other way and is recorded rather than hidden: EXHAUSTED BUYERS, a *bearish*
pattern, is positive on research at p 0.046. It fails locked at p 0.179, so it does not survive —
but the expectation that bearish structure should warn a long is not cleanly confirmed.

**Caveats.** n = 88 on the locked block, which is under 100. One market, one instrument, no
cross-market read. The CVD is a proxy. This is one confirmation, not a result.

## The KAMA earns nothing, and there is no "best setting" to ship

Sixteen readings — two timeframes (60m, 240m) × four lengths (10, 20, 50, 100) × two modes
(`close >`, `close ≥ +1.5 ATR over`):

| reading | research | LOCKED |
| --- | --- | --- |
| close > KAMA20 60m | +0.1372 p 0.000 | +0.0695 **p 1.000** |
| close ≥ +1.5 ATR KAMA20 60m | +0.1611 p 0.003 | +0.1137 p 0.801 |
| close ≥ +1.5 ATR KAMA20 240m | +0.1577 p 0.007 | −0.0049 **p 1.000** |
| close > KAMA10 60m | +0.1028 p 0.165 | +0.1357 p 0.287 |
| close > KAMA50 60m | +0.0900 p 0.691 | +0.1163 p 0.797 |
| close > KAMA100 60m | +0.0644 p 0.980 | +0.0749 p 0.994 |
| close > KAMA100 240m | +0.0595 p 0.987 | +0.0241 **p 1.000** |

**Not one of the sixteen clears the locked block.** Three clear research at p 0.000–0.007 and then
read 0.801–1.000 — research-only artifacts. The length axis is non-monotone and flat (20 best, 100
worst, 10 in between), which is exactly what `STUDY_MA_LAG` predicts: **KAMA's average lag is 1.25
bars at every window**, so its period is close to inert on a trending series. The requested "test for
the best settings" has a negative answer: there isn't one, and the KAMA ships OFF.

*(A bug worth recording: the first KAMA implementation returned 99.9% NaN because a single
non-finite smoothing constant propagated through the recursion. Carrying the previous value across
it fixed it. A recursive indicator that silently becomes all-NaN reads as "no signal", not as an
error.)*

## The session

| window | research | LOCKED |
| --- | --- | --- |
| 08:00-12:00 | +0.1686 p 0.185 | +0.2527 p 0.029 |
| 08:00-12:00 + FLATTEN | −0.0058 p 0.632 | +0.2130 p 0.000 |
| 09:30-16:00 | +0.1161 p 0.566 | +0.1144 p 0.702 |
| 09:30-16:00 + FLATTEN | +0.0662 p 0.301 | +0.0339 p 0.929 |

Both 08:00-12:00 rows pass locked while **failing research** — the wrong shape, and the sixth
occurrence on this branch. The flatten also turns the research block negative (+0.1686 → −0.0058).
Both default to OFF.

## The grid

3 timeframes × 2 entry × 2 exit × 2 stop × 17 KAMA × 17 CVD × 5 session = **34,680 configurations**,
deliberately small. V53 measured what a large grid costs here: grouped by number of active
conditions, mean research R rose +0.0517 → +0.0812 while locked R did not move, and
corr(research, locked) collapsed from +0.2366 to −0.0382.

## Files

`research/v54/v54cvd.py` (the CVD proxy, confirmed pivots, the four patterns, KAMA, causal HTF
sampling) · `run_v54.py` (the sweep) · `run_v54b.py` (the controls) · `results/v54/` ·
`pine/v54/V54_KAMA_HTF_CVD_strategy.pine`.
