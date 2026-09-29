# V19 — an attempt to destroy the one rule that replicated, and what was left standing

**The rule I set out to confirm failed. What replaced it is simpler, older, and survives harder
tests — but its timeframe was chosen post-hoc and it does not clear its own multiplicity.**

---

## 1. The frozen test, and its failure

V17's finding — a Donchian breakout pays only when the close is also above the last completed
09:30–16:00 session's high — was the only thing on this branch that had ever replicated. It was
frozen exactly as shipped and run on four markets that had no part in finding it.

| market | span | n | EV (R) | PF | Sharpe | Sortino |
| --- | --- | --- | --- | --- | --- | --- |
| US30 | 2024-08→2026-08 | 256 | −0.0445 | 0.921 | −0.26 | −0.27 |
| **US100** | 2024-08→2026-08 | 254 | **+0.1962** | **1.421** | 1.01 | 1.29 |
| US30L | 2016-10→2025-07 | 1,137 | −0.0218 | 0.962 | −0.14 | −0.14 |
| XAU | 2004-06→2026-01 | 2,843 | −0.0117 | 0.979 | −0.07 | −0.07 |
| *NQ (where it was found)* | | 367 | *+0.2840* | *1.635* | *1.45* | *1.93* |

One of four. And the one that works is the Nasdaq-100 — the same index NQ tracks.

**It is not independent evidence.** 59.9% of NQ's signal bars are *also* US100 signal bars at the
identical timestamp; 83.6% within ±2 bars. Splitting US100 at the end of NQ's data:

| US100 period | n | EV (R) | PF | Sharpe |
| --- | --- | --- | --- | --- |
| overlaps NQ | 158 | **+0.2952** | 1.684 | 1.48 |
| after NQ's data ends | 96 | **+0.0334** | 1.064 | 0.18 |

The entire result lives in the period that duplicates trades already counted. **One footing, not
two.** V17's feature is dead as a general rule.

---

## 2. The diagnosis: cost, not absence of edge

| market | EV with costs | EV at zero cost | cost as % of stop |
| --- | --- | --- | --- |
| US30 | −0.0445 | **+0.0373** | 8.1% |
| US100 | +0.1962 | +0.2310 | 3.1% |
| US30L | −0.0218 | **+0.1125** | 11.2% |
| XAU | −0.0117 | **+0.1029** | 9.8% |

Gross-positive everywhere. The rule did not lack an edge; it lacked an edge large enough for its own
cost. The only axis that changes cost-in-R with a mechanism is **bar size** — and the arithmetic is
neutral, because cost-in-R and gross-edge-in-R shrink by the same factor. Anything that moves net is
a property of the market.

| EV (R) | 15m | 30m | 60m |
| --- | --- | --- | --- |
| US30L (8.5 yr) | −0.0218 | +0.0663 | **+0.2511** |
| US30 | −0.0445 | +0.0483 | **+0.2177** |
| XAU (22 yr) | −0.0117 | +0.0568 | **+0.1154** |
| US100 | +0.1962 | +0.0376 | **−0.0793** |

Monotone on three, **inverted on the Nasdaq one** — consistent with the 15-minute result having been
the NQ artifact. The *gross* edge rises too (US30L +0.113 → +0.316), so this is not cost arithmetic.

**Drop-one then removed V17's own feature.** At 60 minutes the session-high filter earns nothing, and
on the 8.5-year history removing it *improves* the rule (+0.2511 → +0.2554, control p 0.005 → 0.001).
On gold both filters hurt.

---

## 3. Three findings that said "this is just drift"

**The short mirror loses what the long side wins:** US30L +0.2511 long against −0.1650 short; US30
+0.2177 against −0.2715; gold +0.1154 against −0.0080.

**The edge lives entirely above the 200-day:**

| market | above 200d | below 200d |
| --- | --- | --- |
| US30L | +0.2689 (259 trades) | +0.0210 (61) |
| XAU | +0.2062 (651) | −0.0464 (227) |
| US30 | +0.1575 (52) | −0.0544 (10) |

**And a minute-of-day control on 60-minute bars is a weak null** — about seven distinct minutes to
match on, so it prices the clock and not the direction.

---

## 4. The test that decided it

