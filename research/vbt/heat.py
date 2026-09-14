"""How much heat does a winning trade take before it pays? Excursions in POINTS, not R.

THE QUESTION THIS ANSWERS, and it is the one that decides a stop and a points-target:
  * for trades that eventually reach the target, how far AGAINST them did price go first?
    That is the heat you must be willing to sit through. A stop tighter than it converts
    winners into losers.
  * across ALL signals, what is the average adverse excursion? That is what the account
    actually feels every time a signal fires, whatever the outcome.

Reported in price points AND as a fraction of the trade's own risk, because points do not
transfer between a 44,000 index and a 2,000 metal but the ratio does.

THE TRAP, stated because this measurement is unusually good at inviting it: MAE/MFE make the
sample-optimal stop and target obvious, and choosing them that way is curve fitting with extra
steps -- the optimum is a property of the realised path. These numbers DESCRIBE and generate
hypotheses; any parameter they suggest is a new hypothesis needing its own out-of-sample block.
"""
from __future__ import annotations

import sys
import numpy as np

sys.path.insert(0, "research"); sys.path.insert(0, "research/turtle2"); sys.path.insert(0, "research/vbt")
import ytdata, run_intraday as RI

STOP_EXIT, TARGET_EXIT, FLAT_EXIT = 1, 2, 3


def collect(cfg, chart=15, block="oos", ws=570, we=720):
    mkts = [m for m in ytdata.BASE if ytdata.BASE[m] <= chart]
    out = {}
    for m in mkts:
        P = RI.prep(m, chart)
        if P is None:
            continue
        r = RI.go(P, m, chart, cfg, block, ws=ws, we=we)
        if len(r[0]):
            out[m] = r
    return out


def report(res, label=""):
    R = np.concatenate([v[0] for v in res.values()])
    WHY = np.concatenate([v[2] for v in res.values()])
    MAE = np.concatenate([v[5] for v in res.values()])
    MFE = np.concatenate([v[6] for v in res.values()])
    RSK = np.concatenate([v[7] for v in res.values()])
    ok = RSK > 0
    R, WHY, MAE, MFE, RSK = R[ok], WHY[ok], MAE[ok], MFE[ok], RSK[ok]
    print(f"\n{label}   n={len(R)}")
    print(f"  {'group':<28}{'n':>6}{'MAE pts':>10}{'MAE/R':>8}{'p90 MAE/R':>11}"
          f"{'MFE pts':>10}{'MFE/R':>8}")
    for name, m in (("ALL signals", np.ones(len(R), bool)),
                    ("reached the TARGET", WHY == TARGET_EXIT),
                    ("stopped out", WHY == STOP_EXIT),
                    ("flattened on the clock", WHY == FLAT_EXIT)):
        if m.sum() < 5:
            continue
        print(f"  {name:<28}{m.sum():>6}{np.mean(MAE[m]):>10.1f}"
              f"{np.mean(MAE[m]/RSK[m]):>8.2f}{np.percentile(MAE[m]/RSK[m], 90):>11.2f}"
              f"{np.mean(MFE[m]):>10.1f}{np.mean(MFE[m]/RSK[m]):>8.2f}")
    return R, WHY, MAE, MFE, RSK


def per_market(res):
    print(f"\n  {'market':<10}{'n':>6}{'risk pts':>11}{'MAE pts (all)':>15}"
          f"{'MAE pts (winners)':>19}{'MFE pts (all)':>15}")
    for m, v in res.items():
        R, WHY, MAE, MFE, RSK = v[0], v[2], v[5], v[6], v[7]
        ok = RSK > 0
        w = ok & (WHY == TARGET_EXIT)
        print(f"  {m:<10}{ok.sum():>6}{np.mean(RSK[ok]):>11.1f}{np.mean(MAE[ok]):>15.1f}"
              f"{(np.mean(MAE[w]) if w.sum() else float('nan')):>19.1f}"
              f"{np.mean(MFE[ok]):>15.1f}")


if __name__ == "__main__":
    CFG = (30, (0, 0.0, 20), 5.0, 20, 1.0, (True, False))
    print("INTRADAY 09:30-12:00 New York, 15m, long only, 30-bar entry, 20-bar stop, 5R target")
    for blk in ("is", "oos"):
        res = collect(CFG, block=blk)
        report(res, "IN-SAMPLE" if blk == "is" else "OUT-OF-SAMPLE")
        if blk == "oos":
            per_market(res)
