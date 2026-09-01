# V60 — the complete quant test on the V41 stack, with the Aroon oscillator

**The brief.** Take the shipped V41 strategy (EMA cross → Donchian breakout confirmation, an
ADX/CHOP regime gate, an ATR stop), add the **Aroon oscillator**, and run a full quant workup:
correlation matrices, out-of-sample, Monte Carlo, robustness, a hundred thousand combinations,
and a vectorbt cross-check — to find the best mean performance and to say **which indicators help
and which do not.**

**The answer, in one line.** *The Aroon oscillator cannot filter a Donchian breakout, because a
Donchian breakout **is** an Aroon reading.* Where the Aroon period is no longer than the Donchian
entry length, the breakout bar is by construction the N-bar high, so **Aroon Up = 100 and the
oscillator ≥ 0 on 100.0% of breakout bars — 60,000 bars, three markets, zero exceptions.** The
two rungs a trader would reach for (`osc ≥ 0`, `up ≥ 70`) remove not one signal. The one rung that
does bind (`osc ≥ 50`) makes every locked block worse.

**And the strategy underneath it does not survive either.** The top-of-grid configuration clears a
minute-of-day matched control on two of three markets and decays hard out of sample; its
neighbourhood is **100% profitable on research and 26.6% profitable on NQ's locked block**; and the
research→locked rank correlation across 121,282 NQ configurations is **−0.4426**.

---

## 1. What was run

`research/v60/`. Three markets on **60-minute** bars: **US100L** (51,889 bars), **NQ** (18,243),
**US30L** (49,325). Research is the first 65% of bars, locked the last 35%.

| axis | settings |
| --- | --- |
| EMA condition | **off**, `cross` (breakout within *win* bars of an up-cross), `state` (fast > slow) |
| EMA fast / slow | 8, 13, 21 / 34, 48, 62 |
| confirmation window | 0, 5, 10, 20, 40 bars |
| Donchian entry | 10, 20, 30, 55 |
| Donchian exit channel | 10, 20 |
| stop | 1.5, 2.0, 2.5, 3.0 × ATR(20, **Wilder**) |
| take profit | none, 2.0R, 3.0R |
| regime gate | off, ADX(14) ≥ 20, CHOP(14) ≤ 45 |
| **Aroon period** | 14, 25 |
| **Aroon condition** | off, `osc ≥ 0`, `osc ≥ 50`, `osc ≥ −50`, `up ≥ 70` |

**388,800 nominal cells per market × 3 markets = 1,166,400 configurations evaluated.** Of those,
**142,560 per market are distinct** (427,680 in all): with the EMA condition off, `ema_f`, `ema_s`
and `win` change nothing, and in `state` mode `win` changes nothing, so 246,240 of each market's
cells are duplicates of cells already in the grid. `STUDY_RULE_ANATOMY.md` caught this branch
overstating a configuration count by 24% once; the count published here is the distinct one.

A **cached exit tensor** makes it affordable: a trade's outcome depends only on its **signal bar**
and its **geometry**, never on which indicator fired, so the price is walked once per
(bar, geometry) — 24 walks — and every one of the 142,560 configurations is an array lookup plus a
numba position-lock pass. The whole grid is one walk of the bars.

Everything is read at the **signal** bar; the entry is the **next bar's open**; the entry bar
carries its own stop; a **position lock** is enforced. Sharpe is computed over **every trading day
in the block, zero-filled on days that did not trade** — over traded days only, a filter is paid
for trading less. ATR is **Wilder's** `rma(TR, 20)`, matching the shipped Pine's `ta.atr(20)`
rather than this branch's usual `ema(TR, n)`.

---

## 2. The Aroon–Donchian identity — the finding

Aroon Up(N) is `100 × (bars since the N-bar high has not been exceeded) / N`; it is 100 exactly
when the newest bar of the window is its highest. A Donchian(E) long breakout fires when the close
exceeds the prior E-bar high. **If N ≤ E, a breakout bar is necessarily the N-bar high, so Aroon Up
is 100 and the oscillator (Up − Down) is non-negative — always, by construction.**

`research/v60/v60aroon.py` checks it bar by bar rather than asserting it:

| market | donchian | aroon N | breakout bars | Aroon Up = 100 | osc ≥ 0 | osc ≥ 50 | up ≥ 70 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| US100L | 20 | 14 | 4,114 | **100.0%** | 100.0% | 74.8% | 100.0% |
| US100L | 30 | 25 | 3,407 | **100.0%** | 100.0% | 84.0% | 100.0% |
| US100L | 55 | 25 | 2,759 | **100.0%** | 100.0% | 84.7% | 100.0% |
| NQ | 20 | 14 | 1,370 | **100.0%** | 100.0% | 72.0% | 100.0% |
| NQ | 30 | 25 | 1,093 | **100.0%** | 100.0% | 80.1% | 100.0% |
| NQ | 55 | 25 | 875 | **100.0%** | 100.0% | 80.5% | 100.0% |
| US30L | 20 | 14 | 3,482 | **100.0%** | 100.0% | 76.6% | 100.0% |
| US30L | 30 | 25 | 2,878 | **100.0%** | 100.0% | 86.2% | 100.0% |
| US30L | 55 | 25 | 2,291 | **100.0%** | 100.0% | 88.3% | 100.0% |

Zero exceptions in every cell where N ≤ E. Only `don_e = 10` with `aroon N` of 14 or 25 leaves any
room at all (64–91%), and that is the one corner where the Aroon period is *longer* than the
channel.

Stated as a filter's base rate, which is how `STUDY_V16_MOMENTUM.md` framed the same mechanism for
RSI: on US100L, `aroon25 osc ≥ 0` fires on **54.6% of all bars and 100.0% of breakout bars**;
`up ≥ 70` on 40.8% and **100.0%**. A filter that passes every signal is not a filter.

