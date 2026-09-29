"""V60 part two: consensus, the matched control as a GATE, ONE locked read, and Monte Carlo.

The order is fixed and is the branch's, not a preference:
  * rank on RESEARCH only, by the WORSE of the three markets' Sharpe, so no configuration can be
    bought by one index;
  * read the top 1000 as a CONSENSUS of marginal shares, never by its first row, which is the
    maximum of ~140,000 draws per market;
  * put the top candidates through a MINUTE-OF-DAY MATCHED CONTROL -- the same exits, stop,
    target, costs and position lock with a RANDOM entry bar. `STUDY_TURTLE.md`: the right null
    for a trend system is the same trade management with a random entry, and on this branch that
    null has killed five separate breakout triggers;
  * then read the locked block ONCE;
  * then Monte Carlo, bootstrapping WITH REPLACEMENT for the edge and PERMUTING for the drawdown,
    because permuting cannot change the endpoint and reporting one from it is meaningless.
"""
from __future__ import annotations

import os
import pickle
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "v38"))
sys.path.insert(0, os.path.join(HERE, "..", "v39"))

import v60core as V             # noqa: E402
import v38grid as G             # noqa: E402
import v39mc as MC              # noqa: E402
from run_v60 import MARKETS      # noqa: E402
from v60judge import load, axis_index, MIN_N       # noqa: E402


def label(key, geom):
    md, a, b, w, e, g, an, ar = key
    x, sn, tp = geom
    ema = "no EMA" if md == "off" else (f"{a}/{b} state" if md == "state"
                                        else f"{a}/{b} cross win {w}")
    return (f"{ema:<18} don {e}/{x} stop {sn}N tp {'none' if tp == 0 else f'{tp}R'} "
            f"gate {g:<9} aroon {ar}{'' if ar == 'off' else f'({an})'}")


def share(vals):
    c = {}
    for v in vals:
        c[v] = c.get(v, 0) + 1
    n = len(vals)
    return "  ".join(f"{k} {v / n * 100:.0f}%" for k, v in sorted(c.items(), key=lambda t: -t[1]))


