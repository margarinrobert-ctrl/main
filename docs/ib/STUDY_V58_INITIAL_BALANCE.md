# V58 — the Initial Balance retracement, 1,555,200 configurations on three markets

**The brief.** Take the Initial Balance indicator as it is written — first hour's range, wait for
the close, wait for a break, enter on a 25% retracement, 60% stop, 50% target, flat at 15:55 —
and search a hundred thousand combinations with other indicators for the most robust,
highest-profit-factor version that works on every market.

**The answer.** 777,600 configurations were swept per market on US30 and US100, then 777,600 more
in a second pass, then the survivor was read once on NQ. The family as published **loses on all
three markets**, and it loses to a random entry taking the same risk on the same days. One
configuration out of 1,555,200 carries a pre-registered test, on **48 trades**.

---

## 1. What was swept

`research/v58/v58ib.py`. A day's outcome depends only on the day, the Initial Balance length, the
side and the four geometry numbers — never on which indicator was consulted — so the price is
walked once per (day, geometry) and every filtered configuration becomes a masked mean. The
whole grid costs one pass over the bars.

| axis | settings |
| --- | --- |
| IB length | 30, 60, 90 minutes from 09:30 New York |
| entry | 0.00, 0.10, 0.25, 0.40, 0.50 of the range back inside the broken edge |
| stop | 0.40, 0.60, 0.80, 1.00, 1.30 of the range from the broken edge |
| target | 0.50, 0.75, 1.00, 1.50, 2.50 of the range beyond it, or **none** |
| flatten | 13:00, 15:00, 15:55 New York |
| side | long, short, both |
| ADX(14) at the IB close | off, ≥ 20, ≥ 25, ≤ 20 |
| IB range vs its own trailing 20-day median | off, ≥ 0.8×, ≥ 1.2×, ≤ 1.2× |
| where the last IB bar closed in the range | off, ≥ 0.6, ≥ 0.5, ≤ 0.4 |
| EMA 13 against EMA 48 | off, fast over slow, fast under slow |

3 × 5 × 5 × 6 × 3 × 3 × 4 × 4 × 4 × 3 = **777,600** per market, US30 2016-10→2025-07 and
US100 2016-11→2025-10, research the first 65% of sessions and locked the last 35%.

Calendar conditions are banned (`CLAUDE.md`). Every filter is stamped at the **Initial Balance
close**, which is the moment the plan is made, so `ent_bar` leakage is structurally impossible:
there is one decision per day and it is taken before the trade window opens. Filters are stored
**side-oriented** — higher is always more favourable to the side being taken — because a single
threshold otherwise means two different things on the two sides and the sweep quietly rewards
whichever one the sample's drift prefers.

---

## 2. The first ranking was two artifacts, and both are in this repository's notes already

The first run ranked in **R** and skipped the fill bar for exits. It returned **25 of 25** top
configurations clearing a matched control at **p 0.000**, with the control losing 0.37–0.62 R per
trade. That is not a result, it is a symptom, and the cause was two of this branch's own
documented traps firing together.

**The R denominator collapsed.** The top of the ranking was entry 0.50 with a stop at 0.60 —
a risk of a **tenth** of the Initial Balance range, a median of **11.6 points** on US30, with a
reward:risk of **10:1**. In R a configuration can buy its own score by moving the stop closer to
the entry. `STUDY_SWEEP_110K.md` caught exactly this and measured 94% of an apparent edge as the
denominator; this family reaches it from the other direction, by construction rather than by
accident, because the risk is a *difference of two swept fractions* and the difference can be
made arbitrarily small.

> **A SWEEP OVER TWO LEVELS IMPLIES A SWEEP OVER THEIR DIFFERENCE. If the risk is the gap between
> two swept numbers, the grid contains a cell where the risk is nearly zero, and in R that cell
> wins.** Score in ATR units at the plan bar, and take profit factor in points.

