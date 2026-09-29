# V17 — 21 engineered features on the best base, and the one that survived

**The pool was null and one condition replicated anyway.** 285 conditions, 16 beat their control at
p ≤ 0.05 against 14.2 expected by chance. One was carried on the shape of its gradient rather than
its rank, and out of sample it took the strategy's profit factor from 1.31 to 1.78 and its Sharpe
from 1.05 to 1.55.

---

## 1. The base, established rather than inherited

Two candidates had a claim, and they are not the same claim: **V16** (Donchian 30/20, 30m) is the
most block-stable thing on this branch but fails its matched control; **V11** (Donchian 55,
ADX ≥ 25, 2.5 × ATR(20), 20-bar exit, no take profit) was the first breakout here to beat one. Both
were re-measured under one cost model, one block split and one position lock:

| candidate | tf | research R/trade | PF | Sharpe | locked R/trade | PF | Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **V11 don55/20 2.5N adx25** | **15m** | **+0.1680** | **1.328** | **1.08** | **+0.1356** | **1.308** | **1.05** |
| V11 don55/20 2.5N, no adx | 15m | +0.0574 | 1.101 | 0.52 | +0.1091 | 1.205 | 0.95 |
| V16 don30/20 2.0N | 15m | +0.0192 | 1.030 | 0.17 | +0.1186 | 1.206 | 1.05 |
| V16 don30/20 2.0N | 30m | +0.1126 | 1.193 | 0.80 | +0.1033 | 1.188 | 0.80 |
| V11 don55/20 2.5N adx25 | 30m | +0.0787 | 1.171 | 0.46 | +0.0502 | 1.127 | 0.38 |

V11 at 15 minutes wins on both blocks and is the only one whose research block is *better* than its
locked block while both are strong — the right shape. **ADX ≥ 25 reproduces independently** as the
thing that earns it (+0.0574 → +0.1680 research, +0.1091 → +0.1356 locked).

**Sharpe is computed over every trading day in the block, zero-filled on days that did not trade.**
This is the single most consequential choice in the study. Over traded days only, a filter is *paid*
for trading less — keep twelve days a year and the ratio explodes while the account earns nothing.
Zero-filling forces a filter to earn its selectivity.

---

## 2. The features, and the constraint that shaped them

V16 established that momentum cannot help a breakout, because a breakout *is* a momentum event and
95% of breakout bars already pass an RSI filter. So every feature here had to describe something the
breakout does **not** already say:

| family | features | what it encodes |
| --- | --- | --- |
| A breakout anatomy | 7 | penetration depth, close position in bar, bar size, body, gap, relative volume |
| B channel geometry | 5 | channel width vs ATR, its own percentile, staleness of the level, channel-top slope |
| C higher timeframe | 10 | causal daily trend states, distance from the last session's high/close, position in its range |
| D volatility regime | 5 | ATR vs its mean, ATR percentile, vol-of-vol, short/long vol ratio, Parkinson vs close-to-close |
| E path structure | 4 | efficiency ratio, up-bar fraction, semivariance asymmetry, drawdown from the 20-bar high |

**Every feature is tested in both directions.** On this branch two shipped filters turned out to
point the wrong way at 15 minutes, and the only reason that was found is that the reverse was
tested. Both directions are counted in the multiplicity: 21 features × 6 levels × 2 directions =
252 conditions, 328 with the daily binaries, 285 scorable at ≥ 30 trades.

**Three duplicate pairs were found inside the pool** and are reported rather than double-counted:
`C_pos_pdr ≥ 1` **is** `C_dist_pdh ≥ 0`; `C_D_ema_gap ≥ 0` **is** `C_D_ema20_50`;
`C_D_dist_ema200 ≥ 0` **is** `C_D_above200`. That is the second time an engineered pool here has
turned out to contain the same condition twice.

---

## 3. The family result: nothing

| | |
| --- | --- |
| scorable conditions | 285 |
| beat a same-selectivity control on **Sharpe** at p ≤ 0.05 | **16** (14.2 expected) |
| beat it on **net R** | **7** (14.2 expected) |

By family, pass rates were 8.0% (anatomy), 7.0% (volatility), 5.8% (higher timeframe), 2.5% (path),
2.3% (channel geometry) — against 5% by construction. **This is a null pool.** Everything below is
read against that.

---

## 4. The one condition, carried on shape

`C_dist_pdh` — how far the signal bar's close sits above the **last completed 09:30–16:00 New York
session's high**, in ATR — is the only feature whose entire ladder is sign-consistent in both
directions on research:

| level | ≤ level (R/trade) | ≥ level (R/trade) |
| --- | --- | --- |
| −2.0N | −0.103 | +0.176 |
| −0.5N | −0.060 | +0.233 |
| 0.0 | −0.046 | **+0.265** |
| +0.5N | −0.040 | +0.251 |
| +1.5N | +0.035 | +0.364 |

Every rung of one side loses and every rung of the other wins. That is a gradient, not a cell.
**The level shipped is 0, not the +1.5N that scores best** — zero is the boundary the feature
already has, costs no parameter, and keeps 49 more trades.