def main():
    D = {mk: load(mk) for mk in MARKETS}
    keys, geoms = D[MARKETS[0]][1], D[MARKETS[0]][2]
    sig_ax, geo_ax = axis_index(keys, geoms)

    ok = np.ones_like(D[MARKETS[0]][0]["n"][:, :, 0], bool)
    sh = []
    for mk in MARKETS:
        M = D[mk][0]
        ok &= M["n"][:, :, 0] >= MIN_N
        sh.append(np.nan_to_num(M["sharpe"][:, :, 0], nan=-9.0))
    score = np.where(ok, np.minimum.reduce(sh), -9.0)

    print("=" * 100)
    print("3. RANKING AND CONSENSUS -- scored by the WORSE of three markets' research Sharpe")
    print("=" * 100)
    print(f"  scorable on all three markets: {int(ok.sum()):,} of {ok.size:,}")
    flat = score.ravel()
    top = np.argsort(flat)[::-1][:1000]
    si, gi = top // len(geoms), top % len(geoms)
    print("  entry mechanic ", share([keys[i][0] for i in si]))
    print("  confirm window ", share([str(keys[i][3]) for i in si]))
    print("  donchian entry ", share([str(keys[i][4]) for i in si]))
    print("  regime gate    ", share([keys[i][5] for i in si]))
    print("  AROON          ", share([keys[i][7] for i in si]))
    print("  exit channel   ", share([str(geoms[j][0]) for j in gi]))
    print("  stop           ", share([f"{geoms[j][1]}N" for j in gi]))
    print("  take profit    ", share(["none" if geoms[j][2] == 0 else f"{geoms[j][2]}R"
                                      for j in gi]))

    print("\n" + "=" * 100)
    print("4. MATCHED CONTROL ON RESEARCH -- same exits, stop, target, costs, lock; RANDOM entry")
    print("=" * 100)
    Pm = {mk: V.prep(60, mk) for mk in MARKETS}
    ten = {}
    print(f"{'#':>3} {'configuration':<74} {'mkt':<7} {'n':>5} {'$/tr':>8} {'ctrl':>8} {'p':>6}")
    gate = []
    for r in range(12):
        s, g = int(si[r]), int(gi[r])
        key, geom = keys[s], geoms[g]
        worst = 0.0
        for mk in MARKETS:
            P = Pm[mk]
            cut = int(P["n"] * V.SPLIT)
            tk = (mk, geom)
            if tk not in ten:
                ten[tk] = G.tensor_stop(P, geom[0], geom[1], geom[2], 0)
            xb, pnl, _ = ten[tk]
            m = V.signal_mask(P, key)
            sig = np.flatnonzero(m[:cut]).astype(np.int64)
            p_, s_ = MC.gather(P, xb, pnl, sig)
            if len(p_) < MIN_N:
                continue
            pool = np.flatnonzero(np.isfinite(P["atr"]) & (P["atr"] > 0))
            pool = pool[pool < cut]
            ctrl = MC.control(P, xb, pnl, pool, len(p_), draws=400, seed=29 + r)
            pv = float((ctrl >= p_.mean()).mean())
            worst = max(worst, pv)
            print(f"{r + 1 if mk == MARKETS[0] else '':>3} "
                  f"{label(key, geom) if mk == MARKETS[0] else '':<74} {mk:<7} {len(p_):>5d} "
                  f"{p_.mean():>+8.2f} {np.median(ctrl):>+8.2f} {pv:>6.3f}")
        gate.append((worst, s, g))
    surv = [x for x in gate if x[0] <= 0.05]
    print(f"\n  {len(surv)}/12 clear the matched control on ALL THREE markets at p <= 0.05.")

    print("\n" + "=" * 100)
    print("5. THE SINGLE LOCKED READ, and the population diagnostic")
    print("=" * 100)
    for mk in MARKETS:
        M = D[mk][0]
        a = M["usd"][:, :, 0]
        b = M["usd"][:, :, 1]
        m = ok & (M["n"][:, :, 1] >= MIN_N) & np.isfinite(a) & np.isfinite(b)
        print(f"  {mk:<7} corr(research, locked) over {int(m.sum()):,} configurations "
              f"{np.corrcoef(a[m], b[m])[0, 1]:+.4f}    research median {np.median(a[m]):+.2f} "
              f"-> locked {np.median(b[m]):+.2f}")
    print()
    print(f"{'#':>3} {'mkt':<7} {'res n':>6} {'res $/tr':>9} {'res PF':>7} "
          f"{'lock n':>7} {'lock $/tr':>10} {'lock PF':>8}")
    for r in range(min(6, len(gate))):
        _w, s, g = gate[r]
        for mk in MARKETS:
            M = D[mk][0]
            print(f"{r + 1 if mk == MARKETS[0] else '':>3} {mk:<7} "
                  f"{int(M['n'][s, g, 0]):>6d} {M['usd'][s, g, 0]:>+9.2f} "
                  f"{M['pf'][s, g, 0]:>7.3f} {int(M['n'][s, g, 1]):>7d} "
                  f"{M['usd'][s, g, 1]:>+10.2f} {M['pf'][s, g, 1]:>8.3f}")
        print("   " + "-" * 60)

    print("=" * 100)
    print("6. MONTE CARLO on the leading configuration -- bootstrap for edge, permute for drawdown")
    print("=" * 100)
    _w, s, g = gate[0]
    key, geom = keys[s], geoms[g]
    print(f"  {label(key, geom)}")
    for mk in MARKETS:
        P = Pm[mk]
        xb, pnl, _ = ten[(mk, geom)]
        m = V.signal_mask(P, key)
        for bn, sl in (("research", slice(0, int(P["n"] * V.SPLIT))),
                       ("locked", slice(int(P["n"] * V.SPLIT), P["n"]))):
            sig = np.flatnonzero(m)[
                (np.flatnonzero(m) >= (sl.start or 0)) & (np.flatnonzero(m) < sl.stop)]
            p_, s_ = MC.gather(P, xb, pnl, sig.astype(np.int64))
            if len(p_) < MIN_N:
                print(f"  {mk:<7} {bn:<9} -- too few trades --")
                continue
            day = P["day"][s_]
            bo = MC.boot(p_, day, draws=2000)
            pe = MC.perm(p_, draws=2000)
            print(f"  {mk:<7} {bn:<9} n {len(p_):>4d}  mean {p_.mean():>+8.2f}  "
                  f"P(mean<=0) {bo['p_le0']:.3f}  90% CI [{bo['p5']:+.2f}, {bo['p95']:+.2f}]  "
                  f"maxDD real {pe['dd_real']:>8.0f} vs MC p50 {pe['dd50']:>8.0f} "
                  f"p95 {pe['dd95']:>8.0f}")


if __name__ == "__main__":
    main()
