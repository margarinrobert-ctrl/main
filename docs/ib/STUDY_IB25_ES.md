# STUDY: the IB 25 retracement on ES — the half that is answerable, and the half that is not

**The ask.** Build the posted "IB 25 retracement" — anchored 09:30 VWAP, wait for the 10:20 close,
fib the 09:30–10:30 range, limit at 25% retrace, target the extreme (1:1), stop at 50% — for ES.

**What was delivered.** The strategy, built to spec for ES/MES with the mechanics corrected, plus
the one ES question that can be settled without ES bars: the cost arithmetic. **No ES backtest is
claimed, because no ES series exists on this branch** — `research/datasets.py` lists sixteen feeds
and none is the S&P, and CLAUDE.md has carried "ES has never been supplied" since
`STUDY_TURTLE_15M`. The only market here that can run the rule at all is NQ: US100 and US30 are
15-minute feeds and cannot resolve a 10:20 close or a 1-minute limit fill.

**Code.** `research/ib25/run_ib25_es.py` (the cost translation),
`pine/ib25/IB25_RETRACEMENT_ES_strategy.pine`. Output `results/ib25/es_cost.txt`, `es_cost.csv`.
The rule itself is `research/ib25/ib25_core.py`, unchanged from `STUDY_IB25_RETRACEMENT.md`.

## The ES cost arithmetic — and it runs against the strategy

This branch's standing rule is that **a cost is a fraction of risk, not a number of points**. The
recorded failure is `STUDY_TURTLE_15M`, which charged NQ's 1.72-point round turn in *gold's* points
and reported PF 0.35 as a decisive result, when the same cost was 54.2% of gold's stop against 3.7%
of NQ's.

This rule sizes its stop as a **fraction of the morning range**, and a morning range is a percentage
of the index rather than a number of points. Measured on 527 NQ trades:

| | median | p25 | p75 |
| --- | --- | --- | --- |
| risk, points | 29.19 | 22.50 | 39.69 |
| risk, % of entry price | **0.1509%** | 0.1129% | 0.2013% |
| morning range, % of price | 0.6086% | | |

That percentage is the quantity that carries across two US equity indices trading the same 09:30
auction. What does *not* carry is the tick, and that is the whole ES question:

| contract | pt value | tick | fee RT | RT points | RT % of price | risk points at 0.151% | **RT as % of risk** |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MNQ Micro Nasdaq-100 | $2 | 0.25 | $1.44 | 1.220 | 0.0049% | 37.7 | **3.2%** |
| **MES Micro S&P 500** | $5 | 0.25 | $1.44 | 0.788 | 0.0116% | 10.3 | **7.7%** |
| NQ E-mini | $20 | 0.25 | $4.28 | 0.714 | 0.0029% | 37.7 | 1.9% |
| **ES E-mini** | $50 | 0.25 | $4.28 | 0.586 | 0.0086% | 10.3 | **5.7%** |

**MES pays 2.37× the fraction of risk MNQ pays.** ES's 0.25 tick is 0.0037% of a 6,800 index against
0.0010% of a 25,000 one — 3.7× — and the fee is spread over 2.5× fewer points. **ES is the cheaper
contract in dollars and the more expensive one in R.**

Re-charging the NQ series so the round turn is the same fraction of risk it would be on each
contract — same bars, same rule, same trades, only the cost moves:

| charged as | research %/trade | research PF | locked %/trade | locked PF |
| --- | --- | --- | --- | --- |
| MNQ | −0.00985 | 0.871 | +0.01530 | 1.181 |
| **MES** | **−0.01698** | **0.796** | +0.00965 | 1.110 |
| NQ | −0.00770 | 0.895 | +0.01701 | 1.203 |
| **ES** | **−0.01381** | **0.828** | +0.01216 | 1.141 |

This isolates ES's *cost structure* from ES's *price path* and answers the first exactly. The cost
objection to this rule is **larger** on ES than on the market it was measured on, not smaller.

## But cost is not the binding objection, and that is the number that decides it

At **zero** fee and **zero** slippage the rule is still negative on the block that would select it:

| | n | gross %/trade | PF | win |
| --- | --- | --- | --- | --- |
| research | 345 | **−0.00466** | 0.930 | 48.4% |
| locked | 182 | +0.01942 | 1.235 | 57.1% |

A cost problem is a rule that makes money gross and loses it net — better fills, a cheaper broker or
a bigger contract would then rescue it. This one is negative gross, so none of that applies. And it
loses on research while winning on locked, which is the wrong shape for the tenth time on this
branch: the block permitted to select it is the block it fails.

