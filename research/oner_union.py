"""More entries from the same mechanism, instead of a different mechanism.

The four validated 1R versions each fire 80-120 times in three years. That is the binding
constraint on all of them, and the usual fix -- go find another rule -- costs a fresh multiple
comparisons problem. This module tries the cheaper fix first.

Each version's conditions are thresholds on continuous features, and the thresholds were chosen
by a search that only had one rung to choose from. So:

  1. PARAMETERISE the version. `ATR > 1.5x mean AND BB width < 0.7x mean AND close < 20-bar low`
     becomes `ATR > k AND width < m AND close < N-bar low` over a grid of (k, m, N).
  2. SCORE every grid point on the RESEARCH BLOCK ONLY, against the population base win rate of
     its own geometry -- the same null Phase 2 uses, for the same reason (CLAUDE.md).
  3. UNION the trigger bars of every grid point that beats its base. One position at a time, so
     the union is not four positions stacked; it is the same mechanism admitted at whichever
     threshold happens to be met first.
  4. Read the locked block once, at the end.

The union is a weaker form of search than the sweep that produced the rule: it never introduces
a feature the rule did not already use, and it cannot pick a threshold, because it takes all of
the ones that work. What it can do is turn 86 entries into several hundred if -- and only if --
the mechanism really is a mechanism rather than a threshold coincidence. That is the test.
"""
from __future__ import annotations

import sys
from itertools import product

import numpy as np

sys.path.insert(0, "research")
import indicators as I
from bos_choch import prep
from test_suite import PV, COMM, EC, SE, sim_core

STOPS = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
FLATS = [0, 900, 960]
GEOS = [(a, f) for a in STOPS for f in FLATS]

_D = {}


def bars(tf):
    if tf not in _D:
        _D[tf] = prep(tf)
    return _D[tf]


# ---- the four versions, parameterised ------------------------------------------------------
# Each entry: the shipped setting, the grid, and a mask builder. The shipped setting is always a
# point ON the grid, so "the union beat the original" is a comparison inside one family.

def _v1(d, k, m, n):
    """Wide bars, clustered closes, a break of the range floor. The failed-breakdown setup."""
    c, h, l, atr_ = d["c"], d["h"], d["l"], d["atr"]
    a20 = I.sma(atr_, 20)
    _u, _b, _lo, bw = I.bollinger(c)
    bwm = I.sma(bw, 50)
    return (atr_ > k * a20) & (bw < m * bwm) & (c < I.shift(I.rmin(l, n)))


def _v2(d, ab, q, w):
    """Trend up, a bearish engulfing bar, early. A first-hour fade of a countertrend bar."""
    o, c = d["o"], d["c"]
    a, b = ab
    body = np.abs(c - o) / np.maximum(d["h"] - d["l"], 1e-12)
    eng = (c < I.shift(o)) & (o > I.shift(c)) & (c < o) & (body >= q)
    return (I.ema(c, a) > I.ema(c, b)) & eng & (d["mod"] >= 570) & (d["mod"] < 570 + w)


def _v3(d, n, r, w):
    """A Donchian break on an expansion bar, early."""
    o, h, l, c, atr_ = d["o"], d["h"], d["l"], d["c"], d["atr"]
    out = (h > I.shift(h)) & (l < I.shift(l)) & ((h - l) >= r * atr_)
    return (c > I.shift(I.rmax(h, n))) & out & (d["mod"] >= 570) & (d["mod"] < 570 + w)