The rule was restricted to the up state and scored against a control drawn from **the same up-trend
bars** — the honest null for a regime-conditional rule.

| market | trades | rule R | control median | p | excess per trade |
| --- | --- | --- | --- | --- | --- |
| US30L (8.5 yr) | 263 | +72.3 | +21.9 | **0.004** | **+0.192** |
| XAU (22 yr) | 659 | +141.5 | +78.8 | **0.032** | **+0.095** |
| US30 (2 yr) | 53 | +7.4 | +1.6 | 0.241 | +0.108 |

And against the blunter baseline — **every** eligible bar in the same up state with identical
geometry, no breakout at all: US30L +0.2750 vs +0.0531, XAU +0.2148 vs +0.0948, US30 +0.1391 vs
+0.0083. **The breakout adds +0.12 to +0.22 R per trade over simply being long in that regime.**

---

## 5. The surviving configuration

Donchian 55 up-break, **60-minute** bars, only above the instrument's own 200-day average,
ADX(14) ≥ 25, stop at the nearer of 2.5 × ATR(20) and the 20-bar low, **no target**, market order,
one unit, long only.

| market | span | n | EV (R) | PF | win% | net R | maxDD | MAR | Sharpe | Sortino | Ulcer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| US30L | 2016-10→2025-07 | 263 | **+0.2750** | **1.597** | 44.1 | +72.3 | 15.5 | 4.67 | 0.90 | 0.65 | 6.48 |
| XAU | 2004-06→2026-01 | 659 | **+0.2148** | **1.474** | 39.9 | +141.5 | 12.7 | 11.17 | 0.71 | 0.59 | 4.97 |
| US30 | 2024-08→2026-08 | 53 | +0.1391 | 1.290 | 37.7 | +7.4 | 7.0 | 1.06 | 0.56 | 0.38 | 2.91 |
| US100 | 2024-08→2026-08 | 63 | −0.0723 | 0.876 | 20.6 | −4.6 | 13.6 | −0.34 | −0.30 | −0.23 | 7.11 |

* **Bootstrap** P(mean daily R ≤ 0): US30L **0.0034**, XAU **0.0005**, US30 0.268.
* **Walk-forward**, US30L by year: +15.0, +18.8, −4.0, +0.9, −1.4, −1.6, +8.7, +27.8, +8.1 —
  **6 of 9 positive**, losses small, but 2024 alone is 38% of the total.
* **Cost stress**: still +0.138 (US30L), +0.109 (XAU), +0.049 (US30) at **3×** the assumed friction.
* **Perturbation**, US30L: entry length 40/45/55/65/75 → +0.317/+0.289/+0.275/+0.266/+0.321 (flat —
  the Donchian length is *not* the mechanism); exit channel rises to 25 (+0.406); stop falls with
  width (1.75N → +0.336). **The shipped cell is deliberately not the peak on either axis.**

---

## 6. What is wrong with it

1. **The timeframe was chosen after looking.** Three were compared and 60 minutes won. No downstream
   testing repairs a post-hoc choice.
2. **It does not clear its own multiplicity.** This session took roughly sixty looks; Bonferroni
   needs ≈0.0008 and the best control p is 0.004.
3. **Not established on the Nasdaq.** US100 is negative at every 60-minute setting tested.
4. **Realised drawdown was lucky.** Monte Carlo median 22.4R against a realised 15.5 (US30L) and
   38.6 against 12.7 (XAU), p99 **60.8R and 98.8R**. Size for the p99.
5. **The daily filter is 98.0–99.0% identical** between the research construction and what a script
   can build; the residual is day-boundary bars, and it is a real difference, not noise.
6. **It is a drift harvester that beats its own drift.** In a bear market it will not trade.

## Files

`research/v19/v19frozen.py` (the frozen rule, four markets) · `v19destroy.py` (overlap, zero-cost,
controls) · `v19scale.py` (the timeframe axis) · `v19attack.py` (drop-one, perturbation,
walk-forward, cost stress, MC) · `v19drift.py` (short mirror, trend split, out-of-sample) ·
`v19verdict.py` (the regime-matched control) · `v19ship.py` · `v19_parity.py` ·
`pine/turtle/V19_H1_TREND_BREAKOUT_strategy.pine`.
