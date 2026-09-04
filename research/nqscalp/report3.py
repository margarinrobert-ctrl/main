"""Append the cross-instrument round and the component analysis to the study."""
import json, numpy as np, pandas as pd, os
D = "/home/user/main/docs/nqscalp/"
CT = pd.read_csv(D + "crosstest.csv"); DO = pd.read_csv(D + "dropone.csv")
FN = pd.read_csv(D + "finalists.csv")
CN = pd.read_csv(D + "corr_conditions_NAS.csv", index_col=0)
FE = {s: pd.read_csv(D + f"features_{s}.csv") for s in ("NAS", "US30")}
SR = {s: pd.read_csv(D + f"stochrsi_{s}.csv") for s in ("NAS", "US30")}
L = []; A = L.append

A("\n## 19. Cross-instrument test, component correlations, and what to delete\n")
A("""The NAS holdout has been read three times, so this round buys its out-of-sample evidence a
different way: **a second instrument**. US30 costs nothing from the NAS budget, and if an
EMA-pullback plus StochRSI entry carries real information about intraday index futures, it should
carry it on the Dow as well as the Nasdaq. Two 0.85-correlated indices trading the same session
with the same participants is about as favourable a replication test as exists.\n""")

A("### 19a. The signal does not replicate on US30 — it inverts\n")
A("| configuration | instrument | trades | gross (ATR units) | net | control | excess | p |")
A("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
for _, r in CT.iterrows():
    A(f"| {r.label} | {r.sym} | {int(r.n):,} | {r.gross_atr:+.3f} | {r.net:+.2f} | "
      f"{r.ctrl:+.2f} | {r.excess:+.2f} | {r.p:.4f} |")
rth_n = CT[(CT.sym == "NAS") & (CT.label.str.contains("RTH"))].iloc[0]
rth_u = CT[(CT.sym == "US30") & (CT.label.str.contains("RTH"))].iloc[0]
A(f"""
Gross edge is quoted in ATR units because that is the only scale on which two instruments are
comparable. **All three configurations disagree in sign**, and US30's excess over the matched
control is negative in every one, at p 0.79 to 0.95 — the strategy is consistently *worse* than
random entries there.

The reversal is sharpest on the one configuration that looked promising. The 09:31–11:00 window
is {rth_n.gross_atr:+.3f} ATR gross on NAS with excess {rth_n.excess:+.2f} at p {rth_n.p:.3f}; on US30 it is **{rth_u.gross_atr:+.3f} ATR** with excess
**{rth_u.excess:+.2f}** at p {rth_u.p:.3f}. The single best finding of the previous round does not weaken on a second
instrument, it points the other way.

That is the cleanest evidence in the whole study. A real intraday effect in the US cash open should
not be present on the Nasdaq and inverted on the Dow.\n""")

A("### 19b. Matrix correlations over the strategy's own conditions\n")
A("""Each entry rule as a boolean series over research bars, long side (US30's matrix is the same to
two decimals, which is itself worth knowing — the *structure* replicates even though the edge does
not):\n""")
A("| | " + " | ".join(c[:22] for c in CN.columns) + " |")
A("| --- | " + " | ".join("---:" for _ in CN.columns) + " |")
for i, n in enumerate(CN.index):
    A(f"| {n} | " + " | ".join(f"{CN.iloc[i,j]:.2f}" for j in range(len(CN.columns))) + " |")
A(f"""
Two things stand out.

**The pullback depth and the EMA touch are 0.53 correlated and fire on 71% and 75% of bars.** They
are close to the same rule, and neither is selective: a "filter" that passes three bars in four is
not filtering. The trend gate is *negatively* correlated with the touch (−0.32), which is just the
observation that price touches a fast MA more often when it is below the slow one.

**The %K/%D cross is the only independent, selective condition in the strategy.** It correlates
0.00–0.04 with everything else and fires on 12.2% of bars. Whatever selection this strategy does,
that line does it.\n""")

A("### 19c. Drop-one — what each condition is actually worth\n")
A("""Each condition removed from the **triggers** and the book re-simulated, which is the only valid
way to test a filter; splitting realised trades is not. A condition earns its place only if removing
it *hurts* on both instruments.\n""")
piv = DO.pivot(index="dropped", columns="sym", values="worth")
pn = DO.pivot(index="dropped", columns="sym", values="n")
A("| condition | worth on NAS | worth on US30 | trades without it (NAS) | verdict |")
A("| --- | ---: | ---: | ---: | :---: |")
for k in piv.index:
    nas, us = piv.loc[k, "NAS"], piv.loc[k, "US30"]
    v = "**KEEP**" if (nas > 0 and us > 0) else ("**DELETE**" if (nas <= 0 and us <= 0) else "mixed")
    A(f"| {k} | {nas:+.2f} | {us:+.2f} | {int(pn.loc[k,'NAS']):,} | {v} |")
A(f"""
**Nothing is worth keeping on both instruments.** Two conditions are actively harmful on both, and
they are the two that define the pullback: the **depth requirement** ({piv.loc['pullback depth >= 1.15 ATR','NAS']:+.2f} on NAS,
{piv.loc['pullback depth >= 1.15 ATR','US30']:+.2f} on US30) and the **MA touch** ({piv.loc['touch of fast/slow EMA','NAS']:+.2f}, {piv.loc['touch of fast/slow EMA','US30']:+.2f}). Removing either makes the
strategy better on both instruments, and they are 0.53 correlated with each other anyway.

So the answer to "what should be deleted" is uncomfortable but specific: **the moving-average
pullback mechanism is the part that does not earn its place.** That is the part the strategy is
named after. The conditions with positive worth on NAS — trend gate, StochRSI reset, the cross, the
session — all have negative worth on US30, which is the same non-replication as §19a seen through a
different instrument.\n""")

A("### 19d. The features your script has but never switched on\n")
A("""Four early exits, quick-scalp mode, and the volume and MACD filters were all `false` in the
supplied settings and had never been measured. Round turn is 0.62 points on NAS (full-size NQ) and
2.50 on US30 (YM).\n""")
A("| feature | NAS net | NAS ex-crisis | US30 net | US30 ex-crisis |")
A("| --- | ---: | ---: | ---: | ---: |")
for _, r in FE["NAS"].iterrows():
    u = FE["US30"][FE["US30"].feature == r.feature]
    if not len(u): continue
    u = u.iloc[0]
    A(f"| {r.feature} | {r.net:+.2f} | {r.ex_crisis:+.2f} | {u.net:+.2f} | {u.ex_crisis:+.2f} |")
A(f"""
**Every early exit makes it worse on NAS**, and quick-scalp mode is the worst thing in the table
(−1.48 to −2.30). Cutting a trade short at a fixed 8 points when the ATR-based target is 2.5 ATR is
the same mistake as the fixed-point trail: a distance that does not scale.

The volume and MACD filters are the only features that help, and only on NAS.\n""")

A("### 19e. The StochRSI trigger parameters\n")
A(f"""486 configurations per instrument — RSI length, stoch length, %K and %D smoothing,
oversold/overbought levels, reset lookback. This is the actual trigger and it had never been swept.\n""")
A("| | NAS | US30 |")
A("| --- | ---: | ---: |")
A(f"| cells with ≥60 trades | {len(SR['NAS'])} | {len(SR['US30'])} |")
A(f"| median net | {SR['NAS'].net.median():+.2f} | {SR['US30'].net.median():+.2f} |")
A(f"| best net | {SR['NAS'].net.max():+.2f} | {SR['US30'].net.max():+.2f} |")
A(f"| cells above the round turn | {(SR['NAS'].net > 0.62).sum()} / {len(SR['NAS'])} | {(SR['US30'].net > 2.50).sum()} / {len(SR['US30'])} |")
A(f"| …and still above it without 2020+2022 | **0** | **0** |")
A(f"""
No parameterisation of the trigger clears its own cost floor durably on either instrument. Every
marginal is negative on both. The default 14/14/3/3 with 20/80 is not a bad choice — there is no
good one.\n""")

A("### 19f. The finalists, through the whole gate\n")
A("""Three cells survived the cheap screen. The gate, declared before running: **G1** net above the
round turn; **G2** excess over the matched control at p&lt;0.05; **G3** still above the round turn with
2020 and 2022 removed; **G4** stable across 250-session blocks; **G5** the same on both instruments.\n""")
A("| candidate | instrument | trades | net | excess | p | ex-crisis | blocks positive | G1 | G2 | G3 | G4 |")
A("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | :-: | :-: | :-: | :-: |")
for _, r in FN.iterrows():
    A(f"| {r.cand} | {r.sym} | {int(r.n)} | {r.net:+.2f} | {r.excess:+.2f} | {r.p:.4f} | "
      f"{r.ex_crisis:+.2f} | {r.blocks_pos:.0%} | {'✓' if r.G1 else '✗'} | {'✓' if r.G2 else '✗'} | "
      f"{'✓' if r.G3 else '✗'} | {'✓' if r.G4 else '✗'} |")
vt_n = FN[(FN.sym == "NAS") & (FN.cand.str.contains("volume 1.5"))].iloc[0]
vt_u = FN[(FN.sym == "US30") & (FN.cand.str.contains("volume 1.5"))].iloc[0]
A(f"""
**Zero candidates pass on both instruments.**

The volume-thrust filter is the best single thing found anywhere in this study: on NAS it is
**4 of 4**, at {vt_n.net:+.2f} points per trade against a 0.62 round turn, excess {vt_n.excess:+.2f} over the matched control
at p {vt_n.p:.4f}, still {vt_n.ex_crisis:+.2f} with the crisis years removed, and positive in {vt_n.blocks_pos:.0%} of 250-session blocks.
On US30 it is **0 of 4**, at {vt_u.net:+.2f} points per trade with excess {vt_u.excess:+.2f} at p {vt_u.p:.3f}.

A filter that is the strongest result on one index and the weakest on its near-twin is a property
of the sample, not of the market. The NAS holdout was not opened for it.\n""")

A("### 19g. What to delete\n")
A("""On the evidence above, in order of confidence:

1. **Quick-scalp mode.** Worst feature measured, on both instruments. It re-introduces the
   fixed-point scale bug that §18a is about.
2. **All four early exits.** Every one is negative on NAS; the least-bad is the trend break.
3. **The pullback depth and MA-touch conditions.** Negative worth on both instruments, 0.53
   correlated with each other, and each passes ~3 bars in 4. This is the strategy's namesake
   mechanism and it is the part that does not work.
4. **The MA period and type inputs** — not deleted, but stop tuning them. 165 structures, all
   within 0.2 points of each other (§18c).
5. **The fixed-point distance inputs** — already replaced by ATR-relative ones in §18a.

What survives as *worth keeping in the code*: the ATR-relative distances, the session flatten, the
New York clock, and the volume-thrust filter as an option with its NAS-only caveat attached. That
is a cleaner script. It is not a profitable one.\n""")

txt = open(D + "STUDY_NQSCALP.md").read()
mark = "## Files\n"
i = txt.index(mark)
txt = txt[:i] + "\n".join(L) + "\n\n" + txt[i:]
txt = txt.replace("""> **VERDICT""", """> **VERDICT""", 1)
open(D + "STUDY_NQSCALP.md", "w").write(txt)
print(f"appended section 19; doc now {len(txt):,} chars")
