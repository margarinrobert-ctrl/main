"""A slow, obvious reference walker, asserted trade-for-trade against sim._walk.

The fast path is a numba state machine with a lazily-advanced bar cursor and a no-overlap lock;
those are exactly the places an off-by-one hides. This reimplements the same rule in plain Python
the dumbest way possible and requires the two to agree on every field of every trade.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import bars as B, sim


def reference(b, atr, r0, r1, arm, last, flat, stop_k, tgt_k, tgt_mode, side="both", buf=0.0):
    hi, lo, ready = sim.levels(b, r0, r1)
    n = b["n"]; mod = b["mod"]; si = b["si"]
    out = []
    tookU = tookD = False; cur = -1; busy = -1
    for i in range(n - 1):
        if si[i] != cur:
            cur = si[i]; tookU = tookD = False
        if not ready[i] or mod[i] < max(r1, arm) or mod[i] >= last:
            continue
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        up = hi[i] + buf * atr[i]; dn = lo[i] - buf * atr[i]
        u = b["h"][i] >= up; d = b["l"][i] <= dn
        if side == "long": d = False
        if side == "short": u = False
        want = 0
        if u and not tookU: want = 1
        elif d and not tookD: want = -1
        if u: tookU = True
        if d: tookD = True
        if want == 0 or i < busy: continue
        j = i + 1
        fill = b["t30o"][b["s0"][j]]
        sp = stop_k * atr[i]
        tg = 0.0
        if tgt_mode == "atr": tg = tgt_k * atr[i]
        elif tgt_mode == "r": tg = tgt_k * sp
        elif tgt_mode == "pts": tg = tgt_k
        stop_px = fill - sp * want
        tgt_px = fill + tg * want if tg > 0 else None
        p = b["s0"][j]; res = None; px = None
        while p < b["s1"][n - 1]:
            # which aggregated bar covers 30s index p?
            bar = int(np.searchsorted(b["s0"], p, "right") - 1)
            if si[bar] != si[i]: res, px = B.FLAT, b["t30o"][p]; break
            if flat > 0 and b["t30mod"][p] >= flat: res, px = B.FLAT, b["t30o"][p]; break
            hh, ll = b["t30h"][p], b["t30l"][p]
            hs = ll <= stop_px if want == 1 else hh >= stop_px
            ht = False
            if tgt_px is not None: ht = hh >= tgt_px if want == 1 else ll <= tgt_px
            if hs: res, px = B.STOP, stop_px; break
            if ht: res, px = B.TARGET, tgt_px; break
            p += 1
        if res is None: res, px = B.FLAT, b["t30o"][b["s1"][n - 1] - 1]
        bar = int(np.searchsorted(b["s0"], p, "right") - 1)
        out.append((i, bar, want, res, round(float((px - fill) * want), 9)))
        busy = bar + 1
    return out


if __name__ == "__main__":
    cases = [
        dict(tf=15, r0=540, r1=555, arm=570, last=960, flat=960, stop_k=1.5, tgt_k=0.0, tgt_mode="none"),
        dict(tf=5,  r0=570, r1=585, arm=585, last=900, flat=960, stop_k=1.0, tgt_k=2.0, tgt_mode="r"),
        dict(tf=1,  r0=570, r1=600, arm=600, last=840, flat=960, stop_k=2.0, tgt_k=3.0, tgt_mode="atr"),
        dict(tf=3,  r0=570, r1=585, arm=585, last=960, flat=0,   stop_k=1.5, tgt_k=0.0, tgt_mode="none"),
        dict(tf=30, r0=540, r1=570, arm=570, last=960, flat=960, stop_k=2.5, tgt_k=1.0, tgt_mode="r"),
    ]
    bad = 0
    for cs in cases:
        tf = cs.pop("tf")
        b = B.bars(tf); a = B.atr(b, 14)
        ref = reference(b, a, **cs)
        r = sim.run(b, a, stop_mode="atr", **cs)
        got = list(zip(r["eb"].tolist(), r["xb"].tolist(), r["side"].tolist(),
                       r["why"].tolist(), [round(float(x), 9) for x in r["gross"]]))
        ok = got == ref
        print(f"tf={tf:>2}m {cs['r0']}-{cs['r1']} stop{cs['stop_k']} tgt{cs['tgt_k']}{cs['tgt_mode']:>5}"
              f"  ref={len(ref):>4} fast={len(got):>4}  {'OK' if ok else 'MISMATCH'}")
        if not ok:
            bad += 1
            for x, y in zip(got, ref):
                if x != y: print("   first diff  fast", x, " ref", y); break
    print("\nPARITY:", "all cases agree trade for trade" if not bad else f"{bad} MISMATCHES")
    sys.exit(1 if bad else 0)