**This is the third time on this branch that an "extra confirmation" has turned out to be the
trigger restated.** `STUDY_V16_MOMENTUM.md`: 94.7% of breakout bars already pass RSI(14) ≥ 55.
`STUDY_RULE_ANATOMY.md`: eight conditions in the pool were literal duplicates and three pairs were
a theorem. The pattern to internalise is that **a momentum or position indicator computed over a
window no longer than the entry channel is not new information about a breakout — it is the
breakout's definition, rearranged.**

### The correlation matrix says the same thing from the other side

| pair (US100L / NQ / US30L) | ρ |
| --- | --- |
| `ema13>ema48` vs `aroon25 osc ≥ 0` | **+0.583 / +0.571 / +0.595** |
| `aroon25 osc ≥ 0` vs `up ≥ 70` | +0.646 / +0.617 / +0.651 |
| `aroon25 osc ≥ 50` vs `up ≥ 70` | +0.668 / +0.635 / +0.685 |
| `donchian brk 30` vs `aroon25 up ≥ 70` | +0.319 / +0.307 / +0.310 |
| `adx≥20` vs `chop≤45` | +0.210 / +0.195 / +0.198 |

Aroon is **0.57–0.60 correlated with the EMA state it was being added to** — it is a second
reading of the same trend, not a new one. And its own three rungs correlate 0.58–0.69 with each
other: one indicator wearing three hats.

---

## 3. Which settings actually help — the marginal table

Read a grid by its **marginal average per axis**, never by its top row: the top cell is the
maximum of ~140,000 draws. $ per trade, averaged over the whole grid, both blocks, three markets.
**A setting earns its place only by beating `off` (or its baseline) in all six columns.**

| axis | setting | US100 res | US100 lock | NQ res | NQ lock | US30 res | US30 lock | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EMA | off | 9.79 | 22.23 | 38.77 | −28.91 | 64.36 | 62.97 | baseline |
| EMA | **cross** | 26.61 | 31.19 | 44.85 | −23.73 | 90.65 | 12.99 | **5 of 6** |
| EMA | state | 16.09 | 22.30 | 47.76 | −33.44 | 87.95 | 66.81 | 5 of 6 |
| gate | off | 25.16 | 20.83 | 32.58 | −24.62 | 97.93 | 16.74 | baseline |
| gate | ADX ≥ 20 | 24.33 | 31.21 | 56.30 | −33.72 | 88.48 | 11.87 | **2 of 6** |
| gate | CHOP ≤ 45 | 24.25 | 36.65 | 47.50 | −19.44 | 82.78 | 39.69 | 4 of 6 |
| aroon | off | 24.67 | 31.82 | 45.38 | −22.77 | 92.63 | 27.37 | baseline |
| aroon | osc ≥ 0 | 24.42 | 31.65 | 44.31 | −21.85 | 89.87 | 27.31 | 1 of 6 |
| aroon | **osc ≥ 50** | 24.51 | **21.38** | 47.77 | **−41.77** | 88.00 | **7.43** | 1 of 6 |
| aroon | osc ≥ −50 | 24.73 | 31.43 | 44.40 | −24.19 | 89.79 | 28.21 | 2 of 6 |
| aroon | up ≥ 70 | 24.61 | 32.40 | 44.59 | −18.07 | 89.80 | 25.49 | 2 of 6 |
| aroon N | off | 24.67 | 31.82 | 45.38 | −22.77 | 92.63 | 27.37 | best in 4 of 6 |
| take profit | **none** | 32.44 | 32.73 | 56.03 | −32.01 | 103.31 | 34.60 | **best in 5 of 6** |
| take profit | 2.0R | 17.17 | 26.49 | 36.71 | −14.99 | 72.19 | 2.68 | worst in 5 of 6 |
| stop | 1.5N | 18.37 | 27.37 | 38.53 | −8.21 | 75.63 | 28.09 | |
| stop | **3.0N** | 28.95 | 32.06 | 48.33 | −37.13 | 108.23 | 28.36 | best in 4 of 6 |
| exit channel | 20 | 28.38 | 39.97 | 57.51 | −49.08 | 104.18 | 29.18 | best in 5 of 6 |
| donchian entry | 55 | 30.55 | 36.28 | 49.43 | −26.64 | 123.84 | 32.71 | best in 5 of 6 |

**What helps:** the EMA condition (5 of 6, whichever form), **no take profit** (5 of 6), a **wide
stop** (4 of 6), a **long entry channel** and a **long exit channel** (5 of 6).

**What does not:** **Aroon, in every form.** No setting beats `off` in more than 2 of 6 columns,
the differences are ±1 on a base of 25–90, and the one rung that actually removes signals
(`osc ≥ 50`, which drops 14–20% of breakouts) is decisively worse — it costs US100L 10.4 and US30L
20.0 dollars a trade on the locked block and doubles NQ's locked loss.

**And the gate the leading configuration uses is the weaker of the two.** ADX ≥ 20 beats `off` in
only 2 of 6 columns; CHOP ≤ 45 manages 4 of 6. This replicates `STUDY_V12`'s finding that the ADX
filter is "both the only thing that survived selection AND the thing that inverts out of sample".

**The take-profit result is the fifth independent confirmation on this branch that no target beats
every target tested** (V11, V15, V17, V59, and now V60).

**NQ's locked block is negative for every setting on every axis** (−8 to −49). No configuration of
this family makes money on NQ out of sample; the axis choices only decide how much is lost.

---

## 4. The top of the grid, and why it is not the consensus

Ranked on **research only**, by the **worse of the three markets' Sharpe**, so no configuration can
be bought by one index. 132,396 cells are scorable on all three.

Top-1000 consensus shares:

```
entry mechanic  cross 82%   state 18%
confirm window  40 76%   0 18%   20 6%   10 1%
donchian entry  10 48%   20 31%   55 13%   30 8%
regime gate     off 52%   adx>=20 45%   chop<=45 3%
AROON           osc>=-50 29%   off 23%   osc>=0 22%   up>=70 20%   osc>=50 6%
exit channel    10 52%   20 48%
stop            3.0N 41%   2.5N 31%   2.0N 17%   1.5N 10%
take profit     none 56%   3.0R 33%   2.0R 11%
```

