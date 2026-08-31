"""The 243,000-configuration EMA 16/64 sweep, on the RESEARCH block only.

Nothing here reads the locked block. `v59judge.py` does that once.

Trades are scored in POINTS divided by the ATR AT THE SIGNAL BAR, because the stop is a swept
ATR multiple and ranking in R would pay a configuration for tightening its own denominator.
Profit factor is in points. Sharpe is over every trading day in the block, zero-filled.
"""
from __future__ import annotations

import numpy as np
import sys, os, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.v59 import v59core as C                                   # noqa: E402

SPLIT = 0.65
MK = ["US30L", "US100L"]
MIN_N = 50


def prep(mk, frame=None, cost=None):
    F = C.build(mk, frame)
    cost = C.COST_PTS[mk] if cost is None else cost
    days = np.unique(F["day"])
    dmap = {d: i for i, d in enumerate(days)}
    S = {}
    for m in range(len(C.MODE)):
        for sd in (0, 1):
            sig = C.signals(F, m, sd)
            pts, xb = C.outcomes(F, sig, sd, cost)
            a = F["atr"][sig] if len(sig) else np.zeros(0)
            S[(m, sd)] = dict(sig=sig, pts=pts / np.maximum(a, 1e-9)[:, None], ptsraw=pts, xb=xb,
                              day=np.array([dmap[d] for d in F["day"][sig]], np.int64),
                              adx=F["adx"][sig], atr=F["atr_ratio"][sig])
    return F, S, len(days)


def keepmask(s, f):
    fn = C.filt_name(f)
    k = np.ones(len(s["sig"]), bool)
    a, r = s["adx"], s["atr"]
    if fn["adx"] == "adx>=15": k &= a >= 15
    elif fn["adx"] == "adx>=20": k &= a >= 20
    elif fn["adx"] == "adx>=25": k &= a >= 25
    elif fn["adx"] == "adx<=20": k &= a <= 20
    if fn["atr"] == "atr>=0.8x": k &= r >= 0.8
    elif fn["atr"] == "atr>=1.2x": k &= r >= 1.2
    elif fn["atr"] == "atr<=1.2x": k &= r <= 1.2
    elif fn["atr"] == "atr<=0.8x": k &= r <= 0.8
    return k & np.isfinite(a) & np.isfinite(r)


def aggregate(S, sel, ndays):
    """(mode, sidemode, filter) -> (NG, 5) sums. `sel` is a boolean mask over bar indices."""
    out = {}
    for m in range(len(C.MODE)):
        parts = {}
        for sd in (0, 1):
            s = S[(m, sd)]
            inb = sel[s["sig"]] if len(s["sig"]) else np.zeros(0, bool)
            parts[sd] = (s, inb)
        for f in range(C.NF):
            km = {sd: keepmask(parts[sd][0], f) & parts[sd][1] for sd in (0, 1)}
            for name, sd in (("long", 0), ("short", 1)):
                s = parts[sd][0]
                o = np.zeros((C.NG, 5))
                if len(s["sig"]):
                    C._lock(s["pts"], s["xb"], s["sig"], km[sd], s["day"], ndays, o)
                out[(m, name, f)] = o
            a, b = parts[0][0], parts[1][0]
            o = np.zeros((C.NG, 5))
            if len(a["sig"]) and len(b["sig"]):
                C._lock2(a["pts"], a["xb"], a["sig"], km[0], a["day"],
                         b["pts"], b["xb"], b["sig"], km[1], b["day"], o)
            out[(m, "both", f)] = o
    return out


def metrics(o, ndays):
    n = o[:, 1]
    mean = o[:, 0] / ndays
    var = np.maximum(o[:, 4] / ndays - mean ** 2, 1e-12)
    return dict(n=n, atr=np.where(n > 0, o[:, 0] / np.maximum(n, 1), np.nan),
                pf=np.where(o[:, 3] < 0, o[:, 2] / np.maximum(-o[:, 3], 1e-9), np.nan),
                sharpe=mean / np.sqrt(var) * np.sqrt(252.0))


def main():
    os.makedirs("results/v59", exist_ok=True)
    for mk in MK:
        t0 = time.time()
        F, S, ndays = prep(mk)
        cut = int(F["n"] * SPLIT)
        res = np.zeros(F["n"], bool); res[:cut] = True
        lock = ~res
        nres = len(np.unique(F["day"][:cut]))
        nlock = len(np.unique(F["day"][cut:]))
        ar = aggregate(S, res, nres)
        al = aggregate(S, lock, nlock)
        np.savez_compressed(f"results/v59/{mk}.npz",
                            **{f"r_{m}_{s}_{f}": ar[(m, s, f)] for (m, s, f) in ar},
                            **{f"l_{m}_{s}_{f}": al[(m, s, f)] for (m, s, f) in al},
                            nres=nres, nlock=nlock, cut=cut, nbars=F["n"])
        tot = prof = 0
        for k, o in ar.items():
            mm = metrics(o, nres)
            ok = mm["n"] >= MIN_N
            tot += int(ok.sum()); prof += int(((mm["atr"] > 0) & ok).sum())
        nsig = {m: sum(len(S[(m, sd)]["sig"]) for sd in (0, 1)) for m in range(len(C.MODE))}
        print(f"\n=== {mk}  {F['n']:,} bars, research {nres} sessions / locked {nlock}   "
              f"({time.time()-t0:.1f}s)")
        print(f"    raw signals by entry mechanic: " +
              ", ".join(f"{C.MODE[m]} {nsig[m]:,}" for m in nsig))
        print(f"    GRID SHAPE: {prof:,}/{tot:,} = {prof/max(tot,1)*100:.1f}% of scorable "
              f"configurations are profitable on research")
        for m in range(len(C.MODE)):
            v = np.concatenate([metrics(ar[(m, s, f)], nres)["atr"][
                metrics(ar[(m, s, f)], nres)["n"] >= MIN_N] for s in ("long", "short", "both")
                for f in range(C.NF)])
            print(f"      {C.MODE[m]:<18} median {np.nanmedian(v):+.4f} ATR/trade, "
                  f"{np.nanmean(v > 0)*100:.1f}% profitable")


if __name__ == "__main__":
    main()
