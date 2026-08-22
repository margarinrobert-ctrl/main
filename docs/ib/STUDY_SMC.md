# Smart money concepts and break of structure, tested as machine learning

**Question asked:** *"do machine learning to use break of structure and smart money concepts to find a
profitable edge on intraday trading scalping"*, then *"robust it and find anomalies to prediction for
edge"*.

**Answer:** no edge. Not a weak one, not a costed-away one — the concepts as specified carry
essentially no directional information on three years of 1-minute NQ, and the model that ranks them
puts *volatility and time of day* above every SMC feature. The robustness sweep and the FDR-controlled
event study below are what turn that from one run's result into a finding.

Code: `research/smc.py` (features, 18 unit tests in `research/test_smc.py`), `research/smc_ml.py`
(model), `research/smc_events.py` (robustness + event study).

## 0. Why this study had to define SMC mechanically first

Smart money concepts are taught visually. A visual rule cannot be falsified: any chart can be
annotated after the fact so the concept looks right. So the first job was to write each concept as an
explicit, causal rule on OHLCV bars, and the second was to unit-test those rules against hand-built
bar sequences with a known answer. `research/test_smc.py` does that — 18 tests covering pivot
confirmation lag, BOS/CHoCH transitions, FVG geometry, sweep detection, and the dealing range.

| concept | the rule actually tested |
| --- | --- |
| swing pivot | fractal high/low, **confirmed `k=3` bars later** — a pivot at *t* is invisible until *t+3* |
| BOS | close beyond the last confirmed swing in the direction of structure |
| CHoCH | the first BOS *against* the prevailing structure |
| FVG | three-bar imbalance: `low[i] > high[i-2]` (bullish), `high[i] < low[i-2]` (bearish) |
| order block | last opposing candle before the impulse that broke structure |
| liquidity sweep | wick beyond a prior swing that **closes back inside** |
| premium/discount | position inside the current dealing range |

Everything at bar *i* uses only bars ≤ *i*. The pivot confirmation lag is the part most SMC backtests
get wrong, and it is the part that flatters them most.

## 1. The model

- **Data:** 292,908 RTH 1-minute NQ bars (09:30–16:00), Dec 2022 – Dec 2025. 292,114 labelled.
- **Labels:** triple barrier, ±1.0×ATR(30), 60-bar limit, capped at the session close.
- **Features:** 21 SMC features plus ATR-relative volatility, minutes-since-open, range position,
  and relative volume.
- **Model:** gradient boosting, 120 trees, depth 3, learning rate 0.05.
- **Validation:** purged + embargoed 5-fold CV (1% embargo). Triple-barrier labels *overlap* — a
  bar's outcome is determined by bars up to 60 minutes later — so plain K-fold leaks the answer
  across the fold boundary. This is the single correction that decides the result.
- **Holdout:** the last 58,428 bars, opened once.
- **Costs:** $19.00 per round turn (1 tick spread + 1 tick slippage per side + $4 commission).

### Results

```
base rate (up barrier first): 0.5025
take-EVERY-bar-long baseline: $-18.22/trade

REAL labels      purged-CV AUC 0.5080    $/trade at p>=0.55: +26.24
SHUFFLED labels  purged-CV AUC 0.5019    $/trade at p>=0.55: -57.93

LOCKED HOLDOUT (58,428 bars), AUC 0.5106
  threshold   trades   $/trade      total $   win%
   take all    58428    -20.51   -1,198,289  49.6%
       0.50    38666    -15.89     -614,356  50.3%
       0.55      387    -56.97      -22,049  45.5%

top features: atr_rel 0.153  mso 0.143  range_pos 0.109  ob_dist 0.091  vol_rel 0.083
```

Three things to read here.

**The AUC is 0.508 against a shuffled control of 0.502.** That is the honest size of the signal: six
thousandths of an AUC point. It is not zero, but it is nowhere near the ~0.53 you need before a
1-minute strategy pays a $19 round turn.

**The one number that looked like an edge did not survive the holdout.** In cross-validation, the
high-confidence bucket paid **+$26.24/trade**. On the locked holdout, the same rule at the same
threshold paid **−$56.97**. This is the third time in this project that purged, embargoed CV has
overstated a result enough to flip its sign (meta-labelling did the same: $441 → −$245). Purging is
necessary and it is not sufficient.

