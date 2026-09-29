# V34 — the entry mechanic, pre-registered, on the true 1-minute path

**Ask.** Stop searching and settle whether the entry mechanic — the one effect on this branch large
enough to survive being looked for — is real, intraday only, to a standard of "beats a matched
control and holds out of sample".

**Answer.** No, and the reason is an engine defect rather than the market. `limit_entry._walk_limit`
holds **a book of simultaneous resting orders** where a script holds one: a mean of **2.45 live at
once** even at the tightest setting, and **15.9 at the longest**. Correcting it to one live order
removes the entire apparent effect. On the corrected engine the resting limit beats a market order
in **17 of 32 declared cells on research (53%) and 18 of 32 on locked (56%)** — chance is 50% — it
is **not monotone in depth**, it is **not symmetric across sides**, and its research→locked rank
correlation is **+0.139**. **Nothing ships. H4 was never reached, because nothing survived H1 to
gate.**

---

## 1. Why this and not another search

Three independent measurements now say in-sample ranking carries no information about out-of-sample
ranking here: V30's surrogate (research surface fitted at ρ 0.96, locked predicted at 0.07), V31's
cross-family (research→locked R correlation +0.215), V33's negative train→validation rank transfer
(−0.05 to −0.375 over 207,360 configurations). A fourth search of the same family finds a fourth
spurious maximum.

So V34 is not a search. **Five hypotheses were written into the module before the first run**, over
**32 declared cells** (2 signal sets × 2 timeframes × 4 depths × 2 sides) with the geometry fixed,
not swept. The target was the largest effect on the branch: `research/atme/` measured a resting
limit at **+0.24 to +0.43 R/trade across four markets** against a best-ever *signal* of **+0.043 R**.

Constraints as specified: intraday only, entries 09:30–15:00 New York, resting order cancelled at
15:00, position flat at 15:55, real MNQ costs (×1.44), the limit charged the **same** entry friction
as the market order (conservative — a resting order should pay less).

## 2. The defect

`_walk_limit` assigns its position lock only on exit:

```python
if done == 1:
    ...
    free = e
```

An order that is **resting and unfilled blocks nothing**, so trigger *i+1* places its own order
while *i*'s is still live, and *i+2* while both are. Counted directly (`order_audit.py`):

| cell | expiry | orders | max live | mean live | share > 1 live |
| --- | --- | --- | --- | --- | --- |
| everybar 5m L | 2 | 32,473 | 3 | **2.45** | **97.7%** |
| everybar 5m L | 18 | 32,473 | **19** | **15.88** | 97.7% |
| donch 15m L | 2 | 1,826 | 3 | 1.49 | 49.7% |
| donch 15m L | 18 | 1,826 | 16 | 3.97 | 72.3% |

Same class as `eem.run`'s eight simultaneous orders in `STUDY_V15_BOOK`, which kept 24–47% of its R
once corrected — and invisible there too in P&L per trade, showing only in the trade count.

**It is visible in the result before it is visible in the code.** Holding depth fixed and
lengthening the resting window, the **fill rate stops rising at expiry 6 (0.139) and stands still
through 18**, while $/signal climbs monotonically:

`−0.505 → +0.228 → +0.895 → +1.400 → +1.759 → +2.115`

Extra profit with no extra fills is not a mechanic. It is the engine choosing among orders it should
not have had. **A rising edge on an axis where the fill rate is flat is the signature.**

## 3. The correction, and what it costs

One line: an unfilled order holds the lock until it expires.

```python
if f < 0:
    free = i + expiry      # <- the whole correction
    continue
```

| cell | expiry | old $/signal | **corrected $/signal** | trades kept |
| --- | --- | --- | --- | --- |
| everybar 5m L | 2 / 6 / 12 | −0.022 / +0.481 / +0.748 | **−0.127 / −0.130 / −0.192** | 0.97 → 0.93 |
| donch 5m L | 2 / 6 / 12 | +0.854 / +2.285 / +2.942 | **+0.335 / +0.235 / +0.019** | 0.89 → 0.81 |
| donch 15m L | 2 / 6 / 12 | +0.181 / +3.305 / +4.919 | **−0.429 / +0.244 / −0.571** | 0.88 → 0.75 |