**The Aroon axis distributes almost uniformly across its five settings — 20–29% each for the four
that do not bind, and 6% for the one that does.** That is the signature of an inert axis: the top
of the grid is indifferent to it, exactly as the identity in §2 predicts. Compare `confirm window`
(76% on one setting) or `entry mechanic` (82%), which are axes the ranking cares about.

The leading cell is **EMA 21/62 cross, confirmation within 40 bars, Donchian 10 entry / 10 exit,
3.0N stop, no target, ADX ≥ 20, Aroon off.** Note that three of its settings — `don_e 10`,
`don_x 10`, `adx ≥ 20` — are the *marginally worse* choice in §3. The top cell is not the
consensus; it is the maximum of 132,396 draws.

---

## 5. The matched control, as a research gate

The right null for a trend system is **the same trade management with a random entry** — same
exits, stop, target, costs and position lock, entries drawn at random from the eligible pool. On
this branch that null has killed five separate breakout triggers.

| # | configuration | US100L | NQ | US30L |
| --- | --- | --- | --- | --- |
| 1 | 21/62 cross w40, don 10/10, 3.0N, no tp, adx≥20 | +66.02 vs +7.48, **p 0.000** | +78.11 vs +27.32, p 0.062 | +258.52 vs +45.80, **p 0.005** |
| 6 | 21/62 cross w40, don 10/20, 3.0N, 3.0R, adx≥20 | +92.86 vs +3.23, **p 0.000** | +103.06 vs +26.67, **p 0.045** | +328.36 vs +66.96, **p 0.005** |
| 8 | …, aroon osc≥0(14) | +84.29 vs +3.36, **p 0.000** | +113.88 vs +25.91, **p 0.025** | +327.34 vs +60.26, **p 0.010** |

**3 of 12 clear the control on all three markets at p ≤ 0.05.** The market that fails is always
NQ, at p 0.025–0.098 — it is also the smallest sample (73–109 research trades against 176–304).
So the trigger does carry information about *where* to enter on US100L and US30L, on research.
That is the strongest thing in this study, and §6 is what happens to it.

---

## 6. The single locked read

| market | corr(research, locked) | configurations | research median | locked median |
| --- | --- | --- | --- | --- |
| US100L | **+0.3295** | 132,396 | +19.93 | +26.29 |
| NQ | **−0.4426** | 121,282 | +42.28 | **−21.10** |
| US30L | **+0.2024** | 132,396 | +80.04 | +31.74 |

**NQ's rank correlation is −0.44 across 121,282 configurations.** Choosing on research is not
merely uninformative there, it is actively counterproductive: the population median goes from
+42.28 to −21.10 and the ordering inverts. US100L and US30L are weakly positive at +0.33 and +0.20.

The leader, read once:

| market | res n | res $/tr | res PF | lock n | lock $/tr | lock PF |
| --- | --- | --- | --- | --- | --- | --- |
| US100L | 212 | +66.02 | 2.143 | 139 | **+30.27** | 1.250 |
| NQ | 83 | +78.11 | 1.831 | 50 | **+9.18** | 1.056 |
| US30L | 208 | +258.52 | 1.893 | 103 | **+65.73** | 1.127 |

Profit factor 1.83–2.14 → **1.06–1.25**. Positive on all three, which is the right *shape*
(a rule chosen on research should look better there), and small enough that §8 can move it through
zero.

Monte Carlo — **bootstrap whole days with their trades attached for the edge, permute for the
drawdown**, because permuting cannot change the endpoint:

| market | block | mean | P(mean ≤ 0) | 90% CI | maxDD real | MC p50 | MC p95 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| US100L | research | +66.02 | **0.000** | [+33, +100] | 1,338 | 1,487 | 2,363 |
| US100L | locked | +30.27 | **0.147** | [−18, +83] | 3,075 | 2,942 | 4,700 |
| NQ | research | +78.11 | 0.017 | [+18, +145] | 1,100 | 1,454 | 2,332 |
| NQ | locked | +9.18 | **0.462** | [−101, +124] | 3,101 | 2,954 | 4,589 |
| US30L | research | +258.52 | 0.001 | [+130, +395] | 6,617 | 6,752 | 10,658 |
| US30L | locked | +65.73 | **0.331** | [−167, +302] | **17,040** | 12,266 | 19,022 |

Every locked block's 90% interval contains zero. And US30L's realised locked drawdown of 17,040 is
**39% above the permutation median** and near its p95 — the realised sequence was not lucky, so
"an unlucky ordering" is not available as an excuse for the decay.

---

## 7. Robustness — a perfect plateau that does not replicate

`research/v60/v60robust.py`. Every cell within one rung of the leader on `ema_f`, `ema_s`, `win`,
`don_e`, `don_x`, `stop` and `tp` simultaneously — 128 cells.

| market | block | scorable | **profitable** | median $/tr | p25 | p75 |
| --- | --- | --- | --- | --- | --- | --- |
| US100L | research | 128 | **100.0%** | +48.04 | +38.48 | +62.45 |
| US100L | locked | 128 | 92.2% | +37.84 | +17.95 | +50.71 |
| NQ | research | 128 | **100.0%** | +78.05 | +59.60 | +96.66 |
| NQ | locked | 128 | **26.6%** | **−32.40** | −85.45 | +1.14 |
| US30L | research | 128 | **100.0%** | +160.21 | +120.11 | +202.97 |
| US30L | locked | 128 | **39.8%** | **−15.32** | −64.23 | +31.36 |

**This is the cleanest plateau this branch has ever measured — 128 of 128 cells profitable on
research, on all three markets — and on two of the three markets it fails out of sample.** It puts
a number on `CLAUDE.md`'s "a plateau is necessary and not sufficient": a *perfect* plateau, with no
negative neighbour anywhere in a seven-dimensional box, still converts to 26.6% on NQ's locked
block. Coherence filters out artefacts of the *search*; it says nothing about the *regime*.