def _v4(d, k, n, f):
    """Oversold into a new low with a rejection tail -- and then sold, not bought."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    kk, _dd = I.stoch(h, l, c)
    lw = (np.minimum(c, o) - l) / np.maximum(h - l, 1e-12)
    return (kk < k) & (c < I.shift(I.rmin(l, n))) & (lw > f)


FAMILIES = {
    "V1": dict(tf=30, side=1, fn=_v1, ship=(1.5, 0.7, 20), am=3.0, flat=900,
               grid=([1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0],
                     [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2],
                     [3, 5, 8, 10, 15, 20, 30, 50, 75]),
               human="ATR > k x mean AND BB width < m x mean AND close < N-bar low"),
    "V2": dict(tf=30, side=-1, fn=_v2, ship=((20, 50), 0.0, 60), am=1.0, flat=960,
               grid=([(10, 20), (20, 50), (20, 100), (50, 100), (10, 50), (50, 200)],
                     [0.0, 0.2, 0.3, 0.4, 0.5],
                     [30, 60, 90, 120, 150, 180]),
               human="EMA a > EMA b AND bearish engulfing (body >= q) AND first w minutes"),
    "V3": dict(tf=15, side=1, fn=_v3, ship=(20, 0.0, 60), am=4.0, flat=960,
               grid=([5, 8, 10, 15, 20, 30, 50, 75, 100],
                     [0.0, 0.8, 1.0, 1.2, 1.5],
                     [30, 60, 90, 120, 150, 180]),
               human="close > Donchian N high AND outside bar (range >= r x ATR) AND first w min"),
    "V4": dict(tf=15, side=-1, fn=_v4, ship=(20, 50, 0.5), am=3.0, flat=960,
               grid=([10, 15, 20, 25, 30, 35, 40],
                     [10, 15, 20, 30, 50, 75, 100, 150, 200],
                     [0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.65]),
               human="Stoch K < k AND close < N-bar low AND lower wick > f"),
}


def _sim(d, trig, side, am, flat):
    return sim_core(d["o"], d["h"], d["l"], d["c"], d["atr"], d["mod"].astype(np.int64),
                    np.asarray(trig, np.int64), np.int64(side), float(am), 1.0,
                    np.int64(flat), np.int64(0), PV, COMM, EC, SE)


def _cut(d):
    us = np.unique(d["sess"])
    return np.searchsorted(us, d["sess"]), int(0.65 * len(us)), len(us)


def base_rate(d, side, am, flat, step=7):
    """Population base: enter on every step'th bar under this geometry, research block only.

    The unconditional win rate of the geometry itself. It is not 1/(1+R): costs push it down, a
    wider barrier pushes it up, and drift lifts longs and sinks shorts. Every grid point below is
    scored against this, never against 50%.
    """
    si, cut, _ = _cut(d)
    trig = np.arange(300, len(d["c"]) - 1, step, dtype=np.int64)
    pnl, eb, _xb, _w, _g = _sim(d, trig, side, am, flat)
    m = si[eb] < cut
    return 100.0 * float((pnl[m] > 0).mean()) if m.sum() > 50 else np.nan


def sweep(key, verbose=True):
    """Every grid point x every geometry, scored on research only."""
    F = FAMILIES[key]
    d = bars(F["tf"])
    si, cut, _ = _cut(d)
    pts = list(product(*F["grid"]))
    masks = {p: F["fn"](d, *p) for p in pts}
    for p in masks:
        masks[p][:300] = False
    bases = {g: base_rate(d, F["side"], g[0], g[1]) for g in GEOS}
    rows = []
    for p in pts:
        trig = np.flatnonzero(masks[p]).astype(np.int64)
        if len(trig) < 40:
            continue
        for am, flat in GEOS:
            pnl, eb, _xb, _w, _g = _sim(d, trig, F["side"], am, flat)
            m = si[eb] < cut
            n = int(m.sum())
            if n < 40:
                continue
            wr = 100.0 * float((pnl[m] > 0).mean())
            rows.append(dict(key=key, p=p, am=am, flat=flat, n_res=n,
                             res=float(pnl[m].sum()), wr_res=wr,
                             base=bases[(am, flat)], exc=wr - bases[(am, flat)]))
    if verbose:
        print(f"  {key}: {len(pts):,} threshold points x {len(GEOS)} geometries = "
              f"{len(pts)*len(GEOS):,} evaluated, {len(rows):,} have 40+ research trades")
    return rows, masks, d, si, cut, bases


def frontier(key, frac=0.6, min_n=40, verbose=True):
    """Relax the thresholds as far as the edge allows, and no further.

    The first version of this took the union of every grid point that merely beat its base on
    research. That is almost no gate -- 297 of V1's 304 points passed -- and because the
    thresholds are monotone, a union of nested masks IS its loosest member. The union therefore
    reproduced the loosest passing threshold and nothing else, and V1 fell from 70.9% to 50.1%.

    So the gate is a MARGIN, not a sign: a point is kept only if it holds at least `frac` of the
    shipped rule's own research excess over its base, and is research-profitable, and has enough
    research trades to mean anything. Everything is decided on the research block. The locked
    block is read once, afterwards, and never enters this function.
    """
    F = FAMILIES[key]
    rows, masks, d, si, cut, bases = sweep(key, verbose=verbose)
    am, flat = F["am"], F["flat"]
    here = [r for r in rows if r["am"] == am and r["flat"] == flat]
    ship = [r for r in here if r["p"] == F["ship"]]
    if not ship:
        raise SystemExit(f"{key}: the shipped setting {F['ship']} is not on its own grid")
    bar = frac * ship[0]["exc"]
    keep = [r for r in here if r["exc"] >= bar and r["res"] > 0 and r["n_res"] >= min_n]
    keep.sort(key=lambda r: -r["n_res"])
    if verbose:
        print(f"     shipped excess {ship[0]['exc']:+.1f} pts -> gate at {bar:+.1f}; "
              f"{len(keep)} of {len(here)} points hold it and are research-profitable")
    if not keep:
        return None
    u = np.zeros(len(d["c"]), bool)
    for r in keep:
        u |= masks[r["p"]]
    loose = keep[0]
    return dict(key=key, trig=np.flatnonzero(u).astype(np.int64), kept=keep, rows=rows,
                loose=loose, loose_trig=np.flatnonzero(masks[loose["p"]]).astype(np.int64),
                ship_row=ship[0], bar=bar,
                d=d, si=si, cut=cut, am=am, flat=flat, side=F["side"], tf=F["tf"],
                base=bases[(am, flat)], n_points=len(here))


def score(d, si, cut, trig, side, am, flat, base):
    pnl, eb, xb, why, gap = _sim(d, trig, side, am, flat)
    m = si[eb] < cut
    w = pnl > 0
    return dict(n=len(pnl), n_res=int(m.sum()), n_lok=int((~m).sum()),
                win=100.0 * float(w.mean()), win_res=100.0 * float(w[m].mean()),
                win_lok=100.0 * float(w[~m].mean()) if (~m).sum() else np.nan,
                net=float(pnl.sum()), res=float(pnl[m].sum()), lok=float(pnl[~m].sum()),
                pf=float(pnl[w].sum() / max(-pnl[~w].sum(), 1e-9)), base=base,
                pnl=pnl, ent_bar=eb, ex_bar=xb, why=why, gap=gap)


def floors(key, U, verbose=True, levels=(58.0, 60.0, 62.0, 65.0, 68.0)):
    """The trade-count / win-rate frontier of one mechanism, decided on research.

    "More entries" and "high win rate" pull against each other, so the useful object is not one
    setting but the frontier: at each research win-rate floor, the loosest threshold point that
    still clears it. Both axes are research-block quantities. The locked column is printed once,
    afterwards, and is not consulted in choosing any row.
    """
    F = FAMILIES[key]
    d, si, cut = U["d"], U["si"], U["cut"]
    here = [r for r in U["rows"] if r["am"] == U["am"] and r["flat"] == U["flat"]]
    out = []
    for fl in levels:
        cand = [r for r in here if r["wr_res"] >= fl and r["res"] > 0 and r["n_res"] >= 40]
        if not cand:
            out.append((fl, None, None)); continue
        best = max(cand, key=lambda r: r["n_res"])
        trig = np.flatnonzero(F["fn"](d, *best["p"])).astype(np.int64)
        out.append((fl, best, score(d, si, cut, trig[trig >= 300], F["side"], U["am"],
                                    U["flat"], U["base"])))
    if verbose:
        print(f"    {'floor':>6}  {'setting':<22}{'trades':>7}{'res':>5}{'lok':>5}"
              f"{'win%':>7}{'res win%':>9}{'lok win%':>9}{'net $':>9}{'lok $':>9}{'PF':>6}")
        for fl, b, s in out:
            if s is None:
                print(f"    {fl:>5.0f}%  (nothing clears it)"); continue
            print(f"    {fl:>5.0f}%  {str(b['p'])[:20]:<22}{s['n']:>7}{s['n_res']:>5}"
                  f"{s['n_lok']:>5}{s['win']:>7.1f}{s['win_res']:>9.1f}{s['win_lok']:>9.1f}"
                  f"{s['net']:>9,.0f}{s['lok']:>9,.0f}{s['pf']:>6.2f}")
    return out


if __name__ == "__main__":
    import sys as _s
    frac = float(_s.argv[1]) if len(_s.argv) > 1 else 0.6
    print(f"THRESHOLD NEIGHBOURHOOD -> RELAXATION   (keep >= {frac:.0%} of the shipped excess)\n")
    hdr = (f"  {'':<7}{'setting':<22}{'trades':>7}{'res':>5}{'lok':>5}{'win%':>7}{'base':>7}"
           f"{'exc':>7}{'net $':>10}{'res $':>9}{'lok $':>9}{'PF':>6}")
    out = {}
    for key in FAMILIES:
        F = FAMILIES[key]
        U = frontier(key, frac=frac)
        if U is None:
            print(f"  {key}: nothing holds the gate\n"); continue
        d, si, cut = U["d"], U["si"], U["cut"]
        sh = np.flatnonzero(F["fn"](d, *F["ship"])).astype(np.int64)
        sh = sh[sh >= 300]
        cards = [("ship", str(F["ship"]), sh),
                 ("loose", str(U["loose"]["p"]), U["loose_trig"]),
                 ("union", f"{len(U['kept'])} points", U["trig"])]
        print(f"\n  {key}  {F['human']}   [{'long' if F['side']==1 else 'short'}, "
              f"{F['tf']}m, {F['am']}xATR, 1R, flat {F['flat'] or '-'}]")
        print(hdr)
        sc = {}
        for nm, lbl, tg in cards:
            s = score(d, si, cut, tg, F["side"], F["am"], F["flat"], U["base"])
            sc[nm] = s
            print(f"  {nm:<7}{lbl[:20]:<22}{s['n']:>7}{s['n_res']:>5}{s['n_lok']:>5}"
                  f"{s['win']:>7.1f}{s['base']:>7.1f}{s['win']-s['base']:>+7.1f}"
                  f"{s['net']:>10,.0f}{s['res']:>9,.0f}{s['lok']:>9,.0f}{s['pf']:>6.2f}")
        print(f"\n    the trade-count / win-rate frontier of this mechanism:")
        fr = floors(key, U)
        out[key] = (U, sc)

    print("\n\n  WHAT THE RELAXATION BOUGHT, LOCKED BLOCK ONLY")
    print(f"  {'':<7}{'ship tr':>9}{'ship $':>9}{'best tr':>9}{'best $':>9}{'pick':>8}")
    tot_s = tot_b = 0
    for key, (U, sc) in out.items():
        cand = max(("loose", "union"), key=lambda k: sc[k]["res"])   # chosen on RESEARCH
        a, b = sc["ship"], sc[cand]
        tot_s += a["lok"]; tot_b += b["lok"]
        print(f"  {key:<7}{a['n_lok']:>9}{a['lok']:>9,.0f}{b['n_lok']:>9}{b['lok']:>9,.0f}"
              f"{cand:>8}")
    print(f"  {'total':<7}{'':>9}{tot_s:>9,.0f}{'':>9}{tot_b:>9,.0f}")

    np.save("results/oner/union.npy", np.array(
        [{"key": k, "trig": v[0]["trig"], "loose_trig": v[0]["loose_trig"],
          "loose_p": v[0]["loose"]["p"], "kept": len(v[0]["kept"]),
          "am": v[0]["am"], "flat": v[0]["flat"], "side": v[0]["side"], "tf": v[0]["tf"],
          "scores": {n: {q: x for q, x in s.items() if not isinstance(x, np.ndarray)}
                     for n, s in v[1].items()}}
         for k, v in out.items()], dtype=object), allow_pickle=True)
