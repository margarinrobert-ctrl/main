# PIN (probability of informed trading) as an intraday signal — Yan (2009), SSRN 1361921

**Verdict: the mechanism is absent on an index future, and the ask is out of reach by a factor of
three. Best research profit factor 1.116 against the 2.0 requested; 0 of 4 cells clear a matched
control; every locked cell clears while every research cell fails.** Ships the machinery, claims
no edge, no Pine written.

## Phase 0 — what the paper gives, and what it does not

The paper is an estimator for **PIN**, not a trading rule. EKOP (1996) model each day as a mixture:
an information event occurs with probability α, is bad with probability δ, informed traders then
arrive at rate μ on one side, and uninformed traders arrive at rates ε_b and ε_s regardless.
`PIN = αμ / (αμ + ε_b + ε_s)`. Yan replaces EKOP's maximum likelihood with four moment steps —
identify event days by event study, classify B and S by Lee-Ready, take conditional means, and
apply eq. (9).

**The mechanism names its counterparty explicitly, which is rare and is why this was worth
building.** The uninformed trade at ε every day whether or not there is news — liquidity,
rebalancing, market-making obligation — and on an event day they are on the wrong side of μ by
construction, because they do not know.

**But PIN itself is not a signal.** It is the unconditional, non-directional fraction of trades
that are informed, used in asset pricing to explain expected returns over months. What is
directional is the **posterior from the same mixture** given today's flow — the market maker's own
belief update:

```
P(good | B,S) ∝ α(1-δ)·Pois(B; ε_b+μ)·Pois(S; ε_s)
P(bad  | B,S) ∝ αδ    ·Pois(B; ε_b)   ·Pois(S; ε_s+μ)
P(none | B,S) ∝ (1-α) ·Pois(B; ε_b)   ·Pois(S; ε_s)
```

That is the object tested here, computed on a running intraday basis with the rates scaled by the
fraction of session elapsed.

**Two degradations, stated once.** B and S are counts of *buyer- and seller-initiated* trades,
classified by Lee-Ready, which needs the **quote midpoint**. No feed on this branch carries quotes
or aggressor tags. And NQ_1m is the only feed with one-minute bars, so this runs on one market.

**Causality.** Yan's step 1 uses an event study over the whole period, which is two-sided and
untradeable. Here an event day is one whose return exceeds k trailing standard deviations, with
every parameter fitted on a 120-session window that closes *before* the session it is used in.

## The number that decided it, before any backtest

| construction | α | ε_b | ε_s | μ | **μ/(ε_b+ε_s)** | **PIN** |
|---|---|---|---|---|---|---|
| session, bar counts | 0.275 | 186.5 | 178.7 | 5.40 | **0.0148** | **0.0043** |
| 30-min buckets, counts | 0.261 | 15.0 | 14.3 | 0.99 | 0.0339 | 0.0088 |
| session, **volume-weighted** | 0.275 | 181.8 | 178.0 | 18.56 | **0.0519** | **0.0142** |

