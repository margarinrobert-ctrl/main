# Volume profile and auction theory on nine strategies

*The ask:* add volume-profile / auction-theory conditions to every strategy and see whether they
improve the edge; and detect inefficiency.

*The answer:* they do not improve anything measurable here, and the inefficiency claim does not
hold on this instrument once the control is matched properly. The most valuable thing this study
produced is a **bug in my own test harness** that had been inflating conditional results, which
this work found because the auction result was too good.

---

## 1. What was built

`research/volprofile.py` — a session volume profile from 1-minute bars. Volume is spread
uniformly across the bins each bar covers (the standard bar approximation, and what a TradingView
profile does), binned at 1 point. Per session it produces the point of control, the 70% value
area, high- and low-volume nodes, unfinished ("poor") extremes, and naked points of control — a
prior POC no later session has traded through. It also produces a **developing** profile: the POC
and value area as they stood at each bar, accumulated from the session open forward.

Node detection smooths the histogram over five bins first. Without that, the first build reported
a median of **24** low-volume nodes per session, which is not structure, it is sampling noise;
smoothed, it is 7.

`research/auction.py` — 47 boolean conditions on any strategy timeframe, in the same vocabulary as
the rest of the condition pool so they can be ANDed onto an existing rule.

| family | conditions |
| --- | --- |
| prior session's value | above / below / inside prior value, above / below prior POC, at prior POC, far from prior POC, above prior high, below prior low |
| shape of the prior auction | prior value narrow / wide, poor high, poor low, value migrated up / down |
| the developing auction | above / below / inside developing value, above / below developing POC |
| inefficiency | at a prior LVN, at a prior HVN, LVN within 1 ATR above / below, no LVN within 1 ATR, HVN within 1 ATR above / below |
| naked POC | naked POC within 2 ATR above / below |
| **VAH / VAL as levels** | at prior VAH, at prior VAL, above prior VAH by 1 ATR, below prior VAL by 1 ATR, at developing VAH, at developing VAL |
| **crossing the edges** | re-entered value from above / below, broke above developing VAH, broke below developing VAL |
| **how the session opened** | open above prior VAH, open below prior VAL, open inside prior value |
| **today's value vs yesterday's** | developing value above / below / overlapping prior |
| **the 80% rule** | 80% rule armed |
| **naked value-area edges** | naked VAH / VAL within 2 ATR above / below |

Both modules carry a `leakage_check()` that rebuilds from truncated data and compares everything
before the cut. Both are clean. Two bugs were caught by building the checks first: the naked-POC
tracker marked every session's own POC as touched, so the two naked conditions fired **zero**
times; and "poor high" measured a single 1-point bin at the extreme, which is always thin, so it
fired on 0% of sessions.

## 2. H1 — do low-volume nodes get revisited?

The auction-theory claim is that a price the market moved through quickly is unfinished business
and gets traded again. The control matters more than the test: a low-volume node sitting near the
session close will be revisited quickly whatever theory says, so the control is a level at **the
same distance from the same session's close**, on a random side.

6,007 low-volume nodes across 744 sessions, median 104 points from the close:

| | revisited ≤1 session | ≤5 | ≤20 | median sessions |
| --- | --- | --- | --- | --- |
| low-volume node | 42.8% | 68.9% | 83.7% | 1.0 |
| distance-matched level | 42.8% | 69.5% | 83.5% | 1.0 |

Mann-Whitney, LVN revisited sooner: **p = 0.67**. Identical to three significant figures on the
one-session number. There is no unfinished-business effect on NQ once distance is controlled for —
and distance is the whole of what an uncontrolled test would have measured.

## 3. H2 — is a target in a low-volume area reached more often?

The claim that could be worth money: a 1R target sitting where the prior session traded thinly
should be reached more often than one sitting at a high-volume node, because less resting interest
stands between price and it. Every trade of every strategy was labelled by the prior session's
smoothed volume density at its target price. 1,212 trades:

| | n | win % | $/trade | share hitting target | locked win % |
| --- | --- | --- | --- | --- | --- |
| target beyond the prior range | 604 | 63.9 | 45 | 39% | 60.6 |
| target density < 0.20 | 194 | 67.5 | 52 | 52% | 59.7 |
| target density 0.20–0.48 | 194 | 64.9 | 52 | 49% | 62.5 |
| target density > 0.48 | 194 | 63.9 | 39 | 53% | 64.8 |

The full-sample column trends the right way by 3.6 points; the locked column trends the **wrong**
way by 5.1. The stop-price version is flatter still. Per strategy the gap is positive on four of
nine and negative on five. Nothing.