The ladder (one axis at a time, everything else at the leader) shows why: on locked, **removing the
EMA condition entirely beats the EMA cross on two of three markets** — NQ +32.55 against +9.18 and
US30L +80.35 against +65.73, on 2.5–3× the trades. The signal the search spent 82% of its top 1000
on is the part that does not transfer.

Walk-forward, five contiguous folds of the research block. `CLAUDE.md`: a walk-forward inside the
discovery block is contaminated by construction, because the thresholds were chosen over the whole
span — it is run to see whether *one fold* carries the result, not as evidence.

| market | fold 1 | fold 2 | fold 3 | fold 4 | fold 5 | locked |
| --- | --- | --- | --- | --- | --- | --- |
| US100L | +8.93 | +23.18 | +49.83 | +136.94 | +114.46 | +30.27 |
| NQ | +3.97 | +91.67 | +145.34 | +87.08 | +102.21 | +9.18 |
| US30L | +88.54 | +305.11 | +326.79 | +439.75 | +131.95 | +65.73 |

**5 of 5 folds positive on all three markets, and it means nothing.** The shape is a hump — weakest
at both ends of the research block, strongest in the middle, and back to near-zero on locked. A
perfect fold record inside the discovery block is what a regime looks like, not what an edge looks
like.

---

## 8. The vectorbt second opinion — and where the engine is optimistic

The whole verdict rests on one engine, and an engine that is wrong is wrong everywhere at once.
`research/v60/v60_vbt.py` rebuilds the leading configuration from the bars with **no shared code
path** — its own Wilder ATR, its own ADX, vectorbt's own EMAs, its own Donchian channels,
vectorbt's order engine instead of the numba walk — and runs it the way `STUDY_PINE_PARITY.md`
requires: **twice.**

**Pass 1, the transcription check.** Compare the *signal sets* bar for bar, isolating the rule from
the order model.

| market | engine | vectorbt | both | eng only | vbt only | agreement | last disagreement |
| --- | --- | --- | --- | --- | --- | --- | --- |
| US100L | 1,352 | 1,350 | 1,348 | 4 | 2 | **99.6%** | bar 63 of 51,889 |
| NQ | 483 | 482 | 482 | 1 | 0 | **99.8%** | bar 32 of 18,243 |
| US30L | 1,135 | 1,134 | 1,134 | 1 | 0 | **99.9%** | bar 14 of 49,325 |

**Every disagreement is inside the EMA(62) warm-up.** After bar 63 of a 51,889-bar series the two
implementations are the same bars. The rule is transcribed correctly.

**Pass 2, the order model.** Same bars, each engine's own execution, gross of costs.

| market | block | eng n | vbt n | count agree | **eng pts** | **vbt pts** | naive |
| --- | --- | --- | --- | --- | --- | --- | --- |
| US100L | research | 212 | 211 | 99.5% | +35.22 | +30.97 | +25.94 |
| US100L | locked | 139 | 138 | 99.3% | **+17.36** | **+5.98** | +5.61 |
| NQ | research | 83 | 81 | 97.6% | +41.28 | +35.38 | +31.99 |
| NQ | locked | 50 | 50 | 100.0% | **+6.81** | **−12.28** | −15.29 |
| US30L | research | 208 | 207 | 99.5% | +53.49 | +45.40 | +42.92 |
| US30L | locked | 103 | 103 | 100.0% | **+14.94** | **−0.09** | +12.93 |

**The trade counts agree at 97.6–100%; the per-trade result does not, and the gap runs one way.**
Under vectorbt's execution the locked block is **+5.98, −12.28 and −0.09** points a trade against
the engine's **+17.36, +6.81 and +14.94** — two of three flip sign. The §6 conclusion that the
leader survives out of sample "small but positive on all three" does not survive a second engine.

**Pass 3, trade by trade, matched on the fill bar, split by exit reason.**

| market | block | matched | stop n | Δbar | Δpx | chan n | Δbar | Δpx | vbt fills at o / c / stop |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| US100L | research | 210 | 31 | +0.10 | −9.37 | 179 | +1.00 | −3.43 | 80% / 11% / 9% |
| US100L | locked | 138 | 26 | +1.46 | −10.66 | 112 | +1.00 | −10.29 | 73% / 14% / 13% |
| NQ | research | 81 | 15 | +2.60 | +8.19 | 66 | +1.00 | −9.40 | 73% / 15% / 12% |
| NQ | locked | 50 | 8 | +0.00 | **−109.79** | 41 | +1.00 | −1.86 | 80% / 18% / 2% |
| US30L | research | 207 | 32 | +0.06 | −17.49 | 175 | +0.71 | −7.00 | 79% / 10% / 11% |
| US30L | locked | 103 | 18 | +0.11 | −44.74 | 85 | +1.00 | −8.74 | 77% / 14% / 10% |

**Pass 4, and a correction I have to make to my own first reading of pass 2.** The obvious
explanation for the pass-2 gap is the channel exit's fill convention: the engine sells at the
**close of the bar that breaks the channel** — a market-on-close order decided by the very close it
fills at, which no script can place — while a script sells at the **next open**. That is exactly
`mean(open[j+1] − close[j])` over the engine's own channel exits, and it is **measurable in one
line**:

| market | block | channel exits | give-up per channel exit | worst single |
| --- | --- | --- | --- | --- |
| US100L | research | 181 | **−0.21** | −24.50 |
| US100L | locked | 113 | **+0.10** | −5.20 |
| NQ | research | 68 | **−0.03** | −1.00 |
| NQ | locked | 41 | **−0.22** | −3.25 |
| US30L | research | 175 | **+0.55** | −96.00 |
| US30L | locked | 85 | **−0.31** | −46.00 |

