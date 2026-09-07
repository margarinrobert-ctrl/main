# A strategy generator, with this branch's failure modes designed in

The Build Alpha idea: don't hand the machine a strategy, hand it a library of **conditions** and a
library of **exits**, enumerate the combinations, and let a validation pipeline decide what
survives. `research/alpha_factory.py` does that. **38 conditions → 9,177 rules × 2 directions ×
6 exit geometries = 110,124 strategies, in 7 seconds.**

The speed comes from the two-phase trick used elsewhere on this branch: what happens if you enter
at bar *i* under exit geometry *g* does not depend on the entry rule, so it is computed once per
bar per geometry. A rule's backtest is then a walk over its trigger bars respecting one-position-
at-a-time — `O(triggers)`, not `O(bars × rules)`.

Every condition is causal (bar *i* uses bars up to and including *i*), fills are at the open of
*i+1*, and the first 250 bars are excluded so no indicator is trusted before it has warmed up.

## The pipeline is the product, not the winner

A generator without a validation pipeline is a machine for producing overfitted rules. Each stage
below exists because of a specific failure documented on this branch.

### 1. The selection curve

| research rank band | n | median research $ | median **LOCKED** $ |
| --- | --- | --- | --- |
| top 1 | 1 | 20,624 | **18,747** |
| top 10 | 10 | 19,834 | 12,743 |
| top 100 | 100 | 17,222 | 9,466 |
| top 1,000 | 1,000 | 12,251 | 4,302 |
| 24th–49th percentile | 19,571 | −7 | 15 |
| 49th–100th percentile | 39,142 | −5,848 | −2,474 |

**Rank correlation research vs locked: +0.632**, and the best-on-research strategy lands at the
**100th percentile** of locked P&L.

That is the opposite of everything else measured here — the 225,792-configuration parameter search
produced a rank correlation of **−0.079** and put its winner at the **13.4th** percentile. The
difference is what is being searched: **coarse, semantically meaningful conditions generalise;
fine-tuning a continuous parameter does not.** That is worth knowing, and section 3 explains most
of why the number is so high.

### 2. The winner, read once

> **LONG: ADX > 25 AND bullish bar**, stop 2.0×ATR, target 3.0R
> research **$20,624** → locked **$18,747**, 573 trades, PF 1.46, maxDD $6,382

Against BOS 30m's $8,932 and supply/demand preset A's $14,638 on the same locked block. It also
happens to be the single best locked result in the entire 110,124 — the hindsight maximum.

### 3. Section 4c, which explains the winner

| | n | median locked | best on research → locked |
| --- | --- | --- | --- |
| all | 78,283 | −$663 | $20,624 → $18,747 |
| **LONG rules** | 39,175 | **+$571** | $20,624 → **$18,747** |
| **SHORT rules** | 39,108 | **−$2,230** | $5,995 → **−$5,760** |

**100% of the top 100 on research are LONG.** The winner is "buy an uptrending market", and the
+0.632 rank correlation is largely the index's drift being reliably present in *both* blocks. A
search that is handed direction will find the drift, and it did — for the eighth time on this
branch.

### 4. The barrier bound, applied only where it is valid

With no time stop a trade runs to one barrier or the other, so a driftless path wins exactly
`1/(1+R)`. With a session flatten most trades touch neither and the bound is meaningless — the
IVB study made exactly that mistake and it is not repeated:

| geometry | n | mean win % | bound | **mean excess** |
| --- | --- | --- | --- | --- |
| stop 1.5×ATR, 1.0R, no time stop | 13,044 | 49.3 | 50.0 | **−0.75** |
| stop 1.5×ATR, 2.0R, no time stop | 13,012 | 33.7 | 33.3 | **+0.34** |
| stop 1.0×ATR, 2.0R, no time stop | 13,063 | 33.1 | 33.3 | **−0.23** |
| stop 2.0×ATR, 3.0R, no time stop | 12,929 | 25.2 | 25.0 | **+0.23** |
| stop 2.0×ATR, 1.0R, flat 16:00 | 13,122 | 46.9 | n/a | n/a |

**Averaged over the whole library, these conditions carry no directional information at all.** The
best excess in each row (+15 to +19) is selection, not signal.

### 5. The matched null — random rules, same trade counts

A bootstrap resamples a rising market and cannot detect a regime bet. A rule that fires at
**random bars** with the same count and the same exit inherits the drift and nothing else, so it
is the correct null here.

| geometry / side | real median locked | random median locked | real beats random |
| --- | --- | --- | --- |
| 1.0R, long | 676 | −2,131 | 77% |
| 1.0R, short | −2,653 | −4,292 | 69% |
| **2.0R, long** | **953** | **428** | **54%** |
| 2.0R, short | −1,655 | −4,247 | 73% |

At 2R long, the median real rule beats a random-entry rule only **54%** of the time. The library's
long-side "edge" is barely distinguishable from firing at random in the same market.

## 6. The one filter the drift cannot pass

Take each rule and geometry and require that **its LONG version and its SHORT version are both
positive on both blocks**. Drift helps one and hurts the other, so it cannot buy a pass.

| | count | share |
| --- | --- | --- |
| rule/geometry pairs scored on both sides | 39,089 | |
| LONG positive on both blocks | 16,978 | 43.4% |
| SHORT positive on both blocks | 1,772 | 4.5% |
| **BOTH sides positive on both blocks** | **113** | **0.3%** |

And the survivors have a shape:

| rule | geometry | LONG res / lock | SHORT res / lock |
| --- | --- | --- | --- |
| RSI14 < 30 AND bullish bar AND far from EMA200 | 2.0×ATR, 3R | 2,204 / 7,201 | 1,943 / 4,061 |
| ADX > 20 AND close < 10-bar low AND volume < 0.7× mean | 2.0×ATR, 3R | 2,503 / 5,216 | 1,776 / 3,224 |
| ATR rising AND close < 50-bar low | 1.5×ATR, 2R | 1,923 / 5,587 | 2,461 / 1,708 |
| close < 10-bar low AND volume < 0.7× mean | 2.0×ATR, 3R | 3,652 / 4,937 | 1,489 / 5,282 |
| RSI14 < 30 AND ADX > 25 AND body > 60% of range | 2.0×ATR, 3R | 2,236 / 2,910 | 2,397 / 1,557 |

Almost every survivor is built from **oversold, new lows, low volume, rising ATR**. The long and
short versions of the *same* condition both work, which means the condition is not predicting
**direction** — it is predicting **movement**. A quiet market at a new low, and then expansion.

**That is the first thing this branch has produced that is not a disguised long bet**, and the
generator found it without being told to look for it, which is the entire point of building it
this way.

## What is not being claimed

- **113 of 39,089 is 0.3%**, out of 110,124 strategies tried. That is a selection, and the usual
  discount applies.
- **The survivor list contains near-duplicates.** `close < 50-bar low` implies `close < 20-bar low`
  implies `close < 10-bar low`, so three of the rows above are the same trades. The effective
  number of distinct survivors is well under 113.
- **Both sides being profitable on the same trigger is a volatility payoff, and volatility
  clusters.** The whole sample is one instrument over three years; a quiet period would flatten
  this entirely.
- Nothing here has been tested out of this sample, and the two Pine strategies that met a real
  chart both disappointed. This is a candidate generator, not a conclusion.

## Reproduce

```
python3 research/alpha_factory.py     # 110,124 strategies, ~7 seconds
python3 research/alpha_validate.py    # selection curve, 4c, barrier bound, matched null
```
