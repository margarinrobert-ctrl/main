"""The two readings with a positive marginal, against a MATCHED RANDOM ENTRY on both blocks.

The control keeps the side mix and runs the identical stop, target and opposite-reading exit --
only the entry bar moves. Sorted, because an unsorted draw makes the position lock reject an
arbitrary share (STUDY_V59).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from linreg import lrcore as L  # noqa: E402

RNG = np.random.default_rng(8080)
ND = 400
MKTS = ("US30L", "US100L", "NQ")
CELLS = [("X slope cross", 50), ("X slope cross", 100), ("B channel break", 50)]
TF, STOP, TP, K, KAT = 60, 2.5, 0.0, 2.0, False


def day_boot(r, ts, nb=1500):
    d = pd.Series(r, index=pd.DatetimeIndex(ts).normalize())
    grp = [v.to_numpy() for _, v in d.groupby(level=0)]
    out = np.empty(nb)
    for i in range(nb):
        pick = RNG.integers(0, len(grp), len(grp))
        out[i] = np.nanmean(np.concatenate([grp[j] for j in pick]))
    return out


def main():
    print(f"{'reading':<18}{'n':>4}{'mkt':<8}{'blk':<10}{'trades':>7}{'%/trade':>9}"
          f"{'PF':>7}{'total':>9}{'ctl':>9}{'p':>7}{'P(<=0)':>8}")
    for nm, ln in CELLS:
        for mk in MKTS:
            f = L.load(mk, TF)
            s = np.unique(f.index.normalize())
            cut = pd.Timestamp(s[int(0.75 * len(s))])
            o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
            at = f["atr"].to_numpy(); mod = f["mod"].to_numpy().astype(np.int64)
            cost = L.COST[mk]
            rd, _, _, _ = L.readings(f, ln, K, KAT)
            eu, ed, xu, xd = rd[nm]
            eb, r, sd, hl, cf = L._walk(o, h, l, c, at, mod, eu, ed, xu, xd, 0,
                                        STOP, TP, 0, -1, -1, cost)
            ts = f.index[eb]
            elig = np.flatnonzero(np.isfinite(at) & (at > 0))
            elig = elig[(elig > ln + 5) & (elig < len(c) - 5)]
            for bl, sel, gm in (("research", np.asarray(ts < cut), f.index < cut),
                                ("HOLDOUT", np.asarray(ts >= cut), f.index >= cut)):
                rr = r[sel]
                if len(rr) < 30:
                    print(f"{nm:<18}{ln:>4}{mk:<8}{bl:<10}{len(rr):>7}  too few")
                    continue
                e = elig[np.isin(elig, np.flatnonzero(gm))]
                share = float((sd[sel] > 0).mean())
                ctl = np.empty(ND)
                for d in range(ND):
                    pick = np.sort(RNG.choice(e, size=min(len(rr), len(e)), replace=False))
                    sdr = np.where(RNG.random(len(pick)) < share, 1, -1)
                    q = L._walk_at(o, h, l, c, at, xu, xd, pick.astype(np.int64),
                                   sdr.astype(np.int64), STOP, TP, 0, cost)
                    ctl[d] = np.nanmean(q)
                mu = float(rr.mean())
                bb = day_boot(rr, ts[sel])
                print(f"{nm:<18}{ln:>4}{mk:<8}{bl:<10}{len(rr):>7}{mu:>9.4f}{L.pf(rr):>7.3f}"
                      f"{rr.sum():>9.2f}{np.nanmedian(ctl):>9.4f}"
                      f"{float(np.mean(ctl >= mu)):>7.3f}{float((bb <= 0).mean()):>8.3f}")
        print()


if __name__ == "__main__":
    main()