**About a fifth of a point, and not always in the same direction.** The pass-2 gap is 4 to 22
points. **So the convention is not the mechanism, and my first version of this section said it
was.** What pass 3 actually shows is vectorbt's own execution: its **stop** exits land on the
*same bar* as the engine's and price **9 to 110 points worse**, and 10–18% of its exits do not fill
at the `price=` series at all. The channel column's Δpx is likewise larger than the convention
because a tenth to a fifth of those trades are resolved by vectorbt's stop machinery rather than by
the exit signal.

The correct reading of the vectorbt columns is therefore the weaker one, and it is still worth
having: **two independent implementations agree on the rule (99.6–99.9% of signal bars) and on
which trades it takes (97.6–100%), and disagree on the exits by 12–100%.** That is a statement
about how much of a bar-level backtest's number is its exit convention — the third time this branch
has measured that, after V38's 2.1× and V41's 22.9× — not a correction to the research.

### The arbiter: the shipped script's own order model

`research/v60/v60_parity.py` settles what the Pine actually does, by writing its order model out
directly rather than through a third library: one live position, market entry at the next open, a
fill-relative bracket in whole ticks placed **with** the entry so the fill bar is protected, the
channel exit tested only from the bar after the fill and filling at the next open, and the earliest
re-entry one bar after the exit.

| preset | market | block | script n | engine n | count | script pts | engine pts | gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | US100L | research | 211 | 212 | 99.5% | +35.41 | +35.22 | +0.5% |
| A | US100L | locked | 139 | 139 | 100.0% | +16.93 | +17.36 | **−2.5%** |
| A | NQ | research | 83 | 83 | 100.0% | +41.26 | +41.28 | −0.1% |
| A | NQ | locked | 50 | 50 | 100.0% | +6.63 | +6.81 | **−2.6%** |
| A | US30L | research | 208 | 208 | 100.0% | +53.96 | +53.49 | +0.9% |
| A | US30L | locked | 103 | 103 | 100.0% | +14.69 | +14.94 | **−1.6%** |
| B | US100L | locked | 87 | 87 | 100.0% | +43.82 | +44.71 | −2.0% |
| B | NQ | locked | 33 | 33 | 100.0% | −20.00 | −20.02 | +0.1% |
| B | US30L | locked | 79 | 79 | 100.0% | +21.21 | +20.28 | +4.6% |

**Trade counts 99.5–100%, per-trade result within −2.6% to +4.6%, and negative on every locked
block** — the conservative direction, which is the one `STUDY_V56.md` had to work to achieve. The
"same exit bar" share is 14.7–39.4% and that is *expected and checked*: every differing trade is a
channel exit and differs by exactly **+1 bar**, so the matching share is simply the stop/target
share of exits (14.6% of US100L research exits are stops, against a 14.7% same-bar rate).

### Two execution traps found while building the harness

**A `price=` fill does not anchor `sl_stop`.** vectorbt resolves the `sl_stop` fraction against the
bar's **close**, not against the fill price handed to it through `price=`. Writing the obvious
`sl_stop = stop_n × ATR / close` therefore puts the stop `(close − open)` away from where the
engine puts it — on a 60-minute bar, a real distance. The `naive` column above is that version;
the difference between it and the corrected one is **up to 13 points a trade** (US30L locked
+12.93 against −0.09, which is a *sign flip in the wrong direction* — the trap happened to flatter
the result there and to depress it elsewhere, which is worse than a consistent bias).

**An unshifted exit signal with `price=open` is lookahead.** vectorbt executes an order on the
**signal** bar at `price`, so a `close < channel` exit written without a shift fills at that same
bar's **open** — a price printed before the break was known. In the first run of this harness that
was worth **+22 to +100 points a trade**, i.e. it more than doubled the result. It is the
`STUDY_V10_LIMIT.md` family of bug in a new library: a fill model taking an order no script can
place.

---

## 8b. Making the Aroon bind — a defect, and the only reading that can refuse a trade

The shipped script's first build resolved its presets by overwriting `aroonMode` with `"off"`, so
**selecting an Aroon condition did nothing unless the preset dropdown read "Custom".** That is a
plain defect and it is fixed: the presets now set the entry, the geometry and the gate, and the
Aroon group, the session and the display are always the user's. A switch that a preset can silently
disarm is not a switch.

But the input being live is only half of it, because of §2. **The only way to make Aroon do work on
a breakout is to read it where the breakout has not already determined it** — the bar *before* the
signal. The prior bar is not required to be the N-bar high, so the identity does not apply and the
condition asks a different, genuinely testable question: *was the trend already up before the
break?* Both readings are causal. Measured on NQ 60m, gross, research → locked $/trade:

**Preset B (Donchian 55, Aroon 25 — the signal-bar reading is the identity):**

| aroon | read at | res n | res pts | lock n | lock pts |
| --- | --- | --- | --- | --- | --- |
| off | — | 54 | +67.30 | 33 | −20.02 |
| osc ≥ 0 | signal | **54** | **+67.30** | **33** | **−20.02** |
| up ≥ 70 | signal | **54** | **+67.30** | **33** | **−20.02** |
| osc ≥ −50 | signal | **54** | **+67.30** | **33** | **−20.02** |
| osc ≥ 0 | prior | 52 | +74.52 | 32 | −16.07 |
| up ≥ 70 | prior | 45 | +98.19 | 30 | −11.82 |

Three conditions returning the trade count **and** the P&L of `off` to the cent is the identity
printed in a results table rather than argued from arithmetic. Moving the read one bar back changes
the trade count immediately.

**Preset A (Donchian 10, Aroon 25 — 25 > 10, so even the signal-bar reading binds), all three
markets, `osc ≥ 0`:**

| market | aroon | read at | res n | res pts | lock n | lock pts |
| --- | --- | --- | --- | --- | --- | --- |
| NQ | off | — | 83 | +41.28 | 50 | +6.81 |
| NQ | osc ≥ 0 | signal | 70 | +48.55 | 38 | +10.57 |
| NQ | osc ≥ 0 | prior | 66 | **+55.86** | 35 | **+14.09** |
| US100L | off | — | 212 | +35.22 | 139 | +17.36 |
| US100L | osc ≥ 0 | prior | 171 | **+29.22** | 104 | +26.25 |
| US30L | off | — | 208 | +53.49 | 103 | +14.94 |
| US30L | osc ≥ 0 | prior | 168 | **+42.48** | 84 | +13.60 |

