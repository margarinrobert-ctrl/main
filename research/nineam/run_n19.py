"""THE CORRECTION APPLIED BACKWARDS, to the two published ladders that used the same ratchet.

`run_n7` measured the auto-breakeven ladder and `run_n8` the secured-points offset, both through
`na_core._walk`, which fills a stop AT ITS LEVEL. Where the secured level sits near the arming
distance the moved stop can be written ABOVE the market and filled there, so both ladders carry
the artifact and the published numbers have to be re-read rather than cited.

Run under `fix = 0` (as published) beside `fix = 1` (a stop fills at the WORSE of its level and
the bar's open), over the same declared ladder, the same two geometries and the same three blocks.
"""
from __future__ import annotations

import os
import sys
import time
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
pd.set_option("display.width", 210)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import na_core as N   # noqa: E402
import na_opt as O    # noqa: E402

BE = (0.0, 25.0, 50.0, 75.0, 100.0, 150.0)
OFF = (0.0, 5.0, 10.0, 25.0)
GEO = {"1.5N / no target": dict(stop_mode="atr", stop_atr=1.5, tgt_mode="none"),
       "100pt / 100pt": dict(stop_mode="points", stop_pts=100.0,
                             tgt_mode="points", tgt_pts=100.0)}


def main():
    t0 = time.time()
    print(__doc__)
    ctxs = {}
    for fx in (0, 1):
        ctxs[fx] = [("US30L", O.Ctx("US30L", fix=fx)), ("US30I", O.Ctx("US30I", fix=fx))]
    rows = []
    for gname, g in GEO.items():
        for side in ("long", "both"):
            for be in BE:
                for off in OFF:
                    if be == 0.0 and off != 0.0:
                        continue                      # the ratchet is off; the offset is inert
                    for i, (nm, _) in enumerate(ctxs[0]):
                        for b in ctxs[0][i][1].blocks:
                            p = dict(range_end=570, side=side, buf_atr=0.0, atr_n=14,
                                     flat_m=960, be_pts=be, be_off=off, ma_mode="off",
                                     x_mode="off", conf="off", **g)
                            r = {}
                            for fx in (0, 1):
                                s, tr = O.score(ctxs[fx][i][1], p, b, min_tpy=0.0)
                                r[fx] = (s["per"], s["n"],
                                         float(tr["thru"].mean()) if tr is not None
                                         and len(tr) else np.nan)
                            rows.append(dict(geom=gname, side=side, be_pts=be, be_off=off,
                                             feed=nm, block=b,
                                             per_pub=r[0][0], per_fix=r[1][0],
                                             delta=r[1][0] - r[0][0], n=r[0][1],
                                             through=r[1][2]))
    D = pd.DataFrame(rows)
    D.to_csv(os.path.join(HERE, "n19_ratchet.csv"), index=False)

    print("\n" + "=" * 118)
    print("THE SECURED-POINTS LADDER, PAIRED AGAINST ITS OWN `be_pts = 0` TWIN, both engines")
    print("=" * 118)
    base = D[D.be_pts == 0].set_index(["geom", "side", "feed", "block"])
    D = D.join(base[["per_pub", "per_fix"]].rename(
        columns={"per_pub": "b_pub", "per_fix": "b_fix"}),
        on=["geom", "side", "feed", "block"])
    D["d_pub"] = D["per_pub"] - D["b_pub"]
    D["d_fix"] = D["per_fix"] - D["b_fix"]
    L = D[D.be_pts > 0]
    print(f"\n{'be_pts':>7s}{'be_off':>7s}{'cells':>7s}"
          f"{'paired delta AS PUBLISHED':>27s}{'CORRECTED':>12s}{'artifact':>10s}"
          f"{'beats off pub':>15s}{'corr':>7s}{'through':>9s}")
    for be in BE[1:]:
        for off in OFF:
            k = L[(L.be_pts == be) & (L.be_off == off)]
            if not len(k):
                continue
            print(f"{be:>7.0f}{off:>7.0f}{len(k):>7d}{k.d_pub.mean():>+27.4f}"
                  f"{k.d_fix.mean():>+12.4f}{(k.d_fix - k.d_pub).mean():>+10.4f}"
                  f"{int((k.d_pub > 0).sum()):>10d}/{len(k):<4d}"
                  f"{int((k.d_fix > 0).sum()):>3d}/{len(k):<3d}{k.through.mean():>9.4f}")
    print("\nMARGINAL OVER THE OFFSET (all be_pts pooled), which is the axis `run_n8` published:")
    print(f"{'be_off':>7s}{'cells':>7s}{'as published':>15s}{'corrected':>12s}"
          f"{'artifact':>10s}{'beats off pub':>15s}{'corrected':>12s}")
    for off in OFF:
        k = L[L.be_off == off]
        print(f"{off:>7.0f}{len(k):>7d}{k.d_pub.mean():>+15.4f}{k.d_fix.mean():>+12.4f}"
              f"{(k.d_fix - k.d_pub).mean():>+10.4f}"
              f"{int((k.d_pub > 0).sum()):>10d}/{len(k):<4d}"
              f"{int((k.d_fix > 0).sum()):>8d}/{len(k):<4d}")
    print(f"\n   As published the offset ladder RISES with the secured distance -- the finding")
    print(f"   recorded as 'a large secured distance stops being a breakeven and becomes a small")
    print(f"   take profit'. Corrected, the rise is the ARTIFACT and not a take profit: the")
    print(f"   biggest offset carries the biggest correction, because that is where the moved")
    print(f"   stop is most often written through the market.")
    print(f"\n[run_n19 done in {time.time() - t0:.0f}s]")


if __name__ == "__main__":
    main()
