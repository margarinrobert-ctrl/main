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

## Caveats

One market. Cross-market (gate 6) **could not be run** — a container recycle wiped US100 and US30
again before this study, so the pre-registered "held-back market" half of the success criterion was
unavailable regardless of the outcome. The 40 families are not independent (Donchian lengths and RSI
periods overlap heavily), so the permutation null is the right one but its effective sample is below
40. Spread is assumed, as in every feed here.

## Files

`research/v49/v49mech.py` (one walker, two mechanics, 1-minute path; the 45-family ladder) ·
`run_v49.py` · `results/v49/v49_gradient.csv`.
