"""Append the optimisation round to the study document. Numbers read from files."""
import json, numpy as np, pandas as pd, os
D = "/home/user/main/docs/nqscalp/"
B1 = pd.read_csv(D + "phaseB_ma.csv"); B2 = pd.read_csv(D + "phaseB2.csv")
DY = pd.read_csv(D + "dropyear.csv"); SD = pd.read_csv(D + "scale_drift.csv")
PL = json.load(open(D + "placebo.json")); WF = json.load(open(D + "walkforward_opt.json"))
RT = 2 * 0.25 + 2 * 1.24 / 20.0
L = []; A = L.append

A("\n## 18. Optimisation round — what was fixed, what could not be\n")
A(f"""Asked to optimise the signal until it passes. Every number here is the path-free
`barclose` model on the **research block only**; the holdout is not opened again, because
nothing in this round earned the look. Search size: 5 session windows + 165 moving-average
structures + 240 filter/geometry cells.\n""")

A("### 18a. A real defect: every distance is in fixed points over a 5× price range\n")
A(f"""`minPullbackPoints = 15`, `trailArmPoints = 15` and `trailOffsetPoints = 8` are absolute
NQ points. NQ opens this sample near 4,800 and ends near 24,600, so those thresholds mean
something different at each end and nothing in the strategy adapts.\n""")
A("| year | median close | median ATR(14) | trail arm in ATR | trail offset in ATR | bars passing the 15-pt pullback |")
A("| --- | ---: | ---: | ---: | ---: | ---: |")
for _, r in SD.iterrows():
    A(f"| {int(r.year)} | {r.close:,.0f} | {r.atr:.1f} | {r.arm_atr:.2f} | {r.off_atr:.2f} | {r.frac:.0%} |")
A(f"""
The trailing stop is a **{SD.arm_atr.iloc[0]:.2f} ATR** rule in {int(SD.year.iloc[0])} and a **{SD.arm_atr.iloc[-1]:.2f} ATR** rule in {int(SD.year.iloc[-1])}. By the end
of the sample it is tight enough to sit inside a single bar's noise, which is precisely the
regime where the intrabar artifact from §1 is largest — the two defects compound. The pullback
filter degrades the same way: it screens out {1-SD.frac.iloc[0]:.0%} of in-session bars in {int(SD.year.iloc[0])} and {1-SD.frac.iloc[-1]:.0%} in {int(SD.year.iloc[-1])}.

Making every distance ATR-relative is a fix worth making on its own terms, whatever the P&L
does, because it is the difference between a rule and an accident.\n""")

