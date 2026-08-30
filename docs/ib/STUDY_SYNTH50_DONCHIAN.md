# Donchian breakout trend-following on 1,800 synthetic years — and what the Monte Carlo says

Asked for: a profitable Donchian breakout trend-following strategy on ~50 years of simulated
Nasdaq/US30-like price action, EMA 200/48/13, ADX > 25, stop 1.5 x ATR, deep learning, scalping
07:00-11:00 New York, with out-of-sample testing and Monte Carlo to find the best mean for each
parameter.

All of that was built and run. **36 independent worlds x 50 years = 1,800 synthetic years**, three
trend regimes, 180 configurations per world, both sides, a matched control per selected
configuration, and a deep-ensemble meta-label trained in-sample only.

Read §1 before §4. The most valuable result in this study is not a strategy; it is that the
in-sample optimiser reliably selected a **harness artefact**, and the Monte Carlo is what exposed
it.

## Modules

| file | what it does |
| --- | --- |
| `research/synth50.py` | the generator: log-OU stochastic volatility, Student-t innovations, an AR(1) slow-drift trend state with an explicit strength, a real intraday volatility profile, overnight gaps, a bid-ask bounce, tick-grid snapping |
| `research/dbt50.py` | indicators, the exit tensor, the merged two-sided book, the matched control, the deep meta-label, and `--stage0` |
| `research/dbt50_run.py` | the experiment: worlds x regimes x configurations |
| `research/dbt50_report.py` | marginals, the selection test, the ablation |

## Generator calibration (measured, not asserted)

`python3 research/synth50.py`

| statistic | measured | real index futures |
| --- | --- | --- |
| annualised volatility | 0.22 | 0.15-0.25 |
| daily return kurtosis | 6.0 | 5-12 |
| bar-level ACF(1) | -0.007 | slightly negative (bid-ask bounce) |
| open (09:30-10:00) vol / midday vol | 2.9 | ~2.5-3.5 |
| pre-market vol / midday vol | 0.99 | below 1 |
| variance ratio VR(5), `trend=0` | 1.03 | 1.0 by construction |
| variance ratio VR(5), `trend=0.10` (default) | 1.03 | ~1.0-1.1 |
| variance ratio VR(5), `trend=0.35` | 1.30 | far trendier than any real index |

The trend strength is an explicit knob, so the study runs the strategy in a world with a realistic
trend, a world with an implausibly strong one, and a **martingale null**. A trend follower that
earns in the null is measuring something other than trend.

## 1. Stage 0 found a real bias, and it is not in the code

`python3 research/dbt50.py --stage0` runs the whole harness over a driftless world **with costs
switched off**. Anything it earns there is engine bias by construction.

| bar built from | 1:1 geometry | 3:1 geometry |
| --- | --- | --- |
| 1 sub-step | +0.0000R | **+0.2324R** |
| 6 sub-steps | -0.0029R | **+0.0883R** |
| 24 sub-steps | -0.0027R | **+0.0374R** |
| 50 sub-steps | -0.0017R | **+0.0291R** |

A symmetric geometry is unbiased at every resolution. An **asymmetric** one is optimistic, and the
optimism shrinks as the bar is built from more sub-steps — so it is bar **discretisation**, not
drift and not a coding error. The mechanism: a bar whose range merely grazes a 3R target books the
full +3R, while the same graze against the 1R stop is capped at -1R. Coarse bars have relatively
larger ranges, so they graze more often, and the 3:1 payoff harvests it.

Two consequences, and they run through everything below:

1. The experiment was re-run at 24 sub-steps per bar, which cuts the artefact to +0.037R.
2. **No raw per-trade number from an asymmetric geometry means anything on its own.** The matched
   control shares the geometry and therefore the bias, so the excess over control is the only
   quantity that survives it.

## 2. The experiment

`python3 research/dbt50_run.py --paths 12 --years 50 --meta`

