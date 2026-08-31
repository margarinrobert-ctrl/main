"""ONE read of the locked block on candidates declared from the research consensus alone,
plus the marginal effect of each condition over the whole grid.

  A  CONSENSUS -- the marginal mode of every axis over the top 1000.
  B  THE SURVIVOR CLUSTER -- the configuration that recurs among the six that cleared the
     matched control on both markets.
  C  AS BRIEFED -- EMA 16/64 cross, both sides, 2N stop, 2R target, four-hour ceiling, fixed
     stop, all hours, no conditions. The baseline everything must beat.
  D  C PLUS THE CONVENTIONAL ADX FLOOR -- because the search chose the OPPOSITE sign and that
     claim has to be tested head-on rather than inferred from a ranking.
"""
from __future__ import annotations

import numpy as np
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.v59 import v59core as C                                   # noqa: E402
from research.v59.run_v59 import MK, MIN_N, prep, metrics, keepmask     # noqa: E402
from research.v59.v59judge import load, control, label                  # noqa: E402


def gi(stop, tgt, hold, trail, sess):
    si = int(np.flatnonzero(C.STOPM == stop)[0])
    ti = int(np.flatnonzero(C.TGTM == tgt)[0])
    hi = int(np.flatnonzero(C.HOLD == hold)[0])
    tr = C.TRAIL.index(trail)
    wi = C.SESS.index(sess)
    return ((((si * len(C.TGTM) + ti) * len(C.HOLD) + hi) * len(C.TRAIL) + tr)
            * len(C.SESS) + wi)


def fi(adx, atr):
    return C.ADX_MODE.index(adx) * len(C.ATR_MODE) + C.ATR_MODE.index(atr)


CAND = {
    "A consensus": (0, "long", fi("adx<=20", "atr>=1.2x"),
                    gi(3.0, 99.0, 16, "ATR trail", "09:30-16:00")),
    "B survivor ": (0, "long", fi("adx<=20", "off"),
                    gi(1.5, 99.0, 12, "ATR trail", "09:30-16:00")),
    "C as briefed": (0, "both", fi("off", "off"),
                     gi(2.0, 2.0, 16, "fixed", "all hours")),
    "D C+ADX>=25": (0, "both", fi("adx>=25", "off"),
                    gi(2.0, 2.0, 16, "fixed", "all hours")),
}


def main():
    D = {mk: load(mk) for mk in MK}
    Fs = {mk: prep(mk) for mk in MK}

    print("=" * 100)
    print("POPULATION DIAGNOSTIC -- corr(research, locked) over every scorable configuration")
    print("=" * 100)
    for mk in MK:
        r, l, nres, nlock, cut, nbars = D[mk]
        a = np.concatenate([metrics(r[k], nres)["atr"] for k in r])
        b = np.concatenate([metrics(l[k], nlock)["atr"] for k in l])
        na = np.concatenate([metrics(r[k], nres)["n"] for k in r])
        nb = np.concatenate([metrics(l[k], nlock)["n"] for k in l])
        ok = (na >= MIN_N) & (nb >= 25) & np.isfinite(a) & np.isfinite(b)
        print(f"  {mk:<7} n={int(ok.sum()):7,d}   corr {np.corrcoef(a[ok], b[ok])[0,1]:+.4f}"
              f"   research median {np.median(a[ok]):+.4f} -> locked {np.median(b[ok]):+.4f}")

    print("\n" + "=" * 100)
    print("THE SINGLE LOCKED READ   (ATR units at the signal bar, net of costs)")
    print("=" * 100)
    print(f"{'candidate':<13} {'blk':<8} {'mkt':<7} {'n':>5} {'ATR/tr':>8} {'PF':>6} {'Sharpe':>7} {'ctrl p':>7}")
    for nm, (m, s, f, g) in CAND.items():
        print("-" * 100)
        print(f"  {label(m, s, f, g)}")
        for mk in MK:
            r, l, nres, nlock, cut, nbars = D[mk]
            F, S, nd = Fs[mk]
            for bn, src, ndy in (("research", r, nres), ("locked", l, nlock)):
                mm = metrics(src[(m, s, f)], ndy)
                if mm["n"][g] < 15:
                    print(f"{nm:<13} {bn:<8} {mk:<7}   -- too few trades --")
                    continue
                sel = np.zeros(F["n"], bool)
                if bn == "research":
                    sel[:cut] = True
                else:
                    sel[cut:] = True
                ps = []
                for s2 in (["long", "short"] if s == "both" else [s]):
                    sd = 0 if s2 == "long" else 1
                    st = S[(m, sd)]
                    km = keepmask(st, f) & sel[st["sig"]]
                    if km.sum() < 10:
                        continue
                    p, _ = control(F, st["sig"][km], sd, g, C.COST_PTS[mk], mm["atr"][g], sel)
                    if np.isfinite(p):
                        ps.append(p)
                print(f"{nm:<13} {bn:<8} {mk:<7} {int(mm['n'][g]):>5d} {mm['atr'][g]:>+8.4f} "
                      f"{mm['pf'][g]:>6.3f} {mm['sharpe'][g]:>7.2f} "
                      f"{(max(ps) if ps else float('nan')):>7.3f}")

    print("\n" + "=" * 100)
    print("MARGINAL EFFECT OF EACH CONDITION over the WHOLE grid (ATR units per trade)")
    print("=" * 100)
    print(f"{'axis':<10} {'setting':<18} " +
          "".join(f"{mk[:-1]+' '+b:>15}" for mk in MK for b in ("res", "lock")))
    for axis, modes, get in (("ADX", C.ADX_MODE, lambda k, g: C.filt_name(k[2])["adx"]),
                             ("ATR", C.ATR_MODE, lambda k, g: C.filt_name(k[2])["atr"]),
                             ("mechanic", C.MODE, lambda k, g: C.MODE[k[0]]),
                             ("trail", C.TRAIL, lambda k, g: C.geom_name(g)["trail"]),
                             ("session", C.SESS, lambda k, g: C.geom_name(g)["sess"]),
                             ("max hold", ["1h", "2h", "3h", "4h"],
                              lambda k, g: f"{C.geom_name(g)['hold']*15//60}h"),
                             ("target", ["none", "1.0R", "2.0R", "3.0R"],
                              lambda k, g: "none" if C.geom_name(g)["tgt"] > 90
                              else f"{C.geom_name(g)['tgt']:.1f}R")):
        for md in modes:
            cells = []
            for mk in MK:
                r, l, nres, nlock, cut, nbars = D[mk]
                for src, ndy, mn in ((r, nres, MIN_N), (l, nlock, 25)):
                    vals = []
                    for k in src:
                        mm = metrics(src[k], ndy)
                        gsel = np.array([get(k, g) == md for g in range(C.NG)])
                        v = np.where(mm["n"] >= mn, mm["atr"], np.nan)
                        vals.append(v[gsel])
                    cells.append(np.nanmean(np.concatenate(vals)))
            print(f"{axis:<10} {md:<18} " + "".join(f"{c:>+15.4f}" for c in cells))


if __name__ == "__main__":
    main()
