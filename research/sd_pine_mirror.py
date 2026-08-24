"""A line-for-line mirror of what the Pine script will execute, checked against the engine.

The Pine cannot iterate a NumPy array of pre-built zones. It sees the 4H series through
`request.security(..., lookahead_off)`, pushes each new zone onto a bounded array as it appears,
prunes by age, and scans that array on every 60m bar. Every one of those differences is a place a
Pine script can silently stop being the strategy that was tested, so the design is mirrored here
in Python and compared with `sd_4h15m.run()` trade for trade BEFORE the Pine is written.

Differences deliberately modelled:
  * zones become visible on the first 60m bar at or after the 4H bar's close (lookahead_off)
  * the zone array is CAPPED and pruned by age, which the engine's unbounded list is not
  * ties, gap fills and the 8xATR risk cap follow the engine exactly
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from bos_choch import prep, SPECS
from sd_4h15m import build_zones, run

S = SPECS["MNQ"]
PV, TICK, COMM = S["pv"], S["tick"], 1.0
EC = (S["spread_t"] + S["slip_t"]) * TICK
SE = S["stop_slip_t"] * TICK
MAX_ZONES = 200          # the Pine array cap


def pine_mirror(H, L, bk, bm, dm, buf, tp_r, age_bars, zt=0, slo=0, shi=1440,
                cap=MAX_ZONES):
    """Exactly the loop the Pine will run, in the order Pine runs it."""
    dH = prep(H); dL = prep(L)
    h4, l4, c4, a4 = dH["h"], dH["l"], dH["c"], dH["atr"]
    idxL = dL["df"].index.values
    close4 = (dH["df"].index + pd.Timedelta(minutes=H)).values
    # --- what request.security(..., lookahead_off) delivers, and WHEN -----------------------------
    # A 4H bar's zone verdict is computed from bars i-bk..i on the 4H series and becomes readable on
    # the first 60m bar at or after that 4H bar's close.
    fire_at = np.searchsorted(idxL, close4, side="left")
    zone_of_bar = {}
    for i in range(bk + 5, len(c4)):
        a = a4[i]
        if np.isnan(a) or a <= 0.0:
            continue
        quiet = True; bl = l4[i - bk]; bh = h4[i - bk]
        for j in range(i - bk, i):
            if (h4[j] - l4[j]) > bm * a:
                quiet = False; break
            bl = min(bl, l4[j]); bh = max(bh, h4[j])
        if not quiet or (h4[i] - l4[i]) < dm * a:
            continue
        d = 1 if c4[i] > bh else (-1 if c4[i] < bl else 0)
        if d == 0:
            continue
        pre = c4[i - bk - 1] - c4[i - bk - 4]
        rev = (d == 1 and pre < 0.0) or (d == -1 and pre > 0.0)
        if zt == 1 and not rev:
            continue
        if zt == 2 and rev:
            continue
        f = fire_at[i]
        if f < len(idxL):
            zone_of_bar.setdefault(f, []).append((bl, bh, d))

    o, h, l, c, aL = dL["o"], dL["h"], dL["l"], dL["c"], dL["atr"]
    mod = dL["mod"]
    n = len(c)
    # --- the Pine bar loop ------------------------------------------------------------------------
    zl = []; zh = []; zd = []; zs = []          # the four Pine arrays
    pos = 0; entry = 0.0; stop = 0.0; tgt = 0.0
    pend = 0; pstop = 0.0; ptgt = 0.0
    P = []; E = []; X = []
    for i in range(2, n - 1):
        # new zones arrive at the top of the bar, exactly as a security value updates
        for (bl, bh, d) in zone_of_bar.get(i, []):
            zl.append(bl); zh.append(bh); zd.append(d); zs.append(i)
        # prune by age, then by capacity -- the Pine array cannot grow without bound
        while zs and (i - zs[0]) > age_bars:
            zl.pop(0); zh.pop(0); zd.pop(0); zs.pop(0)
        while len(zs) > cap:
            zl.pop(0); zh.pop(0); zd.pop(0); zs.pop(0)

        a = aL[i]
        if np.isnan(a) or a <= 0.0:
            continue
        if pend != 0 and pos == 0:
            pos = pend; entry = o[i]; pend = 0; stop = pstop; tgt = ptgt
            ei = i
            if (pos == 1 and stop >= entry) or (pos == -1 and stop <= entry):
                pos = 0
        if pos != 0:
            hit = (l[i] <= stop) if pos == 1 else (h[i] >= stop)
            won = (h[i] >= tgt) if pos == 1 else (l[i] <= tgt)
            if hit:
                px = o[i] if ((pos == 1 and o[i] < stop) or (pos == -1 and o[i] > stop)) else stop
                px += -SE if pos == 1 else SE
                P.append(pos * (px - entry) * PV - COMM - 2.0 * EC * PV); E.append(ei); X.append(i)
                pos = 0
            elif won:
                px = o[i] if ((pos == 1 and o[i] > tgt) or (pos == -1 and o[i] < tgt)) else tgt
                P.append(pos * (px - entry) * PV - COMM - 2.0 * EC * PV); E.append(ei); X.append(i)
                pos = 0
        if pos != 0 or pend != 0:
            continue
        if not (slo <= mod[i] < shi and slo <= mod[i + 1] < shi):
            continue
        for z in range(len(zs)):
            d = zd[z]
            if d == 1:
                if l[i] > zh[z] or l[i] < zl[z]:
                    continue
                if c[i] <= o[i] or c[i] <= zl[z]:
                    continue
                st = zl[z] - buf * a
            else:
                if h[i] < zl[z] or h[i] > zh[z]:
                    continue
                if c[i] >= o[i] or c[i] >= zh[z]:
                    continue
                st = zh[z] + buf * a
            risk = abs(c[i] - st)
            if risk <= 0.0 or risk > 8.0 * a:
                continue
            pend = d; pstop = st; ptgt = c[i] + d * tp_r * risk
            break
    return np.array(P), np.array(E), np.array(X)


def reference(H, L, bk, bm, dm, buf, tp_r, age_bars, zt=0, slo=0, shi=1440):
    dH = prep(H); dL = prep(L)
    zl, zh, zd, zb = build_zones(dH["o"], dH["h"], dH["l"], dH["c"], dH["atr"], bk, bm, dm, zt)
    ct = (dH["df"].index[zb] + pd.Timedelta(minutes=H)).values
    zs = np.searchsorted(dL["df"].index.values, ct, side="left").astype(np.int64)
    trad = ((dL["mod"] >= slo) & (dL["mod"] < shi)).astype(np.uint8)
    A = (S["pv"], S["tick"], 1.0, S["spread_t"], S["slip_t"], S["stop_slip_t"])
    return run(dL["o"], dL["h"], dL["l"], dL["c"], dL["sess"], trad, dL["atr"],
               zl, zh, zd, zs, buf, tp_r, 0, age_bars, 0, 0, *A)


if __name__ == "__main__":
    W = 96
    print("=" * W)
    print("PINE-SEMANTICS MIRROR vs THE ENGINE — trade for trade")
    print("=" * W)
    print("   4H zones, 60m confirmation, base 2 bars < 0.9 ATR, departure > 1.0 ATR, 24h,")
    print("   buffer 0.50 x ATR, 1.5R target, zones live 12 days (288 bars), both sides.\n")
    CFG = dict(H=240, L=60, bk=2, bm=0.9, dm=1.0, buf=0.5, tp_r=1.5, age_bars=288)
    p, e, x = pine_mirror(**CFG)
    rp, re_, rs, rw = reference(**CFG)
    print(f"   engine  {len(rp):>4} trades   net ${rp.sum():>9,.0f}")
    print(f"   mirror  {len(p):>4} trades   net ${p.sum():>9,.0f}")
    if len(p) == len(rp):
        dmax = np.abs(p - rp).max()
        emis = int((np.array(x) != re_).sum())
        print(f"   largest per-trade P&L difference: ${dmax:.4f}")
        print(f"   exit-bar mismatches: {emis}")
        print(f"\n   {'IDENTICAL' if dmax < 0.005 and emis == 0 else 'DIFFERENT'}")
    else:
        k = 0
        while k < min(len(p), len(rp)) and x[k] == re_[k]:
            k += 1
        print(f"   first divergence at trade {k}: mirror exit {x[k] if k < len(x) else '-'} "
              f"vs engine exit {re_[k] if k < len(re_) else '-'}")

    print()
    print("   array cap sensitivity — does the Pine's bounded zone list change anything?")
    for cap in (50, 100, 200, 400):
        q, _, _ = pine_mirror(**CFG, cap=cap)
        print(f"      cap {cap:>4} zones: {len(q):>4} trades, net ${q.sum():>9,.0f}")
    print()
    print("   peak simultaneous zones held (this is what the Pine array must fit):")
    dH = prep(240); dL = prep(60)
    zl, zh, zd, zb = build_zones(dH["o"], dH["h"], dH["l"], dH["c"], dH["atr"], 2, 0.9, 1.0, 0)
    ct = (dH["df"].index[zb] + pd.Timedelta(minutes=240)).values
    zs = np.searchsorted(dL["df"].index.values, ct, side="left")
    hist = np.zeros(len(dL["c"]) + 1, int)
    for s0 in zs:
        hist[s0:min(s0 + 289, len(hist))] += 1
    print(f"      {len(zs)} zones built over the sample; at most {hist.max()} alive at once")

    print()
    print("=" * 96)
    print("SECOND PRESET — the direction-neutral one, 4H zones on a 30m chart")
    print("=" * 96)
    print("   base 3 bars < 0.9 ATR, departure > 1.0 ATR, CONTINUATION origin, RTH 09:30-16:00,")
    print("   buffer 1.00 x ATR, 1.0R target, zones live 12 days (576 bars), both sides.\n")
    CFG2 = dict(H=240, L=30, bk=3, bm=0.9, dm=1.0, buf=1.0, tp_r=1.0, age_bars=576,
                zt=2, slo=570, shi=960)
    p2, e2, x2 = pine_mirror(**CFG2)
    r2, re2, _, _ = reference(**CFG2)
    print(f"   engine  {len(r2):>4} trades   net ${r2.sum():>9,.0f}")
    print(f"   mirror  {len(p2):>4} trades   net ${p2.sum():>9,.0f}")
    if len(p2) == len(r2):
        d2 = np.abs(p2 - r2).max(); m2 = int((np.array(x2) != re2).sum())
        print(f"   largest per-trade P&L difference: ${d2:.4f}   exit-bar mismatches: {m2}")
        print(f"\n   {'IDENTICAL' if d2 < 0.005 and m2 == 0 else 'DIFFERENT'}")
    else:
        k = 0
        while k < min(len(p2), len(r2)) and x2[k] == re2[k]:
            k += 1
        print(f"   first divergence at trade {k}")
