# Initial Balance retracement on US30 — Optuna and a meta layer, two gates

**Verdict — there is no profitable IB version for US30 on this data, and the study says why in
three steps.** Gate 1 fails as published (−0.0167 %/trade, bootstrap p 1.000, **gross negative at
zero cost**), and the mechanism's own prediction — an edge rising with retracement depth, which
`STUDY_V58_ANATOMY` measured monotone on NQ — is flat on US30 at every rung. 3,600 Optuna trials
find a long-only opening-drive exposure whose total-return optimum **discards the retracement**
(0.007) and is beaten by always-long on the same days (+0.0675 vs +0.0450). The one finalist that
clears a random entry on both LONG blocks (the PF optimum, +0.0662 PF 1.57 on 91 locked trades)
then reads **−0.0925 on the 288 sessions of a second provider that postdate everything** — where
every finalist, and always-long itself, is negative. The 30-feature meta layer passes 4 of 15
research cells, is not calibrated across the split, and its research-best cell inverts on locked.
Deflated Sharpe **0.000** at 3,698 counted looks.

Ships `pine/ibus30/IB_US30_strategy.pine` — the rules as published with the IB filter in ATR
units and a no-target option, every number above in the header, no edge claimed.

`research/ibopt/`. Feeds: `US30_LONG_15m` (2016-10 → 2025-07, research = first 65% of sessions to
2022-06-27, locked = the rest) and `US30_ISO_15m` (a different provider, 2024-08 → 2026-08; only
the 288 sessions after the LONG file ends are used, as a block nothing chose on). 1.72 points round
turn, one unit, **percent of entry price** — never R (`STUDY_V58`: risk = (stop − retr) × range
can be driven to nothing).

---

## 1. Phase 0 — the mechanism, and what it predicts

The IB retracement is a **resting limit inside a range after the range breaks**. The counterparty
is the breakout chaser, shaken out on the first pullback. `STUDY_V58_ANATOMY` found exactly this on
NQ: the edge is monotone in retracement depth, zero at zero retracement, and the Initial Balance is
only the ruler. So the primary makes a prediction that can fail: **on US30 the retracement ladder
must rise**. It does not (§3).

## 2. The engine, verified before use

A per-day walker with continuous parameters (Optuna needs a space the V58 tensor cannot reach),
checked against `v58ib`'s tensor on the published geometry: **945/945 long and 989/989 short
trade counts identical; 838 / 847 days identical to the cent**, the residual being bars that open
*through* the limit, which this walker fills at the open (as a limit does) and V58 filled at the
level.

Two things found by the diff, both mine:

- **The flatten.** On this CFD feed the first bar at or after 15:55 is the **18:30 re-open on
  1,247 of 2,246 sessions** (18:00 on 391, no bar at all on 428; a 16:00 bar exists on 153). A
  flatten filled at "the open of the first bar after the cutoff" holds through the closed cash
  session, and it showed as a systematic **+0.087 R on both sides** — overnight drift wearing a
  flatten. The walker now exits at the close of the last bar before the cutoff, and the Pine
  submits its flatten on the bar before so the fill is the cutoff bar's open — on a 1–5 minute
  chart that is 15:55; on a 15-minute chart of this feed it is still 18:30, which the parity
  harness measures (§8).
- **A gap through the stop.** If the fill bar opens beyond the stop, the limit fills at that open
  and the stop is already breached, so the exit is the open too, not the level.

## 3. Gate 1 — as published, and the ladder

| arm | n | %/trade | PF | win | control median | p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **as published, both sides** | 1,023 | **−0.0167** | 0.856 | 34.3% | −0.0230 | 0.205 |
| long only | 617 | −0.0209 | 0.816 | 35.3% | −0.0241 | 0.371 |
| short only | 646 | −0.0096 | 0.916 | 33.7% | +0.0011 | 0.865 |
| zero cost | 1,023 | **−0.0102** | 0.909 | 34.6% | −0.0165 | 0.205 |
| side flip, same days | 1,023 | +0.0060 | 1.055 | 36.1% | | |

`primary_gate`: net −0.0167 %/event, CI95 [−0.0356, +0.0025], bootstrap p **1.000 → FAIL**. It
is negative gross, so no execution improvement reaches it; the mirror is faintly positive, the
thirteenth route to mean reversion on this branch.

The retracement ladder at the published stop and target:

| retr | n | %/trade | PF | median risk (pts) | control median | p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.00 | 1,283 | −0.0077 | 0.942 | 73.2 | +0.0068 | 0.983 |
| 0.10 | 1,171 | −0.0178 | 0.868 | 60.5 | −0.0059 | 0.939 |
| 0.25 | 1,023 | −0.0167 | 0.856 | 41.7 | −0.0230 | 0.205 |
| 0.40 | 847 | −0.0141 | 0.834 | 23.4 | −0.0298 | 0.015 |
| 0.50 | 744 | −0.0163 | 0.686 | 11.6 | −0.0237 | 0.108 |
| 0.60 | 656 | −0.0117 | 0.771 | 11.6 | −0.0264 | 0.008 |

