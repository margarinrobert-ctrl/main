"""The nulls, and one read of the locked block."""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ib25_core as M  # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 240)
POST = dict(retr=0.25, stop_frac=0.50, slope_win=20, slope_thr=0.0, max_cross=99)
BEST = dict(retr=0.50, stop_frac=0.75, slope_win=60, slope_thr=0.0, max_cross=99)


def line(t):
    print("\n" + "=" * 124)
    print(t)
    print("=" * 124)


def blk(t, b):
    return t[t["block"] == b] if len(t) else t


if __name__ == "__main__":
    D = M.build("NQ")
    rng = np.random.default_rng(5)

    line("G. THE MATCHED CONTROL -- same sessions, same side, same barriers, random entry MINUTE")
    print("  The rule's own trades, re-entered at a random minute in the window the rule was")
    print("  allowed to trade (10:21 to the cutoff), keeping the side, the target, the stop and")
    print("  the flatten. Only the entry TIMESTAMP differs, so this prices the LIMIT MECHANIC and")
    print("  the session selection and asks what the fib level itself adds. 1,000 draws.")
    print("  NOTE: the first build of this control had the target and stop signs swapped, so every")
    print("  control trade exited instantly in profit -- median +0.1513 with a 5-95% band of ZERO")
    print("  width. A null with no spread is broken; diagnose a control by its spread, not its")
    print("  median (STUDY_V59 caught the same class of error from the other direction).")
    print(f"\n  {'variant':26s}{'block':10s}{'n':>6s}{'observed':>11s}{'control med':>13s}"
          f"{'5-95%':>24s}{'p':>8s}")
    for nm, cfg in (("as posted", POST), ("retr 0.50 / stop 0.75", BEST)):
        t = M.run(D, **cfg)
        for b in ("research",):
            tt = blk(t, b)
            if len(tt) < 20:
                continue
            obs = tt["pct"].mean()
            # rebuild the control by re-running with the limit level replaced by a market entry
            # at a random eligible minute -- same barriers, same session set
            draws = np.zeros(1000)
            sess_set = set(tt["sess"].tolist())
            st, en, skey = M.sessions(D)
            keep = np.array([s in sess_set for s in skey])
            st_k, en_k = st[keep], en[keep]
            mod, o, h, l, c = D["mod"], D["o"], D["h"], D["l"], D["c"]
            side = dict(zip(tt["sess"], tt["side"]))
            rngsz = dict(zip(tt["sess"], tt["rng"]))
            for d in range(1000):
                vals = []
                for a, bq, sk in zip(st_k, en_k, skey[keep]):
                    w = np.flatnonzero((mod[a:bq + 1] >= M.FIRST_ENTRY)
                                       & (mod[a:bq + 1] < M.CUTOFF)) + a
                    if len(w) == 0:
                        continue
                    i = int(rng.choice(w))
                    s = side[sk]
                    rg = rngsz[sk]
                    px = o[min(i + 1, bq)] + s * D["tick"]
                    # mirror the core walk: for a SHORT the target is BELOW and the stop ABOVE
                    tgt = px + s * cfg["retr"] * rg
                    stp = px - s * (cfg["stop_frac"] - cfg["retr"]) * rg
                    out = np.nan
                    for j in range(i + 1, bq + 1):
                        if (s < 0 and h[j] >= stp) or (s > 0 and l[j] <= stp):
                            out = stp - s * D["tick"]; break
                        if (s < 0 and l[j] <= tgt) or (s > 0 and h[j] >= tgt):
                            out = tgt - s * D["tick"]; break
                        if mod[j] >= M.FLAT_M:
                            out = c[j] - s * D["tick"]; break
                    if not np.isfinite(out):
                        out = c[bq] - s * D["tick"]
                    vals.append(100.0 * (s * (out - px) - 2 * D["cost"]) / px)
                draws[d] = np.mean(vals) if vals else 0.0
            p = float((draws >= obs).mean())
            print(f"  {nm:26s}{b:10s}{len(tt):>6d}{obs:>11.4f}{np.median(draws):>13.4f}"
                  f"   [{np.quantile(draws, .05):+10.4f}, {np.quantile(draws, .95):+9.4f}]"
                  f"{p:>8.3f}")

    line("H. THE ONE LOCKED READ -- two declared configurations, multiplicity stated")
    print("  About 40 research cells were scored above (6 retracement rungs, 5 stops, 16 filter")
    print("  cells, 8 ablations). TWO configurations are read on the locked block: the rule")
    print("  exactly as posted, and the best research cell (retr 0.50 / stop 0.75 / 60-min slope).")
    print(f"\n  {'variant':26s}{'block':10s}{'n':>6s}{'% / trade':>12s}{'total %':>10s}"
          f"{'PF':>8s}{'win %':>8s}{'break-even':>12s}{'max DD %':>10s}")
    for nm, cfg in (("as posted", POST), ("retr 0.50 / stop 0.75", BEST)):
        t = M.run(D, **cfg)
        rr = cfg["retr"] / (cfg["stop_frac"] - cfg["retr"])
        for b in ("research", "locked"):
            s = M.stats(blk(t, b))
            print(f"  {nm:26s}{b:10s}{s['n']:>6d}{s['pct']:>12.4f}{s['tot']:>10.2f}"
                  f"{s['pf']:>8.3f}{s['win']:>8.1f}{100/(1+rr):>12.1f}{s['dd']:>10.2f}")

    line("I. THE BOOTSTRAP")
    for nm, cfg in (("as posted", POST), ("retr 0.50 / stop 0.75", BEST)):
        t = M.run(D, **cfg)
        for b in ("research", "locked"):
            v = blk(t, b)["pct"].to_numpy()
            if len(v) < 20:
                continue
            bs = np.array([rng.choice(v, len(v), replace=True).mean() for _ in range(5000)])
            print(f"  {nm:26s}{b:10s} n {len(v):4d}  mean {v.mean():+.4f}  "
                  f"95% CI [{np.quantile(bs, .025):+.4f}, {np.quantile(bs, .975):+.4f}]  "
                  f"P(mean<=0) {(bs <= 0).mean():.3f}")
