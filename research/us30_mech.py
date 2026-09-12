"""US30 15m: two mechanism-derived candidates from the alpha-discovery stage, pre-registered.

`us30_alpha.py` found no event surviving FDR on the research block, but two effects with a
consistent SIGN across every horizon: the first close beyond the 09:00 range is followed by a
move AGAINST the break (-7.7 / -16.5 / -8.9 / -13.4 pt at 1/2/4/8 bars, drift-adjusted), and a
gap of >= 0.5 ATR is followed by a move TOWARD the prior close (+3.8 / +9.8 / +8.5 / +25.0 pt).
Both say the same thing: on this file the open's first move is reversed more often than it is
continued. That is a mechanism (the opening auction overshoots), so it gets ONE pre-registered
test per effect, with the same gates as every rule search here and a single locked read.

    A  FAILED BREAK   on the first close beyond the 09:00 range (09:30-10:15), enter AGAINST the
                      break at the next open
    B  GAP FILL       at the 09:30 close, if |open - prior close| >= 0.5 ATR(14), enter TOWARD
                      the prior close at the 09:45 open

Geometries are few and named by the mechanism, not swept: fixed 100/100 flat 16:00 (the user's);
100/100 flat 11:00; for A a range-anchored pair (target the far side of the range, stop one
width beyond the break); for B the gap itself (target the prior close, stop one gap beyond).
Multiplicity to carry: 20 event-horizon cells that produced these two, plus the cells here.

    python3 research/us30_mech.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import us30_orb as U
import us30_orb2 as M2
from us30_orb import load, sessions, split_days, ema_of, metrics, fmt, bootstrap_ci, mc_drawdown, subperiods
from us30_orb2 import outcomes2, _pool


def signals_failed_break(d, F):
    c, o = d["c"], d["o"]
    rows = []
    for day, row in F.iterrows():
        for m in range(570, 630, 15):
            j = d["pos"].get((day, m)); f = d["pos"].get((day, m + 15))
            if j is None or f is None:
                continue
            if c[j] > row.hi:
                rows.append(dict(day=day, fill=f, px=o[f], side=-1, lvl=row.hi, w=row.width, ext=c[j] - row.hi)); break
            if c[j] < row.lo:
                rows.append(dict(day=day, fill=f, px=o[f], side=1, lvl=row.lo, w=row.width, ext=row.lo - c[j])); break
    return pd.DataFrame(rows)


def signals_gap_fill(d, F):
    c, o = d["c"], d["o"]
    atr = ema_of(d, 14, "tr")
    rows = []
    for day, row in F.iterrows():
        j = d["pos"].get((day, 570)); f = d["pos"].get((day, 585))
        if j is None or f is None or not np.isfinite(row.gap):
            continue
        if abs(row.gap) >= 0.5 * row.atr:
            pc = o[j] - row.gap
            rows.append(dict(day=day, fill=f, px=o[f], side=-int(np.sign(row.gap)), lvl=pc, w=abs(row.gap), ext=0.0))
    return pd.DataFrame(rows)


def run(d, F, sig, kind, geom, label):
    """geom: ('pts', sl, tp, flat) or ('anchored', flat) -- A: target far side of range, stop one
    width beyond the break; B: target the prior close, stop one gap beyond the entry."""
    if len(sig) == 0:
        return pd.DataFrame()
    px, side = sig.px.to_numpy(float), sig.side.to_numpy()
    if geom[0] == "pts":
        _, sl, tp, flat = geom
        sl = np.full(len(sig), sl, float); tp = np.full(len(sig), tp, float)
    else:
        flat = geom[1]
        if kind == "A":
            # target: the far side of the range from the fill; stop: one range width beyond the level
            tp = np.abs(px - (sig.lvl.to_numpy() - side * sig.w.to_numpy()))     # far side = lvl -/+ width
            tp = side * ((sig.lvl.to_numpy() - side * 0 - side * sig.w.to_numpy()) - px)
            tp = np.where(side == 1, (sig.lvl.to_numpy() + sig.w.to_numpy()) - px, px - (sig.lvl.to_numpy() - sig.w.to_numpy()))
            sl = sig.w.to_numpy() + np.abs(px - sig.lvl.to_numpy())
        else:
            tp = side * (sig.lvl.to_numpy() - px)          # distance to the prior close
            sl = sig.w.to_numpy()                            # one gap
        ok = (tp >= 25) & (sl >= 25)
        sig = sig[ok].reset_index(drop=True); px, side, tp, sl = px[ok], side[ok], tp[ok], sl[ok]
        if len(sig) == 0:
            return pd.DataFrame()
    o = outcomes2(d, sig.fill.to_numpy(), px, side, sl, tp, flat, 0.0)
    df = sig.copy()
    for k in ("gross", "net", "reason", "held", "amb"):
        df[k] = o[k]
    df["sl"], df["tp"] = sl, tp
    df["mod"] = d["mod"][df.fill.to_numpy()]
    cut = split_days(d)
    df["block"] = np.where(df.day < cut, "research", "locked")
    df["date"] = d["dates"][df.day.to_numpy()]
    df.attrs["flat"] = flat
    return df


def control(d, df, flat, draws=2000, seed=7, block="research"):
    sub = df[df.block == block]
    if len(sub) < 10:
        return None
    rng = np.random.default_rng(seed)
    fills = np.empty((len(sub), draws), np.int64)
    mods = sub["mod"].to_numpy()
    for m in np.unique(mods):
        r = np.where(mods == m)[0]
        cand = _pool(d, block, int(m))
        fills[r] = cand[rng.integers(0, len(cand), size=(len(r), draws))]
    f = fills.ravel()
    side = np.repeat(sub.side.to_numpy(), draws)
    sl = np.repeat(sub.sl.to_numpy(float), draws); tp = np.repeat(sub.tp.to_numpy(float), draws)
    o = outcomes2(d, f, d["o"][f], side, sl, tp, flat, 0.0)
    net = o["net"].reshape(len(sub), draws)
    nets = net.sum(0); on = sub.net.sum(); sd = nets.std()
    return dict(n=len(sub), net=on, c_net=nets.mean(), c_sd=sd, z=(on - nets.mean()) / sd if sd > 0 else 0,
                p=((nets >= on).sum() + 1) / (draws + 1), win=100 * (sub.net > 0).mean(), c_win=100 * (net > 0).mean())


def show(d, df, flat, label, block):
    sub = df[df.block == block]
    c = control(d, df, flat, block=block)
    m = metrics(sub)
    print(f"  {label:<52} [{block:8}] " + fmt(m))
    print(f"  {'':<52}            control {c['c_net']:>8,.0f} ± {c['c_sd']:,.0f}  z {c['z']:5.2f}  p {c['p']:.3f}  win vs {c['c_win']:.1f}%")
    for s, nm in ((1, "long"), (-1, "short")):
        ss = sub[sub.side == s]
        if len(ss):
            print(f"  {'':<52}            {nm:<5} n {len(ss):>3}  {ss.net.mean():6.1f} pt/trade  win {100 * (ss.net > 0).mean():.1f}%")
    return c


GEOMS = {"A": [("pts", 100, 100, 960), ("pts", 100, 100, 660), ("anchored", 960), ("anchored", 660)],
         "B": [("pts", 100, 100, 960), ("pts", 100, 100, 720), ("anchored", 960), ("anchored", 720)]}


def main():
    d = load(); F = M2.session_facts(d)
    cut = split_days(d)
    sigs = {"A": signals_failed_break(d, F), "B": signals_gap_fill(d, F)}
    names = {"A": "A failed 09:00 break, enter against", "B": "B gap >= 0.5 ATR, enter toward prior close"}
    print("== RESEARCH block, pre-registered candidates ==")
    results = {}
    for k in ("A", "B"):
        for g in GEOMS[k]:
            gl = f"{g[1]}/{g[2]} flat {g[3] // 60:02d}:{g[3] % 60:02d}" if g[0] == "pts" else f"anchored flat {g[1] // 60:02d}:{g[1] % 60:02d}"
            df = run(d, F, sigs[k], k, g, gl)
            if len(df) == 0:
                continue
            c = show(d, df, df.attrs["flat"], names[k] + " | " + gl, "research")
            results[(k, gl)] = (df, c)
    # gates: n >= 60, both sides >= 25%, z >= 2
    passed = []
    for key, (df, c) in results.items():
        res = df[df.block == "research"]
        minority = min((res.side == 1).mean(), (res.side == -1).mean())
        if len(res) >= 60 and minority >= 0.25 and c["z"] >= 2.0:
            passed.append(key)
    print(f"\n  cells: {len(results)}; passing z>=2, n>=60, both sides: {len(passed)} -> {passed}")
    print("\n== LOCKED, read once ==")
    if not passed:
        print("  Nothing passed the research gate. The best research cell is read on locked for the record only.")
        best = max(results, key=lambda k: results[k][1]["z"])
        passed = [best]
    for key in passed:
        df, c = results[key]
        print(f"\n  ===== {names[key[0]]} | {key[1]}  research z {c['z']:.2f}; chosen from {len(results)} cells + 20 event tests =====")
        show(d, df, df.attrs["flat"], names[key[0]] + " | " + key[1], "locked")
        rm, lm = metrics(df[df.block == "research"]), metrics(df[df.block == "locked"])
        print("  SHAPE WARNING: better on locked than research." if lm["per"] > rm["per"] else f"  shape: research {rm['per']:.1f} -> locked {lm['per']:.1f} pt/trade")
        sp = subperiods(df)
        for blk in ("research", "locked"):
            if blk in sp.index.get_level_values(0):
                x = sp.loc[blk]; print(f"  quarters profitable ({blk}): {int((x['sum'] > 0).sum())} of {len(x)}")


if __name__ == "__main__":
    main()
