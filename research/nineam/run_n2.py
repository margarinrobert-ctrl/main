"""N2 -- every parameter, read by MARGINAL AVERAGE and never by its top row.

THE GRID IS DECLARED BEFORE IT IS RUN, and so is the bar its best row would have to clear:
    3 range windows x 3 buffers x 3 sides x 5 EMA readings x 6 stops x 5 targets x 4 flattens
    = 16,200 cells a feed-timeframe.
`E[max t | pure noise]` over 16,200 looks is printed below and is far above the 2.802 that
detection needs, so the maximum of this grid could not be believed even if the whole space were
noise. That is the reason the marginal average is the only reading taken (`STUDY_V11_MARKET`,
`STUDY_V60_AROON`), and the reason the population shape is printed before any ranking.

SEARCHED ON THE RESEARCH BLOCK ONLY. Locked blocks are computed in the same pass so the
POPULATION-level transfer correlation can be reported -- that is a property of the whole grid and
names no cell, which is the one use of a held-back block that does not spend it (`STUDY_V53`).
"""
from __future__ import annotations
import os, sys, itertools, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import na_core as N

WINDOWS = [(540, 570), (510, 570), (540, 555)]     # 09:00-09:30 (as asked), 08:30-09:30, 09:00-09:15
BUFS = [0.0, 0.10, 0.25]
SIDES = ["long", "short", "both"]
EMAS = ["off", "state", "x5", "x10", "x20"]
STOPS = [0.5, 1.0, 1.5, 2.0, 3.0, -1.0]           # -1 = the opposite side of the range
TGTS = [0.0, 1.0, 1.5, 2.0, 3.0]
FLATS = [660, 720, 960, 0]                        # 11:00, 12:00, 16:00, hold to the session end

FEEDS = [("US30L", 15), ("US30I", 15), ("US100L", 15), ("NQ", 15)]


def gate(f, sig, sd, how):
    if how == "off":
        return sig, sd
    st, age, aged = N.ema_state(f, 13, 48, "ema")
    if how == "state":
        k = np.where(sd > 0, st[sig], ~st[sig])
    else:
        R = int(how[1:])
        k = np.where(sd > 0, age[sig] <= R, aged[sig] <= R)
    return sig[k], sd[k]


def main():
    ncell = len(WINDOWS) * len(BUFS) * len(SIDES) * len(EMAS) * len(STOPS) * len(TGTS) * len(FLATS)
    print(f"declared cells per feed-timeframe: {ncell}")
    print(f"E[max t | pure noise] over {ncell} looks = {N.e_max_normal(ncell):.3f} "
          f"against the 2.802 detection needs -> the top row is unreadable, marginals only.\n")

    allrows = []
    for name, tf in FEEDS:
        t0 = time.time()
        f = N.load(name, tf)
        cost = N.COST[name]
        bl = N.blocks(f, name)
        keys = list(bl)
        res = bl[keys[0]]; lock = bl[keys[1]] if len(keys) > 1 else np.zeros(len(f), bool)
        rows = []
        for (rs, re_) in WINDOWS:
            rhi, rlo, rn = N.ranges(f, rs, re_)
            for buf in BUFS:
                for side in SIDES:
                    s0, d0 = N.events(f, rhi, rlo, side=side, buf_atr=buf, rs=rs, re_=re_)
                    for eg in EMAS:
                        s1, d1 = gate(f, s0, d0, eg)
                        if len(s1) < 30:
                            continue
                        for stop_a in STOPS:
                            use_rng = stop_a < 0
                            for tgt in TGTS:
                                for fl in FLATS:
                                    tr = N.run(f, s1, d1, stop_a=abs(stop_a), tgt_r=tgt,
                                               flat_m=fl, cost=cost, use_rng=use_rng,
                                               rhi=rhi, rlo=rlo)
                                    if len(tr) < 30:
                                        continue
                                    sg = tr["sig"].to_numpy()
                                    for bn, mk in (("res", res), ("lock", lock)):
                                        if not mk.any():
                                            continue
                                        t = tr[mk[sg]]
                                        if len(t) < 25:
                                            continue
                                        p = t["pct"].to_numpy()
                                        rows.append(dict(
                                            feed=f"{name}{tf}", win=f"{rs}-{re_}", buf=buf,
                                            side=side, ema=eg, stop=stop_a, tgt=tgt, flat=fl,
                                            block=bn, n=len(t), pct=p.mean(),
                                            tot=p.sum(),
                                            pf=t.loc[t.pts > 0, "pts"].sum() /
                                               max(-t.loc[t.pts < 0, "pts"].sum(), 1e-9),
                                            win_r=(t.pts > 0).mean()))
        g = pd.DataFrame(rows)
        allrows.append(g)
        print(f"{name}{tf}: {len(g)} scorable rows in {time.time()-t0:.0f}s")
    G = pd.concat(allrows, ignore_index=True)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "n2_grid.csv")
    G.to_csv(out, index=False)
    print(f"\nwrote {out}  ({len(G)} rows)")

    print("\n" + "=" * 100)
    print("N2.1  POPULATION SHAPE FIRST -- a top row is the maximum of however many positive draws")
    print("=" * 100)
    for fd, sub in G.groupby("feed"):
        r = sub[sub.block == "res"]; l = sub[sub.block == "lock"]
        j = r.merge(l, on=["feed", "win", "buf", "side", "ema", "stop", "tgt", "flat"],
                    suffixes=("_r", "_l"))
        print(f"  {fd:8s} research cells {len(r):6d}  profitable {100*(r.pct>0).mean():5.1f}%   "
              f"locked profitable {100*(l.pct>0).mean():5.1f}%   "
              f"corr(res,lock) {j['pct_r'].corr(j['pct_l']):+.3f} Pearson / "
              f"{j['pct_r'].corr(j['pct_l'], method='spearman'):+.3f} Spearman")
        if len(j):
            top = j.nlargest(max(1, len(j) // 100), "pct_r")
            print(f"           top 1% by research: {top['pct_r'].mean():+.4f} -> "
                  f"locked {top['pct_l'].mean():+.4f}   (whole population locked "
                  f"{l['pct'].mean():+.4f})")

    print("\n" + "=" * 100)
    print("N2.2  MARGINAL AVERAGE PER AXIS  (mean %/trade over every cell at that setting)")
    print("=" * 100)
    for ax in ("win", "buf", "side", "ema", "stop", "tgt", "flat"):
        t = G.pivot_table(index=ax, columns=["feed", "block"], values="pct", aggfunc="mean")
        print(f"\n--- {ax} ---")
        print((t * 100).round(2).to_string())
    print("\n  values are basis points of entry price per trade (x100 of the pct column).")


if __name__ == "__main__":
    main()
