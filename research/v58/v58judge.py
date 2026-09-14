"""Selection on research, a risk-matched control as the GATE, then ONE read of the locked block.

The selection rule is fixed before anything is read:
  * scorable on BOTH markets (>= 60 trades each on research),
  * scored by the WORSE of the two markets' research Sharpe, so no configuration can be bought
    by one market,
  * the top 1000 are read as a CONSENSUS -- the marginal share of each axis -- and never by
    their first row, which is the maximum of ~430,000 draws.

THE CONTROL is the one `STUDY_TURTLE_YOUTUBE.md` had to fix: same day, same side, same risk IN
POINTS and same reward in points, entered at a RANDOM bar of the same trade window. Risk here is
a fixed fraction of the Initial Balance range and does not depend on the entry bar, which is why
this family can be controlled honestly where a channel stop could not. One asymmetry remains and
it runs AGAINST the rule: the control enters at a bar's CLOSE so its stop cannot fire on its own
entry bar, while the rule enters at a LEVEL and is charged for that bar.
"""
from __future__ import annotations

import numpy as np
import sys, os
from numba import njit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.v58 import v58ib as V                                     # noqa: E402
from research.v58.run_v58 import MK, aggregate, blocks, MIN_N, prep     # noqa: E402


def gname(gs):
    fl = gs % 3; ti = (gs // 3) % 6; si = (gs // 18) % 5
    ri = (gs // 90) % 5; li = gs // 450
    return dict(ib=int(V.IB_LEN[li]), retr=float(V.RETR[ri]), stop=float(V.STOPF[si]),
                tgt=float(V.TGT[ti]), flat=int(V.FLAT[fl]), li=li)


def label(gs, f, side):
    g = gname(gs); fl = V.filter_name(f)
    t = "none" if g["tgt"] > 90 else f"{g['tgt']:.2f}"
    return (f"IB{g['ib']} {side:5s} retr {g['retr']:.2f} stop {g['stop']:.2f} tgt {t:>4s} "
            f"flat {g['flat']//60:02d}:{g['flat']%60:02d} | {fl['adx']}, {fl['vol']}, "
            f"{fl['cpos']}, ema {fl['ema']}")


@njit(cache=True)
def _control(h, l, c, ibh, ibl, ibe, fend, atr, days, li, side, retr, stopf, tgt,
             cost_pts, draws, seed, out):
    np.random.seed(seed)
    for k in range(draws):
        s = 0.0
        n = 0
        for j in range(len(days)):
            d = days[j]
            hi, lo = ibh[d, li], ibl[d, li]
            rng = hi - lo
            b0, b1 = ibe[d, li], fend[d]
            if b1 - b0 < 2:
                continue
            i0 = b0 + np.random.randint(0, b1 - b0 - 1)
            ent = c[i0]
            risk = rng * (stopf - retr)
            if risk <= 0:
                continue
            rew = rng * (tgt + retr) if tgt < 90.0 else 1e18
            stp = ent - risk if side == 0 else ent + risk
            tp = ent + rew if side == 0 else ent - rew
            pts = 0.0
            done = False
            for i in range(i0 + 1, b1):
                if side == 0:
                    hs = l[i] <= stp; ht = h[i] >= tp
                else:
                    hs = h[i] >= stp; ht = l[i] <= tp
                if hs:
                    pts = -risk; done = True; break
                if ht:
                    pts = rew; done = True; break
            if not done:
                px = c[b1 - 1]
                pts = (px - ent) if side == 0 else (ent - px)
            s += (pts - cost_pts) / atr[d, li]
            n += 1
        out[k] = s / n if n > 0 else np.nan


def control_p(F, gs, side, days, cost_pts, actual, draws=2000, seed=12345):
    g = gname(gs)
    fi = int(np.flatnonzero(V.FLAT == g["flat"])[0])
    out = np.full(draws, np.nan)
    _control(F["h"], F["l"], F["c"], F["ibh"], F["ibl"], F["ibe"], F["fend"][:, fi], F["atr"],
             np.asarray(days, np.int64), g["li"], side, g["retr"], g["stop"], g["tgt"],
             float(cost_pts), draws, seed, out)
    ok = out[np.isfinite(out)]
    return (ok >= actual).mean(), float(np.median(ok)), ok


def load(mk):
    z = np.load(f"results/v58/{mk}_research.npz")
    m = {s: {k: z[f"{s}_{k}"] for k in ("n", "totA", "perTrade", "pf", "sharpe")}
         for s in ("long", "short", "both")}
    A = [np.load(f"results/v58/{mk}_A_{s}.npy").astype(np.float64) for s in ("long", "short")]
    P = [np.load(f"results/v58/{mk}_P_{s}.npy").astype(np.float64) for s in ("long", "short")]
    mm = np.load(f"results/v58/{mk}_masks.npz")
    return m, A, P, mm["mL"], mm["mS"], mm["res"], mm["lock"]


def share(vals, names):
    c = {n: 0 for n in names}
    for v in vals:
        c[v] = c.get(v, 0) + 1
    return "  ".join(f"{k} {v/len(vals)*100:.0f}%" for k, v in sorted(c.items(), key=lambda x: -x[1]))


def main():
    data = {mk: load(mk) for mk in MK}
    F = {mk: V.build(mk) for mk in MK}

    scores = {}
    for side in ("long", "short", "both"):
        ok = np.ones((V.NF, V.NG), bool)
        sh = []
        for mk in MK:
            m = data[mk][0][side]
            ok &= (m["n"] >= MIN_N)
            sh.append(np.where(np.isfinite(m["sharpe"]), m["sharpe"], -9.0))
        scores[side] = np.where(ok, np.minimum(*sh), -9.0)

    allsc = np.stack([scores[s] for s in ("long", "short", "both")])
    top = np.argsort(allsc.ravel())[::-1][:1000]
    sides = np.array(["long", "short", "both"])[top // (V.NF * V.NG)]
    rest = top % (V.NF * V.NG)
    fs, gs = rest // V.NG, rest % V.NG
    G = [gname(g) for g in gs]
    fn = [V.filter_name(f) for f in fs]

    print("=" * 100)
    print("TOP 1000 CONSENSUS   (ranked by the WORSE of the two markets' research Sharpe, ATR units)")
    print("=" * 100)
    print("  side      ", share(list(sides), ["long", "short", "both"]))
    print("  IB length ", share([f"{g['ib']}m" for g in G], [f"{x}m" for x in V.IB_LEN]))
    print("  retrace   ", share([f"{g['retr']:.2f}" for g in G], [f"{x:.2f}" for x in V.RETR]))
    print("  stop      ", share([f"{g['stop']:.2f}" for g in G], [f"{x:.2f}" for x in V.STOPF]))
    print("  target    ", share(["none" if g['tgt'] > 90 else f"{g['tgt']:.2f}" for g in G],
                                ["none"] + [f"{x:.2f}" for x in V.TGT[:-1]]))
    print("  flatten   ", share([f"{g['flat']//60:02d}:{g['flat']%60:02d}" for g in G],
                                [f"{x//60:02d}:{x%60:02d}" for x in V.FLAT]))
    print("  adx       ", share([x["adx"] for x in fn], V.ADX_MODE))
    print("  vol       ", share([x["vol"] for x in fn], V.VOL_MODE))
    print("  close pos ", share([x["cpos"] for x in fn], V.CPOS_MODE))
    print("  ema 13/48 ", share([x["ema"] for x in fn], V.EMA_MODE))
    rr = [(g['tgt'] + g['retr']) / (g['stop'] - g['retr']) for g in G if g['tgt'] < 90]
    print(f"\n  reward:risk implied by the top 1000: median {np.median(rr):.1f}:1, "
          f"p90 {np.percentile(rr, 90):.1f}:1")

    print("\n" + "=" * 100)
    print("RISK-MATCHED CONTROL GATE ON RESEARCH   (2,000 random-entry draws, same day, same risk)")
    print("=" * 100)
    print(f"{'#':>3} {'configuration':<78} {'mkt':<7} {'n':>5} {'ATR/tr':>8} {'ctrl':>8} {'p':>6}")
    gate = []
    for r in range(25):
        side, f, g = str(sides[r]), int(fs[r]), int(gs[r])
        li = g // 450
        worst = 0.0
        rows = []
        for mk in MK:
            m, A, P, mL, mS, res, lock = data[mk]
            act = m[side]["perTrade"][f, g]
            ps = []
            for s2 in (["long", "short"] if side == "both" else [side]):
                si = 0 if s2 == "long" else 1
                msk = (mL if si == 0 else mS)[:, f, li]
                d = res[np.isfinite(A[si][res, g]) & msk[res]]
                if len(d) < 20:
                    continue
                p, med, _ = control_p(F[mk], g, si, d, V.COST_PTS[mk], act)
                ps.append((p, med))
            p = max(x[0] for x in ps) if ps else 1.0
            rows.append((mk, m[side]["n"][f, g], act, np.mean([x[1] for x in ps]), p))
            worst = max(worst, p)
        for i, (mk, n, act, med, p) in enumerate(rows):
            print(f"{r+1 if i==0 else '':>3} {label(g, f, side) if i==0 else '':<78} "
                  f"{mk:<7} {int(n):>5d} {act:>+8.4f} {med:>+8.4f} {p:>6.3f}")
        gate.append(dict(p=worst, side=side, f=f, g=g))

    surv = [x for x in gate if x["p"] <= 0.05]
    print(f"\n  {len(surv)}/25 clear the risk-matched control on BOTH markets at p <= 0.05.")
    np.save("results/v58/gate.npy", np.array(
        [(x["p"], x["side"], x["f"], x["g"]) for x in gate],
        dtype=[("p", "f8"), ("side", "U5"), ("f", "i8"), ("g", "i8")]))


if __name__ == "__main__":
    main()