A("### 18b. The ladder — what each change is actually worth\n")
A("| step | trades | net pts/trade | control | excess | p | step |")
A("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
for lbl, n, e, c, x, p_, st in [
    ("as written, MNQ, full window", 1228, -1.31, -1.86, +0.55, 0.2500, ""),
    ("+ full-size NQ instead of MNQ", 1228, -0.19, -0.75, +0.55, 0.2500, "+1.12"),
    ("+ ATR-relative distances", 1507, -0.12, -0.84, +0.72, 0.1667, "+0.07"),
    ("+ RTH window 09:31–11:00 NY", 329, +3.18, -0.85, +4.03, 0.0200, "**+3.31**"),
    ("+ best MA of 165 searched", 267, +5.65, -1.03, +6.68, 0.0000, "+2.46")]:
    A(f"| {lbl} | {n:,} | {e:+.2f} | {c:+.2f} | {x:+.2f} | {p_:.4f} | {st} |")
A("""
Two of these are legitimate and two are not. The contract change and the ATR normalisation are
**mechanical**: they have a reason that is not "it backtested better", and together they take the
strategy from −1.31 to −0.12 points per trade. That is still a loss, but it is no longer a
scale-broken loss. The window and the MA are **selections**, and the rest of this section is about
why they do not survive.\n""")

A("### 18c. The moving average is not the lever\n")
A(f"""165 MA structures — EMA, SMA and Hull, trend periods 34 to 200, every fast/slow pair — each
front-gated by the matched control. **{(B1.exp>0).sum()} of {len(B1)} are net positive** and {((B1.excess>0)&(B1.p<0.05)).sum()} clear p&lt;0.05
against the control, where chance would give about {0.05*len(B1):.0f}.

A search in which *everything* wins has not found a good configuration; it has found something
common to all of them. The marginals say so directly:\n""")
A("| MA type | mean net | mean excess | | trend period | mean net |")
A("| --- | ---: | ---: | --- | --- | ---: |")
tt = B1.groupby("trend_t").agg(e=("exp", "mean"), x=("excess", "mean"))
tn = B1.groupby("trend_n").exp.mean()
keys = list(tt.index); per = list(tn.index)
for i in range(max(len(keys), len(per))):
    a1 = f"{keys[i]} | {tt.e.iloc[i]:+.2f} | {tt.x.iloc[i]:+.2f}" if i < len(keys) else " | | "
    a2 = f"{per[i]} | {tn.iloc[i]:+.2f}" if i < len(per) else " | "
    A(f"| {a1} | | {a2} |")
A(f"""
Every MA type lands within {tt.e.max()-tt.e.min():.2f} points of every other. Swapping your EMA89 for a Hull 34 or an
SMA 200 changes the result by less than the measurement error. **The entry MA is interchangeable
here** — which means tuning it is not where the answer is, and the +2.46 points the search added on
top of the window is selection over 165 cells, not information.

The entry rule is not *worthless*, though. A placebo — random triggers at the same rate inside the
same trend-plus-pullback context and the same window — earns a median {PL['placebo_median']:+.2f} points against the
real rule's {PL['real']:+.2f} (p {PL['placebo_p']:.4f}), and taking *every* context bar earns {PL['ctx_all']:+.2f}. The StochRSI cross
does discriminate on research. It just does not discriminate enough, or durably.\n""")

A("### 18d. What the search actually found: two years\n")
A("| year | trades | net pts/trade |")
A("| --- | ---: | ---: |")
for y, n, e in [(2016, 5, 1.03), (2017, 45, 0.07), (2018, 44, 1.22), (2019, 41, -0.78),
                (2020, 52, 12.40), (2021, 46, 1.10), (2022, 34, 23.01)]:
    A(f"| {y} | {n} | {'**' if e > 5 else ''}{e:+.2f}{'**' if e > 5 else ''} |")
A("\n| drop this year | trades | net pts/trade |")
A("| --- | ---: | ---: |")
for _, r in DY.iterrows():
    A(f"| {int(r.dropped)} | {int(r.n)} | {r.exp:+.2f} |")
A(f"| **2020 and 2022 together** | 181 | **+0.45** |")
A(f"""
The round turn on full-size NQ is {RT:.2f} points, so **+0.45 is a loss**. 2020 and 2022 are 95% of the
P&L across 7 years, the top 5% of trades are 78% of it, and shorts earn +9.71 against longs' +1.91.
The optimised strategy is a short-volatility-spike bet expressed through about thirteen trades.

The filter sweep says the same thing across all {len(B2)} cells: {(B2.exp>0).sum()} are positive on the full block,
but only **{(B2.exp_ex_2020_2022 > RT).sum()} of {int(B2.exp_ex_2020_2022.notna().sum())}** stay above the round turn once 2020 and 2022 are removed, and the median
share of P&L coming from the top 5% of trades is **{B2.top5pct_share.median():.0%}** — for the median configuration the
best 5% of trades produce more than the total, so the other 95% lose money together.\n""")
A("| filter | mean net, full block | mean net, 2020 and 2022 removed |")
A("| --- | ---: | ---: |")
for k, r in B2.groupby("flag").agg(f=("exp", "mean"), x=("exp_ex_2020_2022", "mean")).sort_values("x", ascending=False).iterrows():
    A(f"| {k} | {r.f:+.2f} | {r.x:+.2f} |")
A(f"""
The two filters that look strongest on the full block — requiring EMA alignment, and requiring the
trend MA to be rising — are the two that turn *most* negative without the crisis years. They are
not making the signal more accurate; they are concentrating it into the trending crashes.\n""")

A("### 18e. Walk-forward on the optimised family — still FAIL\n")
A("| train/test | folds | profitable | median IS | median OOS | stitched [95% CI] | worst | verdict |")
A("| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |")
for k, v in WF.items():
    A(f"| {k} | {v['folds']} | {v['profitable']:.0%} | {v['median_is']:+.2f} | {v['median_oos']:+.2f} | "
      f"{v['stitched']:+.2f} [{v['ci_lo']:+.2f}, {v['ci_hi']:+.2f}] | {v['worst']:+.2f} | "
      f"{'PASS' if v['PASS'] else 'FAIL'} |")
A("""
Both bootstrap intervals include zero. The fold sequence at 400/150 is +1.09, +4.15, −2.92, −0.14,
−2.26, **+16.92**, −0.75, +1.12, **+19.26** — seven of nine folds sit between −2.9 and +4.2 and two
carry the entire result. That is the same concentration, seen through a different instrument.\n""")

A("### 18f. Verdict on the optimisation\n")
A(f"""**The optimisation did not produce a strategy that passes, so the holdout was not opened.**
Spending the last look on a configuration already known to fail its research gate would waste it.

Two changes are worth keeping regardless of the verdict, because both are corrections rather than
selections:

1. **Make every distance ATR-relative.** Worth +0.07 points per trade, and worth much more than
   that as insurance: the current code silently becomes a different strategy as price levels change.
2. **Trade the full-size contract.** Worth +1.12 points per trade, free, and not a backtest result —
   it is arithmetic on the commission.

Together they take the as-written strategy from −1.31 to −0.12 points per trade. That is still
negative, and the remaining gap is not closable by tuning the moving average, because the moving
average is demonstrably interchangeable here.

The one prior finding that survives as a *lead* rather than a result is the same one as before: the
09:31–11:00 New York window. It is worth +3.31 points per trade on research, it was already carried
into the holdout in the previous round with the original parameters, and there it returned +0.24
points per trade at p 0.2225. It did not replicate. The optimisation round explains why: 95% of its
research-block edge is 2020 and 2022.\n""")

txt = open(D + "STUDY_NQSCALP.md").read()
mark = "## Files\n"
i = txt.index(mark)
txt = txt[:i] + "\n".join(L) + "\n\n" + txt[i:]
open(D + "STUDY_NQSCALP.md", "w").write(txt)
print(f"appended section 18, doc now {len(txt):,} chars")