## 3b. H3 — the 80% rule

The most quoted claim in value-area trading: *open outside value, trade back inside, hold two
consecutive 30-minute periods inside, and the market has about an 80% chance of traversing the
whole value area.* The control decides the answer — being inside yesterday's value at 11:00 with
five hours left gives you a fair chance of reaching either edge whatever the rule says — so it is
matched on time of day and on session remaining, against sessions that reached inside value
without opening outside it. What the rule claims to add is the opening context.

231 qualifying sessions:

| | traversed the value area |
| --- | --- |
| the 80% rule, as claimed | 80% |
| **measured on these sessions** | **50.6%** |
| time-matched control (opened *inside* value) | 59.9% |

The rule is **9.2 points worse than the control** (binomial p = 0.998 in the claimed direction),
and p < 0.0001 that its true rate is below 80%. On NQ over this sample the 80% rule is a coin flip
that underperforms simply being inside value at the same hour.

## 4. The 450-test sweep

47 conditions × 9 strategies. At a 5% threshold, 23 pass by chance, so that number goes first.
Protocol fixed in advance: a condition must keep ≥25 research trades and beat a **random filter of
the same selectivity** on both per-trade dollars and win rate at p < 0.05 on the research block;
survivors are then read once on the locked block and put through Benjamini-Hochberg.

    172 of 450 pairs keep enough research trades
      7 beat a random filter on both statistics at p < 0.05   (about 9 expected on either alone)
      0 survive Benjamini-Hochberg at q < 0.10 on the locked block

| | condition | research p$ | pW | **locked p$** | **pW** | q |
| --- | --- | --- | --- | --- | --- | --- |
| V2L | open inside prior value | 0.002 | 0.011 | 0.471 | 0.468 | 0.863 |
| M3 | far from prior POC | 0.009 | 0.005 | 0.156 | 0.263 | 0.863 |
| V4 | no LVN within 1 ATR | 0.010 | 0.045 | 0.211 | 0.240 | 0.863 |
| V2 | LVN within 1 ATR below | 0.016 | 0.016 | 0.642 | 0.617 | 0.863 |
| M2 | LVN within 1 ATR below | 0.019 | 0.045 | 0.765 | 0.806 | 0.863 |
| V1 | open inside prior value | 0.021 | 0.026 | 0.592 | 0.863 | 0.863 |
| V2L | naked VAL within 2 ATR below | 0.045 | 0.050 | 0.813 | 0.737 | 0.863 |

Seven survivors from 172 tests is fewer than chance would give, and **no VAH/VAL condition ranks
any higher than the POC and LVN ones did**. Adding the value-area edges as levels, the crossing
events, the opening classification and the naked edges — 18 more conditions — moved nothing.
**Volume profile adds nothing to these nine strategies on this instrument.**

---

## 5. The bug this study found

The first run of §4 returned sixteen research-block survivors instead of four, and two of them
survived the locked block at q = 0.008. They all pointed the same way — shorts below the
developing POC, longs above it — so that was tested as a single pooled hypothesis across all nine
strategies at once, which is the right way to spend one degree of freedom:

| | n | win % | $/trade | net $ |
| --- | --- | --- | --- | --- |
| LOCKED, all trades | 414 | 61.4 | 62 | 25,528 |
| LOCKED, agreeing with the developing POC | 264 | **72.0** | 95 | 25,193 |
| LOCKED, disagreeing | 150 | **42.7** | 2 | 335 |

Random-filter p on the **locked** block: 0.0005 on dollars and 0.0005 on win rate. The gap was
positive on **9 of 9** strategies, including ones found by completely different searches. That is
about as convincing as this repository ever gets.

It was entirely fake.

The tell was that applying the same condition as an actual entry filter — removing the disagreeing
trigger bars and re-simulating — changed almost nothing (V2: 60.7% → 59.5%). A condition cannot
both split realised trades 72/43 and do nothing when used to filter them. Chasing that
contradiction:

> `sim_core` fills at the open of the bar **after** the signal, and stores that fill bar in
> `ent_bar`. So `condition[ent_bar]` reads a bar whose high, low, close and volume do not exist
> when the order is sent. For "price is below the developing POC", the close being read is the
> close of the bar the trade is *filling into* — and for strategies whose median hold is 0 bars,
> that is the bar the trade resolves on. A winning short means price fell during it. The split was
> conditioned on its own outcome.

Read at the signal bar, the same test:

