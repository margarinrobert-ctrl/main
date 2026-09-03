# STUDY_VWAP_DRIFT — RTH VWAP Drift EVO 1, tested on four markets

`RTHVWAPDriftEVO1` is a Sierra Chart ACSIL study. Its name says drift; the code says **trend
continuation on a VWAP pullback**, and that is what was tested.

**The rule, read out of the source.** On 1-minute bars a VWAP accumulates from the 09:30 RTH open as
`cum(close × volume) / cum(volume)` — close times volume, not typical price — and resets each
session. An efficiency ratio runs on 1-minute closes, `|C[i] − C[i−30]| / Σ|C[j] − C[j−1]|`, resets at
the 18:00 ETH boundary and passes through an Ehlers super smoother of period 10. 15-minute buckets
are anchored to the RTH open, and at every completed bucket:

- **LONG** the previous bucket closed **above** VWAP, this bucket's **low touched** VWAP, this bucket
  **closed back above** it, VWAP is **rising**, the close is at least **0.10%** above its close three
  buckets ago, and **ER > 0.30**. **SHORT** is the mirror.
- **ENTRY** the bucket's close. **STOP** the bucket's low (long) or high (short), on the tick grid.
  **TARGET** entry ± 2 × risk.
- Entries 09:45–13:45, flat 15:55, at most 4 trades and 2 losses a day, one position at a time.

Engine `research/vwapdrift/vd_core.py`, battery `vd_run.py`, output `results/vwapdrift/`. Feeds and
blocks as elsewhere on this branch: NQ 1-minute (research = the first 65% of sessions), US100 and
US30 15-minute 2016–2025 (research < 2022, validation 2022–23, test 2024+), US30_ISO 2024–2026.

## 1. Read the win rate against 33.3%, not against 50%

The stop is the bucket extreme and the target is 2 × risk, so the driftless break-even win rate is
1/(1+2) = **33.3%** before costs. Every win rate below is one to two points above that line.

| feed | block | n | win | PF | mean R | Sharpe |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| NQ 1m | research | 69 | 31.9% | 0.48 | −0.35 | −1.65 |
| NQ 1m | locked | 43 | 41.9% | 1.69 | +0.05 | +0.94 |
| NQ 1m | all | 112 | 35.7% | **1.00** | −0.19 | −0.01 |
| US100 15m | research / validation / test | 1178 / 538 / 438 | 39.0 / 36.4 / 37.4% | 1.06 / 0.99 / 0.96 | −0.01 / −0.02 / +0.02 | +0.29 / −0.09 / −0.26 |
| US30 15m | research / validation / test | 973 / 445 / 324 | 36.1 / 34.4 / 42.0% | 0.88 / 0.90 / 1.29 | −0.07 / −0.08 / +0.14 | −0.66 / −0.59 / +1.43 |
| US30_ISO 15m | research / locked | 323 / 146 | 43.3 / 37.0% | 1.44 / 0.81 | +0.16 / +0.02 | +2.22 / −1.34 |

**Pooled over four feeds: 4,477 trades, −0.0095 R, P(mean ≤ 0) = 0.69.** A coin flip.

On its own native resolution the strategy takes **112 trades in three years** and finishes at profit
factor 1.00. Its research block is the worst of the two (PF 0.48) and its locked block the better
(1.69) — the wrong shape, on 43 trades.

## 2. The efficiency ratio is resolution-dependent, and that changes the strategy

`raw ER = |C[i] − C[i−n]| / Σ|C[j] − C[j−1]|` with n = 30 **minutes** ÷ the bar size. At one minute
that is 30 price points and 30 zig-zags in the denominator; at fifteen it is **two**, so the
denominator can barely exceed the numerator and the ratio saturates.

| feed | bars in the ER window | median ER | share above the 0.30 floor | signals |
| --- | ---: | ---: | ---: | ---: |
| NQ 1m | 30 | 0.154 | **18.7%** | 162 |
| NQ 5m | 6 | 0.383 | 65.5% | 623 |
| NQ 15m | 2 | 0.742 | **99.0%** | 1,057 |

Same code, same instrument, same three years: **162 signals at one minute against 1,057 at fifteen.**
The ER floor removes four signals in five at the resolution the study is written for and one in a
hundred at the resolution a 15-minute feed can offer. Every CFD number in this study is therefore a
materially **looser** strategy, not a coarser view of the same one, and the anatomy confirms it —
turning the ER filter off changes US100's research count by 8 trades in 1,178.

## 3. The direction call is real and is worth less than the round turn

| feed / block | rule | coin-flip side, same bars | p | direction inverted |
| --- | ---: | ---: | ---: | ---: |
| US100 research / validation / test | −0.01 / −0.02 / +0.02 | −0.23 / −0.13 / −0.14 | **0.000** / 0.000 / 0.000 | −0.43 / −0.22 / −0.30 |
| US30 research / validation / test | −0.07 / −0.08 / +0.14 | −0.21 / −0.16 / −0.10 | **0.000** on all three | −0.33 / −0.25 / −0.32 |
| US30_ISO research / locked | +0.16 / +0.02 | −0.07 / −0.16 | 0.000 / 0.000 | −0.38 / −0.38 |
| NQ 1m research / locked | −0.35 / +0.05 | −0.28 / +0.03 | 0.700 / 0.450 | −0.18 / −0.13 |

