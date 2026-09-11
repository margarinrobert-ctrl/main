# Donchian 30/20 intraday trend, built to brief: profitable on US100, negative on US30

Channel fixed by the brief — entry 30, exit 20. Everything else searched on **US30's train block
(pre-2026) only**: 900 cells over ADX floor, EMA100-distance floor, ATR-expansion floor, stop
multiple and take-profit. Then read once on three held-back sets. Costs charged as **3.7% of the 2N
stop on every market**, the fraction MNQ pays.

Three feeds: US30 (48,937 bars), US100 (46,700), and XAU 15-minute resampled from 20 years of
5-minute data (494,235 bars, 2004→2026, clock verified against its own 08:00–10:00 New York
volatility peak).

## The verdict

| | n | PF | Sharpe | pts/trade | max DD | ret/DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| US30 train *(chosen here)* | 281 | 1.45 | 1.84 | +21.16 | 1,968 | 3.02 |
| **US30 2026 JUDGE** | 169 | **0.92** | **−0.53** | **−5.77** | 3,107 | −0.31 |
| US100 train era | 262 | 1.45 | 2.24 | +15.58 | 1,504 | 2.72 |
| **US100 held back 2026** | 135 | **1.42** | **2.01** | **+20.64** | 1,456 | 1.91 |
| XAU train era | 2,627 | 0.98 | −0.14 | −0.05 | 399 | −0.31 |
| XAU held back | 1,507 | 1.19 | 0.94 | +0.56 | 254 | 3.32 |

**It fails on the instrument it was fitted to and holds on the one that chose nothing.** US100 never
saw a parameter — all of them came from US30 — so its held-back block is a genuine pre-registered
out-of-sample test, and it passed with 6/6 walk-forward folds positive (median PF 1.47) and
bootstrap P(mean ≤ 0) = 0.0095.

## Both controls fail everywhere

| control | US30 train | US100 train | US100 held back | US100 full |
| --- | ---: | ---: | ---: | ---: |
| breakout vs a **random bar**, same stop, same exit, same trade count | p 0.063 | p 0.110 | p 0.293 | p 0.060 |
| ADX ≥ 25 vs a **random filter of the same selectivity** | p 0.135 | p 0.249 | p 0.580 | p 0.320 |

On the US100 held-back block a random filter of equal size earned **more** than ADX ≥ 25 (+22.44
against +20.64). The system is consistently profitable and the *trigger is not why*. What earns is
the exit geometry — 2.0×ATR(20) stop, 20-bar channel exit, one unit, no target — on a long-biased
index. The Donchian spaces the trades out and keeps it a Turtle. That is worth saying plainly.

Contrast `STUDY_V11_MARKET`: on NQ, Donchian **55** with the same ADX ≥ 25 and no target passed both
gates at p 0.007 / 0.016. Same family, longer channel, different instrument — and there the trigger
did carry information. The 30 does not.

## What the 900-cell search found

Read by **marginal average per axis**, never by top cell — a top cell is the maximum of 900 draws.

| axis | marginal Sharpe |
| --- | --- |
| ADX | 0: +0.71 · 15: +0.69 · 20: +0.72 · **25: +1.62** · 30: +1.18 |
| EMA100 distance | **none: +1.10** · ≥0.5: +0.91 · ≥1.0: +1.00 · ≥1.5: +0.87 |
| ATR expansion | none: +0.99 · ≥1.0: +0.73 · ≥1.2: +1.24 |
| stop (no TP) | 0.75N: 1.38 PF · 1.5N: 1.38 · 1.75N: 1.43 · **2.0N: 1.45** · 2.5N: 1.35 |
| take profit | flat across none / 2R / 3R |

- **ADX ≥ 25 is the only filter that survived selection** — a clear step, and the identical step
  appears independently on NQ. It is *also* the thing that inverts out of sample: US30 2026 goes
  ungated 1.04 → ADX≥20 0.94 → ADX≥25 0.92. The filter that built the train result is what breaks it.
- **An EMA100-distance filter hurts.** Not included.
- **The ATR-expansion filter is not real.** It looks strong — PF 1.42 → 1.77 as the floor rises —
  and fails a same-selectivity random filter at p 0.117–0.454. *That is what any restrictive filter
  does.* Not included. This is the trap this repository has a standing rule against, and it was
  caught by running the rule rather than admiring the number.
- **No take profit** beat every target, for the third independent time on this branch.
- **One unit.** The ladder generates drawdown, not return.

## The intraday window is a cost, not a feature

Against random same-size subsets of the all-hours trades, on US30 train:

| window (NY) | n | PF | pts/trade | p vs control |
| --- | ---: | ---: | ---: | ---: |
| all hours | 281 | 1.45 | **+21.16** | — |
| 07:00–10:00 | 111 | 1.02 | +0.89 | 0.898 |
| 07:00–11:00 | 165 | 0.98 | −1.10 | 0.985 |
| 09:00–12:00 | 157 | 1.32 | +14.45 | 0.700 |
| 09:30–16:00 | 192 | 1.16 | +8.66 | 0.913 |
| 08:00–20:00 | 235 | 1.29 | +15.16 | 0.854 |

**Every window fails, and every window loses money against all hours.** 08:00–20:00 costs the least
(ret/DD 2.73 against 3.02) and is the sane choice if you must be flat by the close. This is the
eleventh independent time the intraday constraint has come out negative on this branch.

## Robustness (US100, full span)

Perturbation: stop 1.5N/2.5N → PF 1.46/1.42; ADX 22/28 → 1.35/1.60; Donchian 25/35 → 1.45/1.40;
exit channel 25 → 1.43. **The one sensitive parameter is the exit channel at 15 (−0.21).**
Monte Carlo, 20,000 shuffles: realised drawdown 1,504 against a median of 1,481 and p95 2,337 —
neutral, so size for the p99 of 2,836. Walk-forward 6/6 positive, median PF 1.47.

## Shipped

`pine/turtle/V12_DONCHIAN_3020_strategy.pine`, parity-checked against the engine on US100:
89% signal match, profit factor within 0.03, per-trade correlation 0.93–0.9998. Run it on
US100 / NAS100 / MNQ. **Do not run it on US30 on the strength of the train column.**
