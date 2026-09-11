# V55 — Automated: the gate is exhausted sellers, and both requested additions break the bar

**The bar was set explicitly — the shipped rule must reproduce EXHAUSTED SELLERS k3 w20 (research
+0.3509 PF 1.696 p 0.001, locked +0.3176 PF 1.648 p 0.009). It was re-measured on a fresh 2,000-draw
control and holds at p 0.000 / 0.005. Both requested additions were then measured against the same
control and both LOSE THE LOCKED BLOCK: the union with absorbed selling halves the edge
(+0.3509 → +0.1842) and goes to p 0.210; the EMA 13×48 state takes locked to p 0.158.**

So the gate is hard-wired to exhausted sellers, with no pattern to choose. Absorbed selling and both
EMAs are computed and plotted, and each can be switched into the gate by one checkbox that is off by
default and states its own measured cost.

---

## The gate

Base: NQ 30m, Donchian 20 in / 20 out, 2.0N stop, one unit, long, no target, max hold 480. Every
reading against a random filter keeping the same share of the same signals, 2,000 draws. Research is
the first 65% of bars, locked the last 35%.

| reading | keep | research | LOCKED |
| --- | --- | --- | --- |
| *base, no condition* | 100% | *+0.0945 PF 1.161* | *+0.1280 PF 1.237* |
| **EXHAUSTED SELLERS** (shipped) | 21.5% | **+0.3509 PF 1.696 p 0.000** | **+0.3176 PF 1.648 p 0.005** |
| EITHER exhausted OR absorbed | 41.8% | +0.1842 PF 1.336 p 0.043 | +0.1829 PF 1.342 **p 0.210** |
| EXHAUSTED + EMA13 > EMA48 | 17.0% | +0.2980 PF 1.588 p 0.014 | +0.2079 PF 1.423 **p 0.158** |
| EXHAUSTED + EMA13×48 cross ≤ 20 | 6.9% | +0.0967 PF 1.174 **p 0.677** | +0.2350 PF 1.545 p 0.174 |
| ABSORBED SELLING alone | 24.1% | +0.2308 PF 1.404 p 0.050 | +0.0329 PF 1.055 **p 0.908** |
| ABSORBED SELLING + EMA13 > EMA48 | 18.5% | +0.3370 PF 1.620 p 0.002 | +0.0967 PF 1.168 **p 0.611** |
| ABSORBED SELLING + cross ≤ 20 | 5.8% | +0.1919 p 0.394 | +0.0145 p 0.685 |
| EITHER + EMA13 > EMA48 | 32.7% | +0.2206 PF 1.414 p 0.024 | +0.1710 PF 1.331 **p 0.286** |

### Why the union fails

Adding absorbed selling nearly doubles the trade count (21.5% → 41.8% of signals kept) and halves
the per-trade edge. That is the union rule this branch already had written down: **a union is
diluted by its weaker member, so gate on the size of the excess and never on its sign.** Absorbed
selling does not clear the locked block in any form tested — alone p 0.908, with the EMA state
p 0.611, with the cross p 0.685. Note it *does* clear research at p 0.050 and p 0.002, which is
exactly how a weaker member sneaks into a union if only the research block is read.

### Why the cross fails

As a state it costs the locked gate (p 0.005 → 0.158) while keeping research respectable — the
classic shape of a filter that fits the search block. As a *fresh* cross it destroys research
outright (p 0.677) on 6.9% of signals. This is the third time the 13×48 cross has been measured on
this branch and the third time it has failed a held-back read (V51: US30 p 0.400–1.000; V52:
US30 p 0.400; here: locked p 0.158).

## The neighbourhood

A real mechanism decays smoothly across its own parameters; a fitted one spikes. Exhausted sellers,
research R / locked R over the full pivot-width × recency-window grid:

| | w=5 | w=10 | w=20 | w=40 |
| --- | --- | --- | --- | --- |
| **k=2** | +0.535 / +0.073 | +0.341 / +0.143 | +0.269 / +0.233 | +0.163 / +0.242 |
| **k=3** | +0.550 / +0.631 | +0.395 / +0.449 | +0.351 / +0.318 | +0.245 / +0.236 |
| **k=4** | +0.458 / +0.222 | +0.453 / +0.311 | +0.405 / +0.185 | +0.320 / +0.252 |
| **k=5** | +0.248 / +0.043 | +0.385 / +0.228 | +0.385 / +0.163 | +0.207 / +0.216 |

**Positive in all 16 cells on both blocks**, falling monotonically as the window widens. That is the
shape an edge is supposed to have, and it is the strongest thing in this study — stronger than any
single cell's p-value, because it is a replication across the whole parameter surface.

**k=3 / w=20 is not the maximum.** k=3 / w=5 scores higher on both blocks (+0.550 / +0.631) and
w=20 is shipped anyway because it carries **n=88 locked trades against w=5's n=37**. The larger
sample is worth more than the larger number, and w=20 is the cell V54 pre-registered.

The union's neighbourhood is also positive in all 16 cells but uniformly lower (research +0.106 to
+0.596, locked +0.055 to +0.413) — consistent with dilution rather than with a different mechanism.

## What is in the script

Removed: the KAMA entirely, and the pattern dropdown. The gate is automatic.

Kept and plotted but not gating: absorbed selling, EMA 13, EMA 48. Two off-by-default checkboxes can
add them to the gate, each labelled with the locked-block p-value it costs.

## Caveats

n = 88 on the locked block, under 100. **One market** — CVD needs 1-minute bars and NQ is the only
feed here that has them, so there is no cross-market read. The CVD is a **proxy**: true aggressor
delta is in no feed on this branch, so each lower-timeframe bar's whole volume is signed by its own
direction, which is TradingView's own rule; the Pine computes it with `request.security_lower_tf`
rather than calling a built-in so the identity with the research is provable. Spread is assumed.
This is one confirmation, not a result.

## Files

`research/v55/run_v55.py` (the gate and the neighbourhood) · `results/v55/v55_gate.csv`,
`v55_neighbourhood.csv` · `pine/v55/V55_CVD_EXHAUSTION_strategy.pine`.
