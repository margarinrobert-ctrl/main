# Trading this live

The backtest is not a different thing from live trading. This rule evaluates on the close of a
30-minute bar and fills at the next bar's open — both of which happen in real time exactly as they
happen in the test. What follows is the operating procedure, and then the parts that genuinely do
differ.

## The procedure

At each 30-minute close between **10:00 and 15:00 ET** — eleven decision points a day, at fixed
clock times — the alert fires if all of these hold:

1. price closed beyond a confirmed swing pivot (3 bars either side), and
2. it is the **second** such break in the same direction since the structure last flipped, and
3. price is on the trend side of the EMA-200, and
4. price is **at least 1 ATR away** from the EMA-200, and
5. the next bar is still inside the session.

Then: place a **market order**, take the next bar's open, set a stop at **2 × ATR(14)** from your
actual fill, and a target at **2 × that risk**. No CHoCH exit. Then leave it alone.

Nothing there needs interpretation. If you find yourself deciding, you have left the strategy.

**Alert setup:** create the alert with **"Once per bar close"**. Any other frequency fires on an
unconfirmed intrabar break and turns this into the losing variant documented in the script header
(PF 1.58 → 0.56 on a live chart).

**Do not enter mid-bar.** An entry taken twenty minutes into a 30-minute bar is a different trade
from the one that was tested.

## The arithmetic nobody enjoys

Measured, one MNQ contract, Dec 2022 – Dec 2025:

| | both sides, 2R | longs only (reported) |
| --- | --- | --- |
| trades | 141 (47/yr, **3.9 a month**) | 94 (31/yr, **2.6 a month**) |
| net | $11,679 | $4,485 |
| per trade | $83 | $48 |
| **per year, one contract** | **$3,893** | **$1,495** |

On a $100,000 account that is **1.5%–3.9% a year on one contract**. This is not a living. It is a
small, positive, low-frequency edge, and the honest way to describe the experience of trading it is
**long stretches of nothing** punctuated by two to four trades a month.

## Sizing — off the drawdown distribution, not the realised path

The realised max drawdown was $2,865 per contract. The Monte Carlo **p95** was **$4,532**. Size off
the p95; sizing off the realised figure overstates capacity by 58%.

| account | drawdown you will actually sit through | contracts | ~per year | p95 drawdown |
| --- | --- | --- | --- | --- |
| $25,000 | 20% | 1 | $3,893 (15.6%) | $4,532 |
| $50,000 | 10% | 1 | $3,893 (7.8%) | $4,532 |
| $50,000 | 20% | 2 | $7,786 (15.6%) | $9,064 |
| $100,000 | 10% | 2 | $7,786 (7.8%) | $9,064 |
| $100,000 | 20% | 4 | $15,572 (15.6%) | $18,128 |

## What genuinely differs live

1. **Stop gaps.** The test fills the stop at the stop price plus one tick. A gap through a 2 × ATR
   stop — an overnight headline, a CPI print — fills wherever the market is. This is the single
   largest optimistic assumption in the whole study, and it cannot be measured from bar data.
2. **This is not an intraday strategy.** Median hold is **12.5 hours**; 35% of trades cross the
   close and 20% run two or more sessions. You need overnight margin, and a prop-firm
   flat-by-close rule makes the tested spec untradeable as written (the `flatEOD` variant exists
   for that, at roughly half the P&L — see `STUDY_PINE_DIVERGENCE.md`).
3. **One instrument, one regime, three years.** 2022-2025 NASDAQ trended up throughout. The
   long-only variant is a bet on that continuing, not an edge — 76.5% of every configuration that
   beat the spec on both blocks was long-only (`RESEARCH_PROTOCOL.md` §4c).
4. **The statistics do not clear a bar.** PBO 0.571, t = 1.88 against a ~2.7 multiple-testing
   hurdle, and the 2R target's own paired t is +1.22. Profitable and out-of-sample positive; not
   established.

## Time-of-day: two tested ideas, one useful

**Filtering by hour: no.** Every hour bucket flips sign across the research/locked boundary. 10:00
looks best in research ($2,825) and returns $334 locked; 13:00 is −$1,074 research and +$4,654
locked. There is no hour-of-day structure to exploit here.

**Starting the session earlier: only to 09:00.** Locked profit factor degrades monotonically the
earlier entries are allowed:

| session (ET) | research PF | locked PF |
| --- | --- | --- |
| 09:30-16:00 (current) | 1.25 | **2.23** |
| 09:00-16:00 | 1.37 | **2.10** |
| 08:00-16:00 | 1.23 | 1.85 |
| 07:00-16:00 | 1.24 | 1.77 |
| 03:00-16:00 | 1.12 | 1.40 |
| 24 hours | 1.02 | 1.56 |

09:00 buys ~10% more trades at essentially unchanged quality and is defensible. 08:00 and earlier
buys trade count with edge. Pre-market breaks happen in thin liquidity, where a swing pivot carries
less information — which is what the monotone decay is showing.

To use the 09:00 start, set `sessStart = 540`. Nothing else changes.
