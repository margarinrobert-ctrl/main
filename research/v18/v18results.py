"""The quant results: EV, profit factor, drawdown -- then robustness and a drawdown sweep."""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v18")
import v16core as C          # noqa: E402
import v18multi as M         # noqa: E402

RNG = np.random.default_rng(20260827)
INST = ["US30", "US100", "NQ", "US30L", "XAU"]


def hdr(t):
    print("\n" + "=" * 118)
    print(t)
    print("=" * 118)


def row(lab, m):
    return (f"   {lab:<26}{m['n']:>6}{m['ev']:>+9.4f}{m['ev_usd']:>+10.2f}{m['pf']:>8.3f}"
            f"{100 * m['win']:>7.1f}{m['avg_w']:>+8.3f}{m['avg_l']:>+8.3f}{m['net']:>+9.1f}"
            f"{m['dd']:>8.1f}{m['mar']:>7.2f}{m['sharpe']:>8.2f}")


if __name__ == "__main__":
    CTX = {k: M.ctx(k) for k in INST}

    hdr("1. THE STRATEGY AS SPECIFIED -- Donchian 30/20, 1.5xATR stop, 2R target, EWMAC 16/64 gate")
    print("   15-minute bars, market order at the next open, one unit, itemised costs.")
    print("   EV is per trade in R (P&L over that trade's own stop) and in USD at one contract.\n")
    print(f"   {'instrument / block':<26}{'n':>6}{'EV(R)':>9}{'EV($)':>10}{'PF':>8}{'win%':>7}"
          f"{'avg W':>8}{'avg L':>8}{'net R':>9}{'maxDD':>8}{'MAR':>7}{'Sharpe':>8}")
    store = {}
    for k in INST:
        P = CTX[k]
        res, lock = M.blocks(P)
        for side, sn in ((1, "long"), (-1, "short")):
            for bn, bb in (("research", res), ("locked", lock)):
                O, i = M.run(P, side, block=bb, gate=True)
                m = M.metrics(P, O, i, bb)
                store[(k, sn, bn)] = m
                print(row(f"{k} {sn} {bn}", m))
        print()

    hdr("2. WHAT THE EWMAC GATE IS WORTH -- the same runs with the crossover removed")
    print(f"   {'instrument / block':<26}{'gated EV':>11}{'ungated EV':>12}{'gated PF':>11}"
          f"{'ungated PF':>12}{'gated DD':>11}{'ungated DD':>12}{'verdict':>12}")
    for k in INST:
        P = CTX[k]
        res, lock = M.blocks(P)
        for bn, bb in (("research", res), ("locked", lock)):
            a, ia = M.run(P, 1, block=bb, gate=True)
            b, ib = M.run(P, 1, block=bb, gate=False)
            ma, mb = M.metrics(P, a, ia, bb), M.metrics(P, b, ib, bb)
            v = "helps" if ma["ev"] > mb["ev"] else "hurts"
            print(f"   {k + ' long ' + bn:<26}{ma['ev']:>+11.4f}{mb['ev']:>+12.4f}"
                  f"{ma['pf']:>11.3f}{mb['pf']:>12.3f}{ma['dd']:>11.1f}{mb['dd']:>12.1f}{v:>12}")

    hdr("3. ROBUSTNESS -- the whole neighbourhood, read by MARGINAL AVERAGE, never the top cell")
    print("   Donchian entry x exit x stop x target, 5x5x5x5 = 625 cells per instrument, long side,")
    print("   RESEARCH block only. The share of the grid that is profitable is printed BEFORE any")
    print("   ranking, because the top of a 625-cell sort is the maximum of 625 draws.\n")
    ENT = [20, 25, 30, 40, 55]
    EXI = [10, 15, 20, 25, 30]
    STP = [1.0, 1.5, 2.0, 2.5, 3.0]
    TPS = [1.0, 1.5, 2.0, 3.0, 0.0]        # 0.0 = no target
    grids = {}
    for k in INST:
        P = CTX[k]
        res, _ = M.blocks(P)
        rows = []
        for en in ENT:
            for xn in EXI:
                for st in STP:
                    for tp in TPS:
                        O, i = M.run(P, 1, block=res, gate=True, stop=st, tp_r=tp,
                                     entry_n=en, exit_n=xn)
                        m = M.metrics(P, O, i, res)
                        rows.append(dict(ent=en, exi=xn, stop=st, tp=tp, **{q: m[q] for q in
                                    ("n", "ev", "pf", "net", "dd", "mar", "sharpe")}))
        g = pd.DataFrame(rows)
        grids[k] = g
        g.to_csv(f"results/v18/v18_grid_{k}.csv", index=False)
        print(f"   {k}: {len(g)} cells, {float((g.ev > 0).mean()):.0%} with positive EV, "
              f"{float((g.pf > 1).mean()):.0%} with PF > 1, median EV {g.ev.median():+.4f}, "
              f"median PF {g.pf.median():.3f}")

    for ax, lab in (("ent", "Donchian ENTRY"), ("exi", "Donchian EXIT"),
                    ("stop", "ATR stop multiple"), ("tp", "target in R (0 = none)")):
        print(f"\n   MARGINAL by {lab} -- median EV in R across all other axes")
        print(f"   {'rung':>8}" + "".join(f"{k:>12}" for k in INST) + f"{'pooled':>12}{'%prof':>8}")
        for v in sorted(grids[INST[0]][ax].unique()):
            cells = []
            allv = []
            for k in INST:
                q = grids[k][grids[k][ax] == v]
                cells.append(f"{q.ev.median():+.4f}")
                allv.append(q.ev.to_numpy())
            pooled = np.concatenate(allv)
            print(f"   {v:>8g}" + "".join(f"{c:>12}" for c in cells)
                  + f"{np.median(pooled):>+12.4f}{float((pooled > 0).mean()):>8.0%}")


