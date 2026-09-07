# Initial Value Breakout — a look-ahead, found and removed

> ## RETRACTION, 2026-08-23
>
> **The headline result of this study was a look-ahead bug. IVB has no measurable edge and is not
> in the book.**
>
> `session_index` runs a session from 09:30 to 09:30, so a 60-minute bar at 08:00 on calendar day
> D carries the session id of day **D−1**. Keying the higher-timeframe trend filter by that bar's
> own session id therefore handed each session a bar that closed at **09:00 the following
> morning** — after its entire trading window. It applied to **609 of 609 sessions**, a roughly
> 23-hour look-ahead.
>
> It was caught by building a Python mirror of the intended Pine script and finding it could not
> reproduce the engine: with both filters off the two matched exactly (675 trades, $2,586), and
> with the trend filter on they read **$17,890 against −$1,474**. The trend filter was the only
> place they could disagree, and the reason it disagreed is that the Pine could only see this
> morning's bar.
>
> | | as published | **corrected** |
> | --- | --- | --- |
> | ladder step 4 (+ trend filter) | $4,086 | **$574** |
> | ladder step 5 (+ range filter) | $4,164 | **−$105** |
> | best version | **$10,013**, PF 1.95 | **−$1,287**, PF 0.91 |
> | shuffle test | beat 99.7% of shuffles, p = 0.0035 | beat **18.1%**, **p = 0.82** |
> | trend must DISAGREE | −$4,043 | **+$1,984** |
>
> The shuffle test was a correct null and it did its job — it detected a variable that genuinely
> predicted the trading day, because the variable was measured after the trading day. **A correct
> null cannot tell you the data is from the future.** Only reconstructing the rule bar-by-bar,
> the way an execution engine would have to, exposed it.
>
> The corrected engine is in `research/ivb.py` with the fix and its reasoning inline. Everything
> below the line is the original study, kept so the failure is legible; **every figure in it that
> involves the trend filter is wrong.**

---


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

---

# Addendum — the opening window, and the two confirmations that were never tested

Prompted by a report that the shipped script "starts at 10:30". It does not, and the confusion is
mine: every message describing this strategy used a **60-minute** initial value, and the script
that shipped uses **15**, because 15 is what tested best. That change was in a tooltip and not in
the summary.

## The terminology, checked against the sources

These are two different things and the literature is consistent about it:

- **Opening Range Breakout (ORB)** — the high and low of the first **5–30 minutes**, most often 15.
- **Initial Balance (IB)** — on ES and NQ, the high and low of the first **60 minutes, 09:30–10:30
  ET**.

So "10:30" belongs to the Initial Balance definition. With the shipped default of 15 minutes,
entries begin at **09:45**. `ivMin` is an input; set it to 60 for the textbook version.

## Which window is actually better

Same rules otherwise — close beyond the level by 0.15 ATR, stop at the opposite edge, 1.0R target,
flat 15:00, both sides:

| opening window | trades | net $ | PF | win % | research | LOCKED | maxDD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **15 minutes (ORB)** | 752 | **13,244** | **1.24** | 55.7 | **6,418** | **6,826** | 1,978 |
| 30 minutes | 723 | 6,023 | 1.10 | 54.4 | 7,236 | **−1,212** | 4,180 |
| 60 minutes (IB) | 646 | 4,258 | 1.09 | 52.6 | 1,094 | 3,164 | 2,977 |
| 90 minutes | 571 | 2,332 | 1.06 | 51.7 | −1,054 | 3,386 | 2,916 |

**The textbook Initial Balance window earns a third of what the 15-minute window earns**, and the
30-minute window has a negative locked block. The default stays at 15.

## "A full-bodied candle with small wicks"

| | trades | net $ | PF | research | LOCKED |
| --- | --- | --- | --- | --- | --- |
| 15m window, no body filter | 752 | **13,244** | 1.24 | 6,418 | 6,826 |
| 15m window, body ≥ 50% | 745 | 9,434 | 1.17 | 3,729 | 5,705 |
| 15m window, body ≥ 60% | 735 | 10,145 | 1.18 | 4,867 | 5,278 |
| 15m window, body ≥ 70% | 706 | 4,261 | 1.08 | 2,188 | 2,072 |
| 60m window, no body filter | 646 | 4,258 | 1.09 | 1,094 | 3,164 |
| 60m window, body ≥ 50% | 626 | 4,786 | 1.11 | 476 | 4,310 |

**It hurts on the window that works.** It helps slightly on the 60-minute window and never gets
back to the unfiltered 15-minute figure.

## "High trading volume"

Measured the way the sources specify — the breakout bar against the average of the opening range's
own bars. The commonly quoted threshold is 1.5×, credited with 8–12 points of win rate.

| | trades | net $ | PF | win % | research | LOCKED | maxDD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 15m window, none | 752 | 13,244 | 1.24 | 55.7 | 6,418 | 6,826 | 1,978 |
| 15m window, ≥ 1.0× | **129** | 1,464 | 1.12 | 54.3 | 274 | 1,190 | 1,799 |
| 15m window, ≥ 1.5× | — | | | | | | too few |
| 60m window, none | 646 | 4,258 | 1.09 | 52.6 | 1,094 | 3,164 | 2,977 |
| 60m window, ≥ 1.5× | **36** | 2,446 | **1.74** | **58.3** | 149 | 2,298 | **866** |
| 60m window, body 60% + vol 1.5× | **26** | 3,327 | **2.84** | **69.2** | 642 | 2,686 | **555** |

**The win-rate claim is directionally right and the frequency cost is fatal.** On the 60-minute
window 1.5× volume takes the win rate from 52.6% to 58.3% — +5.7 points, in the range the sources
claim — on a sample of **36 trades in three years**. Adding the body filter as well gives PF 2.84
and 69.2% win on **26 trades**, about nine a year.

There is a structural reason the 15-minute window cannot use this filter at all: with a 15-minute
opening range on a 15-minute chart the range is **one bar** — the 09:30 bar, routinely the
highest-volume bar of the session. Almost no later bar clears it.

Both confirmations are now inputs in `NQ_IVB.pine`, defaulted **off**, with these figures in their
tooltips.

## Sources

- [Best Strategy: Initial Balance or Opening Range Breakout? — Investing.com](https://www.investing.com/analysis/best-strategy-initial-balance-or-opening-range-breakout-200678872)
- [30-Minute Opening Range Breakout Strategy — NinjaTrader](https://ninjatrader.com/futures/blogs/opening-range-breakout-strategy/)
- [Initial Balance Trading Strategy, Complete Guide for ES & NQ Futures — Steady Turtle](https://steady-turtle.com/knowledge/initial-balance-trading-strategy)
- [Opening Range Breakout Strategy: How to Trade the First 30 Minutes — TradeAlgo](https://www.tradealgo.com/trading-guides/day-trading/opening-range-breakout-strategy-how-to-trade-the-first-30-minutes)