36 worlds x 50 years x 180 configurations x 2 sides. Each world: pick the best configuration on
the first 65% of its sessions, read the remaining 35% **once**, and run a matched control (400
draws, same side, same geometry, same minute-of-day distribution) for the configuration that was
picked. Costs are NQ's: $4 commission plus one tick of spread each side plus one tick of stop
slippage, on a $20 point value — a **2.8-tick round turn**.

| regime | `trend` | measured VR(5) | measured daily ACF(1) | what it is |
| --- | --- | --- | --- | --- |
| `null_martingale` | 0.00 | 0.979 | −0.005 | no trend, no drift — the ablation |
| `trend_realistic` | 0.10 | 1.021 | +0.003 | about as trendy as a real index |
| `trend_strong` | 0.35 | 1.338 | +0.085 | far trendier than any real index |

## 3. Result

| | null (no trend) | realistic trend | strong trend |
| --- | --- | --- | --- |
| in-sample winner | +0.0247R | +0.0419R | −0.0253R |
| its out-of-sample | −0.0118R | +0.0421R | −0.1338R (median +0.0628R) |
| matched control, out-of-sample | −0.0119R | +0.0346R | −0.2560R (median −0.0032R) |
| **excess over control** | **+0.0001R** | **+0.0075R** | **+0.1222R** |
| t-statistic over 12 worlds | +0.01 | +1.35 | +2.29 |
| worlds with positive excess | 4 / 12 | 6 / 12 | **12 / 12** |
| out-of-sample trades per world | 3,736 | 3,556 | 3,918 |

Read across that row: **+0.000R → +0.008R → +0.122R** as the trend goes from absent to realistic
to implausible. The strategy is doing exactly what a trend follower should — it harvests trend and
nothing else — and it needs **far more trend than a real index has** before it separates from a
random entry with the same geometry and the same time-of-day profile.

Three things follow, and only the third is about a strategy:

* **In the martingale world the strategy IS its control**, to four decimal places (+0.0001R,
  t=0.01). That is the cleanest possible statement that the harness is not manufacturing an edge
  and that the rule contributes nothing when there is nothing to follow.
* **At a realistic trend the excess is +0.0075R at t=1.35, with 6 of 12 worlds positive.** That is
  a coin flip. Over 1,800 synthetic years and 43,000 out-of-sample trades, this Donchian rule does
  not reliably beat a random entry of the same shape.
* **At an implausible trend it wins in 12 worlds out of 12.** The mechanism is real; the market it
  needs is not the one that exists.

The strong-trend row also shows why medians are reported: with a persistent drift state over fifty
years, 5 of 12 worlds ended outside a plausible price band (one finished at 146 from a start of
15,000), and a fixed $14 round turn against a collapsed index makes per-trade R explode. The mean
excess (+0.1222R) and the median excess (+0.0781R) tell the same story, which is the point of
showing both.

## 4. "The best mean on each parameter" — and why there isn't one

Marginal mean out-of-sample R per trade, averaged over the other parameters, across 12 independent
worlds, realistic-trend regime (mean ± standard error over worlds):

| parameter | values | verdict |
| --- | --- | --- |
| Donchian lookback | 10: +0.0211 · 20: +0.0216 · 30: +0.0217 · 40: +0.0211 · 60: +0.0217 (±0.0045) | **flat** |
| ADX threshold | 20: +0.0201 · 25: +0.0187 · 30: +0.0255 (±0.0047) | **flat** |
| max hold | 12: +0.0209 · 24: +0.0225 · 48: +0.0209 (±0.0045) | **flat** |
| target (R) | 1: +0.0013 · 1.5: +0.0162 · 2: +0.0259 · **3: +0.0422** (±0.0050) | a strong, clean gradient |

Every knob is flat inside its error bars except the target multiple, which looks like a real,
monotone optimum at 3R — and the in-sample optimiser duly picked `tp=3.0` in **34 of 36 worlds**.

Now look at the same table in the **martingale world**, where there is no trend to capture:

| parameter | values |
| --- | --- |
| target (R) | 1: −0.0468 · 1.5: −0.0368 · 2: −0.0274 · **3: −0.0173** |