On every 15-minute block the rule beats a coin flip on the same bars at p 0.000, and inverting it
loses 0.2 to 0.4 R a trade. The pattern genuinely knows which way to lean. **It is simply not worth
the cost of trading it**: pooled at zero cost the same 4,477 trades earn **+0.079 R**, at the real
round turn **−0.010 R**, at twice it **−0.085 R**. The entire result sits inside the spread.

On NQ 1-minute — the only faithful resolution — even the direction call fails its control (p 0.700
research, 0.450 locked) on 112 trades.

## 4. Anatomy: the headline filter is inert or harmful

| variant | NQ 1m research / locked | US100 research / validation / test |
| --- | ---: | ---: |
| as written | −0.35 / +0.05 (n 69/43) | −0.01 / −0.02 / +0.02 |
| efficiency-ratio filter OFF | −0.18 / −0.04 (n 369/202) | −0.01 / −0.02 / +0.03 (n 1186) |
| VWAP-slope filter OFF | −0.36 / +0.10 (n 70/44) | unchanged (n 1179) |
| drift filter OFF | −0.28 / −0.05 (n 112/60) | −0.08 / −0.01 / −0.06 |
| VWAP-touch requirement OFF | −0.01 / +0.09 (n 596/324) | −0.08 / −0.01 / +0.01 |
| all four OFF | −0.07 / −0.06 (n 1190/649) | −0.12 / −0.02 / −0.03 |
| zero cost | −0.30 / +0.10 | **+0.12** / +0.04 / +0.08 |

- **The VWAP slope filter is inert.** It removes one signal in 1,178 on US100 and none on NQ. A VWAP
  that has moved in the trade's direction over one 15-minute bucket is nearly always true when price
  has just drifted 0.1% that way.
- **The ER filter is inert at 15 minutes and harmful at one.** The grid's marginal average on NQ runs
  −0.10 R at no floor, −0.17 at 0.20, −0.20 at 0.30 and **−0.30 at 0.40**: the tighter the strategy's
  own headline regime filter, the worse it does.
- **The VWAP touch is the only condition that selects anything on NQ** (69 trades against 596 without
  it) and removing it *improves* the research block (−0.35 → −0.01).
- The daily caps never bind on NQ (0 blocked) and the target ladder is flat from 1R to 4R.

## 5. Parameter grid: the surface does not transfer

2,880 cells per feed over the ER floor, drift threshold and lookback, slope lookback, target multiple
and stop multiple.

| feed | profitable on the first block | on the last | rank transfer (Spearman) |
| --- | ---: | ---: | ---: |
| NQ 1m | **5%** | 89% | +0.374 |
| US100 | 65% | 23% | +0.201 (research → test) |
| US30 | 14% | 48% | **−0.115** (research → test) |
| US30_ISO | 83% | **6%** | −0.024 |

Two feeds have a profitable research block and an unprofitable reserved one; the other two have it
the other way round. A surface whose sign flips between blocks on every feed, in both directions, is
noise.

## 6. The backtest's own fill is one it cannot reach

The study evaluates a bucket on the bar that **starts the next one**, then books the entry at that
bucket's **close** — a price that has already passed when the signal comes into existence — and its
exit scan skips the following bar as well. Filling instead at the open of the bar the signal actually
fires on:

| feed | as written | implementable | gap |
| --- | ---: | ---: | ---: |
| NQ 1m | −0.193 R | −0.226 R | **−0.033** |
| NQ 15m | −0.036 | −0.124 | −0.088 |
| US100 15m | −0.007 | −0.073 | −0.066 |
| US30 15m | −0.035 | −0.088 | −0.052 |
| US30_ISO 15m | +0.120 | +0.027 | −0.093 |

The source's own model is optimistic by 0.03 to 0.09 R a trade on **every** feed. That is between
three and nine times the pooled edge, which is −0.01 R.

## 7. Verdict

**It does not have an edge, and the reason is precise.** The pattern's direction call is real: on
every 15-minute block it beats a coin flip on its own bars at p 0.000 and inverting it loses 0.2 to
0.4 R. But gross it is worth +0.079 R a trade and the round turn is worth about 0.089 R, so the net
is −0.010 R over 4,477 trades at P(mean ≤ 0) = 0.69. Three separate things then push it further under:

1. **The efficiency-ratio filter, its headline regime condition, is inert at 15 minutes (99.0% pass)
   and monotonically harmful at one minute** — the resolution it is written for, where it costs four
   signals in five and the grid marginal falls from −0.10 to −0.30 R as the floor rises.
2. **The VWAP-slope filter is inert everywhere**, removing one signal in a thousand.
3. **The recorded entry is a price the signal cannot reach**, worth 0.03 to 0.09 R a trade against a
   pooled edge of −0.01.

What survives as a fact worth keeping: a bucket that pulls back to a rising session VWAP and closes
back above it does continue more often than not. It is a genuine directional signal that a 2R barrier
pair and a retail round turn cannot monetise on any of these four feeds.

**No entry in `EDGE_LIBRARY.md`.** The bar is a mechanism that clears a matched control on a block it
was not selected on **and** pays for itself; this clears the first and fails the second. What would
change the verdict is a cost structure roughly a tenth of the one assumed here, or a target far enough
out to make the round turn small against it — and §4 shows the target ladder is flat from 1R to 4R,
so the second route is already closed.
