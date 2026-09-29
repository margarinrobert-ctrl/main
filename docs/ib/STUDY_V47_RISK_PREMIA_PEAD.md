# V47 — Risk-premium and PEAD-analogue features on NQ

**The classical trend premium has the wrong sign here — monotone reversal, replicated on the
holdout. The PEAD mechanism does not transfer at all: its family's signs agree with the holdout at
exactly chance. Nothing survives multiplicity correction.**

30 causal daily features, NQ, 763 sessions (495 research / 268 locked), truncation-audit clean.
`research/v47/`.

---

## 0. What these names can and cannot mean on this data

**PEAD is not measurable here, and nothing below claims to measure it.** Post-earnings announcement
drift is defined on single names — SUE from actual-versus-consensus EPS, drift over ~60 days. It
needs earnings dates, analyst consensus and per-stock returns. This branch has index-futures OHLCV.
What is tested is an **index-level analogue of the mechanism**: underreaction to a large information
event, followed by drift in its direction, with the event identified endogenously from a
standardised move. On an index those are macro releases and aggregate earnings season.

**Most classical risk premia are equally out of reach.** Value, size, credit and term need a
cross-section or a bond curve. **The variance risk premium needs implied vol**, which no feed here
carries — so `rv_term` is a *realised* variance term structure, a proxy, and calling it the VRP
would be wrong. What a single futures tape genuinely carries is the session decomposition, realised
higher moments, the semivariance asymmetry, and time-series momentum.

**Power, stated before the results.** 763 sessions. At h=20 the locked block holds roughly 13
independent windows. Enough to reject a large effect, nowhere near enough to establish a small one.

---

## 1. The night premium does not replicate

Where the index return actually accrued, log, annualised:

| | total | mean/day | annualised | vol | Sharpe |
| --- | --- | --- | --- | --- | --- |
| **Overnight** (16:00→09:30) | +0.2919 | +3.83 bp | +9.64% | 11.44% | **0.84** |
| **Intraday** (09:30→16:00) | +0.3571 | +4.68 bp | +11.79% | 15.39% | 0.77 |
| close-to-close | +0.6490 | +8.51 bp | +21.44% | 18.22% | 1.18 |

The published night effect — the equity premium accruing almost entirely overnight — **is not what
this sample shows**: intraday contributed *more* in total. Overnight wins only risk-adjusted, and by
0.07 Sharpe on 763 days, which is nothing.

---

## 2. Drift or reversal after a surprise

Mean of sign(SUE) × forward return. **Positive = drift (what PEAD describes). Negative = reversal.**

| surprise | \|SUE\|≥ | h | research bp | NW t | locked bp | NW t | sign agrees |
| --- | --- | --- | --- | --- | --- | --- | --- |
| close-to-close | 1.0 | 20 | −35.0 | −1.05 | **−65.2** | −1.82 | yes |
| close-to-close | 1.5 | 20 | −5.9 | −0.11 | −54.9 | −1.08 | yes |
| **overnight** | 1.5 | 1 | **+20.7** | +1.91 | **+53.6** | +1.32 | yes |
| **overnight** | 1.5 | 20 | **−66.3** | **−3.33** | −45.5 | −1.09 | yes |

The shape is **short-horizon continuation, long-horizon reversal** — classical overreaction, and the
*opposite* of PEAD at the horizon PEAD is defined on. **Not one cell reaches \|t\| ≥ 2 on both
blocks.** The single strongest research cell (overnight, \|SUE\|≥1.5, h=20, t −3.33) decays to
−1.09 on locked.

---

## 3. The IC battery — nothing survives correction

30 features × 4 horizons × 2 blocks, Spearman IC, **Newey–West t at lag h** because overlapping
forward returns on daily bars are nothing like 763 independent observations.

**The correction is the story.** It deflates the naive t by **1.9× to 3.2×**:

| feature | h | IC | naive t | NW t | inflation |
| --- | --- | --- | --- | --- | --- |
| rp.tsmom120 | 20 | −0.3054 | −6.83 | **−2.26** | 3.0× |
| rp.tsmom60 | 20 | −0.2760 | −6.25 | −2.01 | 3.1× |
| rp.tsmom120 | 10 | −0.2462 | −5.41 | −2.21 | 2.4× |

An IC of 0.31 that looks like t = −6.8 is t = −2.3 once the overlap is priced. **BH at FDR 0.10 over
120 tests needs \|t\| ≥ 3.35; the best achieved is 2.50. Zero pass.** 10 of 120 reach \|t\| ≥ 2
against 5.5 expected — about double chance, not a discovery.

---

## 4. What does replicate: the sign, and only for one family

| subset | keep sign on locked | binomial p |
| --- | --- | --- |
| all 120 tests | 78 / 120 | 0.0013 |
| research \|NW t\| ≥ 1.5 | **25 / 30** | 0.0003 |
| research \|NW t\| ≥ 2 | **10 / 10** | 0.0020 |
| **risk-premium family** | **56 / 80** | **0.0005** |
| **PEAD-analogue family** | **22 / 40** | **0.636** |

**The risk-premium family's signs replicate; the PEAD family's are indistinguishable from coin
flips.** That single contrast is the cleanest result in the study.

*The binomial p overstates its case* — the 120 tests are not independent (features correlate,
horizons overlap), so read the ordering of those rows, not their absolute p-values.

### The trend premium has the wrong sign, monotonically

| lookback | h=1 | h=5 | h=10 | h=20 |
| --- | --- | --- | --- | --- |
| tsmom60 research | −0.092 | −0.171 | −0.238 | −0.276 |
| tsmom120 research | −0.112 | −0.192 | −0.246 | **−0.305** |
| tsmom120 **locked** | −0.070 | −0.121 | −0.212 | **−0.271** |

**11 of 12 momentum cells are negative on both blocks**, and tsmom120 is monotone in horizon on
*both*. The classical time-series momentum premium — the one risk premium this data can actually
carry — is **reversal on NQ**, with a clean decaying gradient that reproduces out of sample.

This is the **eighth independent route to mean reversion** on this branch, after the Turtle feature
study, the trend-pullback family, ATME's mirror-image entry response, the five resolved
trend-following briefs, the MA-regime ICs, the divergence work and the Carver control.

### Turn of month: nothing

The one declared calendar hypothesis, admitted as a single pre-registered test and never as a
search axis: research IC −0.035 / −0.016 / +0.095 / +0.006 across the four horizons, every
\|NW t\| < 1.5, signs flipping between blocks. It fails.

---

## 5. Verdict

**Ships nothing, and two of the three headline names were never testable here.** What the study
establishes:

- **The trend premium is inverted on NQ** and the gradient replicates — the one durable finding.
- **The PEAD mechanism does not transfer to index level**: chance-level sign agreement, and what
  structure exists is overreaction (short continuation, long reversal), not underreaction.
- **The night premium does not replicate** on this sample.
- **Overlap correction is not optional**: it is worth a factor of 2–3 in t, and every "significant"
  daily-horizon IC here is manufactured by ignoring it.

## Caveats

One market, 763 sessions, ~13 independent 20-day windows on locked. No matched control was run —
these are ICs and conditional means, not strategies, and a control belongs with a trading rule. The
US100 (9 years) and US30 (8.5 years) feeds were wiped by a container recycle before this study, so
the cross-market replication that V46 could do was not available here; that is the single most
valuable thing to add.

## Files

`research/v47/v47daily.py` (causal daily frame, exact session split) · `v47feat.py` (30 features +
truncation audit) · `run_v47.py` (drift test, IC battery, NW, BH) · `results/v47/`.