**Flat at every depth.** The control p falls with depth because the *control* gets worse
(+0.007 → −0.026), not because the rule gets better — a rule that beats a losing null is still a
losing rule. On NQ the same ladder went p 1.000 → 0.000 with the rule rising to +0.31 ATR. The
mechanism is market-specific, and this is the market where it is absent.

## 4. Optuna — 3,600 trials, research only

Three multivariate-TPE studies of 1,200 (total % of price; PF; return/DD) at a floor of 150
research trades, over IB length {30, 45, 60, 90}, retracement [0, 0.6], stop (retr, 1.6], target
[0.25, 3] or none, flatten {13:00, 15:00, 15:55}, side, and the IB range as a multiple of ATR
(floor [0, 1.5], ceiling {off, 2, 3, 4}). Every trial's locked result was logged and never used.

**Population:** 2,849 scorable, **62.6% profitable on research**, median +4.3%. corr(research,
locked) **+0.55** — high for this branch, and `STUDY_V64_OPTUNA` explains it: a TPE population is
concentrated in its own good region, so the correlation is measured over a restricted range. It
says the neighbourhood is decent, not that research ranking picks winners; the top 1% goes +31.9% →
+13.8% against the population's +3.3%.

**Marginals:** LONG +10.4% (77% positive) against SHORT −2.5% (34%); IB 30 min +11.4% (82%)
against 45/60 negative; flatten 15:55 best; **ib_atr_max off −2.2% against 3.0/4.0 at +3.2/+9.2%**;
the retracement bins ≤ 0.2 best (+10.0 / +7.4) and (0.5, 0.6] worst (−3.5). **fANOVA puts 0.935 /
0.943 / 0.937 of the three objectives on `ib_atr_max`** — the IB-range ceiling — with everything
else under 0.05.

**Finalists:**

| study | configuration | research |
| --- | --- | --- |
| total | IB 30, **retr 0.007**, stop 0.93, no target, long, flat 15:55, IB 1.48–4.0 ATR | n 789, +0.0450, PF 1.32; box edges `retr`, `ib_atr_min` |
| PF | IB 90, **retr 0.455**, stop 0.94, target **2.98**, both, IB 0.33–3.0 ATR | n 150 (the floor), +0.1117, PF 1.96; box edge `tgt` |
| ret/DD | IB 30, retr 0.07, **stop 0.24**, no target, long, IB 1.1–3.0 ATR | n 495, +0.0243, PF 1.54, **win 9.9%** |

The total optimum buys the break itself — it discarded the mechanism — and holds a 30-minute
opening drive to the close, long only, on large-range days. The ret/DD optimum is a 9.9%-win
lottery with a stop a quarter of the range wide. The PF optimum sits at the trade floor and its
target on the box edge.

## 5. Gate 1 on the finalists — with the arm the marginals demand

| primary | n | %/trade | PF | boot p | random-entry p | **always-side, same days** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| total | 789 | +0.0450 | 1.32 | 0.008 | 0.052 | **+0.0675 (PF 1.41)** |
| PF | 150 | +0.1117 | 1.96 | 0.141 | 0.000 | −0.0665 |
| ret/DD | 495 | +0.0243 | 1.54 | 0.038 | 0.005 | −0.0060 |
| published | 1,023 | −0.0167 | 0.86 | 1.000 | 0.205 | +0.0023 |

**Always-long entered at the IB close on the total optimum's own days earns more than the
optimum.** Its entry subtracts; what it found is a day filter (large 30-minute range, long) on a
rising sample. The PF and ret/DD finalists do beat both nulls on research; the ret/DD one was
carried into the meta layer because it also cleared the bootstrap.

## 6. The meta layer — 30 causal features, six families

Stamped at the plan bar (IB close) or the break bar, side-oriented; fracdiff on the daily close
with **d = 0.3** by ADF on research days; a 3-state Gaussian HMM fitted on research daily returns
and read **filtered** (filtered vs smoothed agreement 96.0% — the 4% is the leak). **Truncation
audit 0 mismatches in 1,200** on all four primaries, after two of my own features (IB range and
volume relative to prior days) had been built from the event table instead of the day series and
failed 80 of 1,200 — construction artefacts, not leaks, but the audit is what said so.

Research screen on ret/DD (495 events): 20 of 30 at p ≤ 0.05 against 1.5 expected, 19 sign-stable
across research halves and three volatility regimes, **no pair above |ρ| 0.85**; the strongest are
the break bar's body and close-through (IC −0.43, −0.49: a break that closes strongly *through* the
edge is worse for a rule that wants a pullback — the mechanism's own logic, restated as a feature).

Gate 2, purged 5-fold with a return objective, beside shuffled twins:

