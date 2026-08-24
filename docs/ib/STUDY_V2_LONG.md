# V2 on the long side

*The ask:* take V2 — `EMA20 > EMA50 AND bearish engulfing (body ≥ 20%) AND 09:30–11:30 New York`,
short, 30-minute bars — and make it long only.

*The answer:* ticking "Allow longs" on that script loses **$7,717**. The mechanism does mirror,
but mirroring it means inverting every directional term, not the order. The mirrored rule wins
**71.7% on the holdout**.

---

## 1. Why the switch is not the answer

Every emitted script carries this tooltip on its direction inputs:

> This rule was measured in ONE direction against that direction's own base rate. Flipping it
> does not give you the mirror-image edge — longs and shorts start from different base rates on a
> market that trended, and the other side of this rule was not tested.

That is a claim, so it was tested. Three long candidates, all on 30-minute bars in the same
09:30–11:30 window, each swept over all 18 stop × flatten geometries on the **research block
only** and scored against the base win rate of a *long* at that geometry:

| | rule | what it means |
| --- | --- | --- |
| **A** | `EMA20 > EMA50 AND bearish engulfing`, **long** | the same trigger, bought instead of sold — a dip buy |
| **B** | `EMA20 < EMA50 AND bullish engulfing`, long | the **true mirror**: every directional term inverted |
| **C** | `EMA20 > EMA50 AND bullish engulfing`, long | uptrend, up bar, bought — what you would write from scratch |

The long base rate matters here and is the reason a flipped short can look survivable. At V2's own
geometry the base for a short is 43.9% and for a long **47.5%** — NQ rose 89% over this sample, so
a long starts nearly four points ahead before any rule is applied.

## 2. Research block, at V2's own geometry (1.0×ATR stop, 1R, flat 16:00)

| | dir | n | win % | base for that side | excess | research $ |
| --- | --- | --- | --- | --- | --- | --- |
| V2 as shipped | short | 125 | 60.8 | 43.9 | **+16.9** | 1,842 |
| **A** same trigger, long | long | 125 | **37.6** | 47.5 | **−9.9** | **−3,042** |
| **B** true mirror | long | 104 | 57.7 | 47.5 | +10.2 | 1,905 |
| **C** long-natural | long | 145 | 54.5 | 47.5 | +7.0 | 682 |

A is not merely unprofitable, it is nearly ten points *below* the base rate — which is what being
on the wrong side of a real edge looks like, and is itself the best evidence that V2's short edge
is real.

## 3. Best geometry for each, chosen on research

| | stop | flat | n | win % | base | excess | research $ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| V2 as shipped | 1.0 | 16:00 | 125 | 60.8 | 43.3 | +17.5 | 1,862 |
| A same trigger, long | 4.0 | 15:00 | 106 | 52.8 | 48.4 | +4.4 | −1,789 |
| **B true mirror** | **2.5** | **15:00** | **86** | **65.1** | 48.9 | **+16.2** | **4,706** |
| C long-natural | 4.0 | 16:00 | 123 | 56.9 | 48.2 | +8.7 | 3,286 |

B is chosen on research: highest excess of the three long candidates, and the only one whose
research dollars come with a win rate well clear of its base. The whole selection is 3 candidates
× 18 geometries = 54 research-block evaluations, and nothing below was consulted in making it.

## 4. The locked block, read once

| | trades | locked n | locked win % | base | excess | net $ | locked $ | PF |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V2 as shipped | 201 | 76 | 60.5 | 43.3 | +17.2 | 4,352 | 2,490 | 1.59 |
| A same trigger, long | 171 | 65 | **40.0** | 48.4 | **−8.4** | **−7,717** | **−5,928** | 0.62 |
| **B true mirror** | **139** | **53** | **71.7** | 48.9 | **+22.8** | **9,575** | **4,868** | **2.12** |
| C long-natural | 185 | 62 | 56.5 | 48.2 | +8.2 | 913 | −2,373 | 1.05 |

A's holdout loss is the same shape as its research loss, so this is not variance. C's research
edge does not survive at all.

---

## 5. B put through the same battery as the other four

### Where the money comes from

| exit | n | share | net $ | of net |
| --- | --- | --- | --- | --- |
| target | 50 | 36% | +13,414 | 140% |
| stop | 23 | 17% | −6,164 | −64% |
| time stop | 66 | 47% | +2,325 | 24% |

