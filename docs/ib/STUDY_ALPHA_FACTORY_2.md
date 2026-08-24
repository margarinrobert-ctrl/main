# 16.2 million strategies, and the collapse that only an honest holdout shows

The generator scaled up: **115 conditions, 253,575 rules of up to three conditions, 2 directions,
32 exit geometries — 16,228,800 strategies, swept in 93 seconds.** 147× the first build.
12,050,899 of them have enough trades to score.

The speed comes from packing every condition into uint64 **bitsets** (combining three conditions
is 559 word-ANDs, not 35,721 byte-ANDs), precomputing what happens if you enter at bar *i* under
exit geometry *g* once per bar, and running the whole enumeration inside one parallel numba kernel
with no Python per rule.

## What 147× more searching bought

| | first build (110,124) | this build (16,228,800) |
| --- | --- | --- |
| best on research → locked | $20,624 → $18,747 | **$25,397 → $8,490** |
| research/locked rank correlation | +0.632 | +0.549 |
| median locked, all scored | −$663 | −$743 |
| top-1,000 on research that are LONG | 100% | **100%** |

The winner is `LONG ATR>1.2× mean AND vol rising AND dist EMA200>2 ATR` at a 3R target. **Every
one of the top 1,000 is long.** Section 4c holds at 147× the search width, which is the eighth
independent time on this branch.

## The methodological trap, walked into and then out of

The first pass through this analysis defined a "direction-neutral" candidate as one whose long
*and* short versions were positive **on both blocks**. That filter reads `locked > 0`, which makes
the locked block part of the **selection criterion**. The portfolio built that way reported:

> full $172,279 · **locked $95,562, Sharpe 3.59, 0 negative folds of 7**

**That number is meaningless** and it is recorded here only because it is exactly the mistake this
repository exists to catch, and it was made anyway, at the last step, after everything else was
done correctly.

Selecting on the **research block alone** and reading the locked block once:

| | selected on both blocks *(wrong)* | selected on research only *(honest)* |
| --- | --- | --- |
| research | $76,717 | $127,072 |
| **LOCKED** | **$95,562** | **$10,812** |
| locked Sharpe | 3.59 | **0.36** |
| locked net/drawdown | 10.44 | **0.77** |
| locked max drawdown | $9,149 | **$14,043** |

Five of the twelve survivors are **negative** on the locked block. The apparent edge was the
selection.

## The diagnostic that says it cleanly

Of the **98,353** rule/geometry pairs whose long and short versions are both profitable on the
research block, read once on the locked block:

| | count | share |
| --- | --- | --- |
| long side still positive | 52,007 | 52.9% |
| short side still positive | 44,661 | 45.4% |
| **both still positive** | **15,165** | **15.4%** |
| *chance, if the two sides were independent* | | *24.0%* |

**Passing both sides on the research block makes a candidate *less* likely than chance to pass
both on the locked block.** Research-block direction-neutrality does not transfer. That is the
single most useful number the generator has produced.

## The de-duplication step, which is worth keeping

A search this wide returns the same trade fifty times with a different label. Candidates are kept
greedily, strongest on research first, only if their daily P&L correlates below 0.30 with
everything already kept. From the top 600 research candidates, **12 distinct strategies** survive,
with mean pairwise correlation **+0.060** and **11.07 effective bets of 12**.

That machinery works and is reusable. What it produced this time does not survive the holdout.

The survivors also share a shape worth noting, the same one the small build found: **RSI7 below
25, closes below Keltner or a 5/10-bar low, expanding ATR or Bollinger width, two down closes** —
oversold conditions with volatility expanding, run in both directions at a 3R target. The family
is consistent across two independent searches. Its out-of-sample performance is not.

## What this build is for

Not for its winner. For three things it does that a list of winners cannot:

1. **It prices the search.** 16.2M strategies, and the selection curve, the direction split and
   the barrier bound all say the same thing about what that search is finding.
2. **It de-duplicates.** 600 candidates → 12 distinct, by correlation rather than by name.
3. **It refuses to launder the holdout.** The two tables above differ by one line of code and by
   a factor of nine in the number they report.

## Reproduce

```
python3 research/alpha_factory2.py     # 16,228,800 strategies, ~93 seconds
python3 research/alpha_validate2.py    # selection curve, 4c, de-duplication, portfolio
```
