# Intraday trend → pullback → continuation on NQ: a 400,226-configuration search

**Task:** develop and validate a robust intraday trend-following edge for NQ/MNQ over EMA lengths,
VWAP deviation, ATR/realised-vol filters, time-of-day, trend regime, pullback depth, momentum,
entry timing, stops, targets and cross-market inputs; search systematically; validate out of
sample; return the strongest statistically defensible specification.

**Answer: there isn't one.** Ten pre-specified variants all lose. A 400,226-configuration search
produces winners that are *negative* out of sample. Walk-forward re-selection loses $27.19/trade.
35 of 37 immediate parameter neighbours flip sign between research and holdout, and the two that
don't are consistently *negative*. The search curve falls monotonically: best-of-300,000 lands at
the **9.2nd percentile** of out-of-sample outcomes.

Code: `research/trend_pullback.py` (engine), `research/trend_search.py` (search),
`research/trend_validate.py` (battery).

## 0. What could not be tested

**Cross-market ES inputs were not tested — there is no ES data in this repository.** `data/` holds
`NQ_1m.csv` and `NQ_5m.csv` only. The engine has the hook and the study is ready to re-run when ES
minute data is added; nothing below uses a cross-market input, and no claim is made about one. This
is the one requested dimension that is missing.

## 1. Design, and what was fixed before searching

**Structure** (fixed, because the structure is the hypothesis):

1. **Trend** — a fast/slow EMA relationship, optionally confirmed by slow-EMA slope or session VWAP.
2. **Pullback** — price retraces into a zone around the fast EMA in ATR units, or back inside a VWAP
   deviation band, or gives back a fraction of the impulse.
3. **Continuation** — an explicit momentum trigger; the fill is the **next bar's open**.

**Searched space** — 5,038,848 cells:

| axis | settings |
| --- | --- |
| EMA fast / slow | 9, 21, 34 / 50, 100, 200 |
| trend regime | EMA stack; + slope; + session VWAP |
| pullback mode | ATR band round fast EMA; VWAP σ-band; impulse give-back |
| pullback depth | 0.25, 0.5, 1.0, 1.5 (ATR or σ) |
| momentum / entry trigger | close through EMA; prior-bar extreme; close in top/bottom third |
| ATR / realised-vol regime | percentile windows [0,1], [0,0.5], [0.5,1], [0.25,0.75] |
| time of day | full RTH; first 2h; first 3.5h; from 11:00 |
| stop | 1.0/1.5/2.0 × ATR, or beyond the pullback extreme |
| target | 1.0/1.5/2.0/3.0 R, ATR multiple, or ride to the close |
| entry timing | max 1/2/3 trades per session; 5/15/30-bar cooldown |

**Three decisions were pre-registered and not searched:**

- **Direction is not a free parameter.** Every search in this project handed a side switch returns
  "longs only" and is fitting the index — eight sightings. Both sides always trade. §7 reports what
  a side switch *would* have bought, as a diagnostic.
- **Selection is on dollars, not R.** Maximising mean R converges on tiny-stop configurations; an
  Asia candidate once reached E = +0.351R while losing $707.
- **Costs are charged before selection:** $19.00/round turn on NQ (1 tick spread + 1 tick slippage
  per side + $4), $3.30 on MNQ. Every figure below is net.

**Splits, on session boundaries:** research 382 sessions / validation 191 / **locked holdout 192**,
from 292,908 RTH 1-minute bars, Dec 2022 – Dec 2025.

## 2. The pre-specified set: all ten lose

Run before any search, holdout closed. Full table in `research/trend_pullback.py --stage prespec`.

| variant | n | $/trade | PF | t | E[R] |
| --- | --- | --- | --- | --- | --- |
| A textbook 21/50, 0.5×ATR pullback, 1:2 | 1,526 | −53.06 | 0.859 | −2.78 | −0.058 |
| B slower trend 34/100 | 1,526 | −62.93 | 0.830 | −3.43 | −0.070 |
| C slope-confirmed trend | 1,526 | −30.95 | 0.916 | −1.52 | −0.015 |
| D VWAP-confirmed trend | 1,526 | −30.96 | 0.912 | −1.61 | −0.020 |
| E VWAP-band pullback (1σ) | 1,526 | −37.14 | 0.901 | −1.91 | −0.052 |
| F deeper pullback, wider stop | 1,515 | −46.42 | 0.906 | −1.80 | −0.049 |
| G swing stop | 1,525 | −22.65 | 0.906 | −1.64 | **+0.017** |
| H morning only | 1,516 | −55.11 | 0.853 | −2.89 | −0.065 |
| I high-volatility regime only | 1,465 | −58.30 | 0.850 | −2.92 | −0.060 |
| J ride to the close | 1,400 | −10.09 | 0.979 | −0.26 | **+0.008** |

