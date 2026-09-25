# STUDY: the V61 CVD rule frozen and run on US30 — it does not transfer

**What this is.** The same battery as `STUDY_V61_SESSION`, run on `US30_LONG_15m` — a market that
had no part in choosing any of the V61 rule's parameters. Both of its blocks are therefore out of
sample, and the only reason to split it is to see whether the result decays in the right direction.

**Verdict: the rule is null on US30, and the CVD gate is actively subtractive there.** All three
nulls beat it. The user's 07:00–11:00 + flatten configuration is **below profit factor 1.0 on both
blocks**. Adding US30 to the NQ book makes the book worse despite a correlation of only 0.11–0.23.

**Code.** `research/v61sess/us30_core.py`, `run_us30.py`, `run_us30_mc.py`, `plot_us30.py`.
Output `results/v61sess/us30*.csv|txt`, panel `us30_panel.png`.

## The data, and the constraint that shapes the whole study

The uploaded file is the registry's **`US30_LONG_15m`**: sha256 prefix **24dcf2e1c7ba398f**,
193,942 rows, 2016-10-26 → 2025-07-15, **byte-identical** to the copy already on disk. TAB-separated,
delivered newest-first, `Volume` identically zero with `TickVolume` the real activity column, clock
New York + 7.

**The binding constraint is not a choice: CVD needs bars finer than the chart, and this feed's
finest is 15 minutes.** The incumbent's 30-minute chart would get **two** sub-bars a bar, which is
not a cumulative delta in any useful sense. So the rule runs on a **60-minute chart with four
sub-bars**, against the **thirty** one-minute sub-bars the NQ result was built on. At 240 minutes
(16 sub-bars) the 90/600-minute order-flow conversion degenerates to k=1, w=2 and is reported
without being relied on.

**And the volume is tick volume, not contracts**, so the proxy signs tick counts — the same pair of
degradations `STUDY_XAU_CVD_FEATURES` had to accept on gold, now on a second market. A null here is
weaker evidence against CVD than a null on NQ would be.

## 1 — The frozen rule

Nothing fitted. Geometry (Donchian 20/20, 2.0 ATR stop, no target, long) and order-flow windows
(90 / 600 minutes) are NQ's. US30 at $1/point, 1.50 points cost and 0.10 slippage a side.

| chart | ent/exit | = minutes | block | n | PF | $ | maxDD $ | ret/DD | %/trade |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 60m | 20/20 | 1,200 | A 2016–22 | 208 | 1.146 | 2,276 | 3,047 | 0.75 | +0.0533 |
| 60m | 20/20 | 1,200 | B 2022–25 | 142 | 1.101 | 1,443 | 2,947 | 0.49 | +0.0195 |
| 60m | **10/10** | **600** (matches NQ 30m) | A | 351 | 1.094 | 1,905 | 2,367 | 0.80 | +0.0180 |
| 60m | 10/10 | 600 | B | 236 | **0.943** | −1,011 | 3,505 | −0.29 | −0.0173 |

Against NQ's 1.784 / 1.611 at ret/DD 10.02 / 8.23, this is a different object. And at **matched time
reach** — 10/10 on 60m is the same 600 minutes as NQ's 20/20 on 30m — it is **negative on block B**.

Cost is only 2.2% of the stop, so this is not a cost problem.

## 2 — All three nulls beat it

| block | n | rule pts/trade | random ENTRY | p | random FILTER | p | always-long |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | 208 | 10.94 | 20.95 | **0.870** | 22.81 | **0.760** | 15.12 |
| B | 142 | 10.16 | 10.74 | 0.507 | 14.60 | 0.595 | **29.55** |

A random entry with the same geometry and exits earns roughly **twice** what the rule earns on
block A. A random filter keeping the same *number* of the ungated base's trades also beats it. And
simply holding long over the same periods beats it on both blocks. There is nothing here.

## 3 — The gate is subtractive, which is the opposite of what it does on NQ

| arm | block | n | PF | pts/trade | total pts |
| --- | --- | --- | --- | --- | --- |
| gate ON (as shipped) | A | 208 | 1.146 | 10.94 | 2,276 |
| **gate OFF (base only)** | A | 568 | **1.265** | **21.96** | **12,471** |
| gate ON | B | 142 | 1.101 | 10.16 | 1,443 |
| **gate OFF** | B | 353 | **1.143** | **14.42** | **5,092** |

