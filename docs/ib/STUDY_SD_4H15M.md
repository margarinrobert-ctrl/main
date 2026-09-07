# The 4H-zone / 15M-confirmation strategy, tested as specified

The most precisely specified version supplied: a 4-hour demand or supply zone for *location*, a
15-minute rejection candle for *confirmation*, a stop at the zone edge plus 0.15 × ATR(15M), and a
2R target. Unlike the earlier documents this can be implemented without interpretation, so it was.

## As written, it loses

330 trades, **−$2,979, PF 0.94, win rate 34.2%.** Adding the "breaks the previous 15M high" filter
makes it worse: 308 trades, −$5,559, PF 0.88, **33.1%**.

The win rate is the whole story, and it needs the right yardstick.

## The yardstick: the driftless barrier bound

For a price path with no drift, the probability of touching the target before the stop is exactly
`1/(1+R)` — a property of the barrier geometry, not of the entry. **An entry rule that adds no
information scores exactly that.** At a 2R target the bound is 33.3%.

| | win rate | bound | excess |
| --- | --- | --- | --- |
| 4H zone + 15M confirmation, as specified | 34.2% | 33.3% | **+0.9** |
| with the "break previous 15M high" filter | 33.1% | 33.3% | **−0.2** |
| **BOS/CHoCH signal, same 2:1 barriers** | **44.0%** | 33.3% | **+10.7** |

Across all 28,136 configurations swept:

| target | bound | mean win rate | mean excess |
| --- | --- | --- | --- |
| 1.5R | 40.0% | 40.0% | **−0.00** |
| 2.0R | 33.3% | 33.9% | **+0.61** |
| 3.0R | 25.0% | 26.4% | **+1.36** |

Mean excess over every configuration: **+0.65 points**, with 54.9% of configurations positive — a
coin flip. The zone-plus-confirmation entry carries roughly **6% of the directional information**
the existing BOS signal does.

The document's own arithmetic is right — at 2:1 you only need 33.3% to break even before costs.
The problem is that 33.3% is what you get for *free*, and after costs you need more than the entry
rule delivers.

## The sweep, and a warning about what walk-forward cannot see

28,136 configurations over base length, base tightness, departure size, zone type, stop buffer,
target, the break filter, zone age, first-retest-only and side:

- **median locked: $1.** Nothing.
- best-on-research → locked **$8,122**, which looks excellent
- walk-forward on that winner: **0 negative folds of 6**, stitched OOS **$17,795**
- Monte Carlo: median $23,870, **P(net < 0) = 0.2%**

Every validation passes. And the winner is **long-only**, with a stop buffer of 1.0 × ATR rather
than the specified 0.15, a 3R target rather than 2R, no break confirmation, and zones up to twelve
days old. It is not the strategy in the document; it is a long bet on 2022-2025 NASDAQ wearing the
document's clothes.

Holding direction fixed (`RESEARCH_PROTOCOL.md` §4c):

| universe | best-on-research → LOCKED | median locked |
| --- | --- | --- |
| direction free | $15,606 → $8,122 | $1 |
| **both sides only** | $12,523 → **$4,316** | **$273** |
| long only | $15,606 → $8,122 | $1,044 |
| short only | $6,186 → **−$556** | −$1,115 |

Of the 7,322 configurations positive on both blocks, **54.7% are long-only against a 29.9% base
rate (lift 1.83)** and only 11.5% are short-only (lift 0.35).

**The methodological point is the important one.** Walk-forward returned six positive folds out of
six. Monte Carlo returned a 0.2% chance of losing money. Both were measuring a directional bet on a
market that rose through every fold and every bootstrap path. **Neither test can detect a regime
bet** — walk-forward because the regime spans all folds, the bootstrap because resampling a rising
market's daily returns produces more rising markets. Only holding direction fixed exposes it, and
doing so cuts the locked result from $8,122 to $4,316 and the median from $1,044 to $273.

## Verdict

There is a faint signal here — both-sides median locked of +$273 and a mean barrier excess of
+0.65 points are positive, not zero. But it is an order of magnitude weaker than the BOS/CHoCH book
on the same data (+10.7 points of excess, $8,932 locked), and the version that looks impressive is
a regime bet that three separate validation methods were unable to flag.

Not worth trading, and not worth combining: at this signal strength it would dilute the existing
book rather than diversify it.

Reproduce with `python research/sd_4h15m_battery.py`.