From `STUDY_IB25_RETRACEMENT.md`, unchanged and still the governing read: as posted it scores
research −0.0169 %/trade / PF 0.807 / −$6.55 an MNQ contract; it **loses to a random entry minute**
in the same window with the same side and barriers at **p 0.845**; research bootstrap P(mean ≤ 0) is
**0.965**.

## The post's own best observation is correct, and it is arithmetic rather than edge

The post says moving the stop from 50% to 75% raises the win rate "a good amount". It does — and it
raises the geometry's own break-even by the same amount. Reward:risk is `retr : (stop − retr)`, so
the driftless bound is `1/(1+RR)`:

| retr | stop | RR | driftless break-even | actual win | net %/trade | gross %/trade |
| --- | --- | --- | --- | --- | --- | --- |
| 0.25 | 0.50 | 1.000 | 50.0% | 51.4% | −0.00767 | +0.00366 |
| 0.25 | **0.75** | 0.500 | **66.7%** | **68.1%** | −0.00447 | +0.00686 |
| 0.35 | 0.50 | 2.333 | 30.0% | 26.7% | −0.02115 | −0.00988 |
| 0.50 | 0.75 | 2.000 | 33.3% | 34.9% | −0.00685 | +0.00447 |
| 0.50 | 1.00 | 1.000 | 50.0% | 51.1% | +0.00893 | +0.02025 |

**The win rate tracks its own break-even at every rung**, never clearing it by more than about a
point and a half. A win rate bought by widening the stop is a change of geometry, not of edge —
which is why the branch's standing instruction is to read a win rate against the break-even the
geometry implies and never against 50%. The shipped script prints both on its panel for exactly
this reason.

## What ships

`pine/ib25/IB25_RETRACEMENT_ES_strategy.pine`, defaults as posted, **no edge claimed** and the
measured numbers in the header. Mechanics corrected against this branch's recorded Pine failures:

- **New York time explicitly.** Bare `hour`/`minute` are *exchange* time — Chicago for CME — which
  would put the whole rule an hour out.
- **ATR is `ta.ema(ta.tr(true), 14)`**, not `ta.atr`.
- **One live order.** `STUDY_V15_BOOK` and `STUDY_V34_MECHANIC` both caught this branch's own
  engines holding a *book* of resting limits where a script holds one, which inflated every
  limit-entry figure they produced. One session, one order, one trade; the level is frozen when the
  order is placed rather than re-priced on each fresh signal (`STUDY_V15_BOOK`: chasing costs 2×).
- **A fill-relative bracket goes out WITH the entry.** `strategy.exit` only runs on a bar where a
  position already exists, so the first stop otherwise lands at the *close of the fill bar* and the
  fill bar is naked — `STUDY_V56` measured 4.4–13.0% of trades. The entry is a limit at a known
  price, so `loss`/`profit` in ticks are known at order time.
- **`barstate.isconfirmed` on every block that writes `var` state**, not only on entries.
  `STUDY_TICK_RECALC` measured the alternative: the same rules went from 11,398 to 14,462 trades.
- **The slope window is declared in MINUTES** and converted by `timeframe.in_seconds()`.
  `STUDY_V57` recorded a shipped script whose 30-minute settings silently became 1-minute ones on a
  1-minute chart — one thirtieth of their reach.
- **The flatten order goes out on the bar *before* the cutoff**, because `strategy.close_all` fills
  at the next bar's open and cannot sell the close of the bar that triggers it (`STUDY_V60`).
- Commission defaults to the MES/micro stack ($0.72 a side); the header says to set 2.14 for
  full-size ES. The script sets real commission *and* slippage — `STUDY_TICK_RECALC`'s reminder to
  read the trade count and the commission load before the P&L.

Lint clean (111 shipped scripts, 0 structural problems), and the linter was verified to actually
read the file by injecting a known CE10013 and confirming it was caught.

## Verdict

**Do not trade this on ES on the strength of anything here.** The rule is negative gross on the one
market that can run it, loses to a random entry minute at p 0.845, and its headline win-rate
improvement is a restatement of its own break-even. The ES-specific arithmetic makes the cost
objection **2.37× larger**, not smaller.

**What is genuinely untested and would need ES bars:** whether the S&P's 09:30–10:30 auction
retraces differently from the Nasdaq's. That is a real question and the script exists so it can be
answered. Supply ES 1-minute bars and it can be measured properly — with the same battery: matched
random-entry control, both blocks, the break-even table, and one locked read.
