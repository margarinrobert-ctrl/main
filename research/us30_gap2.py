"""US30 gap fill, second step: walk-forward validation and ONE pre-registered design change.

`us30_mech.py` found the opening gap fill (fade a >= 0.5 ATR gap toward the prior close, target
the prior close, stop one gap, flat 12:00) passes the matched control on research and is positive
on the single locked read. Two things a disciplined engineer does next, neither of which is a
parameter sweep:

    1. WALK-FORWARD the family (fit 120 sessions, trade 40, small grid, objective net) so the cost
       of having to choose parameters is measured, and report efficiency and parameter stability.
    2. Test the one design change the mechanism itself suggests. The event study's lift grows
       from the moment of the open, and the rule currently waits for the 09:30 bar to close and
       fills at 09:45. Entering at the 09:30 OPEN captures the first bar. On a confirmed-bar
       script that means reading the gap from the 09:15 close (the last pre-open price) and
       filling at the 09:30 open. Pre-registered variants, research only, then the best is read
       on locked ONCE if it is not the already-read base:
           E1  base: gap from the 09:30 open, fill at the 09:45 open
           E2  early: gap from the 09:15 close, fill at the 09:30 open
           E3  early + confirm: E2's signal, but only if the 09:30 bar also opened on the same
               side of the prior close (the proxy was right), fill at the 09:30 open -- not
               implementable on a confirmed bar; measured as the ceiling only
       each at stop 1.0 and 0.75 gap, flat 12:00, target the prior close. Six cells.

    python3 research/us30_gap2.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import us30_orb as U
import us30_orb2 as M2
import us30_mech as X
from us30_orb import load, sessions, split_days, ema_of, metrics, fmt, bootstrap_ci, subperiods
from us30_orb2 import outcomes2


def gap_trades(d, F, thr=0.5, stop=1.0, tgt=1.0, flat=720, entry="E1"):
    c, o = d["c"], d["o"]
    rows = []
    for day, row in F.iterrows():
        j15, j30, j45 = d["pos"].get((day, 555)), d["pos"].get((day, 570)), d["pos"].get((day, 585))
        if j30 is None or not np.isfinite(row.gap):
            continue
        pc = o[j30] - row.gap
        if entry == "E1":
            if j45 is None:
                continue
            gap = row.gap
            if abs(gap) < thr * row.atr:
                continue
            fill, px = j45, o[j45]
        else:
            if j15 is None:
                continue
            gap = c[j15] - pc                   # the proxy, known at the 09:15 close
            if abs(gap) < thr * row.atr:
                continue
            if entry == "E3" and np.sign(o[j30] - pc) != np.sign(gap):
                continue
            fill, px = j30, o[j30]
        side = -int(np.sign(gap))
        tp = side * (pc - px) * tgt
        sl = abs(gap) * stop
        if tp < 25 or sl < 25:
            continue
        rows.append(dict(day=day, fill=fill, px=px, side=side, sl=sl, tp=tp, gap=abs(gap)))
    sig = pd.DataFrame(rows)
    if len(sig) == 0:
        return sig
    oc = outcomes2(d, sig.fill.to_numpy(), sig.px.to_numpy(float), sig.side.to_numpy(),
                   sig.sl.to_numpy(float), sig.tp.to_numpy(float), flat, 0.0)
    for k in ("gross", "net", "reason", "held", "amb"):
        sig[k] = oc[k]
    sig["mod"] = d["mod"][sig.fill.to_numpy()]
    cut = split_days(d)
    sig["block"] = np.where(sig.day < cut, "research", "locked")
    sig["date"] = d["dates"][sig.day.to_numpy()]
    sig.attrs["flat"] = flat
    return sig


def walk_forward(d, F, fit=120, step=40):
    grid = [(thr, stop, flat) for thr in (0.3, 0.5, 0.75, 1.0) for stop in (0.75, 1.0, 1.5) for flat in (660, 720, 780)]
    cache = {g: gap_trades(d, F, thr=g[0], stop=g[1], flat=g[2]) for g in grid}
    days = sessions(d, 540)
    folds, oos = [], []
    start = 0
    while start + fit + step <= len(days):
        fit_days = set(days[start:start + fit].tolist()); test_days = set(days[start + fit:start + fit + step].tolist())
        best, best_s = None, -np.inf
        for g, df in cache.items():
            a = df[df.day.isin(fit_days)]
            if len(a) < 20:
                continue
            s = a.net.sum()
            if s > best_s:
                best, best_s = g, s
        if best is None:
            start += step; continue
        t = cache[best][cache[best].day.isin(test_days)]
        oos.append(t)
        folds.append(dict(fold=len(folds), test_from=str(d["dates"][days[start + fit]]), thr=best[0], stop=best[1],
                          flat=f"{best[2] // 60:02d}:{best[2] % 60:02d}", is_net=best_s, oos_n=len(t), oos_net=t.net.sum(),
                          oos_per=t.net.mean() if len(t) else np.nan))
        start += step
    return pd.DataFrame(folds), (pd.concat(oos) if oos else pd.DataFrame())


def main():
    d = load(); F = M2.session_facts(d)
    print("== 1. WALK-FORWARD of the gap-fill family: fit 120 sessions, trade 40, 36-cell grid, objective net ==")
    folds, oos = walk_forward(d, F)
    print(folds.to_string(index=False, float_format=lambda x: f"{x:,.1f}"))
    if len(oos):
        print("  stitched OOS: " + fmt(metrics(oos)))
        is_med, oos_med = folds.is_net.median(), folds.oos_net.median()
        print(f"  folds profitable: {int((folds.oos_net > 0).sum())} of {len(folds)}; "
              f"walk-forward efficiency (median OOS net x3 / median IS net): {3 * oos_med / is_med if is_med > 0 else float('nan'):.2f}")
        for k in ("thr", "stop", "flat"):
            vc = folds[k].value_counts()
            print(f"  parameter stability {k}: kept {vc.iloc[0]} of {len(folds)} folds ({vc.index[0]})")
        c = X.control(d, oos.assign(block="research"), 720, draws=1000, block="research") if False else None

    print("\n== 2. ENTRY TIMING, pre-registered, research only ==")
    cells = {}
    for entry in ("E1", "E2", "E3"):
        for stop in (1.0, 0.75):
            df = gap_trades(d, F, stop=stop, entry=entry)
            res = df[df.block == "research"]
            c = X.control(d, df, 720, draws=2000, block="research")
            cells[(entry, stop)] = (df, c)
            m = metrics(res)
            print(f"  {entry} stop {stop:<4} n {m['n']:>3}  win {m['win']:5.1f}%  {m['per']:6.1f} pt/trade  PF {m['pf']:.2f}  "
                  f"L/S {m['longs']}/{m['shorts']}  tp/sl/flat {m['tp']}/{m['sl']}/{m['flat']}  control z {c['z']:5.2f} p {c['p']:.3f}")
    # how often does the 09:15 proxy get the side right?
    agree = []
    for day, row in F.iterrows():
        j15, j30 = d["pos"].get((day, 555)), d["pos"].get((day, 570))
        if j15 is None or j30 is None or not np.isfinite(row.gap):
            continue
        pc = d["o"][j30] - row.gap
        g15 = d["c"][j15] - pc
        if abs(g15) >= 0.5 * row.atr:
            agree.append(np.sign(g15) == np.sign(row.gap))
    print(f"  the 09:15 proxy has the same sign as the 09:30 gap on {100 * np.mean(agree):.1f}% of qualifying sessions")

    best = max(cells, key=lambda k: cells[k][1]["z"])
    print(f"\n  best on research: {best}")
    print("\n== 3. LOCKED, once, for the best research cell if it is not the base (E1, stop 1.0 was read in us30_mech) ==")
    for key in ([best] if best != ("E1", 1.0) else []):
        df, c = cells[key]
        loc = df[df.block == "locked"]; res = df[df.block == "research"]
        cl = X.control(d, df, 720, draws=2000, block="locked")
        print(f"  {key}: locked " + fmt(metrics(loc)))
        print(f"        control z {cl['z']:5.2f} p {cl['p']:.3f}; long {loc.net[loc.side == 1].mean():.1f} / short {loc.net[loc.side == -1].mean():.1f} pt/trade")
        print(f"        shape: research {res.net.mean():.1f} -> locked {loc.net.mean():.1f}" + ("  SHAPE WARNING" if loc.net.mean() > res.net.mean() else ""))
        sp = subperiods(df)
        for blk in ("research", "locked"):
            x = sp.loc[blk]; print(f"        quarters profitable ({blk}): {int((x['sum'] > 0).sum())} of {len(x)}")
        w = df; print(f"        whole file: n {len(w)}  {w.net.mean():.1f} pt/trade  net {w.net.sum():,.0f}  PF {w.net[w.net > 0].sum() / -w.net[w.net <= 0].sum():.2f}  maxDD {metrics(w)['maxdd']:,.0f}")
    if best == ("E1", 1.0):
        print("  the base is best on research; no new locked read.")


if __name__ == "__main__":
    main()