On NQ the gate raised per-trade edge in 12 of 14 cells and cut total return. **On US30 it cuts
both** — it removes 63% of the trades *and* halves the per-trade result. That is the cleanest
statement of non-transfer available: the component the V61 study exists to demonstrate does the
opposite thing on a market that never chose it.

## 4 — The NQ session finding does not replicate

| arm | block A PF | block B PF |
| --- | --- | --- |
| all hours, no flatten | 1.146 | 1.101 |
| 07:00–11:00, NO flatten | **1.410** | 1.178 |
| all hours, flatten 11:00 | 1.226 | 1.010 |
| **07:00–11:00 + flatten** | **0.965** | **0.883** |

On NQ the flatten cost 0.4–0.5 profit factor consistently. On US30 the same comparison gives
**+0.081 on block A and −0.091 on block B** — no consistent sign. The *window* helps on block A
(1.410) and barely on block B (1.178). **The one thing that does carry: your exact configuration,
07:00–11:00 with the flatten, is below 1.0 on both US30 blocks.**

## 5 — Monte Carlo

| leg | block | n | mean pts | 5–95% | **P(mean ≤ 0)** | p99 / realised DD |
| --- | --- | --- | --- | --- | --- | --- |
| gate ON | A | 208 | +11.26 | −15.33 to +39.04 | **0.244** | 1.69× |
| gate ON | B | 142 | +11.19 | −30.49 to +57.02 | **0.355** | 1.89× |
| gate OFF | A | 568 | +22.07 | +1.74 to +41.65 | 0.037 | 1.46× |
| gate OFF | B | 353 | +13.86 | −13.66 to +42.03 | 0.218 | 2.30× |
| 07:00–11:00 + flatten | A | 88 | −1.87 | −20.30 to +17.34 | **0.568** | 2.30× |
| 07:00–11:00 + flatten | B | 73 | −5.51 | −29.08 to +19.06 | **0.651** | 1.12× |

The gated rule does not exclude zero on either block. The user's configuration is **negative in
expectation** on both.

## 6 — Portfolio: a decorrelated leg still has to have an edge

On the 923 overlapping days (2022-12-26 on), daily dollars:

| | NQ 30m | NQ 15m | US30 gate ON |
| --- | --- | --- | --- |
| NQ 30m | 1.00 | 0.358 | **0.226** |
| NQ 15m | 0.358 | 1.00 | **0.105** |

US30 is genuinely decorrelated from both NQ legs — and it still hurts:

| combination | $ | maxDD $ | ret/DD | Sharpe | PF |
| --- | --- | --- | --- | --- | --- |
| NQ 15m all hours | 11,674 | 789 | **14.79** | 1.69 | 1.810 |
| NQ 30m + NQ 15m | 12,286 | 921 | 13.34 | **1.78** | 1.857 |
| **+ US30 gate ON** | 8,885 | 949 | **9.37** | **1.60** | 1.700 |
| + US30 gate OFF | 9,441 | 1,587 | 5.95 | 1.47 | 1.550 |

`STUDY_SEMIVARIANCE` recorded this exactly: *adding a coin-flip signal at |ρ| 0.25 raised the book's
net profit, cut its Sharpe 3.73 → 3.23 and more than doubled its drawdown.* A correlation matrix
alone will talk you into this trade. **Diversification is not a substitute for an edge.**

## Verdict

**Do not run this rule on US30.** It is null against every null on the market that chose nothing
about it, its own gate is subtractive there, the configuration in question loses money on both
blocks, and adding it to the NQ book costs 0.18 of Sharpe.

**What this does and does not establish.** It establishes that the *rule as configured*, at this
feed's resolution, has no edge on US30. It does **not** cleanly refute CVD as a concept on the Dow:
four sub-bars a bar on tick volume is a materially cruder object than thirty sub-bars on contract
volume, and `STUDY_XAU_CVD_FEATURES` measured the same degradation weakening the same family on
gold. **What would settle it is 1-minute US30 bars** — the same thing gold needs, and the same
thing that would make this branch's one surviving CVD pattern testable anywhere but NQ.