**And an 11.6-point stop sitting 11.6 points under the entry level is routinely inside the same
15-minute bar as the fill.** A bar engine that skips the fill bar for exits hands the
configuration a free option. Running both models over the whole grid:

| | US30 | US100 |
| --- | ---: | ---: |
| median gain from skipping the fill bar | +0.0095 | +0.0051 ATR/trade |
| p90 | +0.0907 | +0.0828 |
| configurations gaining more than 0.01 | **49.5%** | **45.1%** |

> **THE FILL BAR IS AN EXIT BAR.** Half of this grid is worth measurably more when the bar that
> fills the limit is exempted from the stop. Neither model can order intrabar events; the honest
> procedure is to run both and print the gap, and to place the bracket with the entry in the
> script so the two match.

Re-scored in ATR units with the fill bar tested, the grid's profitable share falls from 21.5% /
17.7% to **13.5% / 13.0%**, and the median configuration loses on both markets.

---

## 3. What the top 1000 agree on — and why the agreement is not evidence

| axis | consensus of the top 1000 |
| --- | --- |
| side | long 62%, both 30%, short 8% |
| IB length | **30m 76%** |
| entry | 0.40 43%, 0.50 30% |
| stop | 1.30 45%, 0.80 29%, 1.00 24% |
| target | 2.50 24%, **none 19%**, 0.50 19% |
| flatten | 15:55 56% |
| ADX | **≥ 25 45%**, ≥ 20 28%, off 16% |
| IB range | ≥ 0.8× 39%, off 30% |
| close position | ≥ 0.5 46%, ≥ 0.6 23% |
| EMA 13/48 | **13 UNDER 48 — 74%** |

The most agreed condition in the whole pool is the *counter-trend* reading of the moving-average
cross: take the long when the fast average is **below** the slow one. That is the eighth
independent route to mean reversion on this branch — and it is also the first thing the marginal
read kills.

**The marginal effect of each condition, averaged over the whole grid rather than at its top row**
(ATR units per trade; a condition earns its place only by beating `off` in all four columns):

| condition | US30 res | US30 lock | US100 res | US100 lock | verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| ADX off | −0.1664 | −0.1603 | −0.1750 | −0.0742 | — |
| **ADX ≥ 25** | **−0.1416** | **−0.1440** | **−0.1525** | **−0.0085** | **better in all four** |
| ADX ≥ 20 | −0.1533 | −0.1474 | −0.1712 | −0.0343 | better in all four |
| ADX ≤ 20 | −0.2066 | −0.2475 | −0.2019 | −0.2498 | worse in all four |
| close pos ≥ 0.5 | −0.1538 | −0.1471 | −0.1854 | −0.0481 | fails on US100 research |
| EMA 13 under 48 | −0.1286 | −0.1484 | −0.1774 | −0.0891 | **fails on both US100 columns** |
| IB range ≥ 0.8× | −0.1611 | −0.1762 | −0.1627 | −0.0500 | fails on US30 |

> **THE CONDITION 74% OF THE TOP 1000 AGREED ON DOES NOT SURVIVE THE SECOND MARKET.** A consensus
> over a ranking is a consensus over what the ranking selected for, and both markets were in the
> ranking. The marginal read — which asks what a condition does to the *whole* grid — separates
> them, and only the **ADX floor** is better than `off` on all four market-block columns.

**Every single marginal is negative.** Every axis, every setting, both markets, both blocks.
Nothing in this family is profitable on average at any setting of anything.

The geometry marginals do say something usable. Entering **on** the break is the worst rung of
its axis in all four columns (−0.2624 / −0.2432 / −0.2790 / −0.1794) and improves monotonically as
the entry moves deeper into the range (0.50: −0.1185 / −0.0838 / −0.0805 / **+0.0333**). **No take
profit** ties for best — the twelfth independent time on this branch.

---

## 4. The pre-registered read, and it fails

Four candidates were declared from research alone and the locked block was read once.