**On NQ the prior-bar reading improves both blocks. On US100L and US30L it makes RESEARCH WORSE
and locked better.** That is the wrong shape on two of three markets — a rule chosen on research
should look better *there*; the holdout is where an edge decays, not where it appears — and it
agrees with §3's whole-grid marginal, which says no Aroon setting beats `off` in more than 2 of 6
market-block columns. Restrictiveness alone raises profit factor, and this branch has recorded an
ATR filter going PF 1.42 → 1.77 while being indistinguishable from a random filter of the same
selectivity. **The NQ-only version of this table, published before the other two feeds were
restored, read as mildly encouraging; the three-market version does not.** The reading bar ships as
a knob with its numbers attached, not as a result.

## 8c. The session window and the flatten, priced rather than warned about

Both were asked for, both ship **off**, and each carries its measured cost in its own tooltip.
Preset A, gross, all three markets — research $/trade then locked:

| window | flatten | NQ | US100L | US30L |
| --- | --- | --- | --- | --- |
| all hours | none | +41.28 / +6.81 | +35.22 / +17.36 | +53.49 / +14.94 |
| all hours | 16:00 | +17.78 / +5.39 | +10.83 / +11.18 | +20.98 / +38.35 |
| all hours | 12:00 | −0.57 / −5.02 | +8.80 / −3.43 | +18.50 / +27.94 |
| 09:30–11:00 | none | +39.71 / −36.70 | +18.04 / +33.63 | **−1.66 / −56.91** |
| 09:30–12:00 | none | **+73.37 / −12.53** | +12.62 / +15.21 | **−16.06 / −5.54** |

**The 16:00 flatten costs 57%, 69% and 61% of the research result per trade on NQ, US100 and US30
— every market, every time — and it RAISES the trade count** (83 → 103, 212 → 260, 208 → 259),
which is where the cost goes: the clock closes trades a channel exit would have held. The locked
column is mixed and does not rescue it.

**No window beats all hours on research on more than one market, and US30 is negative in both
morning windows on both blocks.** NQ's +73.37 at 09:30–12:00 is the best research cell in the whole
table and reads −12.53 out of sample — which is exactly the single-market story a three-market
table exists to prevent. Tenth independent confirmation of the intraday finding on this branch.

Two implementation points the parity harness forced:

* **"Flat by 16:00" means flat at the 16:00 *open*.** `strategy.close()` cannot sell the close of
  the bar that triggers it, so the order is submitted on the bar before — `nyMin + tfMin >= flatMin`
  — which lands the fill exactly where `tensor_stop`'s `flat_mod` path puts it.
* **A signal whose fill would land at or after the cutoff is refused, not opened.** The engine takes
  those and closes them at the same open for zero P&L, diluting the statistics; the script guards
  its entry with `not flatDue`, and the measurement above was redone to match the script.

Parity on all seven configurations, all three markets, gross — **trade counts 99.5–100.0%
everywhere**:

| configuration | market | block | script n | engine n | count | script pts | engine pts |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | US100L | research | 211 | 212 | 99.5% | +35.41 | +35.22 |
| A | NQ | locked | 50 | 50 | 100.0% | +6.63 | +6.81 |
| A | US30L | research | 208 | 208 | 100.0% | +53.96 | +53.49 |
| B | US100L | locked | 87 | 87 | 100.0% | +43.82 | +44.71 |
| B | US30L | research | 162 | 162 | 100.0% | +49.74 | +48.44 |
| A + aroon up≥70 @ prior | US30L | locked | 74 | 74 | 100.0% | +22.17 | +22.78 |
| A + window 09:30–16:00 | NQ | research | 46 | 46 | 100.0% | +71.60 | +71.64 |
| A + flatten 16:00 | US100L | research | 260 | 260 | 100.0% | +11.58 | +10.83 |
| A + flatten 16:00 | US30L | locked | 119 | 119 | 100.0% | +36.31 | +38.35 |
| A + MACD macd>0 @ prior | NQ | research | 66 | 66 | 100.0% | +52.15 | +52.16 |
| B + MACD macd>0 @ signal | NQ | locked | 33 | 33 | 100.0% | −20.00 | −20.02 |

Per-trade gaps run −2.8% to +8.5%, with one −85.7% outlier on US30L's locked entry-window cell
where the engine's own figure is +1.31 — a percentage against a near-zero base, not a defect.

Each optional feature is turned on **alone**, so a parity failure would name one feature rather
than a combination.


---

## 8d. The MACD — a third indicator that turns out to be the breakout restated

Asked to add the standard 12/26/9 MACD, the first number computed was not its P&L but **its base
rate on the breakout's own bars**, because that is what `STUDY_V16_MOMENTUM.md` and §2 both say
decides the answer. Eight readings, three parameter sets, NQ 60m:

| reading | all bars | on breakouts (don 55) | on signals (preset B) | res pts | lock pts |
| --- | --- | --- | --- | --- | --- |
| *(no MACD condition)* | — | — | — | +67.30 | −20.02 |
| `macd > 0` @ 12/26/9 | 58.4% | **99.8%** | 99.7% | +70.21 | −20.02 |
| `macd > 0` @ 8/21/5 | 57.8% | **100.0%** | **100.0%** | **+67.30** | **−20.02** |
| `macd > 0` @ 19/39/9 | 59.2% | 99.2% | 99.7% | +70.21 | −20.02 |
| `hist > 0` @ 12/26/9 | 48.8% | 86.9% | 95.3% | +78.38 | −20.02 |
| `fresh cross ≤ 10` @ 12/26/9 | 39.0% | 55.1% | 45.7% | +123.67 | **+9.48** |
| `fresh cross ≤ 10` @ 8/21/5 | 54.8% | 68.9% | 60.9% | +77.32 | **−29.51** |

