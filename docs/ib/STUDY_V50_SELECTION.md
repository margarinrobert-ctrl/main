# V50 — Adverse selection at a fixed fill rate (pre-registered, PASSED gates 1–5, gate 6 unavailable)

**The hypothesis survived on its own pre-registered threshold: ρ = −0.5887 against a required
−0.50, permutation p 0.0000 against a required 0.05, monotone across all five quintiles, holding
separately on both sides, and keeping its sign on the locked block. It is a confirmed MECHANISM and
not an edge — SELECTION is a cost, and nothing here is tradeable.** The brief's success criterion
also requires a held-back market, and US100/US30 were wiped by a container recycle, so gate 6 could
not be run and the criterion is not met.

Run under `docs/ib/EDGE_LOOP.md` as round 2, taking queue item 1 of `docs/ib/EDGE_LEDGER.md` —
the follow-up V49's own post-mortem generated. NQ 5-minute signals, every trade walked on the true
1-minute path, 44 signal families × 2 sides = 88 cells.

---

## The pre-registration, as written before any computation

| | |
| --- | --- |
| **Hypothesis** | A resting limit fills only after an adverse excursion, so the subset it fills is adversely selected; the size of that adverse selection is set by how front-loaded the signal's edge is. **At a fixed fill rate**, SELECTION — the mean market-price R of the filled subset minus the mean over all signals — falls as immediacy rises. |
| **Control** | Permutation of the immediacy labels across cells, 5,000 draws. The claim is about a relationship, so shuffling labels is the correct null. |
| **Threshold** | ρ ≤ **−0.50**, permutation p ≤ **0.05**, monotone quintiles, **holding within each side separately**, same sign on locked. |
| **Read once** | NQ locked (last 35%), after freezing, for the sign only. |
| **Abandon if** | ρ > −0.30, non-monotone quintiles, or a sign flip on locked. |

Declared and not searched: limit **1.0 × ATR**, stop **2.0N**, **no target**, max hold 480 min,
immediacy = mean mark-to-market R at **+30 min** on the market leg, target fill rate **0.35** (the
`STUDY_ATME` figure at this depth) in a **±0.03** band, research = first 65% of bars.

**SELECTION is computed entirely on the MARKET leg.** Only the fill *mask* comes from the limit
walk, so no price improvement can leak into the quantity being explained.

---

## Gate 1 — the truncation audit, and a leak in V49's ladder

1,150 (family, bar) recomputations on history ending at the bar: **no family changes its value.**

Getting there required one correction. V49's `roc.up{n}` / `roc.dn{n}` cut at
`np.nanquantile(roc, 0.90)` **over the whole series** — a threshold that reads the future. Replaced
with an expanding quantile, shifted one bar. Measured, it is a small leak and it did not change
V49's verdict: it flips **0.82% / 0.95% / 1.30%** of bars at n = 12 / 48 / 192. It is recorded
because a full-sample constant is exactly the kind of thing inspection passes and the audit does not.

## The fill-rate control — the design fix this round exists to apply

`SELECTION = (1 − φ) × (μ_fill − μ_nofill)`, so it scales with the *non*-fill rate: two families
with identical underlying adverse selection but different fill rates report different SELECTION.
V49 left φ to fall out of a declared 5-minute expiry and got **0.173**. Here the expiry is swept per
cell against a pre-computed time-to-fill array (fill rate at any expiry is then a count, so
calibration costs one walk per cell, not one per candidate expiry).

```
achieved fill rate   0.342 .. 0.359   sd 0.0043      88 of 88 cells inside the declared band
calibrated expiry    8 .. 23 minutes, median 14
rho(fill rate, SELECTION) = +0.1342   permutation p 0.8938     [confound check]
rho(expiry,    SELECTION) = +0.0124                            [confound check]
identity SELECTION == (1-phi) * gap: max abs difference 0.000000
```

