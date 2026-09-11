# RSI and Stochastic bullish divergence, plus volume-spike confirmation — for longs

`research/turtlefeat/divergence.py`. Tested as a confirmation gate on the intraday long label:
1:1 at a 1.0×ATR stop, 09:30–12:00 New York, resolved trades only, ≥60 minutes of session left.

## The leak this module exists to avoid, and the one it caught in my own code

A pivot low at bar *i* is defined by the bars on **both** sides of it — `l[i]` must be the lowest of
`l[i-k .. i+k]`. That is not knowable at *i*; it is knowable at *i+k*. Virtually every published
divergence indicator marks the signal at the pivot, which back-tests beautifully and cannot be
traded: by the time the marker appears, the move it "predicted" has already happened. Here a pivot
becomes visible only at `pivot + confirm`, and a divergence only when its **second** pivot confirms.

The truncation audit then caught a second, subtler leak **in this file's own first version**. The
`bars since divergence` feature filled forward as far as the *next* pivot's confirmation bar — so
bar *t* knew when a future pivot would confirm. Measured: `rsi_div_since` read **+37 on the full
series against +999 on history truncated at the same bar**. Replaced with a plain forward scan.
After the fix: **144 checks, 0 mismatches.**

Firing rates on NQ 15m: RSI divergence 1.05% of bars, Stochastic 1.19%, volume spike ≥1.5× the
time-of-day baseline 12.63%, ≥2.0× 5.32%.

## The result

Base rate: **47.27%** research, **46.45%** out of sample. Break-even at 1:1 is **58.36%**.

| gate | n research | win research | n OOS | win OOS | lift OOS |
| --- | ---: | ---: | ---: | ---: | ---: |
| RSI divergence, last 20 bars | 731 | 49.38% | 399 | 47.12% | +0.67 |
| Stochastic divergence, last 20 bars | 765 | 47.45% | 339 | 47.49% | +1.04 |
| RSI **and** Stochastic divergence | 503 | 49.90% | 230 | 47.83% | +1.38 |
| volume spike ≥1.5× | 145 | 45.52% | 75 | 44.00% | **−2.45** |
| volume spike ≥2.0× | 18 | 44.44% | 7 | 28.57% | **−17.88** |
| RSI div + spike | 38 | 42.11% | 18 | 50.00% | +3.55 |
| Stoch div + spike | 41 | 43.90% | 11 | 72.73% | +26.28 |
| RSI div + spike + above channel mid | 9 | 55.56% | 4 | 75.00% | +28.55 |
| RSI div + spike + 20-bar breakout | 9 | 55.56% | 3 | **100.00%** | +53.55 |

**The bottom three rows are noise, and the interval says so.** Clopper-Pearson 95% intervals:

| gate | n | wins | rate | 95% CI | p vs base |
| --- | ---: | ---: | ---: | --- | ---: |
| RSI div + spike + 20-bar breakout | 3 | 3 | 100.0% | **[29.2%, 100.0%]** | 0.100 |
| RSI div + spike + above channel mid | 4 | 3 | 75.0% | [19.4%, 99.4%] | 0.261 |
| Stoch div + spike | 11 | 8 | 72.7% | [39.0%, 94.0%] | 0.074 |
| RSI div + Stoch div | 230 | 110 | 47.8% | [41.2%, 54.5%] | 0.362 |
| RSI divergence alone | 399 | 188 | 47.1% | [42.1%, 52.1%] | 0.414 |

**A 100% win rate on three trades has a lower bound of 29.2%** — consistent with a rule that loses
two thirds of the time. Nine gates were tested; at nine tests one p below 0.10 is expected by
chance, and exactly one appeared.

## What actually holds

**Divergence is worth about one point.** Every gate with a usable sample delivers +0.7 to +1.4
points out of sample, against the **+11.9** needed to reach break-even. It is real-ish and far too
small.

**RSI versus Stochastic: a tie.** RSI is better in-sample (49.38% vs 47.45%), Stochastic better out
of sample (47.49% vs 47.12%). The difference is inside the noise, and the flip across blocks is
what a difference inside the noise looks like. Neither "works better".

**Volume spikes are NEGATIVE for longs here**, and monotonically so: −2.45 points at 1.5× the
time-of-day baseline, −17.88 at 2.0×. That is the opposite of the folklore that a breakout wants
volume behind it, and it is consistent with this branch's repeated finding that trend continuation
is anti-predictive on this data — a volume spike marks the point of maximum participation, which is
where a short-horizon move is most likely to be over.

**Combining them makes the sample too small to say anything**, which is the real reason the stacked
gates look spectacular. Three filters at 1%, 1% and 13% firing rates leave 3 trades.

## Verdict

Confirmation entries do not close the gap. The best honest cell is RSI + Stochastic divergence
together at **+1.4 points out of sample**, on 230 trades, p 0.362 — indistinguishable from base. The
target needs +11.9. And the one filter with a real, repeatable effect points the wrong way: **volume
spikes reduce the probability of a long reaching +1R first.**