### It survived the holdout, and so did the gradient

| block | filter | trades | net R | R/trade | PF | win% | Sharpe | maxDD | R/DD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| research | off | 333 | +55.9 | +0.1680 | 1.328 | 38.14% | 1.08 | 16.4R | 3.41 |
| research | **on** | 238 | +63.0 | +0.2649 | 1.566 | 42.02% | 1.38 | 11.6R | 5.46 |
| LOCKED | off | 174 | +23.6 | +0.1356 | 1.308 | 37.93% | 1.05 | 14.3R | 1.65 |
| **LOCKED** | **on** | 129 | **+41.2** | **+0.3191** | **1.780** | 43.41% | **1.55** | **9.0R** | 4.56 |

Locked gradient — the part a lucky cell cannot fake:

| level | ≤ level | ≥ level |
| --- | --- | --- |
| −2.0N | −0.153 | +0.199 |
| −0.5N | +0.050 | +0.195 |
| 0.0 | +0.017 | **+0.319** |
| +0.5N | +0.057 | +0.295 |
| +1.5N | +0.166 | +0.244 |

### And it is what makes the strategy clear its control

Random entries with the same side, geometry and minute-of-day mix, 2,000 draws:

| | research | LOCKED |
| --- | --- | --- |
| base only | p = 0.0135 | **p = 0.2130** |
| + the filter | p = 0.0055 | **p = 0.0140** (×2 = 0.0280 for two conditions read) |

The base does **not** clear its control out of sample; the filtered version does. Bootstrap on the
locked daily series: **P(mean daily R ≤ 0) = 0.0234**. Drop a random 10% of days: locked Sharpe p5
1.18, median 1.57.

**The honest ceiling.** 285 conditions were searched on research, so Bonferroni over the whole
search puts 0.014 × 285 well past 1. The p-value is not the evidence. The evidence is that the
*gradient*, not just the cell, reproduced on a block it was not chosen on — and that is one
replication, not a settled result.

### It is a LEVEL, not a trend, and specifically the HIGH

All in the same pool with the same controls:

| condition | trades | R/trade | PF | Sharpe | p |
| --- | --- | --- | --- | --- | --- |
| close ≥ last session **high** | 238 | +0.2649 | 1.566 | 1.38 | **0.0067** |
| close ≥ last session **close** | 322 | +0.1809 | 1.354 | 1.13 | 0.1500 |
| daily ADX ≥ 15 | 301 | +0.1850 | 1.367 | 1.12 | 0.2267 |
| daily close > EMA200 | 327 | +0.1530 | 1.297 | 0.99 | 0.9900 |
| daily EMA20 > EMA50 | 277 | +0.1372 | 1.265 | 0.81 | 0.9933 |
| daily uptrend **and** daily ADX > 20 | 176 | +0.1771 | 1.337 | 0.75 | 0.9467 |
| daily +DI > −DI | 234 | +0.1028 | 1.199 | 0.56 | 1.0000 |

The daily trend, in every form tested, does nothing. The prior session's *close* does nothing. Only
the *high* works. The reading is that a 55-bar channel break on 15 minutes and a break of the last
session's high are two different levels agreeing, and the trade is worth taking when they do.

---

## 5. The runner-up, which ships off

`close − channel ≤ 0.1 × ATR` — the rule against chasing a break that has already run — had four
consecutive rungs at p 0.003–0.037 on research with the opposite direction uniformly worse, which
is enough shape to spend a holdout read on.

| block | trades | R/trade | PF | Sharpe | control p |
| --- | --- | --- | --- | --- | --- |
| research | 293 | +0.2544 | 1.536 | 1.48 | 0.0005 |
| LOCKED | 155 | +0.1522 | 1.374 | 1.20 | **0.1725** |

It failed. It is an input, defaulting off. Turning it on *with* the shipped filter produces the best
numbers in the study — locked 109 trades, +0.3961 R/trade, PF 2.068, Sharpe 1.71, control p 0.0040
— but its solo read failed, so its marginal contribution is not established and 109 trades is thin.
That combination is a measurement, not a recommendation.

---

## 6. Parity

Two things had to match. The **feature**: the session-high series the script accumulates on its own
bars is **identical to the tick** to the research construction (1-minute aggregation mapped to the
last session closing strictly earlier), and the condition agrees on **100.0000%** of bars. A leakage
assertion is part of the harness — zero bars map to a session that had not closed. The **order
model** then matches the engine at 100% signal match, 100% exit-bar match and correlation 1.0000,
filter on and off, both blocks.

`request.security` on a daily bar would **not** have worked: it returns the 24-hour futures high,
which is a different number from the 09:30–16:00 session high the research uses.

## Files

`research/v17/v17base.py` (which base, and why) · `v17feat.py` (the 21 features, both directions) ·
`v17run.py` (the 285-condition sweep, Sharpe on all days, same-selectivity null) · `v17judge.py`
(ladders, the locked read, controls, stability) · `v17_parity.py` ·
`pine/turtle/V17_PDH_BREAKOUT_strategy.pine`.
