"""Why is M4 profitable? The decomposition, run as one battery.

M4 is `body<30% AND first hour AND ATR>1.8x mean`, 30-minute bars, long, 4.0 x ATR stop, a 1.0R
target and a 16:00 flatten. It is the only one of three strategies that made money in a
TradingView Deep Backtest (docs/ib/STUDY_PINE_CONFIG.md), and it carries the highest 1R win rate
this branch has produced. This module asks what that win rate is actually made of.

The battery, in the order the answers depend on each other:

  1  exit split          -- target / stop / time. A 1R rule earning at the TIME stop is a
                           direction bet, not a barrier edge (CLAUDE.md).
  2  matched control     -- random entries, same side, geometry and minute of day.
  3  barrier sweep       -- widen the stop to infinity. A barrier edge decays; a direction bet
                           converges to buy-and-hold-to-flatten and stays there.
  4  drop-one            -- which of the three conditions is load bearing.
  5  day vs bar          -- on the SAME days, enter at a RANDOM first-hour bar. If that does as
                           well, the entry bar carries no information and this is day selection.
  6  drift decomposition -- how far M4's days travel 09:30->16:00 against all days.
  7  regime              -- does it need the daily uptrend.
  8  hold time
  9  condition correlation
 10  leg correlation     -- M4 against the other eight shipped legs, daily P&L.
 11  threshold grid      -- a real edge decays smoothly over its own neighbourhood.
 13  bands, not cuts     -- the shape of the relationship, which a threshold grid hides.
 14  entry relocation    -- if the entry bar is noise, move it somewhere causally cleaner.

Usage: python3 research/m4_anatomy.py
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
import indicators as I
from oner_anom import control_from, exits_from
from oner_union import _cut, _sim, bars

TF, SIDE, AM, FLAT = 30, 1, 4.0, 960
WIN = (570, 630)          # 09:30-10:30 New York -- the first hour, and the Initial Balance


def prep(tf=TF):
    d = bars(tf)
    si, cut, nsess = _cut(d)
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    body = np.abs(c - o) / np.maximum(h - l, 1e-12)
    return d, si, cut, nsess, body, I.sma(d["atr"], 20)


def mask(d, body, am20, body_cut=0.3, atr_k=1.8, first_hour=True):
    m = body < body_cut
    if first_hour:
        m &= (d["mod"] >= WIN[0]) & (d["mod"] < WIN[1])
    if atr_k is not None:
        m &= d["atr"] > atr_k * am20
    m = m.copy()
    m[:300] = False
    return m


def _st(d, si, cut, m):
    t = np.flatnonzero(m).astype(np.int64)
    if len(t) < 8:
        return None
    p, e, _x, _w, _g = _sim(d, t, SIDE, AM, FLAT)
    r = si[e] < cut
    if r.sum() < 5:
        return None
    return dict(n=len(p), nr=int(r.sum()), pr=float(p[r].mean()), wr=100 * float((p[r] > 0).mean()),
                nl=int((~r).sum()), pl=float(p[~r].mean()) if (~r).sum() else np.nan,
                wl=100 * float((p[~r] > 0).mean()) if (~r).sum() else np.nan, net=float(p.sum()))


def run():
    d, si, cut, nsess, body, am20 = prep()
    mod, sess = d["mod"], d["sess"]
    m4 = mask(d, body, am20)
    trig = np.flatnonzero(m4).astype(np.int64)
    pnl, eb, xb, why, gap = _sim(d, trig, SIDE, AM, FLAT)
    res = si[eb] < cut
    print(f"M4  body<30% AND first hour AND ATR>1.8x mean | 30m long {AM}xATR flat 16:00")
    print(f"    {len(trig)} triggers -> {len(pnl)} trades, split at session {cut} of {nsess}\n")
    for tag, m in (("research", res), ("locked", ~res)):
        print(f"    {tag:<10}{m.sum():>4} trades{100*(pnl[m]>0).mean():>7.1f}% win"
              f"{pnl[m].sum():>10,.0f}{pnl[m].mean():>9.1f}/trade")

    print("\n--- 1 & 2  exit split and matched control ---")
    exits_from(d, trig, SIDE, AM, FLAT, "M4")
    control_from(d, si, cut, trig, SIDE, AM, FLAT, draws=800, seed=7)

    print("\n--- 3  barrier sweep: is the edge in the barriers or the direction? ---")
    print(f"    {'stop':<12}{'n':>5}{'win%':>8}{'net $':>10}{'$/trade':>10}{'stop/tgt/time':>16}")
    for am in (1.0, 2.0, 3.0, 4.0, 6.0, 10.0, 1e4):
        p, _e, _x, w, _g = _sim(d, trig, SIDE, am, FLAT)
        lab = "no barrier" if am > 1e3 else f"{am:.1f}x ATR"
        print(f"    {lab:<12}{len(p):>5}{100*(p>0).mean():>7.1f}%{p.sum():>10,.0f}{p.mean():>10.1f}"
              f"{f'{(w==1).sum()}/{(w==2).sum()}/{(w==3).sum()}':>16}")

    print("\n--- 4  drop-one ---")
    fh = (mod >= WIN[0]) & (mod < WIN[1])
    hi = d["atr"] > 1.8 * am20
    fam = {"M4 (all three)": (body < 0.3) & fh & hi, "drop body<30%": fh & hi,
           "drop ATR>1.8x": (body < 0.3) & fh, "drop first hour": (body < 0.3) & hi,
           "first hour only": fh}
    print(f"    {'variant':<20}{'n':>5}{'win%':>8}{'net $':>10}{'res $/t':>10}{'lock $/t':>10}")
    for k, m in fam.items():
        m = m.copy(); m[:300] = False
        s = _st(d, si, cut, m)
        print(f"    {k:<20}{s['n']:>5}{100*0+s['wr']:>7.1f}%{s['net']:>10,.0f}{s['pr']:>10.1f}{s['pl']:>10.1f}")

    print("\n--- 5  day selection or bar selection? ---")
    fhb = np.flatnonzero(fh); fhb = fhb[fhb >= 300]
    traded = set(sess[trig].tolist())
    pool = {}
    for b in fhb:
        s = int(sess[b])
        if s in traded:
            pool.setdefault(s, []).append(b)
    rng = np.random.default_rng(11); sims = []
    for _ in range(800):
        t2 = np.sort(np.array([rng.choice(v) for v in pool.values()], dtype=np.int64))
        q, _e, _x, _w, _g = _sim(d, t2, SIDE, AM, FLAT)
        sims.append((100 * (q > 0).mean(), q.mean(), q.sum()))
    A = np.array(sims)
    print(f"    {'':<26}{'win%':>8}{'$/trade':>10}{'net $':>10}")
    print(f"    {'M4 actual':<26}{100*(pnl>0).mean():>7.1f}%{pnl.mean():>10.1f}{pnl.sum():>10,.0f}")
    print(f"    {'same days, random bar':<26}{A[:,0].mean():>7.1f}%{A[:,1].mean():>10.1f}{A[:,2].mean():>10,.0f}")
    print(f"    {'p (M4 >= day control)':<26}{((A[:,0]>=100*(pnl>0).mean()).sum()+1)/(len(A)+1):>8.3f}"
          f"{'':>10}{((A[:,2]>=pnl.sum()).sum()+1)/(len(A)+1):>10.3f}")

    print("\n--- 6  how far do M4's days travel? 09:30 -> 16:00 ---")
    def span(ids):
        out = []
        for s in ids:
            k = np.flatnonzero((sess == s) & (mod >= WIN[0]) & (mod < FLAT))
            if len(k) > 2:
                out.append((d["c"][k[-1]] - d["o"][k[0]]) * 2.0)
        return np.array(out)
    a, b = span(sorted(traded)), span(np.unique(sess).tolist())
    print(f"    {'':<24}{'days':>7}{'mean $':>10}{'median $':>10}{'up %':>8}")
    for tag, v in (("M4 days", a), ("all days", b)):
        print(f"    {tag:<24}{len(v):>7}{v.mean():>10.1f}{np.median(v):>10.1f}{100*(v>0).mean():>7.1f}%")

    print("\n--- 11  threshold neighbourhood, RESEARCH $/trade ---")
    BODY = [0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5]; ATRK = [1.2, 1.4, 1.6, 1.8, 2.0, 2.2]
    print(f"    {'':<11}" + "".join(f"{f'ATR>{x}':>9}" for x in ATRK))
    for bc in BODY:
        line = f"    body<{bc:<5}"
        for ak in ATRK:
            s = _st(d, si, cut, mask(d, body, am20, bc, ak))
            line += f"{s['pr']:>9.0f}" if s else f"{'-':>9}"
        print(line + ("   <== shipped" if abs(bc - 0.3) < 1e-9 else ""))

    print("\n--- 13  bands, not cuts. first hour held fixed ---")
    print(f"    {'body band':<16}{'n_res':>6}{'res $/t':>10}{'n_lock':>8}{'lock $/t':>10}   (ATR>1.8x held)")
    E = [0, .1, .2, .3, .4, .5, .65, .8, 1.01]
    for x, y in zip(E, E[1:]):
        m = (body >= x) & (body < y) & fh & hi; m = m.copy(); m[:300] = False
        s = _st(d, si, cut, m)
        print(f"    [{x:.2f},{y:.2f})".ljust(20) + (f"{s['nr']:>2}{s['pr']:>10.0f}{s['nl']:>8}{s['pl']:>10.0f}" if s else f"{'too few':>26}"))
    print(f"    {'ATR/mean band':<16}{'n_res':>6}{'res $/t':>10}{'n_lock':>8}{'lock $/t':>10}   (body<0.3 held)")
    E2 = [0, .8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.2, 9]
    for x, y in zip(E2, E2[1:]):
        m = (body < 0.3) & fh & (d["atr"] >= x * am20) & (d["atr"] < y * am20); m = m.copy(); m[:300] = False
        s = _st(d, si, cut, m)
        print(f"    [{x:.1f},{y:.1f})".ljust(20) + (f"{s['nr']:>2}{s['pr']:>10.0f}{s['nl']:>8}{s['pl']:>10.0f}" if s else f"{'too few':>26}"))

    print("\n--- 14  M4's days, entered at 10:30 instead of on the signal bar ---")
    late = []
    for s in sorted(traded):
        k = np.flatnonzero((sess == s) & fh)
        if len(k) >= 2 and k[-1] >= 300:
            late.append(k[-1])
    late = np.array(sorted(late), dtype=np.int64)
    print(f"    {'variant':<34}{'n':>5}{'win%':>8}{'$/t':>8}{'net $':>10}{'res $/t':>10}{'lock $/t':>10}")
    for tag, t in (("signal-bar entry (as shipped)", trig), ("entry at 10:30 (IB complete)", late)):
        p, e, _x, _w, _g = _sim(d, t, SIDE, AM, FLAT); r = si[e] < cut
        print(f"    {tag:<34}{len(p):>5}{100*(p>0).mean():>7.1f}%{p.mean():>8.1f}{p.sum():>10,.0f}"
              f"{p[r].mean():>10.1f}{p[~r].mean():>10.1f}")


if __name__ == "__main__":
    run()