**PIN in the equity literature runs 0.10–0.20** (EKOP's own 90 stocks average ~0.19). Measured here
it is 0.004–0.014 — **an order of magnitude smaller**, and both reasons were predictable:

1. **PIN IS A SINGLE-NAME MEASURE.** It prices *firm-specific* private information. There is no
   insider on the Nasdaq-100. An index future is the most liquid, least information-asymmetric
   instrument there is, and the literature's own finding is that PIN *falls* with size and
   liquidity. The mechanism is weakest exactly where it is being applied.
2. **The B/S proxy is coarse** without quotes.

**The count-based posterior is mathematically incapable of confidence.** With μ at 1.5% of ε the
likelihood ratio barely leaves the prior: P(good) maxes at **0.405** and there are **zero** bars
above 0.5. The 30-minute bucket variation raises the *ratio* to 0.034 — the right direction — and
makes the posterior **worse** (max 0.207), because μ falls to **0.99 informed arrivals per 30
minutes** against a background of 30. You cannot detect a signal of one against a background of
thirty.

## What fixed it, and what happened then

Volume weighting. EKOP's footnote 7 states their model ignores trade *size*; but an informed trader
with private information trades size. Weighting B and S by volume raises μ/ε from 0.015 to **0.052**
and the posterior finally spans [0,1] — 1,231 bars above 0.9.

Gate 1, one contract, MNQ costs, 2.5×ATR stop, no target, 10-minute bars:

| threshold | block | n | /yr | pts | PF | win | Sharpe |
|---|---|---|---|---|---|---|---|
| 0.50 | research | 722 | 366 | +2.63 | 1.078 | 48.8% | +0.57 |
| 0.50 | LOCKED | 315 | 296 | +4.06 | 1.076 | 51.4% | +0.46 |
| 0.70 | research | 479 | 243 | +1.29 | 1.037 | 51.4% | +0.23 |
| 0.70 | LOCKED | 232 | 218 | +15.23 | 1.287 | 53.5% | +1.25 |
| 0.85 | research | 278 | 141 | **-2.82** | 0.928 | 46.0% | -0.39 |
| 0.85 | LOCKED | 156 | 147 | +23.18 | 1.427 | 54.5% | +1.49 |
| **0.95** | research | 119 | 60 | +4.17 | **1.116** | 51.3% | +0.35 |
| 0.95 | LOCKED | 83 | 78 | +32.53 | 1.606 | 62.7% | +1.43 |

## The control kills it

Matched random entries — same window, same rate, same side mix, same exits, 300 draws:

| threshold | block | n | rule | control | excess | p |
|---|---|---|---|---|---|---|
| 0.50 | research | 722 | +2.63 | -1.96 | +4.59 | 0.067 |
| 0.70 | research | 479 | +1.29 | -2.44 | +3.72 | 0.197 |
| 0.85 | research | 278 | -2.82 | -2.04 | -0.78 | 0.590 |
| 0.95 | research | 119 | +4.17 | -2.89 | +7.06 | 0.157 |
| 0.50 | LOCKED | 315 | +4.06 | -1.52 | +5.58 | 0.243 |
| 0.70 | LOCKED | 232 | +15.23 | -1.00 | +16.23 | **0.027** |
| 0.85 | LOCKED | 156 | +23.18 | -0.85 | +24.03 | **0.013** |
| 0.95 | LOCKED | 83 | +32.53 | -1.27 | +33.80 | **0.003** |

**0 of 4 research cells clear at p<=0.05; every locked cell clears.** That is the wrong shape at
every single threshold, systematically — the eighteenth occurrence on this branch, and the most
uniform. A rule chosen on research should look better *there*.

## The ask, in arithmetic

Best research cell: mean win **+78.25 pts**, mean loss **-73.75**, win rate **0.513** → PF 1.116.

| target PF | win rate needed | lift required |
|---|---|---|
| 1.5 | 0.586 | +7.3 points |
| **2.0** | **0.653** | **+14.1 points** |
| 3.0 | 0.739 | +22.6 points |

The best honest win-rate lift measured anywhere on this branch is **+1 to +5 points**.
`STUDY_INSTITUTIONAL_FRONTIER` swept 2,792,878 intraday configurations here and found **zero** cells
at PF ≥ 2.0 with ≥ 200 trades/yr *on the research block*, where 89.5% of cells are profitable.
**PF 2 is not a modelling problem on this data; it is arithmetic.**

## What would make PIN work

- **Trade-and-quote data with aggressor side.** Lee-Ready needs the midpoint; everything here is a
  proxy. This is the binding constraint.
- **Single names, not an index.** PIN measures firm-specific asymmetry; run it on stocks around
  earnings, M&A or FDA decisions, where the mechanism actually exists and the literature measures
  PIN at 0.10–0.20 rather than 0.014.
- **The event, not the average.** PIN's documented use is cross-sectional — rank names by PIN and
  hold the high-PIN portfolio — not intraday timing on one liquid future.

`research/pin/pin_core.py`, `run_g1.py`, `run_g2.py`, `run_g3.py`, `run_g4.py`.