| | research p$ | pW | locked p$ | pW | strategies with a positive gap |
| --- | --- | --- | --- | --- | --- |
| read at the fill bar (wrong) | 0.0005 | 0.0005 | 0.0005 | 0.0005 | 9 of 9 |
| read at the signal bar (right) | 0.53 | 0.30 | 0.28 | 0.19 | 5 of 8 |

### What else it touched

`grep` for reads at `ent_bar` found seven more call sites. Each is now fixed and routed through
one helper, `test_suite.sig_bar`:

| where | what it did | consequence |
| --- | --- | --- |
| `oner_anom.slices` | regime and volatility labels at the fill bar | **V2's "edge lives below the 200 EMA" (q = 0.004) was outcome-conditioned. Corrected: q = 0.474, nothing survives.** See the correction in `STUDY_1R_MORE.md` §7d |
| `quant_brain` SignalModel | whole feature matrix at the fill bar | the signal model was trained on the fill bar's own close |
| `vol_sizing`, `sizing_sweep` | position size from the fill bar's ATR | re-checked below |
| `test_suite` ×4 | ATR, regime label, volume and notional at the fill bar | four tests in the 57-test battery |
| `inefficiency` | entry price off by one bar | this study, fixed before publication |

**No shipped strategy's figures move.** A strategy is defined by its trigger bars and by
`sim_core`, and both were always right; the bug lived only in the layers that *describe* trades
after the fact. The 57-test battery on V1 now returns 43 PASS / 4 WARN / 0 FAIL, better than the
41 PASS / 2 FAIL it returned before, because fixing `sim()` also repaired a drop-one test that a
previous change had silently zeroed.

Re-checking the sizing conclusion with causal ATR — the claim in `CLAUDE.md` is "sizing creates no
edge":

| method | net $ | locked $ | Sharpe | maxDD $ | MAR | mean lots |
| --- | --- | --- | --- | --- | --- | --- |
| fixed | 7,492 | **3,333** | 1.62 | 1,177 | 6.36 | 1.00 |
| VAPS | 8,813 | 1,371 | 1.80 | 919 | 9.59 | 1.51 |
| DVS | 25,216 | 3,475 | 1.59 | 3,453 | 7.30 | 4.71 |
| RSPS / DRS | 9,866 | 1,658 | 1.76 | 1,384 | 7.13 | 1.74 |
| VTM | 8,332 | 3,406 | 1.45 | 1,795 | 4.64 | 1.23 |
| VRS | 12,754 | 2,477 | 1.68 | 1,279 | 9.98 | 2.30 |
| VRSP | 7,328 | 1,102 | 1.49 | 1,109 | 6.61 | 1.47 |

Every method that makes more gross dollars does it by taking more lots, Sharpe stays inside
1.45–1.80 against 1.62 flat, and no method beats flat sizing on the locked block by more than
noise. The conclusion stands.

---

## 6. What to take from this

1. **No auction condition earns a place in any of the nine rules.** Four of 121 tests passed on
   research, which is fewer than chance, and none survived the holdout.
2. **The unfinished-business claim is false here** once the control is distance-matched — 42.8%
   against 42.8%. An unmatched control would have "confirmed" it.
3. **A conditional split is not a filter test.** Splitting realised trades by a condition and
   filtering the entry rule by that condition are different questions, and the second is the one
   that matters. Here they disagreed, and the disagreement is what exposed the bug.
4. **The one that generalises:** a condition read at the fill bar is conditioned on the trade's
   own outcome, and the shorter the hold, the more violently it lies. This produced a p = 0.0005
   holdout result that replicated across 9 of 9 independently-found strategies. Replication across
   strategies does not protect you from a bug in the harness they share.

## Files

| | |
| --- | --- |
| `research/volprofile.py` | session and developing profiles, nodes, naked POCs, leakage check |
| `research/auction.py` | 29 causal auction conditions, leakage check, `signal_bars` |
| `research/allstrats.py` | the nine shipped strategies in one registry |
| `research/inefficiency.py` | H1 revisit, H2 target/stop density |
| `research/auction_test.py` | the 261-test sweep with the multiplicity stated up front |
| `research/auction_apply.py` | the pooled single test and the filtered book |
| `research/test_suite.py` | `sig_bar`, the helper every call site now routes through |

Measured on MNQ, 2022-12-26 → 2025-12-12, one contract, $1.00 commission per round turn, one tick
spread plus one tick slippage each side, one extra tick on stops. Research tooling for education
and analysis, not financial advice.
