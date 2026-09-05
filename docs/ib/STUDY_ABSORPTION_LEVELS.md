# The 50% level + MTF swings + absorption bubbles, combined as a reversal system

`research/absorb/`, `results/absorb/`. NQ 15m primary (the only feed here with true contract
volume), US100 / US30 15m as cross-market with the tick-volume caveat attached. Real MNQ costs:
0.86 points a side (0.50 in the fill price, 0.36 as cash), 1.72 round turn.

## Verdict

**The combined rule has no edge, both of its filters subtract, and everything that looks
profitable in it is the trailing stop — which earns the same on a coin-flip entry.**

As specified (50% midline + 1H/4H swings, absorption required, 1.5 ATR stop, 1.0/1.0 ATR trail):

| block | n | %/trade | PF | win% | $ 1 MNQ | random entry, same exits | p |
|---|---|---|---|---|---|---|---|
| research | 1,888 | −0.0070 | 0.920 | 53.4% | −4,771 | −0.0016 (PF 0.981) | 0.865 |
| locked | 1,032 | −0.0251 | 0.778 | 55.5% | −10,415 | +0.0013 (PF 1.013) | 0.990 |

It loses on both blocks and is beaten by a random entry with the identical geometry on both.

## The components were measured before the backtest

Truncation audit: 25 probe bars × 12 constructed columns, **0 leaking columns**.

**The published absorption threshold is nearly unconditional.** `scaledVol = volume /
stdev(volume,100) >= 0.1` passes **78.7%** of all bars — the A–E buckets in the source only change
the *dot size*. The selective part is the wick geometry: the bar's midpoint inside the upper wick
(selling absorption) is 15.0% of bars, inside the lower wick (buying) 17.5%. The full published
bubble is 11.3% / 13.4%.

**Absorption is not simply the level touch restated**, which is the failure mode four prior
studies here found for RSI, Aroon, MACD and MFI on a breakout. Its lift on level-touch bars runs
**1.15× (midline) to 1.55× (1H swings)**, so it does carry independent selection. It just does not
carry *profitable* selection — see the drop-one below.

## Reading the grid by its marginals

211 scorable cells (levels × absorption threshold × side × trail × stop), research block, 49.8%
net-profitable, median −0.0003 %/trade.

| axis | marginal average |
|---|---|
| side | long **+0.3130** (PF 2.22) / short **−0.1065** (PF 0.54) |
| trail | off +0.1917 (n~108) / on −0.0024 (n~619) |
| levels | mid only +0.1361 / all six +0.0914 / swings +0.0722 |
| stop | 1.0 / 1.5 / 2.5 all ≈ +0.09 (flat) |

Two of those are traps and are recorded as such. **The long/short split is drift** — NQ rose 89%
over this sample, and the top eight cells of the grid are almost all long-only with 3–8% win
rates, i.e. positions held until stopped in a rising market. **And the "trail off" marginal is
degenerate**: the submitted design has *only* a stop and a trail, so removing the trail leaves no
profit-taking exit at all — those cells hold to the stop, 110 trades at a 1.8% win rate and a
20-bar median. That marginal is not evidence against the trail; it is an artifact of the ablation.
Given a real exit instead, every no-trail arm is *worse* than the trail (targets 0.5–3.0 ATR:
−0.0118 to −0.0195; max holds 4–96 bars: −0.0223 to +0.0051).

## The trail is the whole result, and a coin flip gets it too

Tightening the trail improves every statistic monotonically, and the win rate rises exactly as the
geometry demands rather than as a signal would produce:

| trail (arm/offset ATR) | n | %/trade | PF | win% | median hold |
|---|---|---|---|---|---|
| 0.25 / 0.25 | 2,515 | +0.0237 | **1.751** | 75.2% | 1 bar |
| 0.5 / 0.5 | 2,268 | +0.0034 | 1.061 | 65.0% | 1 bar |
| 1.0 / 1.0 (as asked) | 1,888 | −0.0070 | 0.920 | 53.4% | 3 bars |
| 2.0 / 2.0 | 1,366 | −0.0101 | 0.923 | 36.8% | 6 bars |

The 0.25/0.25 cell is the one worth attacking, because PF 1.75 at a 75% win rate is what a reader
would ship. **A random entry with the same trail earns PF 1.617 at a 73.7% win rate** — the rule
clears it on research at p 0.045 and then, on the locked block, **the random entry wins**
(rule +0.0281 / PF 1.684 against random +0.0296 / PF 1.787, p 0.610). One research pass that
inverts out of sample.

**And roughly half of that cell is an intrabar tie-break.** A 0.25 ATR trail on NQ 15m is 5.7
points, against bars whose stop and trail routinely fall inside one bar. Switching the convention
from Pine's open→nearer-extreme→farther path to stop-first moves it **+0.0237 → +0.0129** (PF
1.751 → 1.329) — the assumption is worth +0.0108 %/trade, 46% of the result. `CLAUDE.md`'s
standing rule that any sub-0.5 ATR barrier result is set by the tie-break rather than by the
market, reproduced on a trailing stop.

## Drop-one: both filters subtract

At the 0.5/0.5 geometry, research block:

| variant | n | %/trade | PF |
|---|---|---|---|
| full rule (levels + absorption) | 2,268 | +0.0034 | 1.061 |
| **− absorption** | 5,052 | **+0.0096** | **1.181** |
| **− levels (absorption alone)** | 5,502 | **+0.0088** | 1.159 |
| midline only | 1,341 | +0.0064 | 1.116 |
| swings only | 1,380 | +0.0018 | 1.031 |
| longs only | 1,392 | +0.0099 | 1.191 |
| shorts only | 1,188 | +0.0002 | 1.003 |
| zero cost | 2,280 | +0.0143 | 1.279 |
| 2× cost | 2,267 | −0.0065 | 0.893 |

Removing either filter *improves* the result on more than twice the trades. The conjunction the
brief asks for — a level **and** absorption — is worse than either half. Raising the absorption
threshold to 2.0 or 4.0 lifts PF to 1.32/1.37 on 445 and 88 trades, which is restrictiveness
alone: the same effect `STUDY_V12` recorded, and it never clears a same-selectivity control
(p 0.970 at the shipped rung).

Cross-market, same rule unchanged, tight trail: US100 PF 0.987 / 1.132, US30 PF 1.056 / 1.202 —
the same mild positive the tight trail produces everywhere, on feeds whose volume is a tick proxy
so their absorption is a proxy of a proxy.

## What this adds

Fifth strategy on this branch whose apparent result is its exit geometry rather than its entry,
and the second in two studies where a trailing stop decided the whole outcome — but note the sign
is **opposite** to `STUDY_EMA48_VWAP_DL`, where the trail was destructive at every setting. Here
the trail is the only thing making money, and it makes it on a random entry too. Both readings
have the same root: a trailing stop is a take-profit wearing a stop's name, and its distance
relative to the bar's own range decides the win rate before any signal is consulted.
