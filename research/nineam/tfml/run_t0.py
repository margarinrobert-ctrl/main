"""T0  POWER FIRST, BEFORE ANY FEATURE.

Counts the labelled events per timeframe -- the primary's own LOCKED trades, the gated signals and
the ungated breaks each walked ALONE (the unlocked labeller) -- then the MDE a meta-layer uplift
would need at those counts, then the overlap across timeframes (Jaccard on sessions, on (day, side)
break events, on break TIMES) and an effective pooled n. Writes events_all.pkl for T1..T5.
"""
from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tfcore as C  # noqa: E402  (sets the thread caps before numpy)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

pd.set_option("display.width", 220)
N = C.N


def hd(t):
    print("\n" + "=" * 100); print(t); print("=" * 100, flush=True)


t0 = time.time()
evs = []
rows = []
for tf in C.TFS:
    c = C.ctx(tf)
    tr = c.trades(C.P)
    ev = C.events(tf)
    evs.append(ev)
    r = tr["pct"].to_numpy()
    g = ev[ev.gated == 1]
    rows.append(dict(tf=tf, locked=len(tr), locked_sess=len(np.unique(tr["eday"])),
                     locked_pct=r.mean(), locked_pf=C.pf(r), locked_mde=N.mde(r.std(ddof=1), len(r)),
                     gated=len(g), gated_unl_pct=g["pct"].mean(), gated_unl_pf=C.pf(g["pct"]),
                     ungated=len(ev), ung_sess=ev["day"].nunique(),
                     ung_pct=ev["pct"].mean(), ung_pf=C.pf(ev["pct"]), ung_sd=ev["pct"].std(ddof=1),
                     ung_win=ev["win"].mean(), ung_hit=ev["hit"].mean()))
    print(f"  tf {tf:>4}  locked {len(tr):>3}  gated {len(g):>3}  ungated {len(ev):>3}  "
          f"({time.time()-t0:.0f}s)", flush=True)
E = pd.concat(evs, ignore_index=True)
E.to_pickle(os.path.join(HERE, "events_all.pkl"))
cnt = pd.DataFrame(rows)

hd("0a  EVENT COUNTS PER TIMEFRAME")
print(cnt.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

days = np.array(sorted(E.loc[E.tf == 0.5, "day"].unique()))
is_d = days[: len(days) // 2]; oos_d = days[len(days) // 2:]
print(f"\n  tradeable sessions {len(days)}  ({C.DK.from_day(days.min()).date()}.."
      f"{C.DK.from_day(days.max()).date()});  research half {len(is_d)} sessions to "
      f"{C.DK.from_day(is_d.max()).date()}, holdout {len(oos_d)}")
np.save(os.path.join(HERE, "split_days.npy"), np.r_[len(is_d), days])

hd("0b  THE MDE OF A META-LAYER UPLIFT AT THESE COUNTS  (80% power, 5% two-sided, t 2.802)")
print("  A veto keeping fraction k of n events moves the mean by a RANDOM-SUBSET sd of")
print("  sd*sqrt((1-k)/(k n)) under the null, so the smallest resolvable uplift is 2.802 x that.")
mrows = []
for _, q in cnt.iterrows():
    for lab, n, sd in [("gated(primary)", q["gated"], E.loc[(E.tf == q.tf) & (E.gated == 1), "pct"].std(ddof=1)),
                       ("ungated", q["ungated"], q["ung_sd"])]:
        for k in (0.7, 0.5):
            for blk, frac in (("all", 1.0), ("research", 0.5)):
                nn = n * frac
                mrows.append(dict(tf=q.tf, set=lab, block=blk, n=nn, keep=k, sd=sd,
                                  mde_uplift=2.802 * sd * np.sqrt((1 - k) / (k * nn))))
M = pd.DataFrame(mrows)
print(M.pivot_table(index=["tf", "set"], columns=["block", "keep"], values="mde_uplift")
      .to_string(float_format=lambda v: f"{v:.4f}"))
print("\n  Against these, the primary's whole per-trade edge at 30s is "
      f"{cnt.loc[cnt.tf == 0.5, 'locked_pct'].iloc[0]:+.4f} %/trade.")
M.to_csv(os.path.join(HERE, "t0_mde.csv"), index=False)
cnt.to_csv(os.path.join(HERE, "t0_counts.csv"), index=False)

hd("0c  OVERLAP ACROSS TIMEFRAMES -- THESE ARE VIEWS OF THE SAME 92 SESSIONS")
key = E.assign(k=list(zip(E.day, E.side)))
J = []
for i, a in enumerate(C.TFS):
    for b in C.TFS[i + 1:]:
        A = key[key.tf == a]; B = key[key.tf == b]
        sa = set(A.loc[A.gated == 1, "day"]); sb = set(B.loc[B.gated == 1, "day"])
        ka = set(A["k"]); kb = set(B["k"])
        ga = set(A.loc[A.gated == 1, "k"]); gb = set(B.loc[B.gated == 1, "k"])
        m = A.merge(B, on=["day", "side"], suffixes=("_a", "_b"))
        dt = (m["t_sig_a"] - m["t_sig_b"]).abs() / pd.Timedelta(minutes=1)
        same_t = float((dt < max(a, b)).mean()) if len(m) else np.nan
        rho = float(np.corrcoef(m["pct_a"], m["pct_b"])[0, 1]) if len(m) > 2 else np.nan
        J.append(dict(a=a, b=b, jac_sess_gated=len(sa & sb) / max(len(sa | sb), 1),
                      jac_event_all=len(ka & kb) / max(len(ka | kb), 1),
                      jac_event_gated=len(ga & gb) / max(len(ga | gb), 1),
                      same_bar_time=same_t, label_corr=rho, n_matched=len(m)))
J = pd.DataFrame(J)
print(J.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
J.to_csv(os.path.join(HERE, "t0_overlap.csv"), index=False)

hd("0d  EFFECTIVE POOLED n")
rho = float(J["label_corr"].mean())
grp = key.groupby("k").size()
eff = float((grp / (1 + (grp - 1) * rho)).sum())
gk = key[key.gated == 1].groupby("k").size()
effg = float((gk / (1 + (gk - 1) * rho)).sum())
print(f"  nominal pooled ungated events {len(E)} across {len(C.TFS)} timeframes")
print(f"  distinct (session, side) break events {len(grp)} on {E['day'].nunique()} sessions")
print(f"  mean label correlation of the SAME break across two timeframes  rho = {rho:+.3f}")
print(f"  effective n = sum_k k/(1+(k-1)rho) = {eff:.1f}  (ungated)")
print(f"  gated: nominal {int(gk.sum())}, distinct {len(gk)}, effective {effg:.1f}")
print(f"  and the sessions themselves bound it: {E['day'].nunique()} sessions, "
      f"{len(is_d)} in the research half.")
sd0 = E.loc[E.tf == 0.5, "pct"].std(ddof=1)
for k in (0.7, 0.5):
    print(f"  pooled uplift MDE at effective n {eff:.0f}, keep {k}: "
          f"{2.802*sd0*np.sqrt((1-k)/(k*eff)):.4f} %/trade (all); research half "
          f"{2.802*sd0*np.sqrt((1-k)/(k*eff/2)):.4f}")
pd.DataFrame([dict(nominal=len(E), distinct=len(grp), rho=rho, eff=eff, gated_nominal=int(gk.sum()),
                   gated_distinct=len(gk), gated_eff=effg, sessions=E['day'].nunique())]
             ).to_csv(os.path.join(HERE, "t0_effn.csv"), index=False)
print(f"\ndone in {time.time()-t0:.0f}s")