Every one loses. Two (G, J) show **positive E[R] with negative dollars** — the R-versus-dollars
trap, and the reason selection here is on dollars.

An earlier draft of this table ran without the entry-timing controls (`max_per_sess`, `cooldown`)
and took ~19 trades a session, spending $361/day on round turns before the rule had said anything.
Adding those controls cut frequency to ~2/day and is what the figures above reflect; it did not
change the sign of any variant.

## 3. The search, and what it cost

400,226 evaluable configurations, uniformly sampled from the 5,038,848-cell grid.

```
research $/trade: mean -18.83, sd 21.37, best +175.04, 14.2% profitable
holdout  $/trade: mean -26.38, sd 47.10, best +438.70, 25.8% profitable
Spearman rank correlation research -> holdout: +0.1139
```

### The search curve

Take the best configuration out of K on research; look up where it landed on the holdout.

| K | holdout percentile | mean holdout $/trade |
| --- | --- | --- |
| 1 | 47.4% | −30.48 |
| 10 | 49.6% | −27.75 |
| 100 | 43.9% | −38.75 |
| 1,000 | 42.6% | −40.07 |
| 10,000 | 38.3% | −54.66 |
| 30,000 | 31.3% | −71.99 |
| 100,000 | 24.1% | −88.38 |
| **300,000** | **23.2%** | **−74.22** |

**Searching harder makes the answer monotonically worse.** A random pick lands at the 47th
percentile; the best of 300,000 lands at the 23rd. Restricting to configurations with ≥200 research
trades — a fairer search that excludes small-sample flukes — the collapse is sharper still: **9.2nd
percentile at K = 300,000, mean −$150.37/trade.**

This is the third independent reproduction of this curve in this repository, after 225,792 IB
configurations and 2,400 ORB configurations.

### The winners

| selected by | research | validation | **LOCKED holdout** |
| --- | --- | --- | --- |
| best on research (n=86, t=3.20) | **+$175.04** | +$83.43 | **−$94.35** |
| best on research **and** validation | +$93.49 | +$343.79 | **−$109.83** |
| *all 27,929* configs profitable on both | — | — | **mean −$26.62, median −$20.52, 32.4% profitable** |

A best-of-400,226 search draws **E[max z] ≈ 5.08** from noise alone. The research winner reaches
t = 3.20. It does not clear its own search.

The third row is the one that settles it: requiring profitability on *two* independent periods still
leaves 27,929 candidates, and that whole set averages **−$26.62/trade** on the holdout. The double
filter selects nothing.

## 4. Parameter stability: 35 of 37 neighbours flip sign

Every immediate neighbour of the finalist, one axis at a time, run fresh:

```
axis            setting      n   research  validation    HOLDOUT
ema_fast              9    746      93.49      343.79    -109.83  <- finalist
ema_fast             21    740      39.33       26.72    -160.71
ema_fast             34    727     -79.32      -22.40    -207.51
trend_mode            0    746      80.82      230.86    -130.74
trend_mode            2    744      56.65      241.82     -68.42
entry_mode            1    746      53.62      279.07     -61.35
stop_mode             1    746      49.42      275.73     -32.91
stop_mult           1.0    746      30.09      405.71    -121.02
stop_mult           2.0    746      18.70      300.04     -37.67
target_mode           0    746     -30.28      122.38     +58.08
target_mode           1    746     -22.61       73.72     +34.62
max_per_sess          3  1,795       1.75      113.78     -81.14
```

**35 of 37 neighbours flip sign between research and holdout.** The only two that hold their sign
(`ema_fast=34`, `pull_mode=1`) are consistently **negative**. Note `target_mode` 0 and 1: negative on
research, positive on holdout — the surface is not a plateau with a peak, it is noise.

## 5. Walk-forward

Re-select from the top 4,000 on a rolling 250-session window, trade the next 60:

```
stitched out-of-sample: 402 trades, -$10,929, -$27.19/trade, PF 0.942, t = -0.39
8 folds; the procedure re-picked 8 DISTINCT configurations
fixed finalist over the whole sample: +$104.72/trade
```

Eight folds, eight different winners, and the procedure loses money. That is the definition of a
selection rule carrying no information.

## 6. Costs, contract, and Monte Carlo

| cost × | $/round turn | $/trade |
| --- | --- | --- |
| 0.0 | 0.00 | +123.72 |
| 1.0 | 19.00 | +104.72 |
| 2.0 | 38.00 | +85.72 |