| candidate | block | pooled n | ATR/trade | bootstrap P(mean ≤ 0) |
| --- | --- | ---: | ---: | ---: |
| **A** consensus (marginal mode of every axis) | research | 161 | +0.2874 | 0.067 |
| | **locked** | 69 | **+0.0179** | **0.483** |
| **B** most underfit survivor, 4 conditions | research | 491 | +0.1752 | 0.008 |
| | **locked** | 266 | **−0.0691** | **0.789** |
| **C** the rule as published and traded | research | 2,439 | −0.1091 | 1.000 |
| | **locked** | 1,332 | **−0.1263** | **1.000** |
| **D** C plus the single most-agreed filter | research | 1,104 | −0.0877 | 0.987 |
| | **locked** | 637 | **−0.0916** | 0.964 |

**Candidate C is the configuration the indicator ships with**, and it is a well-powered negative:
PF **0.83 / 0.78** on US30 and **0.92 / 0.85** on US100 across 3,771 trades, and it **loses to its
own risk-matched control at p 0.79 to 0.99** — a random entry of the same risk on the same days
does better. Adding the best filter does not rescue it.

**Replication.** The 25 configurations that headed the research ranking, read once on locked:
**2 of 25 positive on both markets** where chance is 6 to 12 of 25, and **0 of 25** beat their
control there. `corr(research, locked)` across the whole scorable population is **+0.07 to
+0.26**. The search bought nothing.

**And an independent second opinion agrees.** `research/v58/v58_vbt.py` rebuilds candidate C in
vectorbt from the bars with no shared code path. The trade count matches **100.0%** in all four
market-side cells (945 / 989 / 930 / 907) and the loss reproduces — the first time vectorbt has
agreed with this branch's engine after three failed transcriptions.

---

## 5. Pass two — the ridge ran off the grid, and stopped

The entry-depth gradient was monotone in all four columns and the best rung sat at the edge of
the grid, which `STUDY_TURTLE_15M.md` flags as a sign the grid was drawn in the wrong place. So a
second pass moved the entry from the middle of the range to the far edge — at 1.00 the trade is no
longer a retracement into a breakout but a **fade** of it.

| entry, fraction of range back inside | US30 res | US30 lock | US100 res | US100 lock |
| --- | ---: | ---: | ---: | ---: |
| 0.50 | −0.1309 | −0.0831 | −0.1150 | +0.0484 |
| 0.60 | −0.0778 | −0.0626 | −0.1516 | +0.0453 |
| 0.75 | −0.0718 | −0.0703 | −0.1658 | −0.0114 |
| 0.90 | −0.1190 | −0.0475 | −0.2203 | −0.0356 |
| 1.00 (a fade) | −0.0749 | +0.0357 | **−0.2326** | **−0.0854** |

**The ridge does not continue.** US100 reverses hard past 0.50 on both blocks while US30 wanders,
so pass one's gradient was an edge effect of where the grid stopped, not a ridge. Extending a grid
along a monotone axis is the right move and it is also how a one-market artifact gets found.

---

## 6. The one thing that survived, and exactly how much it is worth

0.63% of 410,826 configurations are profitable on **all four** market-block cells — and **59% of
those are the wrong shape**, better on locked than on research. That set was chosen by looking at
the locked block, so its statistics there are the selection criterion echoing back, not a test.
What it is good for is a hypothesis, and a hypothesis needs a block that chose nothing.

**NQ is that block.** A different feed, a different contract, a different span, and not one of the
1,555,200 configurations was ever scored on it.

Declared before the file was opened — the cluster that recurs in the survivor list:

> 30-minute Initial Balance, **long only**, entry **0.50** of the range back inside, stop **1.00**
> or **1.30** of the range from the broken edge, **no target**, flat 15:55, with
> **ADX ≥ 20**, **IB range ≥ 0.8×** its trailing 20-day median, the last IB bar closing in the
> **upper half**, and **EMA 13 below EMA 48**.