A barrier strategy, not a drift bet. (Compare A, whose 76% of trades exit at the time stop for a
net of −$54 — it is being carried entirely by its stop losses.)

### Matched control — random longs, same geometry, same minute-of-day distribution

| | n | win % | control | p | net $ | control $ | p |
| --- | --- | --- | --- | --- | --- | --- | --- |
| research | 86 | 65.1 | 53.4 | 0.017 | 4,706 | 709 | 0.010 |
| **locked** | 53 | 71.7 | 55.4 | **0.005** | 4,868 | 601 | **0.020** |
| A, locked | 65 | 40.0 | 57.6 | 1.000 | −5,928 | 1,014 | 0.995 |
| C, locked | 62 | 56.5 | 56.0 | 0.476 | −2,373 | 1,052 | 0.920 |

A random long in that window with a 2.5×ATR stop wins 55.4% and makes $601. B wins 71.7% and
makes $4,868 on the same trades' worth of exposure.

### Each condition against a random filter of the same selectivity, locked block

| condition dropped | rule $/trade | random $/trade | p |
| --- | --- | --- | --- |
| EMA20<EMA50 | 92 | 15 | **0.001** |
| bullish engulfing, body≥20% | 92 | 28 | **0.048** |
| 09:30–11:30 New York | 92 | −4 | **0.001** |

All three carry information on the block they were not selected on.

### Corners

| EMA20<EMA50 | bullish engulf | 09:30–11:30 | n | win % | net $ | PF |
| --- | --- | --- | --- | --- | --- | --- |
| **yes** | **yes** | **yes** | **139** | **67.6** | **9,575** | **2.12** |
| yes | NO | yes | 457 | 51.6 | 2,570 | 1.06 |
| NO | NO | yes | 616 | 52.4 | −560 | 0.99 |
| NO | yes | yes | 190 | 53.2 | −1,570 | 0.90 |
| yes | yes | NO | 1,231 | 46.8 | −5,913 | 0.90 |

One live corner; every other combination sits at or below the base rate. Being long in that
window with no conditions loses money.

### Execution, costs, resampling

| | |
| --- | --- |
| engine → true 1-minute path → +refill | $9,575 → $9,470 → $8,549 |
| $/trade at 1× / 2× / 3× measured costs | 92 / 89 / 86 |
| breakeven cost multiple | **30.9×** |
| block bootstrap, 53 locked trades | 5th pct $2,419, median $4,785, P(net<0) **0.00** |
| 6 walk-forward folds | 2,233 · 1,089 · 745 · 819 · 2,345 · 2,344 — **6/6 positive** |

### Against V2

B requires `EMA20 < EMA50` and V2 requires `EMA20 > EMA50`, so **the two can never fire on the
same bar**. They share 1 trading session out of 136, correlation −0.01. Run together: 340 trades,
$13,966 net, Sharpe 2.19, max drawdown $1,367.

---

## 6. What the mechanism is

V2 and B are one idea seen from both sides: **fade the first sharp counter-trend bar of the
morning**. In an uptrend, a decisive down bar in the first two hours is sold; in a downtrend, a
decisive up bar in the same window is bought. Both take the position *against* the engulfing bar
and *with* the prevailing trend — which is why "the same trigger, long" (A) is not a variant of it
but its exact opposite, and loses accordingly.

The clock condition is not decoration: outside 09:30–11:30 the same setup loses money on both
sides (V2's corner table, and B's `yes yes NO` corner at −$5,913).

## 7. What to run

* **`pine/more1R/V2L_strategy.pine`** — the long side, ready to load. 139 trades, 67.6% win
  against a 48.9% long base, PF 2.12, 71.7% on the holdout, breakeven at 30.9× costs.
* **`pine/more1R/V2_strategy.pine`** — the short side, unchanged.
* Do **not** tick "Allow longs" on V2 itself. That is candidate A, and it is measured above.

One caveat that applies to B and not to V2: B fires in downtrends, and this sample contains three
years of a market that rose 89%. 53 holdout trades is a real number but it is 53, and the regime
that produces them was the minority regime here.

Measured on MNQ, 2022-12-26 → 2025-12-12, one contract, $1.00 commission per round turn, one tick
spread plus one tick slippage each side, one extra tick on stops. Research tooling for education
and analysis, not financial advice.
