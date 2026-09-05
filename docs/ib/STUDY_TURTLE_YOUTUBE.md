# The YouTube Turtle variant, frozen — and one control that does not work yet

`research/turtle2/ytturtle.py`, `ytfilters.py`, `ytdata.py`, `run_yt.py`. Built **separately** from
the original system and never combined with it. No parameter is searched.

## The spec, with every resolved ambiguity marked

| | |
| --- | --- |
| chart | 5m / 15m / 1H (15m and 1H tested; 5m is below several feeds' resolution) |
| entry | 20-bar Donchian breakout, intraday stop order |
| stop | the 10-bar opposite extreme, **fixed at entry** |
| filter 1 | price above/below the **50 EMA on the 4H** chart |
| filter 2 | avoid major S/R — the **daily, weekly and monthly** high (low for shorts) |
| take profit | **Option 1** largest of 3R/2R/1R that fits below the major level; **Option 2** thirds at 1R/2R/3R, stop to break-even after the first |
| sides | long and short |

**Two ambiguities resolved rather than assumed.** The video says "10-bar stop"; a *trailing* 10-bar
channel would make R change during the trade and "1:1 / 2:1 / 3:1" would have no fixed meaning, so
R is fixed at entry. And Option 2's slide reads "Exit ⅓ … Exit **⅔** … Exit final ⅓", which sums to
4/3 of the position — three equal thirds is the only reading that closes.

**One thing that resolved itself.** The avoid-resistance tolerance is not stated in the video, and
I had picked 1.0R as a defensible default. Option 1's "minimum 1 to 1" makes that the *same*
constraint: a trade without 1R of clearance cannot reach its minimum target, so it is not taken.
The tolerance is the video's, not mine.

## Leakage

The 4H EMA on a 15-minute chart is the classic repainting leak. Three readings exist and only the
first two are causal: the EMA of the last **completed** 4H bar (default), the **running** EMA of
the developing bar, and the indefensible one — the EMA of the 4H bar *containing* the current bar,
computed on the whole series, which reads up to 3h45m ahead. The truncation audit passes at
**105 checks, 0 mismatches** on both 5m and 15m.

Filter selectivity, measured: price is above the 4H 50 EMA on **62.5%** of bars; "avoid major
resistance" at 1R blocks **10.0%** of long bars on 5m and **18.6%** on 15m.

## Result — the timeframe decides it

Pooled across markets, R-multiples, per-market 65/35 split, OOS read once.

| chart | exit | block | n | win | E[R] | PF | long | short |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 15m | Option 1 | in-sample | 5,727 | 38.0% | +0.033 | 1.05 | +0.103 | −0.052 |
| 15m | Option 1 | **OOS** | 3,022 | 37.0% | **−0.001** | 1.00 | +0.071 | −0.098 |
| 15m | Option 2 | in-sample | 6,296 | 51.9% | +0.017 | 1.03 | +0.057 | −0.030 |
| 15m | Option 2 | **OOS** | 3,284 | 50.3% | **−0.020** | 0.96 | +0.020 | −0.073 |
| 60m | Option 1 | in-sample | 2,324 | 40.2% | +0.151 | 1.25 | +0.249 | +0.030 |
| 60m | Option 1 | **OOS** | 1,359 | 39.4% | **+0.102** | 1.16 | +0.187 | −0.012 |
| 60m | Option 2 | in-sample | 2,571 | 57.3% | +0.166 | 1.38 | +0.201 | +0.122 |
| 60m | Option 2 | **OOS** | 1,417 | 55.8% | **+0.097** | 1.21 | +0.156 | +0.023 |

**The 15-minute chart fails out of sample and the 1-hour chart does not.** That is the sixth
independent time on this branch that the intraday-scalping end of the timeframe axis has failed
while the slower end survived.

Per market on 1H / Option 2 out-of-sample, **five of six are positive**: US30 +0.157, XAUUSD +0.161,
EURUSD +0.102, BTC +0.063, US100 +0.039, NQ −0.090 (and NQ has the least history by far). That is a
far better spread than the original Turtle, whose entire out-of-sample result was one market.

Cost sensitivity, 1H Option 2 pooled: OOS **+0.170** at zero cost, **+0.097** at the assumed cost,
+0.046 at 1.5×, +0.025 at 2×, **+0.002 at 3×**. It survives to 2× and is gone by 3×.

## How solid is the 1H Option 2 number?

Day-block bootstrap of the pooled out-of-sample mean — whole days resampled with their trades
attached, 5,000 draws, because trades cluster within a session and a trade-wise resample would
overstate the precision:

**95% CI [+0.0344, +0.1643], P(mean ≤ 0) = 0.0020.**

Leave-one-market-out, which is the test the original Turtle failed badly:

| dropped | n | E[R] |
| --- | ---: | ---: |
| BTC | 1,164 | +0.1039 |
| EURUSD | 1,040 | +0.0947 |
| NQ | 1,347 | +0.1063 |
| US100 | 1,207 | +0.1066 |
| US30 | 1,216 | +0.0867 |
| XAUUSD | 1,111 | +0.0789 |

**No single market carries it** — the spread is +0.079 to +0.107 against a pooled +0.097. Compare
the original Turtle, where removing BTC alone took the out-of-sample block from +0.018 to −0.052.

So the *sample mean* is not fragile. What remains unestablished is the **attribution**, below.

## THE BREAKOUT CONTRIBUTES NOTHING — the control now works, and it says no

The first attempt at this control was broken and is documented below, because the fix is the
finding's foundation. **Risk-matched** now: for each real trade, the control draws a random bar
whose 10-bar channel risk lies within ±15% of that trade's own risk, on the same side, keeping the
4H EMA filter, the avoid-resistance rule, the stop and the R:R ladder. It differs from the rule in
**when it enters and in nothing else**.

| | rule E[R] | control E[R] | excess | p |
| --- | ---: | ---: | ---: | ---: |
| Option 1, in-sample | +0.151 | **+0.186** | −0.035 | 0.750 |
| Option 1, out-of-sample | +0.102 | **+0.133** | −0.031 | 0.625 |
| Option 2, in-sample | +0.166 | **+0.205** | −0.039 | 0.750 |
| Option 2, out-of-sample | +0.097 | **+0.197** | **−0.100** | 0.875 |

**A random entry at matched risk beats the Donchian breakout in all four cells.** The excess is
negative everywhere and largest out of sample. Whatever this configuration earns comes from the
**4H EMA regime filter, the avoid-resistance rule and the 1R/2R/3R geometry** — not from the
20-bar channel.

This is the third independent time on this branch that a breakout trigger has failed against its
own random-entry control: the Turtle channel scored +0.595 against a coin flip's +0.601
(`STUDY_TURTLE.md`), the eight-hypothesis programme found H1/H6/H7 to be one rule wearing three
hats, and now this.

**It also explains the live result.** A TradingView run of the shipped Pine lost money (PF 0.94,
−10.2%). If the trigger adds nothing, the strategy reduces to "be long above the 4H EMA with a
scale-out", which is thin enough that an implementation difference — and there was one, a broken
avoid-resistance gate taking 2.3× the trades — flips the sign.

One caveat on the control's own construction: the ±15% risk band means some real trades have no
matching candidate bar, so the control carries fewer trades than the rule (102 against 328 on US30
in-sample) and its mean is noisier. The direction is consistent across all four cells and eight
draws, and the control sits *above* the rule rather than below, so sample size is not what produced
the sign.

## Appendix: how the first control was wrong

My first attempt printed a control mean of **−0.97 to −2.08 R**, arithmetically impossible for a
stop-loss system and a defect rather than a finding.

**Diagnosis, measured on US30 60m:** the 10-bar channel stop sits a median **0.693% of price** from
a breakout bar and only **0.372%** from a random bar, and **6.8% of random bars have less than a
tenth of the breakout median**. A breakout bar is by construction at the top of its range, so its
channel stop is far away; a random bar's is not. A near-zero risk denominator turns any adverse
move into an enormous R-multiple. The control was measuring **stop placement, not entry**.

The fix was trade-for-trade risk matching, and the result is the section above. Recording the
defect matters because the broken control's numbers looked *favourable* to the rule — a control
that loses 2R per trade makes any strategy look brilliant by comparison. **A control that flatters
the thing it is testing is the one to distrust most.**
