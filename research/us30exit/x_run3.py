"""x_run3 -- decompose the trail's PF, because PF rose while points a trade did not.

x_run2 produced the shape that matters: the trail takes PF from 1.236 to 1.422 and takes points a
trade from +6.260 to +6.242. A profit factor is sum(wins) / sum(losses), so it can be raised by
shrinking the denominator without adding a single point of return. That is a THIRD way a PF gain
can be empty, distinct from `STUDY_V24`'s trade-less artifact (this cell trades MORE) and from
`STUDY_V63`'s unit disagreement (here the units mostly agree). It is decomposed here rather than
argued about.

And the control ladder is carried through, because the decisive number in x_run2 was that a COIN
FLIP with a 0.25 ATR trail reads PF 2.473 -- the trail is a PF multiplier applied to whatever
entry it is attached to.
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


def gross(p):
    p = np.asarray(p, float)
    return float(p[p > 0].sum()), float(-p[p < 0].sum()), float(p[p > 0].mean()), \
        float(-p[p < 0].mean())


def ctl_full(f, t, elig, n_draw, seed, **kw):
    """Control draws returning pts, PF AND return/drawdown, so every headline statistic the rule
    is praised for has its own null."""
    rng = np.random.default_rng(seed)
    pool = np.flatnonzero(elig)
    n = len(t)
    o = np.full((n_draw, 3), np.nan)
    for i in range(n_draw):
        pick = np.sort(rng.choice(pool, size=n, replace=False))
        sd = rng.permutation(t["side"].to_numpy())[:len(pick)]
        tt = X.xwalk(f, pick, sd, **kw)
        if len(tt) < 5:
            continue
        p = tt["pts"].to_numpy()
        eq = np.cumsum(p)
        mdd = float(np.max(np.maximum.accumulate(eq) - eq))
        o[i] = [p.mean(), S.pf(p), p.sum() / mdd if mdd > 0 else np.nan]
    return o[np.isfinite(o[:, 0])]


def main():
    f = S.load("US30L")
    bl = S.blocks(f, "US30L")
    res = bl["A_research"]
    nsess = f.index[res & S.window(f)].normalize().nunique()
    M = X.L.build_masks(f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy())
    sig, sd = X.signals(f, ARM, res, M)
    chlo = X.chan_low(f, 10, 1)
    elig = S.window(f) & res

    print("=== 1. WHERE THE PF GAIN COMES FROM -- gross wins against gross losses ===")
    print("    PF = sum(wins) / sum(losses). A cell can raise it by shrinking the denominator")
    print("    and add nothing to the numerator, which is money it never made.\n")
    rows = []
    for nm, st, tg, pol in (("C0 50/150 flatten", 50, 150, "flatten"),
                            ("C5 100/150 flatten", 100, 150, "flatten"),
                            ("C4 100/none flatten", 100, None, "flatten"),
                            ("C1 100/150 trail1.0", 100, 150, "+trail1atr"),
                            ("   100/150 trail0.5", 100, 150, "+trail1atr"),
                            ("   100/150 trail0.25", 100, 150, "+trail1atr"),
                            ("C3 150/none trail1.0", 150, None, "+trail1atr")):
        mult = 1.0
        if "0.5" in nm:
            mult = 0.5
        if "0.25" in nm:
            mult = 0.25
        t = X.xwalk(f, sig, sd, stop=st, tgt=tg, policy=pol, tr_mult=mult, chlo=chlo)
        gw, gl, mw, ml = gross(t["pts"])
        r = X.stats(t, nsess, st, tg)
        rows.append(dict(cell=nm, n=r["n"], nwin=int((t.pts > 0).sum()),
                         win=r["win"], gross_win=gw, gross_loss=gl, mean_win=mw, mean_loss=ml,
                         payoff=mw / ml, pf=r["pf"], total=r["total"], pts=r["pts"],
                         dd=r["dd"], ret_dd=r["ret_dd"], med_min=r["med_min"]))
    D = pd.DataFrame(rows).set_index("cell")
    print(D.round(3).to_string())
    print("\n  read the gross_loss column down the page: that is the whole PF story.")

    print("\n=== 2. THE TRAIL LADDER WITH THE CONTROL'S OWN PF AND ret/DD ===")
    print("    Every statistic the trail is praised for is given its own null. `pf_ratio` is the")
    print("    rule's PF over its twin's -- the part of PF the entry actually owns.\n")
    lad = []
    for mult in (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, None):
        pol = "flatten" if mult is None else "+trail1atr"
        kw = dict(stop=100, tgt=150, policy=pol, chlo=chlo)
        if mult is not None:
            kw["tr_mult"] = mult
        t = X.xwalk(f, sig, sd, **kw)
        r = X.stats(t, nsess, 100, 150)
        c = ctl_full(f, t, elig, 300, 17, **kw)
        cp, cf, cr = np.nanmedian(c[:, 0]), np.nanmedian(c[:, 1]), np.nanmedian(c[:, 2])
        lad.append(dict(trail="none" if mult is None else f"{mult:.2f}", n=r["n"],
                        pf=r["pf"], ctl_pf=cf, pf_ratio=r["pf"] / cf,
                        pts=r["pts"], ctl_pts=cp, edge=r["pts"] - cp,
                        total=r["total"], ctl_total=cp * r["n"],
                        excess_total=(r["pts"] - cp) * r["n"],
                        ret_dd=r["ret_dd"], ctl_ret_dd=cr,
                        win=r["win"], med_min=r["med_min"],
                        p_pts=float(np.mean(c[:, 0] >= r["pts"])),
                        p_pf=float(np.mean(c[:, 1] >= r["pf"]))))
    L = pd.DataFrame(lad)
    print(L.round(4).to_string(index=False))
    print("\n  the two columns that decide it: `ctl_pf` (what a coin flip earns with the same")
    print("  trail) and `excess_total` (the points the ENTRY is worth once the trail is priced).")

    print("\n=== 3. does the trail change the SIGNAL or only the EXIT? paired on entry bars ===")
    a = X.xwalk(f, sig, sd, stop=100, tgt=150, policy="flatten", chlo=chlo)
    b = X.xwalk(f, sig, sd, stop=100, tgt=150, policy="+trail1atr", chlo=chlo)
    common = np.intersect1d(a.e_bar.to_numpy(), b.e_bar.to_numpy())
    aa = a.set_index("e_bar").loc[common]
    bb = b.set_index("e_bar").loc[common]
    d = bb.pts.to_numpy() - aa.pts.to_numpy()
    se = d.std(ddof=1) / np.sqrt(len(d))
    print(f"  entry bars shared by both policies: {len(common)} of {len(a)} / {len(b)}")
    print(f"  paired delta (trail - flatten), points a trade: {d.mean():+.3f}  "
          f"MDE {X.Z80 * se:.3f}  -> "
          f"{'OUTSIDE' if abs(d.mean()) > X.Z80 * se else 'inside'} the paired MDE")
    print(f"  trades the trail improves: {float((d > 0).mean()):.1%};  worsens "
          f"{float((d < 0).mean()):.1%};  identical {float((d == 0).mean()):.1%}")
    print(f"  trades ADMITTED only because the trail freed the position lock earlier: "
          f"{len(b) - len(common)}")
    extra = b[~b.e_bar.isin(common)]
    if len(extra):
        print(f"     those {len(extra)} extra trades earn {extra.pts.mean():+.3f} pts each, "
              f"{extra.pts.sum():+.1f} total  (PF {S.pf(extra.pts.to_numpy()):.3f})")

    print("\n=== 4. the stop axis in THREE units on the flatten policy, `STUDY_V63`'s test ===")
    print("    the axis that moved PF second-most, read the way V63 said to read it.\n")
    sr = []
    for st in (30, 50, 75, 100, 150, 200):
        t = X.xwalk(f, sig, sd, stop=st, tgt=150, policy="flatten", chlo=chlo)
        r = X.stats(t, nsess, st, 150)
        sr.append(dict(stop=st, n=r["n"], pf=r["pf"], pts=r["pts"], R=r["R"], total=r["total"],
                       dd=r["dd"], ret_dd=r["ret_dd"], win=r["win"], be=r["be"],
                       win_minus_be=r["win"] - r["be"], mde=r["mde"]))
    print(pd.DataFrame(sr).round(4).to_string(index=False))

    print("\n=== 5. the target axis in three units, no-take-profit included ===")
    tr = []
    for tg in (50, 100, 150, 200, 300, None):
        t = X.xwalk(f, sig, sd, stop=100, tgt=tg, policy="flatten", chlo=chlo)
        r = X.stats(t, nsess, 100, tg)
        tr.append(dict(tgt="none" if tg is None else tg, n=r["n"], pf=r["pf"], pts=r["pts"],
                       R=r["R"], total=r["total"], dd=r["dd"], ret_dd=r["ret_dd"], win=r["win"],
                       be=r["be"], mde=r["mde"], sh_tgt=r["sh_target"], sh_flat=r["sh_flat"]))
    print(pd.DataFrame(tr).round(4).to_string(index=False))


if __name__ == "__main__":
    main()