The gradient is still there, and it is the same size: **+0.030R from 1R to 3R in a world with no
trend at all**, against the +0.037R of harness optimism that §1 measured directly at 3:1. The
"best parameter" is the discretisation artefact.

Subtracting the martingale world's marginals value by value leaves the trend-attributable part:

| parameter | trend-attributable marginal |
| --- | --- |
| Donchian lookback | 10: +0.0533 · 20: +0.0538 · 30: +0.0537 · 40: +0.0535 · 60: +0.0531 |
| ADX threshold | 20: +0.0483 · 25: +0.0504 · 30: +0.0618 |
| target (R) | 1: +0.0481 · 1.5: +0.0531 · 2: +0.0533 · 3: +0.0595 |
| max hold | 12: +0.0526 · 24: +0.0543 · 48: +0.0535 |

**Every parameter is flat.** Across a 6x range of lookback, a 3x range of target and a 4x range of
holding time, nothing moves outside the noise. So the honest answer to "find the best mean on each
parameter" is: *there is no best value for any of them, and the one that appeared to have one was
an artefact of the simulator.* A single 50-year backtest would have reported `tp=3.0, don=20,
adx=30` with confidence.

## 5. The deep learning layer

A heteroscedastic deep ensemble (5 members x 20 MC-dropout passes, `research/uq_net.py`) used as a
**meta-label**: it never picks a side, it only declines some of the rule's own signals. Trained on
in-sample trades only, threshold set from training rows only, 11 signal-bar features, no calendar
variables.

| | value |
| --- | --- |
| unfiltered out-of-sample | +0.0421R |
| filtered (keeps the top half by P(win)) | +0.0399R |
| change | **−0.0022R, t = −0.34, 7 of 12 worlds improved** |

**No effect.** It halves the trade count and moves per-trade R by less than a fifth of a standard
error. That is the expected outcome when the thing being filtered has no conditional structure to
find: the network is well-calibrated (in-sample ECE around 0.03) and still has nothing to say.
Note the coarse-bar run reported −0.0222R at t=−3.15 — the network was reliably *destroying* value
by declining exactly the trades that the 3:1 artefact was paying for. Both runs agree on the
conclusion: the model layer is not where anything is happening.

## 6. What this says about the real thing

The request was a profitable strategy. In the trending worlds this one is profitable in dollars —
and so is a random entry taken at the same times with the same barriers, which is the entire point
of quoting the control. The parts that transfer to a real instrument:

1. **A trend follower needs trend, and the amount it needs is measurable.** At VR(5) = 1.02 —
   roughly a real index — the excess over control is a coin flip. At VR(5) = 1.34 it wins in every
   world. Before running this on NQ, measure NQ's variance ratio; `docs/RESEARCH_PROTOCOL.md`
   Stage 2 already computes it.
2. **Asymmetric barrier geometries cannot be trusted from bar data alone.** The +0.037R optimism
   at 3:1 with 24 sub-steps per bar is larger than the entire trend-attributable edge in the
   realistic regime. On real 5-minute bars there are no sub-steps at all — the correct instrument
   is `research/intrabar.py`, which walks the true 1-minute path.
3. **The 07:00-11:00 window is priced by the control, not credited to the rule.** The generator has
   a real intraday volatility profile (open vol 2.9x midday), so trading the open genuinely gives
   more range — and the minute-of-day-matched control captures that, which is why the excess is so
   much smaller than the raw number.
4. **1,800 years was barely enough.** With 3,500 out-of-sample trades per world the per-world
   excess has a standard error of about 0.006R, so a +0.0075R effect sits at t=1.35 across twelve
   worlds. Any real study with three years of one instrument is working with a hundredth of this
   statistical power — which is the honest reason most single-instrument breakout results do not
   replicate.

## 7. Reproducing

```bash
python3 research/synth50.py                     # generator calibration self-test
python3 research/dbt50.py --stage0              # the discretisation table in §1
python3 research/dbt50_run.py --paths 12 --years 50 --meta --out /tmp/r.json
python3 research/dbt50_report.py /tmp/r.json    # §3, §4, §5
```

Runtime is about 6.5 minutes for the full 1,800-year experiment on one core.
