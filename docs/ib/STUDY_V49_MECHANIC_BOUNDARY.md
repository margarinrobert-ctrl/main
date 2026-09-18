# V49 — Where does the limit entry stop helping? (pre-registered, FAILED at gate 2)

**Hypothesis rejected on its own pre-registered threshold. ρ = −0.193 against a required −0.50;
permutation p 0.122 against a required 0.05. The abandonment condition (ρ > −0.30) triggered.**

Run under `docs/ib/EDGE_BRIEF.md`. NQ 5-minute signals, every trade walked on the **true 1-minute
path**, 45 declared signal families, 40 scorable.

---

## The pre-registration, as written before any computation

| | |
| --- | --- |
| **Hypothesis** | The limit entry's advantage over a market entry is a *decreasing function of the signal's own immediacy*. A resting limit fills only after an adverse excursion, so it discards trades that move in your favour at once. |
| **Prediction** | (limit − market) delta falls monotonically as immediacy rises, crossing zero inside the observed range. |
| **Control** | Permutation of the immediacy labels, 5,000 draws. The claim is about a *relationship*, so shuffling labels is the correct null. |
| **Threshold** | ρ ≤ **−0.50**, permutation p ≤ **0.05**, same sign on locked, zero-crossing inside the range. |
| **Read once** | NQ locked (last 35%), after freezing. |
| **Abandon if** | ρ > −0.30, non-monotone quintiles, or sign flip on locked. |

Declared parameters, none searched: limit **1.0 × ATR**, order live **5 minutes**, stop **2.0N**,
**no target**, max hold 480 min, immediacy = mean mark-to-market R at **+30 min** on the market leg.

---

## Gate 2: the result

```
40 families with >=100 filled trades on both mechanics
Spearman rho(immediacy, limit-minus-market) = -0.1929
permutation p (5,000 label shuffles)        =  0.1224
threshold: rho <= -0.50 and p <= 0.05       ->  FAIL
```

| immediacy quintile | families | mean immediacy | mean delta |
| --- | --- | --- | --- |
| Q1 | 8 | −0.0545 | −0.0140 |
| Q2 | 8 | −0.0413 | −0.0225 |
| Q3 | 8 | −0.0353 | −0.0131 |
| Q4 | 8 | −0.0181 | −0.0343 |
| Q5 | 8 | **+0.0020** | **−0.0554** |

**The direction is right and the magnitude is not.** Q1 → Q5 falls from −0.014 to −0.055, roughly
monotone with a bump at Q3, and the sign holds on locked (ρ −0.062). But −0.193 is a fraction of the
−0.50 required, it does not clear its own permutation null, and the abandonment condition fires.
**Per the brief, this stops here. No holdout was read as evidence and no configuration is proposed.**

---

## What the failed run measured anyway

**The limit entry was worse than a market entry almost everywhere**: negative in **30 of 40**
families on research (mean −0.0279 R) and **23 of 40** on locked (mean −0.0246). The predicted
zero-crossing does not exist in this sample because the delta never reaches zero from above.

The extremes behave as the mechanism predicts even though the gradient is too weak to pass:

| family | immediacy | market R | limit R | delta |
| --- | --- | --- | --- | --- |
| rsi.lo28 | −0.0869 | +0.0132 | −0.1421 | −0.1553 |
| roc.dn192 | −0.0542 | −0.0617 | −0.0891 | −0.0274 |
| roc.up48 | +0.0043 | **+0.2100** | +0.1467 | −0.0633 |
| rsi.hi28 | **+0.0345** | **+0.2311** | +0.1371 | **−0.0940** |

The two strongest signals (`roc.up48`, `rsi.hi28`, market R +0.21 and +0.23) lose the most to the
limit — which is the substitution effect `STUDY_LIMIT_ENTRY` described. What is missing is the other
end: no family here is helped.

### The confound, and why it is not resolved by tuning