**Confirmed on all three markets.** At 12/26/9, `macd > 0` passes **100.0%** of US30L's Donchian-55
breakout bars — 162 trades, +48.44 research / +20.28 locked, identical to no condition — **99.9%**
of US100L's and **99.8%** of NQ's; at 8/21/5 NQ reaches 100.0% and is identical too. A close above the 55-bar high on a 60-minute chart essentially
guarantees EMA(12) > EMA(26) — the fast average cannot be below the slow one when price has just
made a two-and-a-half-day high. **That is the third indicator on this branch to be the trigger
restated**: RSI(14) ≥ 55 passes 94.7% of breakout bars, `aroon osc ≥ 0` passes 100.0% by
construction, and now `macd > 0` passes 99.2–100.0% empirically.

The one reading that binds is the **fresh bullish cross**, at 42–45% of signals — and it is the one
to trust least. Preset B locked $/trade at 12/26/9: NQ −20.02 → **+9.48**, US100L +44.71 →
**+99.44**, US30L +20.28 → **+0.94**. It looks spectacular and it fails every shape test at once:
on US100L it makes *research* worse (+26.61 → +19.70) while more than doubling the locked block,
and on NQ it flips from +9.48 at 12/26/9 to **−29.51** at 8/21/5. A result that flips sign across
its own neighbourhood is a spike, and this branch rejects those *before* the holdout. This one was
seen after, which is worse.

The **prior-bar** reading of `macd > 0` on preset A is the better-behaved row: locked +15.00 /
+15.23 / +22.75 at 12/26/9, 8/21/5 and 19/39/9 against a +6.81 baseline — consistent across all
three parameterisations rather than spiking on one. On preset B the prior-bar reading is itself
near-inert (98.5–99.1% of signals on all three markets): a long entry channel makes the zero-line
condition redundant however it is read. A knob, not a result.

**One refinement to `STUDY_MA_LAG.md`.** That study established MA *type* is not a degree of
freedom: at matched lag, SMA and EMA trigger sets overlap 89.5–97.3%. **That does not carry to the
MACD**, because the MACD is a *difference* of two averages plus a third smoothing, so the lag
mismatch compounds. At 12/26/9 the EMA and SMA readings of `hist > 0` agree on only **79.2%** of
bars and `hist > 0 and rising` on **76.2%**. The SMA column reads better on locked (`macd > 0`:
EMA +8.24, SMA +25.27) — but that difference lives on the ~20% of trades that differ, which is
precisely what `STUDY_MA_LAG` calls noise until it replicates elsewhere. EMA ships as the default
because it is the reference indicator's.

## 8e. The same two session features on the YouTube Turtle — and they point the other way

`research/turtle2/yt_gates.py`. The frozen `ytturtle.run` kernel is quoted by three studies, so it
is **copied once** rather than parameterised, with a parity assertion that the gated engine
reproduces it trade for trade when every gate is open — **158/158 in-sample and 70/70 out-of-sample,
identical R**. NQ 1H only; the other five feeds were wiped by a container recycle.

| window | flatten | ADX | IS n | IS R | OOS n | OOS R | OOS PF |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all hours | none | off | 158 | **+0.193** | 70 | **−0.090** | 0.83 |
| all hours | 12:00 | off | 261 | +0.121 | 138 | **+0.174** | 1.65 |
| all hours | 16:00 | off | 326 | +0.123 | 168 | +0.111 | 1.36 |
| 09:30–11:00 | none | off | 82 | +0.117 | 44 | +0.094 | 1.21 |
| 09:30–12:00 | none | off | 90 | +0.169 | 51 | −0.006 | 0.99 |
| 09:30–16:00 | none | off | 108 | +0.144 | 60 | −0.056 | 0.89 |
| all hours | none | ≥ 20 | 138 | +0.147 | 62 | +0.140 | 1.34 |
| all hours | none | ≥ 25 | 114 | +0.170 | 57 | +0.156 | 1.35 |
| all hours | none | ≥ 30 | 96 | +0.140 | 36 | **+0.307** | 1.84 |

**Every one of these appears to rescue the out-of-sample block, and every one does it in the wrong
shape — in-sample worse, out-of-sample better.** That shape has been treated as a defect twice
before on this branch and was right both times. Three further reasons it is not a discovery:

* **NQ is the one market of six where the frozen rules failed out of sample** (−0.090 R, against
  US30 +0.157, XAUUSD +0.161, EURUSD +0.102, BTC +0.063, US100 +0.039). Fixing the market that
  failed, on the market that failed, is selection.
* **The ADX gradient is what restrictiveness alone looks like**: OOS R rises +0.140 → +0.156 →
  +0.307 as n falls 62 → 57 → 36. Compare the ATR filter that went PF 1.42 → 1.77 and was
  indistinguishable from a random filter of the same selectivity.
* **The flatten raises the trade count 158 → 326.** It is not filtering, it is cutting trades short
  and letting new ones start.

**And the flatten's sign is opposite to §8c's**, where the identical change cost 57% of the V60
breakout's per-trade result. Two systems, opposite signs, one market each — which is the definition
of not knowing.

### What the combined grid ships, and why it is not the top row

`research/turtle2/yt_best.py` puts all five gates in one grid — window × flatten × ADX × MACD ×
Aroon, 960 cells, 685 scorable at 40+ in-sample trades — selects on the **in-sample block only** by
the **marginal average per axis**, and reads out-of-sample once. Aroon length is 25 against the
Turtle's 20-bar entry channel, so §2's identity does not apply and the condition binds.