**The monotone rise with resting time disappears completely.** Under the correct policy, letting an
order rest longer is neutral to harmful. The trade count falls 3–25%, and it falls fastest exactly
where concurrency was highest — the tell `STUDY_V15_BOOK` identified.

`limit_entry.py` is left untouched so earlier results stay reproducible. `research/v34/v34one.py` is
the corrected engine and everything below is scored on it.

## 4. The five hypotheses, scored on the corrected engine

| | research | locked |
| --- | --- | --- |
| **H1** limit beats market, per signal | **17 / 32 (53%)**, mean +0.070 $/sig | 18 / 32 (56%), mean **−0.515** |
| **H2** monotone in depth | 0.25 → 1.00: +0.190, −0.099, −0.133, +0.320 — **no** | −0.720, −0.834, −0.755, +0.249 — **no** |
| **H3** present on both sides | long **+0.351**, short **−0.212** | long −0.504, short −0.526 |
| **H5a** sign holds research → locked | sign kept **59%** over 32 paired cells | Spearman **+0.139** |
| **H4** beats a matched control | **not reached** | nothing survived H1 to gate |

**H1 fails**: 53% is chance. **H2 fails**: the depth response is erratic, not monotone, and on
research it is *negative* at the two middle rungs. **H3 fails**: research long earns +0.351 against
short's −0.212, a sign split, which is drift and not a mechanic — and on locked both sides are
negative. **H5 fails**: sign kept 59% on 32 paired cells.

Measured **per signal**, which is the honest denominator: fill rates run 4.0–30.3%, so an unfilled
limit earns nothing while having consumed the opportunity, and per-trade accounting hides that. The
per-trade column is printed beside it throughout and tells a flattering, wrong story — `donch 15m
long` at depth 1.00 reads **+$41.56 per trade** on 119 trades from 974 signals, which is
**+$5.08 per signal**.

## 5. What the intraday constraint cost

Run as specified, with an unconstrained twin beside it purely to measure the difference:

| block | intraday (as specified) | unconstrained |
| --- | --- | --- |
| research | −0.628 $/signal, PF 0.925 | −0.343 $/signal, PF 0.935 |
| locked | +0.720 $/signal, PF 1.045 | +0.132 $/signal, PF 0.984 |

The two blocks disagree in direction, so on this evidence the constraint is not the binding problem
here — the mechanic is. That is a *narrower* claim than the branch's seven prior measurements of the
intraday penalty, and it is narrower because this test is one market with a fixed geometry.

## 6. What this changes

**It corrects a module this branch has published from.** `STUDY_V10_LIMIT` and `STUDY_LIMIT_ENTRY`
both used `limit_entry`, and any figure in them that let an order rest for more than a bar is
inflated by the same artifact. The direction is known — correcting it always reduces the result —
and the size scales with the resting window. `research/atme/` used its own engine and is not
directly affected, but its headline (+0.24 to +0.43 R/trade, monotone in depth) is exactly the shape
this artifact produces, and it should be re-measured under a one-order policy before being relied on.

**And it is the sixth mechanical defect this branch has caught by measurement rather than reading**
— after `ent_bar` leakage, the HP filter's two-sided fit, the partial-exit ladder re-opening, the
overnight mask's missing end, the divergence fill-forward, and `eem.run`'s eight orders. The
detector each time was a number moving on an axis where nothing should have moved it.

**Ship nothing.** The mechanic, run once as declared under a policy a script can execute, is a coin
flip on this market under this constraint.

Reproduce: `python3 research/v34/run_v34.py`, `order_audit.py`, `expiry_cal.py`. Raw output:
`docs/ib/v34_mechanic_output.txt` (corrected), `docs/ib/v34_uncorrected_output.txt` (the artifact).