| | n | ATR/trade | points/trade | PF | win | control p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ, stop 1.00, no target | 48 | **+0.3544** | +21.60 | **1.801** | 45.8% | **0.003** |
| NQ, stop 1.30, no target | 48 | +0.3920 | +21.77 | 1.700 | 54.2% | 0.003 |
| NQ, stop 1.00, target 2.50 | 48 | +0.3346 | +20.60 | 1.764 | 45.8% | 0.004 |
| NQ, stop 1.30, target 1.50 | 48 | +0.2490 | +15.83 | 1.509 | 54.2% | 0.021 |
| **NQ, candidate C (as published)** | 637 | **−0.0368** | −1.59 | **0.940** | 36.4% | **0.758** |

Pooled over the six cells: **+0.3163 ATR/trade, bootstrap P(mean ≤ 0) = 0.010**.

**What that is and is not.** It is one clean read of a pre-declared rule on an instrument that had
no part in choosing it, and it beats a risk-matched random entry on the same days, which prices in
drift, costs, barrier width and session timing at once. It is also **48 trades**, the six cells
share the same 48 signal days so "six of six" is one observation and not six, and the rule reached
NQ only because it was selected on two other markets' held-back blocks. A footing, not a result.

**A clock error nearly made it a false one.** `NQ_1m` is stamped in UTC and every other feed here
is already on a New York clock. The first version of the NQ reader did not convert, which put the
"Initial Balance" at 04:30 New York — inside the pre-open block this branch has measured as the
worst part of the day four separate times — and returned a materially different table (48 trades
became 89, PF 1.80 became 1.49). The registry states the clock; read it before loading.

---

## 7. Order-model parity

Both questions were measured rather than argued:

* **The fill bar.** The engine tests the stop on the bar that fills the limit, and the shipped
  script places the bracket **with** the entry on the signal bar so the stop is live on the fill
  bar too. Across the grid this is worth up to +0.09 ATR/trade to whoever gets it wrong.
* **The flatten.** `strategy.close_all()` fills at the **next** bar's open and cannot sell the
  close of the bar that triggers it. Re-running the shipped cluster against the next open rather
  than the last in-window close moves it by **+0.0013 ATR/trade** — negligible here, because at a
  15:55 flatten with no target the trade is usually already out.

---

## 8. What ships

`pine/v58/V58_IB_CLUSTER_strategy.pine` — lint clean, checked for the multiple-of-4 continuation
indent, ATR as `ta.ema(ta.tr(true), 14)`, `ta.dmi`'s **third** element for the ADX, New York
wall-clock via `hour(time, TZ)`, every `var`-writing block guarded by `barstate.isconfirmed`, and
the trailing IB-range median taken before today's range is pushed so it never sees itself. It
carries its own evidence in the header, including the 48.

**Never backtested on TradingView.** No Strategy Tester claim is made about it.

---

## 9. What this study is worth if the configuration is noise

The negatives are better powered than the positive and they cost nothing to reuse:

1. **A sweep over two levels is a sweep over their difference**, and if the risk is that
   difference, the grid contains a near-zero-risk cell that wins in R. Score in ATR units.
2. **The fill bar is an exit bar** — half of this grid is worth more when it is exempted.
3. **The Initial Balance family as published loses on three markets**, to a random entry of the
   same risk, and vectorbt independently agrees.
4. **A consensus over a ranking is not a marginal effect.** The condition 74% of the top 1000
   agreed on fails on the second market's whole grid.
5. **Only the ADX floor earns its place** of four indicator conditions — the same ADX ≥ 25 that
   `STUDY_V11_MARKET.md` found, and here it only makes a loss smaller.
6. **Trading the break itself is the worst entry on the axis**, in all four columns. Ninth
   confirmation that chasing a breakout is the most reliably destructive choice in this search.
7. **No take profit** ties for best again — the twelfth time.
