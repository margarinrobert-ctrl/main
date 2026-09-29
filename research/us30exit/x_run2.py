"""x_run2 -- the artifact battery on what the marginals chose, BEFORE any out-of-sample read.

The 80-cell marginal picked the TRAIL on every unit at once, which rules out `STUDY_V24`'s
trade-less artifact (it trades MORE, not less) and leaves `STUDY_ABSORPTION_LEVELS`' artifact as
the live question: a trail is a take profit wearing a stop's name, and at a tight setting the win
rate is set by the bar's own range before any signal is consulted. So every trail and channel cell
here is run beside a RANDOM ENTRY carrying the IDENTICAL exit machinery, and the trail multiplier
is swept as a neighbourhood with a twin at every rung -- if the rule's advantage over its twin
vanishes as the trail tightens, the trail is geometry and not signal.

CANDIDATES, declared here from the MARGINAL AVERAGES of x_run1 and not from its top row:
  C0  50/150 flatten          the section-12 incumbent, the reference every cell is judged against
  C1  100/150 +trail1atr      the marginal consensus (stop 100 leads PF/total/per-trade,
                              target 150 leads all four units, trail leads all four)
  C2  50/150  +trail1atr      the ret/DD marginal's stop (50 leads ret/DD at 2.643)
  C3  150/none +trail1atr     THE TOP ROW, carried only so it can be shown to be the top row
  C4  100/none flatten        no take profit with no trail -- isolates the 25-times finding alone
  C5  100/150 flatten         the marginal consensus WITHOUT the trail -- isolates the trail
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x_lib as X  # noqa: E402
import s30core as S  # noqa: E402

pd.set_option("display.width", 280)
ARM = "+adx<=20"

CAND = [
    ("C0 incumbent  50/150 flatten", 50, 150, "flatten"),
    ("C1 marginal  100/150 trail1", 100, 150, "+trail1atr"),
    ("C2 retdd      50/150 trail1", 50, 150, "+trail1atr"),
    ("C3 TOP ROW   150/none trail1", 150, None, "+trail1atr"),
    ("C4 no-target 100/none flat", 100, None, "flatten"),
    ("C5 no-trail  100/150 flat", 100, 150, "flatten"),
    ("C6 chan      100/150 chan10", 100, 150, "+chan10"),
    ("C7 be1R      100/150 be1R", 100, 150, "+be1R"),
]
COLS = ["n", "pts", "total", "pf", "ret_dd", "dd", "win", "be", "mde", "outside_mde", "t",
        "sharpe", "med_min", "amb", "sh_stop", "sh_target", "sh_chan", "sh_flat"]


def main():
    f = S.load("US30L")
    bl = S.blocks(f, "US30L")
    res = bl["A_research"]
    nsess = f.index[res & S.window(f)].normalize().nunique()
    M = X.L.build_masks(f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy())
    sig, sd = X.signals(f, ARM, res, M)
    chlo = X.chan_low(f, 10, 1)
    elig = S.window(f) & res

    print("=== 1. THE DECLARED CANDIDATES, every unit side by side ===")
    print("    `be` is the driftless two-outcome break-even (stop+cost)/(stop+tgt); it does not")
    print("    exist without a target and does not apply once a trail or channel can exit.\n")
    rows = []
    keep = {}
    for nm, st, tg, pol in CAND:
        t = X.xwalk(f, sig, sd, stop=st, tgt=tg, policy=pol, chlo=chlo)
        r = X.stats(t, nsess, stop=st, tgt=tg)
        r["cand"] = nm
        rows.append(r)
        keep[nm] = (t, dict(stop=st, tgt=tg, policy=pol, chlo=chlo))
    C = pd.DataFrame(rows).set_index("cand")
    print(C[COLS].round(4).to_string())

    print("\n=== 2. THE MATCHED RANDOM ENTRY -- identical exit machinery, 400 draws ===")
    print("    `STUDY_ABSORPTION_LEVELS`: a 0.25 ATR trail read PF 1.751 and a random entry with")
    print("    the same trail read 1.617. The gap over the twin is the only thing the rule owns.\n")
    out = []
    for nm, (t, kw) in keep.items():
        cp, cf = X.control(f, len(t), t["side"].to_numpy(), elig, n_draw=400, seed=11, **kw)
        p = t["pts"].to_numpy()
        out.append(dict(cand=nm, n=len(t), rule_pts=p.mean(), ctl_pts=float(np.median(cp)),
                        edge=p.mean() - float(np.median(cp)),
                        p_pts=float(np.mean(cp >= p.mean())),
                        rule_pf=S.pf(p), ctl_pf=float(np.median(cf)),
                        d_pf=S.pf(p) - float(np.median(cf)),
                        p_pf=float(np.mean(cf >= S.pf(p)))))
    print(pd.DataFrame(out).set_index("cand").round(4).to_string())

    print("\n=== 3. THE TRAIL LADDER, each rung beside its own twin ===")
    print("    If the advantage over the twin shrinks as the trail tightens, the trail is the")
    print("    bar's range and not the signal. Stop 100 / target 150 held fixed.\n")
    lad = []
    for mult in (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0):
        kw = dict(stop=100, tgt=150, policy="+trail1atr", tr_mult=mult, chlo=chlo)
        t = X.xwalk(f, sig, sd, **kw)
        r = X.stats(t, nsess, stop=100, tgt=150)
        cp, cf = X.control(f, len(t), t["side"].to_numpy(), elig, n_draw=300, seed=13, **kw)
        lad.append(dict(trail_atr=mult, n=r["n"], pts=r["pts"], pf=r["pf"], win=r["win"],
                        total=r["total"], ret_dd=r["ret_dd"], med_min=r["med_min"],
                        amb=r["amb"], mde=r["mde"],
                        ctl_pts=float(np.median(cp)), edge=r["pts"] - float(np.median(cp)),
                        ctl_pf=float(np.median(cf)), d_pf=r["pf"] - float(np.median(cf)),
                        p_pts=float(np.mean(cp >= r["pts"]))))
    LAD = pd.DataFrame(lad)
    print(LAD.round(4).to_string(index=False))
    print("\n  no trail at all, same geometry, for the bottom of the ladder:")
    t0 = X.xwalk(f, sig, sd, stop=100, tgt=150, policy="flatten", chlo=chlo)
    r0 = X.stats(t0, nsess, stop=100, tgt=150)
    cp0, cf0 = X.control(f, len(t0), t0["side"].to_numpy(), elig, n_draw=300, seed=13,
                         stop=100, tgt=150, policy="flatten", chlo=chlo)
    print(f"    n {r0['n']}  pts {r0['pts']:+.3f}  pf {r0['pf']:.3f}  win {r0['win']:.3f}  "
          f"total {r0['total']:+.1f}  ret/DD {r0['ret_dd']:.2f}  ctl_pts {np.median(cp0):+.3f}  "
          f"edge {r0['pts'] - np.median(cp0):+.3f}  ctl_pf {np.median(cf0):.3f}")

    print("\n=== 4. GAP-THROUGH: does the trail actually fill where it is priced? ===")
    print("    The walker fills a stop AT its level. On a trail sitting close to price that is an")
    print("    assumption, so it is measured: how often the exit bar OPENS beyond the level.\n")
    for nm, (t, kw) in keep.items():
        if kw["policy"] not in ("+trail1atr", "flatten"):
            continue
        st = t[t.why == 0]
        if not len(st):
            continue
        o = f["open"].to_numpy()[st.x_bar.to_numpy()]
        ent = f["open"].to_numpy()[st.e_bar.to_numpy()]
        lvl = ent - st.risk.to_numpy() if kw["policy"] == "flatten" else None
        gap = np.nan
        if lvl is not None:
            gap = float((o < lvl).mean())
        print(f"  {nm:30s} stop exits {len(st):4d} ({len(st)/len(t):.1%})  "
              + (f"exit bar opens below the fixed stop {gap:.2%}" if lvl is not None
                 else "trail level is path-dependent, see below"))
    tt = keep["C1 marginal  100/150 trail1"][0]
    st = tt[tt.why == 0]
    o = f["open"].to_numpy()[st.x_bar.to_numpy()]
    lo = f["low"].to_numpy()[st.x_bar.to_numpy()]
    print(f"\n  C1 trail exits: {len(st)} of {len(tt)}.  On those bars the OPEN is below the LOW+"
          f"range midpoint in {(o - lo).mean():.2f} pts of mean travel from the open to the low --")
    print("  the exit-bar open-to-low travel is the room a fill at the level assumes it has.")

    print("\n=== 5. THE FLATTEN, priced separately (the user keeps it ON for the headline) ===")
    fl = []
    for nm, st, tg, pol in CAND:
        a = X.xwalk(f, sig, sd, stop=st, tgt=tg, policy=pol, flat=X.FLAT, chlo=chlo)
        b = X.xwalk(f, sig, sd, stop=st, tgt=tg, policy=pol, flat=0, chlo=chlo)
        ra, rb = X.stats(a, nsess, st, tg), X.stats(b, nsess, st, tg)
        fl.append(dict(cand=nm, n_on=ra["n"], n_off=rb["n"], pts_on=ra["pts"], pts_off=rb["pts"],
                       d_pts=rb["pts"] - ra["pts"], pf_on=ra["pf"], pf_off=rb["pf"],
                       tot_on=ra["total"], tot_off=rb["total"],
                       rdd_on=ra["ret_dd"], rdd_off=rb["ret_dd"],
                       flat_sh=ra["sh_flat"], med_on=ra["med_min"], med_off=rb["med_min"]))
    print(pd.DataFrame(fl).set_index("cand").round(3).to_string())

    print("\n=== 6. TIE-BREAK on the candidates ===")
    for nm, st, tg, pol in CAND:
        a = X.xwalk(f, sig, sd, stop=st, tgt=tg, policy=pol, tie=0, chlo=chlo)
        b = X.xwalk(f, sig, sd, stop=st, tgt=tg, policy=pol, tie=1, chlo=chlo)
        ra, rb = X.stats(a, nsess, st, tg), X.stats(b, nsess, st, tg)
        print(f"  {nm:30s} amb {ra['amb']:.2%}   stop-first {ra['pts']:+7.3f} PF {ra['pf']:.3f}"
              f"   target-first {rb['pts']:+7.3f} PF {rb['pf']:.3f}"
              f"   spread {rb['pts'] - ra['pts']:+6.3f}")

    print("\n=== 7. what a PF gain is worth against the bar the study set ===")
    base = C.loc["C0 incumbent  50/150 flatten"]
    for nm in C.index:
        r = C.loc[nm]
        print(f"  {nm:30s} PF {r.pf:.3f}  pts {r.pts:+7.3f}  MDE {r.mde:5.2f}  "
              f"delta vs C0 {r.pts - base.pts:+7.3f}  "
              f"{'OUTSIDE its MDE' if abs(r.pts) > r.mde else 'inside its MDE'}"
              f"   PF1.2 needs +10.61, PF1.5 needs +23.62")


if __name__ == "__main__":
    main()
