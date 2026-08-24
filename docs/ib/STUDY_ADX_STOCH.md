# ADX and Stochastic on the BOS/CHoCH book — neither helps, and both fail mechanically

Two of the most commonly bolted-on filters, tested against the 2R book on MNQ 30m. Both were
pre-specified with a reason before any number was read:

- **ADX** — this is a trend-continuation rule, so it should work better when a trend is present,
  and ADX is the standard measure of that. If a trend filter cannot help a trend strategy, that is
  informative in itself.
- **Stochastic** — as an entry *veto*, not a signal: a break that fires while the oscillator is
  pinned at an extreme is a break with nothing left to run.

Sharpe below spans **every session** in its block with zero on non-trading days.

## Nothing beats doing nothing

| filter | research net | research Sh | LOCKED net | LOCKED Sh |
| --- | --- | --- | --- | --- |
| **baseline, no filter** | $2,747 | 0.66 | **$8,932** | **1.70** |
| ADX(14) > 20 | $1,661 | 0.44 | $7,496 | 1.49 |
| ADX(14) > 25 | $1,016 | 0.29 | $5,110 | 1.43 |
| ADX(14) > 30 | −$877 | −0.32 | $5,014 | 1.64 |
| ADX rising over 3 bars | **$3,168** | **0.95** | $6,262 | 1.38 |
| ADX > 20 AND rising | $1,619 | 0.55 | $4,272 | 1.00 |
| Stoch veto K>80 / K<20 | $902 | 0.67 | −$711 | −1.25 |
| Stoch veto K>70 / K<30 | $20 | 0.04 | −$350 | −0.88 |
| Stoch K > D alignment | **$3,345** | **0.81** | $5,370 | 1.34 |
| ADX>20 + Stoch veto 80 | $695 | 0.66 | −$711 | −1.25 |

The two filters that look **best** in research — ADX rising ($3,168) and Stochastic alignment
($3,345), both above the baseline's $2,747 — are the ones that degrade most out of sample. That is
now the ninth and tenth reproduction of this pattern in this work.

A wider sweep (476 cells: 3 ADX periods × 13 thresholds × rising on/off × 3 Stochastic periods × 6
veto levels) does not rescue it. The best cell on research returns **$2,138** on the locked block
against the unfiltered baseline's **$8,932** — searching cost **$6,794**. Only 36 of 476 (7.6%)
beat the baseline on the locked block, and **15 (3.2%) beat it on both** — fewer than independent
chance would produce.

## Why the Stochastic cannot work here — a structural failure, not a statistical one

Measured at the moment each signal fires:

| | n | median %K | at the extreme |
| --- | --- | --- | --- |
| LONG signals | 97 | **95.7** | 91.8% above 80 |
| SHORT signals | 68 | **5.4** | 95.6% below 20 |

A break of structure **is** a new extreme of the recent range, and %K measures exactly where the
close sits within that range. A bullish BOS therefore prints %K near 100 almost mechanically.
"Don't buy an overbought break" does not filter this strategy, it **deletes** it: 92 research
trades become 9, and 49 locked trades become 2.

The two ideas are contradictory by construction — the oscillator is measuring the same quantity the
entry rule is built on. No amount of threshold tuning fixes that, and none of the six veto levels
tested did.

This is the kind of conclusion that is invisible in P&L and obvious in a distribution. The veto
row simply looks like a bad filter with a small sample; only the %K histogram shows that the
sample is small *because the filter and the signal are the same variable*.

## Why ADX does not help

| bar population | median ADX | share > 25 |
| --- | --- | --- |
| all in-session bars | 26.4 | 56.5% |
| bars ≥ 1 ATR from the EMA (filter admits) | 27.1 | **58.8%** |
| bars < 1 ATR from the EMA (filter rejects) | 24.1 | **46.3%** |
| BOS signal bars | 27.1 | 63.0% |

The existing 1-ATR-from-EMA range filter is partly a trend filter already, so ADX is partly
redundant — but a 58.8% vs 46.3% shift is modest and does not on its own explain the damage.

The better explanation is visible in the table above: as the ADX threshold rises, the **count**
falls sharply (92 → 77 → 63 → 43 trades) while profit factor and win rate barely move. A filter
that changes *n* without changing the *profile* of what remains is not selecting anything — it is
sampling. And sampling a positive-expectancy set at random can only reduce the total.

That is the general form of the result, and it is worth stating plainly: **a filter earns its place
by making the surviving trades better, not fewer.** Neither of these did.

Reproduce with `python research/adx_stoch.py`.