**The feature ranking is the finding.** `atr_rel` (volatility) and `mso` (minutes since the open) are
the top two features, ahead of every smart-money concept. The best-placed SMC feature is order-block
distance at 0.091. A gradient booster handed the entire SMC vocabulary preferred *what time it is*.

## 2. Robustness — is this a property of SMC, or of one barrier?

The failure above rested on one geometry, where the round turn was 8.4% of the median risk. A wider
barrier cuts that fraction proportionally, so the fair question is whether cost is what is killing it.

```
   barrier   bars         n  up first  median risk  cost/risk  long $/trade  short $/trade
+/-0.5xATR     60   292,114    47.51%         $104      18.2%        -25.17         -12.83
+/-1.0xATR     60   292,114    50.12%         $209       9.1%        -18.68         -19.32
+/-2.0xATR     60   292,114    50.30%         $417       4.6%        -18.44         -19.56
+/-2.0xATR    240   292,114    50.32%         $417       4.6%        -17.97         -20.03
+/-3.0xATR     60   292,114    51.22%         $626       3.0%        -11.35         -26.65
+/-3.0xATR    240   292,114    50.88%         $626       3.0%        -11.75         -26.25
```

**Cost falls six-fold, from 18.2% of risk to 3.0%, and nothing crosses zero.** If the spread were the
binding constraint, the widest barrier would fix it; instead the long side improves from −$25 to −$11
and stops there, and the short side gets *worse*. That asymmetry at wide barriers is the NQ uptrend
showing through a longer horizon, not an edge — it is the same effect that made `sideMode=1` win every
optimiser search in this repository.

The 60-bar and 240-bar rows are nearly identical because session capping resolves most barriers well
inside an hour. Horizon is not the free parameter it looks like.

## 3. The anomaly hunt: which SMC events pay?

17 event conditions, each tested LONG and SHORT, barrier ±2×ATR / 120 bars, Newey-West t-statistics
with the lag set to the barrier horizon, Benjamini-Hochberg across all 30 tests, research (first 80%)
versus holdout (last 20%).

```
event                               side       n   $/trade       t       q   research   holdout
premium (>0.75 of range)           short 100,629    -26.06   -5.47   0.000     -26.79    -23.10  *
bull FVG just below (<0.5 ATR)     short  75,840    -26.72   -5.45   0.000     -27.70    -22.81  *
BOS up                             short  59,205    -28.54   -5.42   0.000     -30.79    -19.24  *
BOS up, fresh (<10 bars)           short 126,509    -25.88   -5.41   0.000     -27.81    -17.91  *
bear FVG just above (<0.5 ATR)      long  70,926    -23.55   -4.39   0.000     -21.16    -33.43  *
CHoCH down                         short   4,903    -34.61   -4.01   0.000     -32.55    -42.94  *
...
BOS up                              long  59,205     -9.46   -1.80   0.077      -7.21    -18.76  *
premium + bear BOS                 short  23,205     -9.89   -1.33   0.189      -8.39    -15.58
CHoCH down                          long   4,903     -3.39   -0.39   0.694      -5.45      4.94

28 of 30 tests survive FDR at q < 0.10 — and 0 of them are positive.
```

Full table in `research/smc_events.py` output. Every SMC event, on both sides, loses money, and 28 of
30 do so with formal statistical significance.

**But this table is the wrong test, and it is worth being explicit about why.** Every arm is charged
the same $19 round turn. At n = 100,000 a fair coin with a spread reports t = −5 with total
confidence, and the thing it is confident about is the spread. A table like this is what an
overconfident anomaly hunt looks like: 28 "significant" results, all of them measuring the commission.

## 4. The test that actually asks the question

The right test is the event against **not the event** — the same barrier, the same costs, differenced
out, leaving only the lift. HAC lag set to 120 bars, matching the barrier horizon over which
neighbouring observations overlap.