**Fill rate is 17.3%, against the ~35% `STUDY_ATME` measured at 1.0 × ATR.** That is my declared
5-minute expiry: a limit live for one 5-minute bar is a materially more restrictive mechanic than the
one ATME scored. **So this does not overturn ATME's +0.24 to +0.43 R** — it measures a different,
tighter order and finds it costly. It is, however, consistent in direction with `STUDY_ATME_LIVE`,
which already found the 5-minute result collapsing from +0.331 R to −0.003 when re-run on the
1-minute path.

Widening the expiry now, having seen this, would be searching after the fact. **The expiry is the
single variable worth pre-registering in the next run of this brief**, with the fill rate declared
as a control variable rather than left to fall out.

## WHY IT FAILED — the delta is a residual of two large, near-cancelling forces

Decomposing the tested quantity on 44 families, research block:

```
delta = (SELECTION: which signals the limit fills) + (PRICE: the better fill)

component                                   mean    median    <0 in
SELECTION  mkt(on fills) - mkt(all)      -0.5492   -0.5628    44/44
PRICE      lim(on fills) - mkt(on fills)  +0.5366   +0.5342     0/44
DELTA      the tested quantity            -0.0126   -0.0266    30/44
```

**Each component is about 0.54 R and they cancel to −0.013.** The hypothesis was aimed at a residual
roughly **forty times smaller than its own parts**, so a pre-registered threshold of ρ ≤ −0.50 was
asking for a clean gradient in a quantity dominated by noise in either half. That is a design fault
in the test, not a property of the market.

**The PRICE term is close to an arithmetic identity, not an edge.** Entering 1.0 × ATR lower with a
risk denominator of 2.0 × ATR is worth exactly **0.5 R** by construction; the measured +0.5366
is that identity plus a +0.037 residual from path and cost differences. The limit does not earn
+0.54 R — it *relocates* the entry, and R is measured off the new base.

**The SELECTION term is what the market charges for that relocation**, and it is −0.5492: the
signals a limit actually fills are worth half an R *less* at market prices than the average signal
of the same family. **The two are within 0.013 R of each other in 44 of 44 families.** That is as
clean a statement of efficiency at this horizon as anything measured on this branch — you can move
your entry a full ATR, and the population of trades you get instead costs you almost exactly what
the price improvement is worth.

**And the hypothesised mechanism is real — it just lives in the wrong term.**

```
rho(immediacy, SELECTION) = -0.3844
rho(immediacy, PRICE)     = +0.1377
rho(immediacy, DELTA)     = -0.3205
```

The gradient is **stronger against selection than against the net**, and in the predicted direction:
the more front-loaded a signal's edge, the worse the trades a limit ends up filling. The hypothesis
named the right mechanism and then tested the wrong quantity.

**A second design fault: the independent variable barely varies.** Immediacy spans −0.119 to +0.034
and **only 2 of 44 families are positive**. A gradient across immediacy was tested without supplying
a front-loaded end of the range — and the predicted zero-crossing was always going to be absent
because the delta never approaches zero from above.

### What to pre-register next time

Test **SELECTION**, not the net delta: for a fixed fill rate, does the market-price value of the
filled subset fall as signal immediacy rises? Declare fill rate as a control variable and sweep the
expiry to hold it constant across families, so the fill population is comparable. And build the
ladder to span positive immediacy, which this one did not.

## Caveats

One market. Cross-market (gate 6) **could not be run** — a container recycle wiped US100 and US30
again before this study, so the pre-registered "held-back market" half of the success criterion was
unavailable regardless of the outcome. The 40 families are not independent (Donchian lengths and RSI
periods overlap heavily), so the permutation null is the right one but its effective sample is below
40. Spread is assumed, as in every feed here.

## Files

`research/v49/v49mech.py` (one walker, two mechanics, 1-minute path; the 45-family ladder) ·
`run_v49.py` · `results/v49/v49_gradient.csv`.