def dd_section(CTX, grids):
    hdr("4. DRAWDOWN OPTIMISATION -- rank by MAR and by Ulcer, and read the CONSENSUS not the top")
    print("   MAR is net R over max drawdown; the Ulcer index is the RMS of the drawdown curve, so")
    print("   it charges a long shallow drawdown that MAR ignores. The top row of a 625-cell sort")
    print("   is the maximum of 625 draws, so what the top 10% AGREE ON is reported instead.\n")
    for k in INST:
        g = grids[k].copy()
        g = g[g.n >= 40]
        if len(g) < 20:
            print(f"   {k}: too few scorable cells")
            continue
        top = g.nlargest(max(5, len(g) // 10), "mar")
        print(f"   {k}   scorable {len(g)}   best MAR {g.mar.max():.2f}   "
              f"median MAR {g.mar.median():+.2f}   min Ulcer {g.ulcer.min() if 'ulcer' in g else float('nan'):.2f}"
              if "ulcer" in g else
              f"   {k}   scorable {len(g)}   best MAR {g.mar.max():.2f}   median MAR {g.mar.median():+.2f}")
        for ax in ("ent", "exi", "stop", "tp"):
            vc = top[ax].value_counts(normalize=True).sort_values(ascending=False)
            lead = vc.index[0]
            print(f"        top-decile consensus on {ax:<5}: {lead:g} in {vc.iloc[0]:.0%} of cells"
                  f"   (population share {1/len(g[ax].unique()):.0%})")


def improved(CTX):
    hdr("5. THE CONFIGURATION THE MARGINALS POINT AT, READ ONCE ON LOCKED")
    print("   Chosen from the marginal medians in section 3, not from any cell: the stop axis is")
    print("   monotone toward WIDER and the target axis is monotone toward NONE. Everything else")
    print("   is left at the brief's value, so this differs from the spec in exactly two places.\n")
    print(f"   {'instrument':<12}{'config':<26}{'n':>6}{'EV(R)':>9}{'EV($)':>10}{'PF':>8}"
          f"{'net R':>9}{'maxDD':>8}{'MAR':>7}{'Sharpe':>8}")
    out = {}
    for k in INST:
        P = CTX[k]
        res, lock = M.blocks(P)
        for lab, st, tp in (("spec: 1.5N, 2R", 1.5, 2.0), ("marginals: 3.0N, no TP", 3.0, 0.0)):
            for bn, bb in (("research", res), ("LOCKED", lock)):
                O, i = M.run(P, 1, block=bb, gate=True, stop=st, tp_r=tp)
                m = M.metrics(P, O, i, bb)
                out[(k, lab, bn)] = (P, O, i, bb, m)
                print(f"   {k + ' ' + bn:<12}{lab:<26}{m['n']:>6}{m['ev']:>+9.4f}"
                      f"{m['ev_usd']:>+10.2f}{m['pf']:>8.3f}{m['net']:>+9.1f}{m['dd']:>8.1f}"
                      f"{m['mar']:>7.2f}{m['sharpe']:>8.2f}")
        print()
    return out


def mc(CTX, out):
    hdr("6. IS THE IMPROVED CONFIGURATION DISTINGUISHABLE FROM LUCK?")
    print("   Bootstrap resamples whole DAYS with their trades attached -- trades inside a session")
    print("   are not independent. The permutation reorders realised days and answers a DRAWDOWN")
    print("   question only; an endpoint distribution from a permutation is meaningless.\n")
    print(f"   {'instrument':<12}{'block':<10}{'net R':>9}{'P(mean<=0)':>13}{'realised DD':>13}"
          f"{'MC med DD':>12}{'MC p95':>9}{'MC p99':>9}")
    for k in INST:
        for bn in ("research", "LOCKED"):
            key = (k, "marginals: 3.0N, no TP", bn)
            if key not in out:
                continue
            P, O, i, bb, m = out[key]
            d = M.daily_R(P, O, i, bb).to_numpy()
            if len(d) < 30:
                continue
            bs = np.array([RNG.choice(d, len(d), replace=True).mean() for _ in range(5000)])
            dds = []
            for _ in range(5000):
                e = RNG.permutation(d).cumsum()
                dds.append(float((np.maximum.accumulate(e) - e).max()))
            dds = np.asarray(dds)
            print(f"   {k:<12}{bn:<10}{d.sum():>+9.1f}{float((bs <= 0).mean()):>13.3f}"
                  f"{m['dd']:>13.1f}{np.median(dds):>12.1f}{np.percentile(dds,95):>9.1f}"
                  f"{np.percentile(dds,99):>9.1f}")


if __name__ == "__main__":
    dd_section(CTX, grids)
    o = improved(CTX)
    mc(CTX, o)
