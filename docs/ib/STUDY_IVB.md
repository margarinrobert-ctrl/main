# Initial Value Breakout — which component actually carries the edge

The specification asked for exactly the right test: **IVB alone vs IVB + retest vs IVB + retest +
trend filter**, so that it is possible to see whether each component adds an edge rather than
just making the chart look better. That ran first, before any parameter search.

Setup throughout: 09:30–10:30 initial value, IVH/IVL from the opening period, 30-minute bars,
target 1.5× the initial range, flat at 15:45, both sides, MNQ at 1 contract with $1.00 commission,
1 tick spread + 1 tick slip each side, 1 extra tick on stops. Research block = first 65% of
sessions, locked block read once.

## 1. The ladder — three of the five steps make it worse

| step | trades | net $ | PF | win % | research | LOCKED | maxDD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1. break and go at the next open | 675 | 2,697 | 1.06 | 44.0 | 2,456 | 241 | 4,527 |
| 2. + wait for a retest of the level | 522 | **1,530** | 1.04 | 45.8 | −1,036 | 2,566 | 2,892 |
| 3. + stop below the retest bar | 523 | **−994** | 0.97 | 30.6 | −2,459 | 1,465 | 3,464 |
| 4. **+ the 60m trend must agree** | 258 | **4,086** | **1.33** | 37.2 | 1,729 | 2,357 | 1,209 |
| 5. + opening range in the 20th–80th percentile | 141 | 4,164 | **1.66** | 37.6 | 1,263 | 2,901 | **901** |

**The retest hurts** (−$1,167), and **the structure stop hurts more** (−$2,524, and the win rate
collapses from 45.8% to 30.6% — a stop below the retest bar is inside the noise). The higher-
timeframe trend filter is worth **+$5,080** on its own and turns a losing rule into a winning one.
The range-size filter adds little P&L but halves the trade count and cuts drawdown by a quarter.

This is the opposite of what the specification expected, and the opposite of the branch's own
Initial-Balance finding that pullback entries beat breakout entries. It reverses here.

## 2. A methodology correction, stated before the numbers that depend on it

The first pass reported the win rate against the driftless barrier bound, `1/(1+R)` — the standard
diagnostic everywhere else on this branch — and it produced spectacular figures: **+17.4 points of
excess at 1.5R, +23.4 at 2.0R, +31.7 at 3.0R.** All of it was an artifact.

The giveaway was that the win rate barely moved with the target: 57.4% at 1.5R, 56.7% at 2.0R,
**56.7% at 3.0R**. A more distant target cannot be reached as often. Counting how trades actually
end explains it:

| target | ends at the stop | ends at the target | **flattened at 15:45** | % reaching the target |
| --- | --- | --- | --- | --- |
| 1.0R | 33 | 58 | 50 | 41.1% |
| 2.0R | 36 | 25 | 80 | 17.7% |
| 3.0R | 36 | 6 | **99** | **4.3%** |

**The barrier bound assumes the trade runs until one of the two barriers is hit. This strategy has
a time stop, so most trades never touch either.** At a 3R target 70% of trades are closed by the
session cutoff, and the "win rate" is measuring "closed positive at 15:45", not "hit the target".
The bound does not apply and those excess figures are meaningless. They are recorded here because
the mistake is easy to repeat.

The correct null for a time-stopped rule is a **matched control**, below.

## 3. Is the trend filter real? The shuffled control

Take the rule exactly as it is and randomise only the *assignment* of the 60-minute trend to
sessions. This preserves the trade count, the long/short balance and the marginal distribution of
the filter — everything except the information.

| | trades | net $ |
| --- | --- | --- |
| **the real 60m trend** | 141 | **4,164** |
| 2,000 shuffles | 132 avg | mean 385, p5 −1,793, p95 2,658 |

**The real trend beats 99.7% of shuffles — empirical p = 0.0035.** It beats **97.5%** on the
research block and **97.7%** on the locked block *separately*, so no single block is carrying it.

The mirror image is the confirmation a real conditioning variable should give:

| | trades | net $ | PF | win % |
| --- | --- | --- | --- | --- |
| trend must AGREE | 141 | **4,164** | 1.66 | 37.6 |
| no filter | 289 | 479 | 1.03 | 29.4 |
| trend must **DISAGREE** | 168 | **−4,043** | **0.63** | 23.2 |

And it is not a long bias — **section 4c passes cleanly**, both sides positive: longs $2,707,
shorts $1,458.

### It helps everywhere, not only where it was found

The same filter applied to **eighteen different base configurations** — different entries, stops,
targets, bar sizes, initial-value windows, cutoffs:

**18 of 18 improve**, by **+$1,650 to +$6,472**.

## 4. The best simple version

Keeping the ladder steps that helped and dropping the ones that did not:

> 09:30–10:30 initial value → a 30-minute close beyond **IVH/IVL** → enter at the next open (**no
> retest**) → stop at the **opposite edge** of the initial value range → target **1.5× the range**
> → **the 60-minute trend must agree** → opening range between the 20th and 80th percentile of the
> trailing 60 sessions → flat at 15:45, both sides.

| | trades | net $ | PF | win % | research | LOCKED | maxDD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **the version** | 211 | **10,013** | **1.95** | 57.8 | **5,905** | **4,108** | **1,469** |
| longs only | 136 | 6,293 | 2.12 | 61.0 | 4,588 | 1,706 | 703 |
| shorts only | 75 | 3,720 | 1.75 | 52.0 | 1,317 | 2,402 | 1,443 |
| no trend filter | 371 | 1,949 | 1.07 | 49.1 | 859 | 1,090 | 2,437 |
| trend must disagree | 193 | **−9,344** | **0.56** | 36.8 | −6,092 | −3,252 | 6,092 |

Return over drawdown is **6.8**, against the BOS 30m leg's 4.08 on the same data.

## 5. What was rejected

- **Strategy B, the failed breakout** (break out, close back inside, fade it): −$2,823 to −$3,617
  across every target tested, with a locked block near **−$3,900** in all of them. Not marginal.
- **The volume-profile variant (§10 of the specification)** — breaking the opening **value area**
  edge instead of the high/low: **−$3,445** break-and-go against **+$2,697** for the high/low, and
  −$1,249 against −$994 with a retest. The variant flagged as "particularly interesting" is the
  worse of the two. It survives the trend filter (+$5,427) but still trails the high/low version.
- **A 15- or 30-minute initial value**: both worse than 60 minutes at every step tested.

## 6. What it adds to the book

| | BOS 30m | BOS 60m | S/D A | S/D B | IVB |
| --- | --- | --- | --- | --- | --- |
| **IVB** | 0.08 | 0.16 | 0.08 | 0.04 | 1.00 |

**Effective number of bets 4.85 of 5, PC1 29%.**

| book | block | net $ | maxDD | Sharpe |
| --- | --- | --- | --- | --- |
| without IVB | full | 65,950 | 6,202 | 2.19 |
| **with IVB** | full | **75,962** | **6,459** | **2.43** |
| without IVB | LOCKED | 35,931 | 6,202 | 2.59 |
| **with IVB** | LOCKED | **40,039** | **6,459** | **2.79** |

**+$10,012 for +$257 of drawdown** — the cheapest addition measured on this branch, because the
leg is nearly uncorrelated with everything and carries a $1,469 drawdown of its own.

## What is not being claimed

- **Scale.** $10,013 over three years on one MNQ contract is about **$3,300 a year**. It is an
  edge; it is not a living.
- **Selection.** The trend filter's p = 0.0035 comes from a proper null and the 18-of-18 table is
  strong evidence for *that component*. The stop and target choices were made by looking at a
  table, and carry the usual selection discount.
- The win rate here is **not** comparable to `1/(1+R)`, for the reason in section 2, and should
  not be quoted alongside win rates from the BOS or supply/demand studies.

## Reproduce

```
python3 research/ivb_ladder.py    # the component ladder, strategy B, the section-10 variant
python3 research/ivb_leg.py       # the leg's correlation with the book and what it adds
```
