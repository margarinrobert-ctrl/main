# Reverse-engineering the Initial Balance model — what actually creates the edge

**The question.** `STUDY_V58_INITIAL_BALANCE.md` swept 1,555,200 configurations, rejected the
family on three markets, and found one survivor: a cluster read once on NQ — 48 trades,
+0.3544 ATR/trade, PF 1.801, beating a risk-matched random entry at p 0.003. What is that number
made of?

**The answer in one line.** *Not the Initial Balance, and not the four conditions.* **It is the
retracement depth — a resting limit entry priced in IB-range units — and its effect is monotone
across all five rungs: buy the break with no pullback and there is no edge at all (p 1.000); make
the market come 50% of the range back to you and you get +0.3087 ATR/trade at p 0.000 on 329
trades.** The Initial Balance is the yardstick the limit is measured in, not the signal. The four
declared conditions collectively buy **+0.0457 ATR/trade and cost 85% of the sample**.

`research/v58/v58_anatomy.py`. Method is `STUDY_M4_ANATOMY.md`'s, run in the same order.

---

## 1. The four conditions do not create the edge

| rule | n | ATR/trade | PF | win | vs full | control p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **full rule (all four)** | 48 | +0.3544 | 1.801 | 45.8% | | 0.003 |
| **geometry only, no conditions** | **329** | **+0.3087** | 1.539 | 38.0% | −0.0457 | **0.000** |

**The unconditional geometry already clears the control at p 0.000 on 329 trades.** Stacking four
conditions on top of it adds 0.046 ATR/trade and throws away 85% of the trades. That is the whole
result of the condition search, stated as a single comparison.

**Drop one, and each alone:**

| | n | ATR/trade | PF | vs full | control p |
| --- | ---: | ---: | ---: | ---: | ---: |
| without `ADX ≥ 20` | 59 | **+0.6489** | 2.161 | **+0.2945** | 0.000 |
| without `IB range ≥ 0.8×` | 68 | +0.2966 | 1.752 | −0.0578 | 0.002 |
| without `close in upper half` | 79 | +0.0340 | 1.148 | **−0.3204** | 0.043 |
| without `EMA 13 under 48` | 111 | +0.1906 | 1.715 | −0.1637 | 0.004 |
| `ADX ≥ 20` alone | 245 | +0.2183 | 1.482 | −0.1360 | 0.001 |
| `IB range ≥ 0.8×` alone | 206 | +0.2684 | 1.510 | −0.0860 | 0.000 |
| **`close in upper half` alone** | **222** | **+0.4132** | **1.772** | **+0.0588** | **0.000** |
| `EMA 13 under 48` alone | 143 | +0.2333 | 1.431 | −0.1210 | 0.001 |

**ADX ≥ 20 is actively harmful — removing it nearly doubles the result.** Its ladder says why: off
+0.6489, ≥20 +0.3544, ≥25 +0.1134. The condition is monotone in the *wrong* direction, and the
inverted rung (`ADX ≤ 20`) is the best cell in the table at +1.9341 on **11 trades** — an artifact,
but one pointing the same way. The declared cluster carries the ADX filter backwards.

**One condition carries: where the last Initial Balance bar closed in its own range.** Alone it
scores **+0.4132 on 222 trades**, better than the four-condition stack on 4.6× the sample. Its
ladder is directionally clean: closing in the bottom 40% gives **−0.3211**, off gives +0.0340,
upper half gives +0.3544. That is a real monotone mechanism — the last IB bar's position is a
one-number read of who won the opening hour.

The other two are decoration: the volatility filter costs 0.058 to remove, the EMA state 0.164, and
neither has a coherent ladder.

---

## 2. The edge is the retracement — and it is monotone

All four conditions off, one geometry axis moved at a time:

| retracement (fraction of range back inside the broken edge) | n | ATR/trade | PF | control p |
| --- | ---: | ---: | ---: | ---: |
| 0.00 — buy the break itself | 496 | **+0.0226** | 1.079 | **1.000** |
| 0.10 | 468 | +0.1072 | 1.203 | 0.902 |
| 0.25 — *as the indicator is published* | 413 | +0.2148 | 1.300 | 0.075 |
| 0.40 | 356 | +0.2397 | 1.369 | 0.001 |
| **0.50 — the deepest rung in the grid** | 329 | **+0.3087** | 1.539 | **0.000** |

**Perfectly monotone across all five rungs, with the control p-value falling monotonically with
it.** At zero retracement — chasing the breakout — there is no edge whatsoever: p 1.000 means every
random entry on those days did at least as well. The published 0.25 is halfway up the ramp and does
not clear a control. The edge appears only as you make the market come back to you.