Both confounds are clean, and the φ-invariant gap `μ_fill − μ_nofill` carries the identical
gradient (ρ −0.5890 against SELECTION's −0.5887), so the result does not depend on the normalisation.

## Gate 2 — the gradient

```
rho(immediacy, SELECTION)  = -0.5887   permutation p 0.0000   n 88
threshold: rho <= -0.50 and p <= 0.05                  ->  PASS
abandonment condition rho > -0.30                      ->  not triggered
within side  L  rho -0.4717  p 0.0004  (n 44)
within side  S  rho -0.4732  p 0.0008  (n 44)
```

| immediacy quintile | cells | mean immediacy | SELECTION | fill/no-fill gap | fill |
| --- | --- | --- | --- | --- | --- |
| Q1 | 18 | −0.0867 | −0.4654 | −0.7168 | 0.351 |
| Q2 | 17 | −0.0582 | −0.4750 | −0.7322 | 0.352 |
| Q3 | 18 | −0.0397 | −0.5301 | −0.8166 | 0.351 |
| Q4 | 17 | −0.0293 | −0.5351 | −0.8232 | 0.350 |
| Q5 | 18 | −0.0042 | **−0.5751** | −0.8832 | 0.349 |

Monotone on every step. The requirement that it hold **within side** matters: this sample is 89%
up-drift, and a gradient visible only when longs and shorts are pooled would be that drift. It holds
at ρ −0.47 on each side alone.

## Gates 3–5

**Gate 3 — the population, before any cell is named.** SELECTION is negative in **88 of 88** cells
(mean −0.5164). The limit beats the market in **34 of 88 = 38.6%** of cells, mean net −0.0205. **No
configuration is proposed and none is rankable**: this round measures a quantity, not a strategy.

**Gate 4 — cost stress.** The gradient survives, because SELECTION is a market-leg differential in
which the cost largely cancels: ρ **−0.5887 / −0.5802 / −0.5454** at 1× / 1.5× / 2× the assumed
spread. Net delta stays negative on average at every cost level (−0.0205 / −0.0219 / −0.0249).

**Gate 5 — one locked read.** ρ **−0.3120** over 84 cells, **sign held**, decayed from −0.5887 —
the right shape. SELECTION is negative in 84 of 84.

**Gate 6 — cross-market: NOT RUN.** A container recycle wiped `US100_LONG_15m` and `US30_LONG_15m`
again. The pre-registered success criterion requires a held-back market, so **the criterion is not
met regardless of the result above**, and this is one market and one instrument.

---

## The post-mortem: a THIRD component, and it is equal and opposite

V49 decomposed the net into SELECTION and PRICE and called PRICE "close to an arithmetic identity."
**That was wrong as a statement about its variation.** PRICE's *mean* is the identity; its
*dispersion across families* is as large as SELECTION's, and it moves with immediacy in the
opposite direction:

```
                              mean       sd     range              rho vs immediacy      p
SELECTION                   -0.5164   0.0689   -0.6695..-0.3801       -0.5887         0.0000
PRICE                       +0.4959   0.0674   +0.2098..+0.6805       +0.4711         0.0002
NET (the tested quantity)   -0.0619*  ......                          -0.2277         0.0350
```
\* mean |net|; the signed mean is −0.0205. **The net is 8.3× smaller than its parts.**

So the mechanism is real and strong in SELECTION, and it is *cancelled* by an opposing force of
nearly the same magnitude. That is why V49's net gradient was −0.32 and why this one is −0.23.

### The obvious explanation for PRICE is refuted

If PRICE rises with immediacy because a market order **chases** — filling at the next bar's open
after the price has already moved — then the open gap itself must carry the gradient. It does not:

```
adverse open gap   mean +0.0000 ATR   range -0.0109..+0.0109 ATR   (worst cell = +0.0054 R)
rho(immediacy, adverse open gap) = -0.0390   permutation p 0.7182
```

On continuously traded futures the next open is the previous close. **There is no chasing cost on
this data at 5-minute resolution**, which also means every market-entry backtest on this branch is
not quietly paying one.

### It is the EXIT PATH, and that is the next hypothesis

Splitting PRICE into the pure entry offset and everything else:

```
entry offset (an identity)   mean +0.498745   sd 0.001729     construction says 0.5000
exit path                    mean -0.0028     sd 0.0673       range -0.2894..+0.1821
share of PRICE's cross-family variance that is exit path:  99.8%
rho(immediacy, exit path) = +0.4750
```

**99.8% of PRICE's variation is the exit path.** Two trades on the same signal, with the same risk
denominator, differing only in that one entered 1 ATR lower — and therefore carries a stop 1 ATR
lower in price and starts its 480-minute clock later — diverge by up to **0.29 R**, and that
divergence is what cancels the adverse selection. The entry price is an identity; the *location of
the stop* is the whole variable.

### The design fault that most limited this round

**Immediacy still does not span positive.** It runs −0.1191 to +0.0343 with **4 of 88 cells
positive** — barely better than V49's 2 of 44, and over the identical range. Mirroring every family
to the short side was supposed to supply the front-loaded end and did not, because immediacy carries
a **common-mode cost drag of about 0.04 R** (a 0.72-point round turn against a ~20-point risk) that
pushes both sides negative. The fix is to measure immediacy **gross**, or to source families with
genuinely front-loaded edge, not to mirror.

## Caveats

One market, one instrument; gate 6 was unavailable. The 88 cells are **not independent** — Donchian
lengths and RSI periods overlap heavily, and each rule's long and short mirror share signal bars —
so the permutation null is the right one but its effective sample is well below 88. Spread is
assumed, as in every feed here. And the headline is a cost, not an edge: confirming that adverse
selection grows with immediacy tells you where a limit mechanic is *least bad*, not where money is.

## Files

`research/v50/v50sel.py` (both mechanics, both sides, one walker, the time-to-fill calibrator, the
ladder with the quantile leak fixed) · `run_v50.py` (gate 1 + the cell table) · `stats_v50.py`
(gate 2) · `run_v50b.py` (gates 3–5) · `run_v50c.py` (the chasing test and the PRICE split) ·
`results/v50/`.