| in-sample marginal R/trade | best → worst |
| --- | --- |
| MACD | `hist>0 and rising` **+0.390**, fresh cross +0.387, `hist>0` +0.314, `macd>0` +0.199, off +0.184 |
| Aroon | `osc≥0` **+0.304**, `osc≥50` +0.302, `up≥70` +0.300, off +0.222 |
| window | 08:00–12:00 **+0.312**, 09:30–16:00 +0.304, all hours +0.268, 09:30–12:00 +0.218 |
| flatten | none +0.349, 16:00 +0.247, 12:00 +0.236 |
| ADX | off +0.314, ≥20 +0.277, ≥25 +0.274, ≥30 +0.228 |

| configuration | in-sample | out-of-sample |
| --- | --- | --- |
| frozen rules, no gates | n 158, +0.193, PF 1.46 | n 70, **−0.090**, PF 0.83 |
| top row by in-sample R | n 40, **+0.682**, PF 4.00 | n 18, **−0.058**, PF 0.87 |
| **marginal consensus (shipped)** | n 64, +0.414, PF 2.84 | n 34, **+0.207**, PF 1.75 |

**The top row is the trap and the marginal is the answer.** Ranking on in-sample expectancy buys a
40-trade cell that reads −0.058 out of sample — this branch has bought 30-trade configurations that
way before. The marginal consensus keeps 64 in-sample trades and is the only one of the three
positive on both blocks. Its neighbourhood is smooth rather than a spike: moving one axis at a time,
out-of-sample R/trade reads all hours +0.239, flatten 12:00 +0.257, MACD `hist>0` +0.124, ADX off
+0.327.

Shipped defaults: **08:00–12:00 entry window, hard flatten 16:00, ADX ≥ 20, MACD `hist>0 and
rising` 12/26/9, Aroon `osc ≥ 0` (25)** — all ON. Two facts stated with them rather than buried:
**ADX off scores better than any ADX floor on both blocks** (+0.438 / +0.327), and it is on at ≥20
because it was asked for; and this is one market, the one of six where the frozen rules failed out
of sample.


---

## 9. What to carry forward

1. **Do not add a channel-position indicator to a channel breakout.** Aroon, Donchian, Williams %R
   and "distance from the N-bar high" are one measurement. Before adding any confirmation to a
   trigger, compute **its base rate on the trigger's own bars**: 100.0% here, 94.7% for RSI on
   V16's breakouts. Two lines of code ahead of a million-cell sweep.
2. **A perfect plateau is not evidence.** 128 of 128 cells profitable on research on three markets
   → 26.6% on NQ's locked block. Coherence rejects search artefacts; it cannot detect a regime.
3. **5-of-5 walk-forward folds inside the discovery block is not evidence either**, and the hump
   shape here shows what it actually measures.
4. **A negative research→locked rank correlation is a stop sign.** NQ: −0.4426 over 121,282
   configurations. When it is negative, selection on that market is worse than not selecting.
5. **Measure the mechanism you name.** I attributed a 4–22 point engine-vs-vectorbt gap to the
   channel exit's fill convention without measuring the convention. It is worth **0.2 points**, an
   order of magnitude out, and not always in the same direction. One line —
   `mean(open[j+1] − close[j])` over the exits in question — would have caught it before the claim
   was written, and a purpose-built parity harness confirms the script lands within 2.6% of the
   engine. A plausible mechanism with the right sign is not a measurement.
6. **`sl_stop` in vectorbt anchors to the close, not to `price=`**, and 10–18% of its exits do not
   fill at the `price=` series at all. Solve for the fraction that reproduces your engine's
   absolute level, and treat the residual as the library's execution rather than as your engine's
   error — the arbiter of what a *script* does is the script's own order model, written out.
7. **No take profit beat every target again** — fifth independent confirmation on this branch.
8. **A preset must not disarm a switch.** The first build of the shipped script overwrote
   `aroonMode` during preset resolution, so the one input a reader would most want to experiment
   with was dead unless they left the preset. A preset should set what it has an opinion about and
   nothing else.
9. **Compute a confirmation's base rate on the trigger's own bars BEFORE its P&L.** Three
   indicators have now failed that test on the same breakout: RSI ≥ 55 at 94.7%, Aroon `osc ≥ 0` at
   100.0%, MACD `macd > 0` at 99.2–100.0%. It is two lines of code ahead of any sweep.
10. **MA type is not a degree of freedom for a single average and IS one for the MACD** — a
   difference of two averages plus a third smoothing compounds the lag mismatch, and EMA/SMA
   readings of `hist > 0` agree on only 79.2% of bars, against 89.5–97.3% for price-vs-MA rules.
11. **The same session feature can have opposite signs on two systems.** A hard flatten costs the
   V60 breakout 57% of its per-trade result and appears to rescue the YouTube Turtle's NQ block —
   both on one market, both in the wrong shape where it helps.
12. **An indicator that is an identity on the signal bar can still bind one bar earlier**, and that
   is the only version of it worth testing. It is a different question — "was the trend already up
   before the break" — not a rescue of the original one.

---

## 10. Files

| file | what it does |
| --- | --- |
| `research/v60/v60core.py` | the tensor: Aroon, signal keys with inert axes collapsed, the parallel sweep |
| `research/v60/run_v60.py` | the sweep, research block only, saved to `results/v60/` |
| `research/v60/v60judge.py` | the condition correlation matrix and the marginal table |
| `research/v60/v60aroon.py` | the Aroon–Donchian identity, checked bar by bar |
| `research/v60/v60verdict.py` | consensus, matched control gate, the single locked read, Monte Carlo |
| `research/v60/v60robust.py` | the ladder, the one-rung box, and the in-block walk-forward |
| `research/v60/v60_vbt.py` | the vectorbt second opinion: transcription, order model, trade-by-trade diff, fill attribution |
| `research/v60/v60_parity.py` | **the shipped Pine's own order model in Python, diffed against the engine** |
| `research/v60/v60session.py` | the Aroon reading bar, and the session window x flatten grid |
| `pine/v60/V60_AROON_DONCHIAN_strategy.pine` | the shipped script: two presets, every component switchable, the identity live in its panel |
| `results/v60/logs/` | the raw output of all five |
