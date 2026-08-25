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

## The control does not work, and the number it printed is not a result

`STUDY_TURTLE.md` established that the decisive test for a breakout system here is a random entry
with identical exits. My first attempt printed a control mean of **−0.97 to −2.08 R**, which is
arithmetically impossible for a stop-loss system and is a defect, not a finding.

**Diagnosis, measured on US30 60m:** the 10-bar channel stop sits a median **0.693% of price** from
a breakout bar and only **0.372%** from a random bar, and **6.8% of random bars have less than a
tenth of the breakout median**. A breakout bar is by construction at the top of its range, so its
channel stop is far away; a random bar's is not. A near-zero risk denominator turns any adverse
move into an enormous R-multiple. The control was measuring **stop placement, not entry**.

**So the breakout in this variant is still UNTESTED against a random entry.** The fix is to match
the risk *distribution* as well as the exits — restrict random draws to bars whose channel risk
falls inside the rule's observed range, or give both an ATR stop so the denominator cannot
collapse. Until that runs, the 1H result above should be read as promising and unvalidated: a
meaningful part of it may be the filters and the R:R geometry rather than the Donchian trigger.
