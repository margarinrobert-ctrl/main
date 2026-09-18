"""N14 -- the ATR PERIOD as a selectable axis, and an ATR TAKE PROFIT.

Two additions asked for on the 09:00-range script. Both touch the geometry every published figure
in this study was measured at, so both are measured before either ships.

SECTION 1 -- THE IDENTITY, ASSERTED NOT ASSUMED. Under an ATR stop, `target = k x ATR` and
`target = r x stop` are the SAME LEVEL when k = r x stop_a, so an ATR target is not a new axis
there; it is the R target renamed. It becomes a separate axis only under a POINTS stop or the
opposite-side-of-the-range stop, where the risk is not an ATR multiple. That has to be checked
rather than reasoned about -- `STUDY_V40` found two features reproducing each other to the cent and
`run_r3` built the same check in deliberately.

SECTION 2 -- THE ATR PERIOD LADDER. This is a genuine new axis: every figure in
`docs/ib/STUDY_NINE_AM_RANGE.md` used `ema(tr, 14)`, and changing the period moves the stop, the
break buffer and (now) the target together. Declared rungs 7 / 10 / 14 / 21 / 30 / 50 x long and
both x two geometries x three blocks = 72 cells, of which 60 are SCORABLE against their own ATR-14
twin. Paired on identical feed / block / side / geometry, because an ATR period changes which bars
fire and the level is not comparable across rungs while the paired delta is.

SECTION 3 -- THE ATR TARGET LADDER at the shipped 1.5N stop, paired against no target. This is
where the 26-instance no-take-profit streak gets its 27th read, and the rungs are chosen so they
also double as the identity's test points (1.5 ATR = 1R, 3.0 = 2R, 4.5 = 3R behind a 1.5N stop).

Both bars are printed before any table: `E[max t | pure noise]` for the declared count, and each
cell's own MDE. Neither addition changes a default -- the ATR period ships at 14 and the target
ships OFF.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import na_core as N

pd.set_option("display.width", 235)
HERE = os.path.dirname(os.path.abspath(__file__))

ATRS = [7, 10, 14, 21, 30, 50]          # 14 is the incumbent and the twin every rung is paired to
SIDES = ["long", "both"]
GEOMS = {"1.5N / none": dict(stop_a=1.5, tgt_r=0.0),
         "1.5N / 3ATR": dict(stop_a=1.5, tgt_atr=3.0)}
TGT_ATR = [0.0, 1.5, 2.25, 3.0, 4.5, 6.0]
FEEDS = ["US30L", "US30I"]
RS, RE = 540, 555


def stats(t):
    w = t.loc[t.pts > 0, "pts"].sum()
    lo = -t.loc[t.pts < 0, "pts"].sum()
    return float(t["pct"].mean()), float(w / max(lo, 1e-9))


def main():
    f14 = N.load("US30L", 15)
    rhi, rlo, _ = N.ranges(f14, RS, RE)
    sig, sd = N.events(f14, rhi, rlo, side="both", rs=RS, re_=RE, open_m=570)

    print("=" * 120)
    print("SECTION 1  IS AN ATR TARGET A NEW AXIS? -- asserted, not assumed")
    print("=" * 120)
    for stop_a in (1.5, 2.5):
        for r in (1.0, 2.0, 3.0):
            a = N.run(f14, sig, sd, stop_a=stop_a, tgt_r=r, flat_m=960, cost=2.29)
            b = N.run(f14, sig, sd, stop_a=stop_a, tgt_atr=r * stop_a, flat_m=960, cost=2.29)
            same = len(a) == len(b) and bool((a["xb"].to_numpy() == b["xb"].to_numpy()).all())
            d = float(np.abs(a["pts"].to_numpy() - b["pts"].to_numpy()).max()) if same else np.nan
            print(f"  ATR stop {stop_a}N: tgt_r={r} vs tgt_atr={r*stop_a}  "
                  f"n {len(a)}/{len(b)}  identical exit bars {same}  max |dpts| {d:.3e}")
    # and where it is NOT an identity
    for spts in (50.0, 100.0):
        a = N.run(f14, sig, sd, stop_pts=spts, tgt_r=2.0, flat_m=960, cost=2.29)
        b = N.run(f14, sig, sd, stop_pts=spts, tgt_atr=3.0, flat_m=960, cost=2.29)
        m = a.merge(b, on="sig", suffixes=("_r", "_a"))
        agree = float((m["xb_r"] == m["xb_a"]).mean()) if len(m) else float("nan")
        print(f"  POINTS stop {spts:.0f}: tgt_r=2 vs tgt_atr=3 -- n {len(a)} vs {len(b)}, "
              f"same exit bar on {agree:.3f} of the {len(m)} shared signals: the two axes SEPARATE")

    print("\n" + "=" * 120)
    print("SECTION 2  THE ATR PERIOD LADDER -- paired against its own ATR(14) twin")
    print("=" * 120)
    n_cells = len(ATRS) * len(SIDES) * len(GEOMS) * 3
    n_pair = (len(ATRS) - 1) * len(SIDES) * len(GEOMS) * 3
    print(f"  declared cells {n_cells}, of which {n_pair} are PAIRED against the ATR(14) twin")
    print(f"  E[max t | pure noise] over {n_pair} looks = {N.e_max_normal(n_pair):.3f} "
          f"against the 2.802 detection needs")
    print("  every figure in this study was measured at ema(tr, 14); this axis is new\n")

    rows = []
    for name in FEEDS:
        base = N.load(name, 15)
        cost = N.COST[name]
        bl = N.blocks(base, name)
        for an in ATRS:
            f = N.set_atr(base, an)
            rhi, rlo, _ = N.ranges(f, RS, RE)
            for side in SIDES:
                s0, d0 = N.events(f, rhi, rlo, side=side, rs=RS, re_=RE, open_m=570)
                for gname, geom in GEOMS.items():
                    tr = N.attach_day(f, N.run(f, s0, d0, flat_m=960, cost=cost, **geom))
                    for bn, msk in bl.items():
                        t = tr[msk[tr["sig"].to_numpy()]]
                        if len(t) < 25:
                            continue
                        e, pf = stats(t)
                        rows.append(dict(feed=name, block=bn, side=side, geom=gname, atr=an,
                                         n=len(t), pct=round(e, 4), pf=round(pf, 3),
                                         med_atr=round(float(t["atr"].median()), 2),
                                         risk=round(float(t["risk"].median()), 1),
                                         mde=round(N.mde(t["pct"].std(), len(t)), 4)))
    o = pd.DataFrame(rows)
    o.to_csv(os.path.join(HERE, "n14_atr_period.csv"), index=False)
    for g in GEOMS:
        print(f"\n--- {g} ---")
        print(o[o.geom == g][["feed", "block", "side", "atr", "n", "pct", "pf",
                              "med_atr", "risk", "mde"]].to_string(index=False))

    k = ["feed", "block", "side", "geom"]
    b14 = o[o.atr == 14].set_index(k)[["pct", "n", "pf", "risk"]]
    j = o[o.atr != 14].set_index(k).join(b14, rsuffix="_14")
    j["d_pct"] = j["pct"] - j["pct_14"]
    j["d_n"] = j["n"] - j["n_14"]
    jr = j.reset_index()
    print("\n  marginal average of the paired delta, by ATR period:")
    print(jr.groupby("atr").agg(d_pct=("d_pct", "mean"), d_n=("d_n", "mean"),
                                beats=("d_pct", lambda x: float((x > 0).mean())),
                                cells=("d_pct", "size")).round(4).to_string())
    print("\n  by block (research is the only one permitted to choose):")
    print(jr.groupby(["feed", "block"]).agg(d_pct=("d_pct", "mean"),
                                            beats=("d_pct", lambda x: float((x > 0).mean())),
                                            cells=("d_pct", "size")).round(4).to_string())
    n_out = int((jr["d_pct"].abs() > jr["mde"]).sum())
    print(f"\n  paired deltas exceeding their own MDE: {n_out} of {len(jr)}")
    print(f"  rungs beating the ATR(14) twin: {int((jr.d_pct > 0).sum())} of {len(jr)} "
          f"(chance is 50%)")
    jr.to_csv(os.path.join(HERE, "n14_paired.csv"), index=False)

    print("\n" + "=" * 120)
    print("SECTION 3  THE ATR TAKE PROFIT at the shipped 1.5N stop -- paired against NO target")
    print("=" * 120)
    rows = []
    for name in FEEDS:
        f = N.load(name, 15)
        cost = N.COST[name]
        bl = N.blocks(f, name)
        rhi, rlo, _ = N.ranges(f, RS, RE)
        for side in SIDES:
            s0, d0 = N.events(f, rhi, rlo, side=side, rs=RS, re_=RE, open_m=570)
            for ta in TGT_ATR:
                tr = N.attach_day(f, N.run(f, s0, d0, stop_a=1.5, tgt_atr=ta,
                                           flat_m=960, cost=cost))
                for bn, msk in bl.items():
                    t = tr[msk[tr["sig"].to_numpy()]]
                    if len(t) < 25:
                        continue
                    e, pf = stats(t)
                    hit = float((t["why"].to_numpy() == 2).mean())
                    rows.append(dict(feed=name, block=bn, side=side, tgt=ta, n=len(t),
                                     pct=round(e, 4), pf=round(pf, 3),
                                     win=round(float((t.pts > 0).mean()), 3),
                                     hit=round(hit, 3),
                                     mde=round(N.mde(t["pct"].std(), len(t)), 4)))
    q = pd.DataFrame(rows)
    q.to_csv(os.path.join(HERE, "n14_atr_target.csv"), index=False)
    print(q.to_string(index=False))
    k2 = ["feed", "block", "side"]
    b0 = q[q.tgt == 0].set_index(k2)[["pct", "n", "pf"]]
    jj = q[q.tgt > 0].set_index(k2).join(b0, rsuffix="_0").reset_index()
    jj["d_pct"] = jj["pct"] - jj["pct_0"]
    print("\n  marginal average of the paired delta, by ATR target (R equivalent at a 1.5N stop):")
    m = jj.groupby("tgt").agg(d_pct=("d_pct", "mean"), hit=("hit", "mean"),
                              beats=("d_pct", lambda x: float((x > 0).mean())),
                              cells=("d_pct", "size"))
    m["R_equiv"] = [round(t / 1.5, 2) for t in m.index]
    print(m.round(4).to_string())
    print(f"\n  targets beating NO TARGET: {int((jj.d_pct > 0).sum())} of {len(jj)} "
          f"(chance is 50%)")
    print(f"  paired deltas exceeding their own MDE: "
          f"{int((jj['d_pct'].abs() > jj['mde']).sum())} of {len(jj)}")


if __name__ == "__main__":
    main()