**This is the branch's biggest recorded lever wearing a new costume.** `STUDY_LIMIT_ENTRY.md` and
`research/atme/`: a resting limit in your favour is worth +0.24 to +0.43 R/trade against a
best-ever *signal* of +0.043 R; buying dips improves monotonically as the limit gets deeper while
buying strength via a stop entry degrades monotonically as it gets further; *"chasing a breakout is
the single most reliably destructive choice in the whole search."* A retracement fraction of the
Initial Balance range **is** a resting limit, priced in IB units instead of ATR units. This is the
sixth independent route to that conclusion on this branch, and the first where the limit was hiding
inside someone else's indicator.

The rest of the geometry ladder agrees with everything already on file:

| axis | reading |
| --- | --- |
| target | monotone — **none** +0.3087, 2.5R +0.2991, 1.5R +0.2687, 1.0R +0.2171, 0.75R +0.1880, 0.5R +0.1163. **Sixth confirmation that no take profit beats every target tested.** |
| stop | 1.30 +0.3258 ≈ 1.00 +0.3087 ≫ 0.80 +0.1640, 0.60 +0.1448. Wide, as everywhere else here. |
| IB length | 30 +0.3087, 60 +0.2812, 90 +0.2544 — all at p 0.000. **The Initial Balance length barely matters**, which is what you expect if the IB is a ruler and not a signal. |
| flatten | 15:00 +0.3518, 15:55 +0.3087, 13:00 +0.2361 |
| side | long +0.3087 (p 0.000); **short −0.0658** (p 0.001 — it beats its own control while losing money, because random shorts on those days lose more. Drift, not edge.) |

---

## 3. Three tests that could have killed it, and what they said

**Exit split — this one is a warning.** 22 of 48 trades stop out at −1.3551 ATR each; 26 flatten at
15:55 at +1.8009. **The time exit contributes 275% of net and the stops give back 175%.** By
`STUDY_M4_ANATOMY`'s rule, a rule earning at the time exit is a direction bet on the session rather
than a barrier edge — and the target ladder above agrees, since every target makes it worse. What
is owned here is a *held directional position*, not a barrier system.

**Widen the stop until the barriers stop binding.** Unlike M4, the stop is not decoration:
infinite stop +0.1546 against the shipped 1.00's +0.3544, so the stop is worth **+0.1998
ATR/trade**. But the neighbourhood is not smooth — 0.60 +0.2129, **0.80 −0.0751**, 1.00 +0.3544,
1.30 +0.3920 — a negative rung sitting between two positive ones. On the unconditional 329-trade
sample that dead band disappears (0.60 +0.1448, 0.80 +0.1640, 1.00 +0.3087, 1.30 +0.3258), which is
itself the evidence: **the dead band is a 48-trade sampling artifact, and the conditions are what
made the sample small enough to produce one.**

**Day versus bar.** On the same 48 days with the same geometry and a random entry moment, the
control median is **−0.1286** against the rule's +0.3544, p 0.0030. The entry moment is doing real
work.

**And the selected days are not a drift bet** — the opposite of M4. The 48 chosen sessions travel
**−0.5945 ATR** from the IB close to 15:55 and finish up only **47.9%** of the time, against
**+0.1775** and **57.1%** for every other day. The rule buys, on days that end lower than they
started, and still makes money. That rules out "it picks sessions that drift up", which is exactly
how M4's apparent edge dissolved.

---

## 4. What this costs, and what would test it

**NQ is spent.** It was reserved as the block that chose nothing and `STUDY_V58` spent it on one
pre-registered read. This anatomy has now read roughly **sixty cells** on it. Every p-value above
is **descriptive** — it says which parts of the rule carry the result — and none of them is
pre-registered any more. The next test of anything here needs a block none of this touched.

**What to carry forward, in order:**

1. **The retracement depth is the edge.** Buy the break and there is nothing (p 1.000); make the
   market come half the range back and there is +0.3087 at p 0.000. Everything else in this model
   is scaffolding around a limit order.
2. **Drop the ADX filter.** It is backwards on this family; removing it raises the result by
   +0.2945 ATR/trade.
3. **Keep exactly one condition** — the last IB bar's close position in its own range. Alone,
   +0.4132 on 222 trades.
4. **No target, wide stop, long only** — the same three answers this branch keeps arriving at.
5. **Test the retracement axis past 0.50.** The grid stops there and the surface is still rising;
   the interesting question — how deep before the fill rate kills it — is off the end of the grid.
   `STUDY_ATME.md` puts the fill rate at 35% for a 1.0×ATR limit, so there is a ceiling and this
   sweep never reached it.

---

| file | what it does |
| --- | --- |
| `research/v58/v58_anatomy.py` | the whole anatomy: exit split, infinite stop, day-vs-bar, drop-one, both ladders |
| `results/v58_anatomy.txt` | its raw output |
