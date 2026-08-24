"""V2 taken long instead of short. Measured, not assumed.

The emitted script carries a tooltip saying that flipping the direction switch does not give you
the mirror-image edge, because longs and shorts start from different base rates on a market that
rose 89%, and because only one side of the rule was ever tested. This is the test.

Three candidates, all on 30-minute bars in the 09:30-11:30 New York window:

  A  SAME TRIGGER, LONG.  `EMA20 > EMA50 AND bearish engulfing (body >= 20%)`, bought instead of
     sold. Read as an idea in its own right this is "buy the first sharp down bar of the morning
     inside an uptrend" -- a dip buy. It is not the mirror of anything; it is the same signal
     with the opposite sign.

  B  THE TRUE MIRROR.     `EMA20 < EMA50 AND bullish engulfing (body >= 20%)`, long. Every
     directional term inverted, which is what "the mirror-image edge" would actually mean.

  C  LONG-NATURAL.        `EMA20 > EMA50 AND bullish engulfing (body >= 20%)`, long. Uptrend,
     up bar, bought. The version someone would write from scratch if they wanted a long.

Each is swept over all 18 geometries on the RESEARCH block only and scored against the base win
rate of a LONG at that geometry -- which is materially higher than the short base, and is the
whole reason a flipped short can look profitable while adding nothing.

Usage: python3 research/v2_long.py
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
import indicators as I
from oner_anom import control_from, exits_from
from oner_union import GEOS, _cut, _sim, bars, base_rate, score

TF = 30
WIN = (570, 690)          # 09:30-11:30 New York, the re-set V2 window
Q = 0.2                   # minimum body fraction on the engulfing bar
SHIP = dict(am=1.0, flat=960)


def masks(d):
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    mod = d["mod"]
    body = np.abs(c - o) / np.maximum(h - l, 1e-12)
    bear = (c < I.shift(o)) & (o > I.shift(c)) & (c < o) & (body >= Q)
    bull = (c > I.shift(o)) & (o < I.shift(c)) & (c > o) & (body >= Q)
    up = I.ema(c, 20) > I.ema(c, 50)
    win = (mod >= WIN[0]) & (mod < WIN[1])
    m = {
        "V2 as shipped (short)": (up & bear & win, -1),
        "A same trigger, long": (up & bear & win, 1),
        "B true mirror, long": (~up & bull & win, 1),
        "C long-natural": (up & bull & win, 1),
    }
    for k in m:
        m[k][0][:300] = False
    return m


def sweep():
    d = bars(TF)
    si, cut, _ = _cut(d)
    M = masks(d)
    bases = {}
    for side in (1, -1):
        for am, flat in GEOS:
            bases[(side, am, flat)] = base_rate(d, side, am, flat)
    rows = {}
    for name, (mk, side) in M.items():
        trig = np.flatnonzero(mk).astype(np.int64)
        out = []
        for am, flat in GEOS:
            pnl, eb, _x, _w, _g = _sim(d, trig, side, am, flat)
            m = si[eb] < cut
            if m.sum() < 40:
                continue
            wr = 100.0 * float((pnl[m] > 0).mean())
            b = bases[(side, am, flat)]
            out.append(dict(am=am, flat=flat, n_res=int(m.sum()), res=float(pnl[m].sum()),
                            wr_res=wr, base=b, exc=wr - b))
        rows[name] = (trig, side, out)
    return d, si, cut, rows, bases


def main():
    d, si, cut, rows, bases = sweep()
    print("V2 TAKEN LONG -- three candidates, 30m bars, 09:30-11:30 New York\n")
    print("RESEARCH BLOCK ONLY, at V2's own geometry (1.0 x ATR stop, 1R target, flat 16:00)")
    print(f"  {'':<24}{'dir':>6}{'n':>6}{'win%':>7}{'long/short base':>17}{'excess':>9}{'res $':>9}")
    for name, (trig, side, out) in rows.items():
        here = [r for r in out if r["am"] == SHIP["am"] and r["flat"] == SHIP["flat"]]
        if not here:
            print(f"  {name:<24}{'long' if side==1 else 'short':>6}   (too few research trades)")
            continue
        r = here[0]
        print(f"  {name:<24}{'long' if side==1 else 'short':>6}{r['n_res']:>6}{r['wr_res']:>7.1f}"
              f"{r['base']:>17.1f}{r['exc']:>+9.1f}{r['res']:>9,.0f}")

    print(f"\nBEST GEOMETRY FOR EACH, CHOSEN ON RESEARCH (max excess, 40+ research trades)")
    print(f"  {'':<24}{'stop':>6}{'flat':>6}{'n':>6}{'win%':>7}{'base':>7}{'excess':>9}{'res $':>9}")
    best = {}
    for name, (trig, side, out) in rows.items():
        if not out:
            continue
        b = max(out, key=lambda r: r["exc"])
        best[name] = (trig, side, b)
        print(f"  {name:<24}{b['am']:>6.1f}{(b['flat']//60 if b['flat'] else 0):>6}{b['n_res']:>6}"
              f"{b['wr_res']:>7.1f}{b['base']:>7.1f}{b['exc']:>+9.1f}{b['res']:>9,.0f}")

    print(f"\nTHE LOCKED BLOCK, READ ONCE, at each candidate's research-chosen geometry")
    print(f"  {'':<24}{'trades':>8}{'lok n':>7}{'lok win%':>10}{'base':>7}{'excess':>9}"
          f"{'net $':>9}{'lok $':>9}{'PF':>6}")
    for name, (trig, side, b) in best.items():
        s = score(d, si, cut, trig, side, b["am"], b["flat"], b["base"])
        m = si[s["ent_bar"]] >= cut
        lp = s["pnl"][m]
        print(f"  {name:<24}{s['n']:>8}{len(lp):>7}{100*(lp>0).mean():>10.1f}{b['base']:>7.1f}"
              f"{100*(lp>0).mean()-b['base']:>+9.1f}{s['net']:>9,.0f}{lp.sum():>9,.0f}"
              f"{s['pf']:>6.2f}")

    for name, (trig, side, b) in best.items():
        if side != 1:
            continue
        print(f"\n{'='*95}\n{name}   [long, {TF}m, {b['am']}xATR stop, 1R, flat "
              f"{b['flat'] or '-'}]\n{'='*95}")
        exits_from(d, trig, side, b["am"], b["flat"], name)
        control_from(d, si, cut, trig, side, b["am"], b["flat"])


# ---- the one that works, put through everything --------------------------------------------
B_CONDS = ["EMA20<EMA50", "bull engulf b>=0.2", "first 120m"]
B_GEO = dict(am=2.5, flat=900)


def b_masks(d):
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    body = np.abs(c - o) / np.maximum(h - l, 1e-12)
    return [I.ema(c, 20) < I.ema(c, 50),
            (c > I.shift(o)) & (o < I.shift(c)) & (c > o) & (body >= Q),
            (d["mod"] >= WIN[0]) & (d["mod"] < WIN[1])]


def b_strategy(drop=None):
    from test_suite import build
    d = bars(TF)
    mk = b_masks(d)
    use = [i for i in range(3) if i != drop]
    m = np.ones(len(d["c"]), bool)
    for i in use:
        m &= mk[i]
    m[:300] = False
    return build([B_CONDS[i] for i in use], side=1, atr_mult=B_GEO["am"], tp_r=1.0,
                 flat_min=B_GEO["flat"], tf=TF, trig=np.flatnonzero(m).astype(np.int64),
                 name="B" + ("" if drop is None else f" without {B_CONDS[drop]}"))


def validate():
    from itertools import product
    from dropone import filter_null
    from intrabar import compare
    from test_suite import _daily, _dd, _sharpe
    d = bars(TF)
    si, cut, _ = _cut(d)
    full = b_strategy()

    print(f"\n{'='*95}\nB, THE TRUE MIRROR, PUT THROUGH THE SAME BATTERY AS THE OTHER FOUR"
          f"\n{'='*95}")
    print("\n1. EACH CONDITION AGAINST A RANDOM FILTER OF THE SAME SIZE   (locked block)")
    print(f"   {'condition dropped':<24}{'n full':>8}{'n sub':>8}{'full $/tr':>11}"
          f"{'random $/tr':>13}{'p':>8}")
    for j, nm in enumerate(B_CONDS):
        sub = b_strategy(drop=j)
        obs, rnd, pv = filter_null(full, sub, draws=2000)["lok"]
        print(f"   {nm:<24}{int((full.ent_sess>=full.cut).sum()):>8}"
              f"{int((sub.ent_sess>=sub.cut).sum()):>8}{obs:>11,.0f}{rnd:>13,.0f}{pv:>8.3f}"
              + ("  <- real filter" if np.isfinite(pv) and pv < 0.10 else ""))

    print("\n2. CORNERS   every condition held or inverted")
    mk = b_masks(d)
    print("   " + "".join(f"{n[:18]:<20}" for n in B_CONDS)
          + f"{'n':>5}{'win%':>7}{'net $':>10}{'PF':>7}")
    rws = []
    for sgn in product((1, 0), repeat=3):
        m = np.ones(len(d["c"]), bool)
        for s, x in zip(sgn, mk):
            m &= x if s else ~x
        m[:300] = False
        tg = np.flatnonzero(m).astype(np.int64)
        if len(tg) < 20:
            continue
        pnl, _e, _x, _w, _g = _sim(d, tg, 1, B_GEO["am"], B_GEO["flat"])
        if len(pnl) < 20:
            continue
        w = pnl > 0
        rws.append((sgn, len(pnl), 100 * w.mean(), float(pnl.sum()),
                    float(pnl[w].sum() / max(-pnl[~w].sum(), 1e-9))))
    for sgn, n, wr, net, pf in sorted(rws, key=lambda r: -r[3]):
        print("   " + "".join(f"{('yes' if s else 'NO'):<20}" for s in sgn)
              + f"{n:>5}{wr:>7.1f}{net:>10,.0f}{pf:>7.2f}")

    print("\n3. TRUE 1-MINUTE EXECUTION PATH")
    _s, out, (offs, tim) = compare(B_CONDS, side=1, atr_mult=B_GEO["am"], tp_r=1.0,
                                   flat_min=B_GEO["flat"], tf=TF, trig=full.trig)
    for lab, (pnl, why, amb) in out.items():
        w = pnl > 0
        print(f"   {lab:<32}{len(pnl):>6}{pnl.sum():>10,.0f}"
              f"{pnl[w].sum()/max(-pnl[~w].sum(),1e-9):>7.2f}{100*w.mean():>8.1f}")
    print(f"   {'entry delayed 0/1/2/5/10/20/29m':<32}" + "  ".join(f"{x:,.0f}" for x in tim))

    print("\n4. COSTS, BOOTSTRAP, WALK-FORWARD   (locked block)")
    lp = full.pnl[full.ent_sess >= full.cut]
    row = []
    for cm in (1.0, 1.5, 2.0, 3.0):
        s = full.sim(cost_mult=cm)
        row.append(s.pnl[s.ent_sess >= s.cut].mean())
    lo, hi = 1.0, 60.0
    for _ in range(24):
        mid = 0.5 * (lo + hi)
        s = full.sim(cost_mult=mid)
        q = s.pnl[s.ent_sess >= s.cut]
        (lo, hi) = (mid, hi) if (len(q) and q.mean() > 0) else (lo, mid)
    print(f"   $/trade at 1x/1.5x/2x/3x costs: " + "  ".join(f"{x:,.0f}" for x in row)
          + f"   breakeven at {0.5*(lo+hi):.1f}x")
    rng = np.random.default_rng(3)
    nets = []
    for _ in range(3000):
        o2 = []
        while len(o2) < len(lp):
            i = rng.integers(0, len(lp))
            o2.extend(lp[i:i + 20] if i + 20 <= len(lp)
                      else np.r_[lp[i:], lp[:20 - (len(lp) - i)]])
        nets.append(np.array(o2[:len(lp)]).sum())
    nets = np.array(nets)
    print(f"   block bootstrap, {len(lp)} locked trades: 5th pct ${np.percentile(nets,5):,.0f}, "
          f"median ${np.median(nets):,.0f}, 95th ${np.percentile(nets,95):,.0f}, "
          f"P(net<0) {(nets<0).mean():.2f}")
    edges = np.linspace(0, full.n_sess, 7).astype(int)
    vals = [float(full.pnl[(full.ent_sess >= a) & (full.ent_sess < b)].sum())
            for a, b in zip(edges[:-1], edges[1:])]
    print(f"   6 walk-forward folds: " + "  ".join(f"{v:,.0f}" for v in vals)
          + f"   {sum(1 for v in vals if v > 0)}/6 positive")

    print("\n5. AGAINST V2, WHICH IT MIRRORS")
    print(f"   B needs EMA20 < EMA50 and V2 needs EMA20 > EMA50, so the two can never fire on the")
    print(f"   same bar. Overlapping SESSIONS: ", end="")
    from oner_more import daily as _md, select
    from oner_union import FAMILIES, score as _sc
    S = select("V2", verbose=False)
    v2 = _sc(S["d"], S["si"], S["cut"], S["trig"], S["side"], S["am"], S["flat"], S["base"])
    ns = full.n_sess
    a = np.zeros(ns); b2 = np.zeros(ns)
    for p_, e in zip(full.pnl, full.ent_sess):
        a[e] += p_
    for p_, e in zip(v2["pnl"], S["si"][v2["ent_bar"]]):
        b2[e] += p_
    ov = ((a != 0) & (b2 != 0)).sum()
    sd = a.std() * b2.std()
    print(f"{ov} of {int((a!=0).sum())}, correlation "
          f"{np.cov(a, b2)[0,1]/sd if sd else 0:+.2f}")
    port = a + b2
    eq = np.cumsum(port)
    dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
    print(f"   B + V2 together: {len(full.pnl)+v2['n']} trades, ${port.sum():,.0f} net, "
          f"Sharpe {_sharpe(port):.2f}, maxDD ${dd:,.0f}")
    return full


if __name__ == "__main__":
    main()
    validate()