The finalist is nearly cost-insensitive — it trades only 746 times — so **costs are not why it
fails.** It fails because it is fitted. On **MNQ** the same trades net **$9.07/trade** ($6,768
total): a $2/point contract cannot carry a $3.30 round turn on this geometry.

Monte Carlo on the finalist's trade list (20,000 paths, $50k) gives median drawdown 33.8%, 95th
percentile 64.1%, P(ruin) 1.5% on resampling. **This is reported for completeness and is not
evidence:** the trade list is two-thirds in-sample, and reshuffling an in-sample equity curve cannot
tell you whether the edge is real. Monte Carlo tests path sensitivity, never selection bias.

## 7. The side-switch diagnostic

What allowing direction to be searched would have bought:

| | research | holdout |
| --- | --- | --- |
| longs only | +$39.50 | **−$100.33** |
| shorts only | +$31.23 | **+$154.05** |

The sides disagree between halves, as they have in every prior study here — except that this time
**shorts** win the holdout, where earlier studies had longs winning. That reversal is itself the
point: the side that "works" is a property of the period, not of the setup. Keeping direction fixed
was the right pre-registration.

## 8. The strongest statistically defensible specification

Not from this search. The strongest defensible trend → pullback → continuation rule in this
repository remains the one already validated here, re-verified live for this study:

> **Initial-balance retracement.** Build the initial balance 09:30–10:30 ET. On a *close* beyond
> either edge, rest a limit at a **50% retracement** of that range. Stop at **80%** of the range from
> the broken edge. Fixed **1:2** target. **Both sides.** Flat at 11:59. One trade per session.
>
> `n = 167, mean +0.3248R`, block bootstrap (10,000 paths, mean block 5)
> **95% CI [+0.1614, +0.4895], P(mean ≤ 0) = 0.0000**, PBO 0.17–0.24 across S = 10/12/16.

It is the same three-part structure — trend identification, pullback, continuation entry — but
anchored to a **session event** rather than to a continuously-armed EMA state machine. That
difference is most of the story: the IB rule is armed once per day by a specific event, takes ≤1
trade, and its parameters are read off a range that exists independently of the rule. The EMA
version is armed continuously, and a continuously-armed condition on 1-minute bars is a machine for
finding coincidences.

Caveats that belong with it: re-optimising it destroys value ($14,580 rolling re-optimisation vs
$27,253 fixed over identical out-of-sample bars), its research/holdout split is 0.414R vs 0.116R, and
a longs-only filter looks like its largest improvement while scoring −0.006 research / +0.255
holdout — i.e. the same direction trap.

## 9. Evidence the absence of an edge is not itself an artifact

The honest failure mode of a negative result is a broken engine. Four checks:

1. **The engine finds the effects it should.** The same code reproduces the IB configuration above to
   the digit against a separately written TypeScript engine (1,413 trades across five
   configurations, matching on every field).
2. **A real signal is detectable.** In the metric layer used here, a synthetic within-day signal
   scores $285/trade at t = 78 while a pure day-selector scores $2.58 at t = 0.69.
3. **The search does find in-sample winners** — best-on-research reaches +$175.04/trade at t = 3.20.
   The machinery works; the winners just do not survive.
4. **25.8% of configurations are profitable on the holdout** — the holdout is not degenerate, it is
   simply uncorrelated with research (ρ = +0.11).

## 10. Conclusions

1. **No statistically defensible EMA-based intraday trend-pullback specification was found on NQ
   2022–25** at realistic costs.
2. **The search actively destroys value here.** Best-of-K degrades monotonically to the 23rd
   percentile (9.2nd on the higher-trade-count subset).
3. **Profitability on two independent periods is not sufficient.** 27,929 configurations passed that
   filter and averaged −$26.62/trade on the holdout.
4. **The surface is not a plateau.** 35 of 37 immediate neighbours flip sign out of sample.
5. **Costs are not the binding constraint** for the finalist — it fails at zero cost too. On MNQ they
   are: $9.07/trade.
6. **Continuous arming is the structural problem.** The rule that survives is armed once per session
   by an event; the rules that fail are armed on every bar.
7. **ES cross-market inputs remain untested** for want of data, and are the most informative
   remaining test — a trend filter from a correlated index is the one requested feature that could
   not be tried.

## 11. Reproduce

```bash
python3 research/trend_pullback.py --stage prespec   # the ten pre-specified variants
python3 research/trend_search.py --workers 4 --sample 400000
python3 research/trend_validate.py                   # curve, stability, WF, MC, costs, holdout
python3 research/validate.py                         # re-verifies the IB configuration in S8
```