| model | OOF IC | twin | best keep | uplift | boot p | random-filter p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ridge | **−0.145** | −0.073 | 40% | +0.0366 | 0.032 | 0.018 |
| rf | +0.036 | −0.101 | 40% | +0.0317 | 0.049 | 0.032 |
| lgbm | −0.044 | −0.080 | — | +0.0033 | 0.42 | 0.40 |

**4 of 15 cells clear both nulls — and the best model ranks the events backwards** (ridge OOF IC
−0.145) while its top 40% is positive. That is the top-decile-versus-IC disagreement `STUDY_V28`
recorded, and it is what a score fitted to 495 events looks like. On the PF primary (150 events):
0 of 15. On the published primary, lgbm "clears" 4 of 15 by taking −0.0167 to +0.0023 — a filter
that makes a loser less bad, which the architecture forbids crediting.

## 7. The one locked read

Multiplicity first: 3,600 trials + 4 primaries + 94 meta looks = **3,698**.

| primary | block | n | %/trade | PF | ret/DD | boot p | random-entry p | always-side |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| total | research | 789 | +0.0450 | 1.32 | 5.34 | 0.008 | 0.052 | +0.0675 |
| total | **locked** | 387 | +0.0426 | 1.28 | 4.60 | 0.084 | **0.292** | **+0.1222** |
| PF | research | 150 | +0.1117 | 1.96 | 3.54 | 0.141 | 0.000 | −0.0665 |
| PF | **locked** | 91 | +0.0662 | 1.57 | 1.82 | 0.227 | **0.002** | −0.0457 |
| ret/DD | research | 495 | +0.0243 | 1.54 | 6.82 | 0.038 | 0.005 | −0.0060 |
| ret/DD | **locked** | 220 | +0.0124 | 1.30 | **0.77** | 0.244 | **0.510** | −0.0001 |
| published | locked | 538 | −0.0145 | 0.87 | −0.70 | 1.000 | 0.240 | −0.0002 |

All three decay (the right shape). The total optimum fails its random entry and always-long
nearly triples it; the ret/DD optimum's return-over-drawdown collapses 6.8 → 0.8 and it is a coin
flip against its control. **The PF optimum is the only one clearing anything** — random entry
p 0.002, beating always-side, decaying — on 91 trades with a bootstrap p of 0.227.

**Meta layer on ret/DD, ridge frozen on research:**

| research keep | kept on locked | n | base | filtered | uplift | random-filter p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 80% | **58%** | 127 | +0.0124 | +0.0214 | +0.0090 | 0.390 |
| 60% | 28% | 62 | +0.0124 | +0.0603 | +0.0479 | 0.119 |
| 50% | 22% | 48 | +0.0124 | +0.0807 | +0.0683 | 0.087 |
| **40%** | **15%** | 32 | +0.0124 | −0.0155 | **−0.0279** | 0.679 |

Not calibrated across the split — a research 40% threshold keeps 15% — and the cell that was best
on research is the one that inverts. Nothing here can be shipped as a default.

**Deflated Sharpe 0.000** at N = 3,698 (and at 1,850 effective).

**Then the second provider.** `US30_ISO_15m` carries 288 sessions after the LONG file ends —
2025-07 to 2026-08 — that no search, no gate and no read touched:

| primary | n | %/trade | PF | win | random-entry p | always-side |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| total | 111 | **−0.0570** | 0.66 | 36.9% | 0.996 | −0.0156 |
| PF | 18 | **−0.0925** | 0.29 | 33.3% | 0.787 | −0.1477 |
| ret/DD | 45 | **−0.0412** | 0.06 | 2.2% | 0.960 | −0.0128 |
| published | 179 | −0.0320 | 0.73 | 31.3% | 0.642 | −0.0261 |

Every finalist negative, the total optimum losing to a random entry at p 0.996, and always-long
negative too: a long-biased opening drive in a stretch where the Dow did not drift up. That is the
regime the LONG research block never contained, and it is the one block that could not have been
selected on.

## 8. Parity

`ib_parity.py` runs the shipped script's order model — tick-rounded levels, the limit live from
the bar after the break, the bracket placed with the entry, and Pine's fill-bar path assumption
(green bar O-L-H-C), under which a long limit filled on the way down can be paid a target on the
same bar. Under the research flatten convention the three finalists match the engine **trade for
trade (715/715, 241/241, 1176/1176), per-trade correlation 1.0000, gap 0.0%**. The published
geometry reads 0.959 with a +3.0% research gap: the residual is exactly the fill-bar target the
broker emulator pays and the research does not (`STUDY_V10`'s artifact, script side). Under the
15-minute chart's actual flatten — the 18:30 open on most sessions — the gap runs to +42% on the
published cell, which is the number to remember if a Strategy Tester report on this feed ever
looks better than these tables.

## 9. What would move it

Not a parameter and not a feature. The mechanism is absent on US30 at every retracement depth, so
the honest search space is a different primary. Gold and NQ carried it (NQ once, on 48 trades); a
1-minute US30 file would at least let the limit's fill be measured rather than assumed.