```
unconditional baseline at this barrier:  long $-18.00   short $-20.00

event                               side       n   lift $      t      q  research  holdout    net $
CHoCH down                          long   4,903   +14.86   2.04  0.236    +10.69   +31.63    -3.14
bull FVG just below (<0.5 ATR)      long  75,840    +9.08   1.95  0.236     +7.65   +14.85    -8.92
BOS up                              long  59,205   +10.72   1.88  0.236    +10.99    +9.23    -7.29
BOS up, fresh (<10 bars)            long 126,509   +10.38   1.77  0.236    +10.23   +10.51    -7.62
premium (>0.75 of range)            long 100,629    +9.25   1.76  0.236     +7.26   +17.04    -8.75
premium + bear BOS                 short  23,205   +10.98   1.55  0.296    +14.81    -4.09    -9.02
bear FVG just above (<0.5 ATR)     short  70,926    +7.32   1.48  0.296     +6.88    +9.51   -12.68
...
premium (>0.75 of range)           short 100,629    -9.25  -1.76  0.236     -7.26   -17.04   -29.25
CHoCH down                         short   4,903   -14.86  -2.04  0.236    -10.69   -31.63   -34.86

0 of 30 lift tests survive FDR at q < 0.10
positive lift, same sign in BOTH halves: 0 that also clear costs
```

Long and short lifts are exact negatives of each other, as they must be under a symmetric barrier —
the table is really 15 tests shown twice, which is a useful internal check that the estimator is
doing what it claims. Even scoring it as 15 tests, the best q is ≈0.12: still nothing.

### What this table does say

**SMC points the right way.** Every trend-continuation event carries a positive lift on the side its
doctrine names: BOS up favours longs by **+$10.72**, and the research/holdout split is **+$10.99 /
+$9.23** — that replicates about as cleanly as anything in this repository. Fresh BOS up: **+$10.23 /
+$10.51**. Bull FVG below: **+$7.65 / +$14.85**. The concepts are not noise. They are just small.

**And they are smaller than the spread.** The largest lift anywhere in the table is $14.86 against a
$19.00 round turn. The **net** column — baseline plus lift — is negative for all 30. There is no
threshold, no filter and no combination in this study that turns a $10 lift into a profitable
1-minute trade at retail futures costs.

**The mean-reversion half of SMC is backwards on this sample.** SMC teaches *sell premium, buy
discount*. On NQ 2022–25:

| doctrine | what the data says |
| --- | --- |
| sell premium (>0.75 of range) | shorting premium is the **worst** lift (−$9.25); *buying* it is +$9.25 |
| buy discount (<0.25 of range) | the weakest signal in the table, lift +$0.85, t=0.16 |
| short after a bearish CHoCH | the largest positive lift in the table is **fading** it, +$14.86 long |

Every rule that says "price is expensive, sell it" loses; every rule that says "it broke up, follow
it" gains. That is a three-year uptrend acting on a mean-reversion rule, and it is the same contamination this
project has now recorded on every strategy family it has tested — which is exactly why the positive
lifts above should not be read as an edge either. They are the same drift wearing a different name,
and they still do not clear costs.

## 5. Conclusions

1. **Break of structure and smart money concepts, specified mechanically and tested honestly on
   292,114 NQ bars, produce no tradeable intraday edge.** Purged-CV AUC 0.508 against a shuffled
   control of 0.502; the one profitable-looking bucket flipped from +$26/trade to −$57 on the locked
   holdout.
2. **Costs are not the excuse.** Widening the barrier six-fold, from 18.2% cost-to-risk down to 3.0%,
   moves nothing across zero.
3. **The concepts carry a real but sub-spread signal.** ~$10 of lift per trade on trend-continuation
   events, replicating across both halves, against a $19 round turn. On a cheaper instrument, a
   cheaper fill, or a larger barrier per trade, that ordering is where an edge would have to come
   from — it is not one here.
4. **The premium/discount rule is inverted on this sample**, and the model agrees: `range_pos` is the
   third-ranked feature, so the booster found it useful and used it *against* doctrine.
5. **A t-statistic on a costed arm is not an anomaly test.** 28 of 30 "significant" results in §3
   evaporate to 0 of 30 in §4. The difference is one line of specification, and it is the difference
   between publishing an edge and publishing a commission schedule.
6. **The model ranked volatility and time-of-day above every SMC concept.** If there is intraday
   structure in NQ worth trading at this frequency, this study says it is in *when* and *how fast*,
   not in *where the last swing broke*.

## 6. Reproduce

```bash
python3 research/smc_ml.py        # model, purged CV, shuffled control, locked holdout
python3 research/smc_events.py    # robustness sweep, event study, lift test
python3 research/test_smc.py     # 18 tests on the feature definitions
```
