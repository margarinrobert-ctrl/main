"""Consensus on research, a minute-of-day matched control as the GATE, then one locked read.

THE RIGHT NULL FOR A TREND SYSTEM IS THE SAME TRADE MANAGEMENT WITH A RANDOM ENTRY
(`STUDY_TURTLE.md`). The control keeps the side, the stop, the target, the trail, the four-hour
ceiling, the session, the costs and the POSITION LOCK, and replaces only the moment: each real
signal is swapped for a random bar carrying the SAME MINUTE OF DAY, so session timing is priced
in rather than credited to the rule.

Selection is fixed before anything is read: scorable on both markets, scored by the WORSE of the
two research Sharpes, and the top 1000 read as a consensus of marginal shares.
"""
from __future__ import annotations

import numpy as np
import sys, os
from numba import njit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.v59 import v59core as C                                   # noqa: E402
from research.v59.run_v59 import MK, MIN_N, prep, metrics, keepmask     # noqa: E402


@njit(cache=True)
def _ctrl(o, h, l, c, mod, atr, pool, pool_start, pool_len, modidx, nsig,
          stopm, tgtm, hold, lo_m, hi_m, side, cost, draws, seed, out, ncnt):
    """A draw samples one random bar per real signal, SORTS them, then walks them under the same
    position lock.

    The sort is the whole point. Sampled bars come out in the order of the signals they replace,
    which is not chronological, so a lock written as `skip while the last exit is ahead of me`
    rejects an arbitrary and enormous share of them -- the first version of this control kept a
    fraction of its trades and its spread was so wide that a rule earning +0.18 against a control
    median of +0.00 scored p 0.404. A control with the wrong variance cannot reject anything.
    """
    n = len(c)
    buf = np.empty(nsig, np.int64)
    for d in range(draws):
        m = 0
        for k in range(nsig):
            mi = modidx[k]
            ln = pool_len[mi]
            if ln <= 0:
                continue
            buf[m] = pool[pool_start[mi] + np.random.randint(0, ln)]
            m += 1
        picks = np.sort(buf[:m])
        last = -1
        s = 0.0
        cnt = 0
        for q in range(m):
            i = picks[q]
            if i <= last or i + 1 >= n - 1:
                continue
            e = i + 1
            ent = o[e]
            a = atr[i]
            risk = stopm * a
            if risk <= 0:
                continue
            stp = ent - risk if side == 0 else ent + risk
            tp = (ent + tgtm * risk if side == 0 else ent - tgtm * risk) if tgtm < 90.0 \
                else (1e18 if side == 0 else -1e18)
            px = c[min(e + hold - 1, n - 1)]
            xb = min(e + hold - 1, n - 1)
            peak = ent
            for j in range(e, min(e + hold, n)):
                if mod[j] >= hi_m and hi_m < 1440:
                    px = o[j]; xb = j; break
                if side == 0:
                    if l[j] <= stp:
                        px = stp; xb = j; break
                    if h[j] >= tp:
                        px = tp; xb = j; break
                    if h[j] > peak:
                        peak = h[j]
                    if peak - risk > stp:
                        stp = peak - risk
                else:
                    if h[j] >= stp:
                        px = stp; xb = j; break
                    if l[j] <= tp:
                        px = tp; xb = j; break
                    if l[j] < peak:
                        peak = l[j]
                    if peak + risk < stp:
                        stp = peak + risk
                px = c[j]; xb = j
            last = xb
            s += (((px - ent) if side == 0 else (ent - px)) - cost) / max(a, 1e-9)
            cnt += 1
        out[d] = s / cnt if cnt > 0 else np.nan
        ncnt[d] = cnt


def control(F, sig, side, g, cost, actual, sel, draws=800, seed=99):
    gm = C.geom_name(g)
    wi = C.SESS.index(gm["sess"])
    lo_m, hi_m = C.SESS_WIN[wi]
    mods = F["mod"]
    ok = sel & (mods >= lo_m) & (mods < hi_m)
    order = np.argsort(mods[ok], kind="stable")
    bars = np.flatnonzero(ok)[order]
    mm = mods[bars]
    uniq, start = np.unique(mm, return_index=True)
    length = np.diff(np.append(start, len(mm)))
    lut = {int(u): i for i, u in enumerate(uniq)}
    mi = np.array([lut.get(int(m), -1) for m in mods[sig]], np.int64)
    keep = mi >= 0
    if keep.sum() < 10:
        return np.nan, np.nan
    out = np.full(draws, np.nan)
    ncnt = np.zeros(draws, np.int64)
    np.random.seed(seed)
    _ctrl(F["o"], F["h"], F["l"], F["c"], mods, F["atr"], bars.astype(np.int64),
          start.astype(np.int64), length.astype(np.int64), mi[keep], int(keep.sum()),
          gm["stop"], gm["tgt"], int(gm["hold"]), int(lo_m), int(hi_m), side, float(cost),
          draws, seed, out, ncnt)
    v = out[np.isfinite(out)]
    if len(v) == 0:
        return np.nan, np.nan
    return float((v >= actual).mean()), float(np.median(v))


