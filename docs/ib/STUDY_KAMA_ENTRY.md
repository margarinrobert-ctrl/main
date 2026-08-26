# KAMA 9 and other moving-average crossovers: as a trigger, and as an entry location

`research/donchian/kama_entry.py`. Two questions that look like one and are not, so they are asked
separately because they need different controls:

* **Q1** — does a KAMA crossover *earn* anything as a trigger of its own?
* **Q2** — given a trade you were taking anyway, does waiting for a KAMA condition give a **better
  location**: a cheaper fill, and a better outcome from it?

NQ 30-minute, 2022-12 → 2025-12, MNQ fees and bar-speed slippage (1.72 points round turn), 65/35
session split, locked block read once. A 3×ATR trailing stop in every cell, so only the entry varies.

## Q1 — the crossover as a trigger

Twelve crossovers on two timeframes, each against a matched control (same side, same geometry, same
minute-of-day, same ATR at entry). Research block, 30-minute:

| crossover | n | pts/trade | R | control | excess | p | PF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **KAMA 9 × EMA 50** | 317 | +20.60 | +0.1600 | +0.0189 | **+0.1410** | **0.002** | 1.48 |
| EMA 50 × EMA 200 | 137 | +12.17 | +0.0851 | +0.0125 | +0.0726 | 0.209 | 1.29 |
| KAMA 9 × KAMA 50 | 373 | +7.82 | +0.0696 | +0.0178 | +0.0518 | 0.124 | 1.19 |
| KAMA 9 × EMA 21 | 451 | +8.00 | +0.0665 | +0.0138 | +0.0526 | 0.057 | 1.19 |
| KAMA 9 × price | 622 | −1.73 | −0.0090 | +0.0120 | −0.0210 | 0.880 | 0.96 |
| EMA 9 × SMA 20 | 562 | −5.32 | −0.0674 | +0.0113 | −0.0787 | 0.997 | 0.88 |

On **5-minute** every crossover clears its control at p < 0.05 — and every one of them is at or below
break-even in absolute terms (best PF 1.02, most 0.9x). They beat a control that loses *more*. That
is a distinction worth keeping: an excess over a negative control is not a profit.

### The 9 is not the mechanism

Over a 6 × 7 grid of KAMA and EMA lengths on research, the surface rises **monotonically with the
KAMA period** — mean excess by KAMA length: 5 → +0.038, 7 → +0.074, 9 → +0.094, 11 → +0.097,
14 → +0.095, **20 → +0.159**. KAMA 20 × EMA 50 scores +0.2566 R. A gradient that runs away from the
parameter you specified is telling you the parameter is not what is working.

### The locked block, read once

Multiplicity stated first: KAMA 9 × EMA 50 — the length 9 was specified, its partner chosen from 12
crossovers on 2 timeframes, factor 24. KAMA 20 × EMA 50 — best corner of a 42-cell grid, factor 42.

| | block | n | pts/trade | R | control | p | PF | max DD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| KAMA 9 × EMA 50 | research | 317 | +20.60 | +0.1600 | +0.0188 | **0.0050** | 1.48 | 1,698 |
| KAMA 9 × EMA 50 | **LOCKED** | 193 | **+4.04** | +0.0612 | +0.0174 | **0.2575** | **1.07** | **2,844** |
| KAMA 20 × EMA 50 | research | 289 | +28.51 | +0.2566 | +0.0211 | 0.0000 | 1.78 | 935 |
| KAMA 20 × EMA 50 | **LOCKED** | 152 | **+3.37** | +0.1067 | +0.0246 | **0.1460** | **1.05** | 3,377 |

**Neither survives.** The decay is at least the right way round — a rule picked on research should
get worse out of sample, unlike the Donchian grid in `STUDY_DONCHIAN_ADX_CHOP.md`, which improved on
every timeframe — but it decays to nothing. By year, KAMA 9 × EMA 50: 2023 +1.7 pts/trade, 2024
+43.9, **2025 −0.9**. The top 1% of trades supply **87%** of net P&L and the top 5% supply **218%**.

## Q2 — the crossover as an entry location

The Donchian breakout arms the trade; instead of paying the next open, wait up to *N* bars for a
pullback to a moving average and fill there. **The control is the thing that decides this**, and the
obvious one is wrong: a random-wait control fills at an *open*, so it hands the tap a better price
and calls the difference an edge. The right control is a **blind limit resting the same number of
ATRs from the signal close, with no average in it** — if the tap only matches that, the *distance*
is choosing the location and the moving average is an expensive way to specify a number.

30-minute, 5-bar window:

| tap | block | filled | of signals | fill better by | R | blind limit at same distance | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| *market next open (baseline)* | research | 475 | 100% | — | **+0.1026** | — | — |
| touch KAMA 9 | research | 125 | 26% | +1.67 ATR | +0.0423 | +0.0195 | 0.430 |
| touch EMA 9 | research | 104 | 22% | +1.83 ATR | −0.0311 | +0.0200 | 0.657 |
| touch EMA 21 | research | 64 | 13% | +2.58 ATR | +0.3253 | +0.2538 | 0.339 |
| touch SMA 20 | research | 54 | 11% | +2.86 ATR | +0.4020 | +0.3474 | 0.401 |
| touch HULL 9 | research | 328 | 69% | +0.59 ATR | +0.1254 | +0.1110 | 0.459 |
| *market next open (baseline)* | **LOCKED** | 275 | 100% | — | **+0.1387** | — | — |
| touch KAMA 9 | **LOCKED** | 85 | 31% | +1.44 ATR | **−0.0223** | +0.0450 | 0.686 |
| touch EMA 21 | **LOCKED** | 41 | 15% | +2.64 ATR | −0.0048 | −0.1702 | 0.124 |
| touch SMA 20 | **LOCKED** | 34 | 12% | +2.76 ATR | +0.0914 | −0.1939 | 0.047 |

**Two negatives, and the second is the more useful one.**

**The tap loses to simply taking the trade.** Out of sample the baseline earns +0.1387 R on all 275
breakouts; waiting for KAMA 9 fills 31% of them and returns −0.0223. The fill genuinely *is* better —
1.4 to 1.7 ATR cheaper — and it does not matter, because waiting for an adverse excursion discards
precisely the trades that ran. `STUDY_LIMIT_ENTRY.md` reached the same place from the other
direction: the limit mechanic **substitutes** for a signal, it does not complement one.

**The moving average is not choosing the location; the distance is.** Not one tap beat a
distance-matched blind limit on either block — research p 0.162–0.985, locked p 0.047–0.686. The one
sub-0.05 cell is SMA 20, one of about forty, and it "passes" locked only because its own control
fell further (+0.0914 against −0.1939) after collapsing from +0.4884 on research. The taps that look
spectacular on research (SMA 20 at PF 4.62, EMA 21 at PF 4.48 in the 3-bar window) are deep limits
taking 8–9% of the trades, and a blind limit at the same depth gets there too.

The `reclaim` and `cross` taps — dip below the average and take it back, or wait for a fast/slow
cross before entering — are worse still: research p 0.610–0.985 against a random wait of the same
length, on 7–34% fill rates.

## What to take from this

Cheaper fills are not free. Across both halves of this study the entry mechanic moved per-trade
numbers a great deal and total profit not at all, because everything that improves the *price* also
selects *which* trades happen — and on a breakout the selection is adverse. The one thing here that
came close to a result, KAMA 9 × EMA 50 as a trigger, has the right decay shape and still ends at
PF 1.07 with 87% of its money in twelve trades.

Only NQ was available, so none of this is cross-market evidence.
`pine/donchian/KAMA_CROSS_strategy.pine` ships the crossover with the tap present and **defaulted
off**, and carries these numbers in its header. Pine has no built-in KAMA; the recursion is written
out and seeded to match the research code.

## Addendum — the tap inside the session box, and the script that ships it

The first script shipped for this study had the KAMA × EMA crossover standing on its own, which is
not where the pullback tap was measured: the tap is always **armed by a Donchian breakout**. That
mismatch is fixed in `pine/donchian/DCS_KAMA_SESSION_strategy.pine`, which carries the breakout, the
three filters as individual toggles, the tap, and free session start / last-entry / flatten times.

Measured for those defaults — Donchian 20, EMA 50, ADX > 20, CHOP < 40, 3×ATR trail, signals
06:00–11:00 New York, flat at 12:00:

| tf | block | n | pts/trade | R | win | PF | max DD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5m | research | 453 | +0.69 | +0.0221 | 35.1% | 1.04 | 1,194 |
| 5m | **LOCKED** | 226 | **−7.75** | −0.0358 | 35.4% | **0.71** | 1,955 |
| 15m | research | 224 | +1.87 | +0.0494 | 38.4% | 1.07 | 1,037 |
| 15m | **LOCKED** | 107 | **−2.71** | +0.0483 | 37.4% | **0.93** | 1,446 |
| 30m | research | 133 | +5.18 | +0.0468 | 49.6% | 1.18 | 932 |
| 30m | **LOCKED** | 74 | +1.66 | +0.0024 | 41.9% | 1.04 | 764 |

The session box is what costs it: unconstrained, the same rules on 30m return **+26.71 points a
trade out of sample at PF 1.49**. This is the eighth independent time the intraday constraint has
removed the result on this branch, and the mechanism is the same one measured in the main study —
the median winner runs 2.1 hours against a median loser's 0.8, so a 12:00 flatten cuts off the tail
the trailing stop is paid in.

**The tap's verdict is unchanged inside the session**, which is the point of re-running it there.
15-minute, the only cell positive on both blocks:

| | research n | research R | LOCKED n | LOCKED R |
| --- | ---: | ---: | ---: | ---: |
| take every trade | 308 | +0.0555 | 149 | **+0.1004** |
| wait for KAMA 9 | 121 | +0.1737 | 49 | +0.0826 |
| blind limit, same distance (1.98 / 2.12 ×ATR) | 126 | +0.0912 | 52 | **+0.1648** |
| | | p 0.215 | | p 0.599 |

Out of sample **the blind limit beats the KAMA tap outright**, and in total R — what is actually
collected — taking every trade wins: **+15.0 R against the tap's +4.0**. Both findings from the main
study survive the session constraint intact: the distance prices the tap, and the tap loses to not
waiting.
