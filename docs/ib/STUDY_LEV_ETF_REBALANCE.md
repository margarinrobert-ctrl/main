# STUDY: the levered-ETF close rebalance, built mechanism-first — and killed by Gate 1

**What this is.** The first strategy on this branch built to the mechanism-first architecture: a
primary derived from a named market mechanism, a meta layer that would only ever score its events,
and two gates that stop features or sizing from being credited with an edge they did not create.

**It did not get past Gate 1.** The meta layer was never built, which is the architecture working:
it cost one module and two scripts to find out, instead of a feature study and a holdout.

**Code.** `research/lev/lev_core.py` (the mechanism, the arithmetic, the event stream, a causality
audit), `research/lev/run_gate1.py`. Output `results/lev/gate1.txt`, `gate1_granularity.txt`.

## Phase 0 — the mechanism, written before any code

| question | answer |
| --- | --- |
| Who is the counterparty? | Issuers of levered and inverse index ETFs and their swap desks — TQQQ (+3x), SQQQ (−3x), QLD, QID, PSQ on the Nasdaq-100; UDOW, SDOW, DDM, DXD, DOG on the Dow. Tens of billions of notional that must be reset daily. |
| Why do they trade anyway? | The prospectus promises a constant multiple of the **daily** return. That is only deliverable if exposure is restored to L × NAV by the close of every session. They are discharging a contract, not forecasting. |
| Why can't they stop? | The daily reset *is* the product. Skipping it breaches the stated objective. The flow is price-insensitive, direction-certain, and clustered at the close because that is when the reference NAV is struck. |
| What do we provide? | Liquidity and patience — the other side of a trade that must happen at a time not of the counterparty's choosing. |
| What would end it? | Levered-ETF assets shrinking, a change in reset frequency, execution spread away from the close, or enough competing capital. Studied since ~2010; the whole sample here is post-publication. |

**Family: constrained flow.** Sharp, capacity-limited, decaying — not a risk premium.

## Phase 1 — the primary, derived not fitted

A fund with leverage L and NAV N holds exposure L·N. After an index return r:

```
required trade = L·N·(1 + L·r) − L·N·(1 + r) = L·N·r·(L − 1)
L=+3 → +6N·r    L=−3 → +12N·r    L=+2 → +2N·r    L=−2 → +6N·r    L=−1 → +2N·r
```

Every coefficient L(L−1) is positive for L>1 **and** for L<0, so long-levered and inverse funds
trade in the *same* direction: all buy into an up day, all sell into a down day. **The side is
sign(r) — forced by arithmetic, with no threshold and nothing fitted.** Aggregate flow is
proportional to |r|, which makes |r| a flow-magnitude proxy and therefore a *meta* feature.

| element | value | source |
| --- | --- | --- |
| trigger | every regular-session day, no condition | the mandate is daily |
| side | sign of the return from the prior cash close to the last price before the window | the fund's own reset reference |
| entry | open of the first bar of the rebalance window | front-run flow that must arrive |
| exit | the cash close (close of the 15:45 bar) | when the reference NAV is struck |

**Free parameters: one** — the observation time, declared at 15:30 New York because levered funds
concentrate execution in the closing half hour. Every alternative evaluated is counted as a trial.

Causality audit (rebuild each trigger from bars ending at or before entry): **0 mismatches** in 144
US100 and 161 US30 probes.

## Gate 1 — the primary alone. It fails on every market, strict and relaxed

Every event, equal weighted, costs in, no filter, no sizing.

| market | span | n | net %/event | 95% CI | p | hit | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| US100 | 8.9 yr | 2,074 | **−0.00864** | [−0.0215, +0.0040] | 1.000 | 47.9% | **FAIL** |
| US30 | 8.7 yr | 2,045 | **−0.01186** | [−0.0217, −0.0013] | 1.000 | 47.7% | **FAIL** |

**And it is not a cost problem.** Gross of all costs, US100 earns **+0.00055 %/event** — the round
turn is 1,662% of that — and US30 is **negative gross** at −0.00611. There is no edge for better
execution to rescue.

**The relaxed gate makes it worse, and that is the decisive evidence.** The mechanism says required
flow is proportional to |r|, so a bigger move must mean a bigger forced trade. Pre-registered, the
upper half of |r| should be where the edge lives. It is where the losses live:

| market | upper half of \|r\| | lower half |
| --- | --- | --- |
| US100 | −0.01563 | −0.00164 |
| US30 | −0.01841 | −0.00531 |

By quintile the gradient runs the wrong way on both markets — US100 Q1 to Q5: +0.0026, +0.0152,
+0.0098, −0.0163, −0.0085 gross; US30: +0.0044, −0.0069, +0.0033, −0.0112, −0.0201 gross. **The
mechanism's own conditioning variable predicts the opposite of what the mechanism predicts.**

**Granularity is not the explanation.** On NQ 1-minute data, tightening the window all the way to
the last five minutes of the cash session leaves gross at **+0.00111 %/event** and net negative:

| window | hold | n | net %/event | gross %/event | p |
| --- | --- | --- | --- | --- | --- |
| 15:00 → 16:00 | 60m | 733 | +0.00401 | +0.01095 | 0.367 |
| 15:30 → 16:00 | 30m | 734 | −0.02940 | −0.02246 | 1.000 |
| 15:50 → 16:00 | 10m | 733 | −0.00837 | −0.00143 | 1.000 |
| 15:55 → 16:00 | 5m | 734 | −0.00583 | +0.00111 | 1.000 |

**Nor is it drift.** Always-long over the same windows is −0.00005 on US100 and −0.00761 on US30.

**Trials counted: 14** — 8 observation times × 2 markets, 1 for the |r| conditioning choice, 5 NQ
granularity windows. No deflation is needed because nothing survived to deflate.

## The inversion, recorded and not traded

Flipping the side is positive on both markets: US30 +0.01186 at **p 0.010**, US100 +0.00864 at
p 0.086. Fading the day's move into the close beats following it.

**This is not adopted, and the reason is the architecture.** It is the second of exactly two looks
at the same events, so one of them was always going to be positive. Turning it into a strategy
would mean writing a new mechanism story to fit a pattern already found — the failure mode this
whole structure exists to prevent, and the one that produced the branch's last two dead candidates.
If closing-auction mean reversion is to be tested it needs its own Phase 0: a named counterparty,
their constraint, and a pre-registered read on data these 14 trials have not touched.

## Verdict

**Stop. This is a Phase 0 problem.** A primary that cannot clear Gate 1 is saying the mechanism is
wrong or the event definition does not isolate it, and no meta layer addresses either. The most
likely reading is that the effect is real but arbitraged: it has been published since about 2010,
this sample is 2016–2025, and issuers hedge continuously with futures rather than dumping at the
bell. The mechanism confers plausibility, not permanence.

**What would reopen it:** levered-ETF AUM and flow data, so the trigger is the *actual* required
notional rather than a return proxy; or single-stock or sector ETFs where levered AUM is large
relative to underlying liquidity and arbitrage capital is thinner. Neither is on this branch's disk.

**What this cost:** one module, two scripts, one session — with no feature engineering, no holdout
spent, and no Pine shipped. Against `STUDY_VP_TPO_SCALP`, where the same verdict arrived after 45
features, 152 looks and a cross-market read, that is the entire argument for the architecture.