def load(mk):
    z = np.load(f"results/v59/{mk}.npz")
    r, l = {}, {}
    for m in range(len(C.MODE)):
        for s in ("long", "short", "both"):
            for f in range(C.NF):
                r[(m, s, f)] = z[f"r_{m}_{s}_{f}"]
                l[(m, s, f)] = z[f"l_{m}_{s}_{f}"]
    return r, l, int(z["nres"]), int(z["nlock"]), int(z["cut"]), int(z["nbars"])


def label(m, s, f, g):
    gm = C.geom_name(g); fn = C.filt_name(f)
    t = "none" if gm["tgt"] > 90 else f"{gm['tgt']:.1f}R"
    return (f"{C.MODE[m]:<17s} {s:<5s} stop {gm['stop']:.1f}N tgt {t:<4s} hold {gm['hold']*15//60}h "
            f"{gm['trail']:<15s} {gm['sess']:<11s} | {fn['adx']}, {fn['atr']}")


def share(vals):
    c = {}
    for v in vals:
        c[v] = c.get(v, 0) + 1
    return "  ".join(f"{k} {v/len(vals)*100:.0f}%" for k, v in sorted(c.items(), key=lambda x: -x[1]))


def main():
    D = {mk: load(mk) for mk in MK}
    keys = list(D[MK[0]][0].keys())
    sh = {mk: np.stack([metrics(D[mk][0][k], D[mk][2])["sharpe"] for k in keys]) for mk in MK}
    nn = {mk: np.stack([metrics(D[mk][0][k], D[mk][2])["n"] for k in keys]) for mk in MK}
    ok = (nn[MK[0]] >= MIN_N) & (nn[MK[1]] >= MIN_N)
    score = np.where(ok, np.minimum(np.nan_to_num(sh[MK[0]], nan=-9),
                                    np.nan_to_num(sh[MK[1]], nan=-9)), -9.0)
    flat = score.ravel()
    top = np.argsort(flat)[::-1][:1000]
    ki, gi = top // C.NG, top % C.NG
    rows = [(keys[k][0], keys[k][1], keys[k][2], int(g)) for k, g in zip(ki, gi)]

    print("=" * 104)
    print(f"TOP 1000 CONSENSUS of {len(keys)*C.NG:,} configurations   (worse of the two markets' "
          f"research Sharpe)")
    print("=" * 104)
    print("  entry mechanic ", share([C.MODE[r[0]] for r in rows]))
    print("  side           ", share([r[1] for r in rows]))
    print("  ADX            ", share([C.filt_name(r[2])["adx"] for r in rows]))
    print("  ATR regime     ", share([C.filt_name(r[2])["atr"] for r in rows]))
    print("  stop           ", share([f"{C.geom_name(r[3])['stop']:.1f}N" for r in rows]))
    print("  target         ", share(["none" if C.geom_name(r[3])['tgt'] > 90
                                      else f"{C.geom_name(r[3])['tgt']:.1f}R" for r in rows]))
    print("  max hold       ", share([f"{C.geom_name(r[3])['hold']*15//60}h" for r in rows]))
    print("  trail          ", share([C.geom_name(r[3])['trail'] for r in rows]))
    print("  session        ", share([C.geom_name(r[3])['sess'] for r in rows]))

    print("\n" + "=" * 104)
    print("MINUTE-OF-DAY MATCHED CONTROL ON RESEARCH  (800 random-entry draws, same management)")
    print("=" * 104)
    Fs = {}
    for mk in MK:
        Fs[mk] = prep(mk)
    print(f"{'#':>3} {'configuration':<86} {'mkt':<7} {'n':>5} {'ATR/tr':>8} {'ctrl':>8} {'p':>6}")
    gate = []
    for r in range(25):
        m, s, f, g = rows[r]
        worst = 0.0
        lines = []
        for mk in MK:
            F, S, nd = Fs[mk]
            mm = metrics(D[mk][0][(m, s, f)], D[mk][2])
            act = mm["atr"][g]
            cut = D[mk][4]
            sel = np.zeros(F["n"], bool); sel[:cut] = True
            ps = []
            for s2 in (["long", "short"] if s == "both" else [s]):
                sd = 0 if s2 == "long" else 1
                st = S[(m, sd)]
                km = keepmask(st, f) & sel[st["sig"]]
                if km.sum() < 10:
                    continue
                p, med = control(F, st["sig"][km], sd, g, C.COST_PTS[mk], act, sel)
                if np.isfinite(p):
                    ps.append((p, med))
            p = max(x[0] for x in ps) if ps else 1.0
            worst = max(worst, p)
            lines.append((mk, mm["n"][g], act, np.mean([x[1] for x in ps]) if ps else np.nan, p))
        for i, (mk, n, act, med, p) in enumerate(lines):
            print(f"{r+1 if i==0 else '':>3} {label(m,s,f,g) if i==0 else '':<86} {mk:<7} "
                  f"{int(n):>5d} {act:>+8.4f} {med:>+8.4f} {p:>6.3f}")
        gate.append((worst, m, s, f, g))
    surv = [x for x in gate if x[0] <= 0.05]
    print(f"\n  {len(surv)}/25 clear the matched control on BOTH markets at p <= 0.05")
    np.save("results/v59/gate.npy", np.array(gate, dtype=[("p", "f8"), ("m", "i8"),
                                                          ("s", "U5"), ("f", "i8"), ("g", "i8")]))


if __name__ == "__main__":
    main()
