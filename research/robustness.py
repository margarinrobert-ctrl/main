"""Why do two of these three strategies fail to reproduce on a different data feed?

The report is that the Initial Balance script reproduces on TradingView and the IVB and
supply/demand scripts do not. That is a controlled experiment, so it is treated as one.

THE HYPOTHESIS. The three strategies differ in HOW THEY DECIDE, not only in what they trade:

  Initial Balance  arms a LIMIT ORDER at a computed price level. It fills if and only if price
                   traded there. Two data feeds that disagree by a tick still agree about whether
                   a level 30 points away was reached.
  IVB              fires when a bar's CLOSE crosses a threshold. Near the threshold, one tick of
                   disagreement between feeds flips the signal on or off entirely -- and the
                   threshold moves too, because it is level + 0.15 x ATR.
  Supply/demand    the same close-threshold decision, plus zones built from hand-aggregated 4H
                   bars and carried for twelve days, so a disagreement compounds forward.

If that is right, perturbing the data by a fraction of a tick should barely move the limit-order
strategy and should scatter the close-threshold ones. This measures exactly that.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from bos_choch import prep

PV = 2.0; TICK = 0.25; COMM = 1.0
EC = 2.0 * TICK; SE = 1.0 * TICK
RTH = 570


def jitter(d, rng, ticks=0.5):
    """A plausible model of 'the same market, a different feed': every bar's OHLC moved by a
    fraction of a tick, independently. Half a tick is smaller than the real disagreement between
    two futures data vendors."""
    o, h, l, c = d["o"].copy(), d["h"].copy(), d["l"].copy(), d["c"].copy()
    n = len(c)
    e = rng.normal(0.0, ticks * TICK, n)
    o += e; c += e
    h = np.maximum(np.maximum(h + e, o), c)
    l = np.minimum(np.minimum(l + e, o), c)
    return o, h, l, c


def sim_ivb(o, h, l, c, mod, sess, atr_, iv_min=15, buf_atr=0.15, tp_r=1.0, flat=900):
    """Close crosses a threshold; fill at the next open."""
    n = len(c); ivh = ivl = np.nan
    pos = 0; entry = stop = tgt = 0.0; pend = 0; ps = pt = 0.0
    took = 0; sp = -1; P = []
    for i in range(1, n - 1):
        m = mod[i]
        if sess[i] != sp:
            ivh = ivl = np.nan; pos = 0; pend = 0; took = 0; sp = sess[i]
        if RTH <= m < RTH + iv_min:
            ivh = h[i] if np.isnan(ivh) else max(ivh, h[i])
            ivl = l[i] if np.isnan(ivl) else min(ivl, l[i])
        if pend != 0 and pos == 0:
            pos = pend; entry = o[i]; pend = 0; stop = ps; tgt = pt
            if (pos == 1 and stop >= entry) or (pos == -1 and stop <= entry):
                pos = 0
        if pos != 0:
            hit = (l[i] <= stop) if pos == 1 else (h[i] >= stop)
            won = (h[i] >= tgt) if pos == 1 else (l[i] <= tgt)
            px = 0.0; done = False
            if hit:
                px = o[i] if ((pos == 1 and o[i] < stop) or (pos == -1 and o[i] > stop)) else stop
                px += -SE if pos == 1 else SE; done = True
            elif won:
                px = o[i] if ((pos == 1 and o[i] > tgt) or (pos == -1 and o[i] < tgt)) else tgt
                done = True
            elif m >= flat:
                px = c[i]; done = True
            if done:
                P.append(pos * (px - entry) * PV - COMM - 2 * EC * PV); pos = 0
        if pos != 0 or pend != 0 or took >= 1 or not (RTH + iv_min <= m < flat):
            continue
        a = atr_[i]
        if np.isnan(a) or a <= 0 or np.isnan(ivh) or ivh <= ivl:
            continue
        d = 1 if c[i] > ivh + buf_atr * a else (-1 if c[i] < ivl - buf_atr * a else 0)
        if d == 0:
            continue
        st = ivl if d == 1 else ivh
        if (d == 1 and st >= c[i]) or (d == -1 and st <= c[i]):
            continue
        rk = abs(c[i] - st)
        if rk <= 0 or rk > 8 * a:
            continue
        pend = d; ps = st; pt = c[i] + d * tp_r * rk; took += 1
    return np.array(P)


def sim_ib(o, h, l, c, mod, sess, retr=0.50, stop_pct=0.80, rr=2.0, flat=719):
    """Break the IB, then a LIMIT ORDER waits for a retracement into the range."""
    n = len(c); ibh = ibl = np.nan
    pos = 0; entry = stop = tgt = 0.0
    armed = 0; ax = astop = atgt = 0.0
    took = 0; sp = -1; P = []
    for i in range(1, n - 1):
        m = mod[i]
        if sess[i] != sp:
            ibh = ibl = np.nan; pos = 0; armed = 0; took = 0; sp = sess[i]
        if RTH <= m < RTH + 60:
            ibh = h[i] if np.isnan(ibh) else max(ibh, h[i])
            ibl = l[i] if np.isnan(ibl) else min(ibl, l[i])
        if pos != 0:
            hit = (l[i] <= stop) if pos == 1 else (h[i] >= stop)
            won = (h[i] >= tgt) if pos == 1 else (l[i] <= tgt)
            px = 0.0; done = False
            if hit:
                px = o[i] if ((pos == 1 and o[i] < stop) or (pos == -1 and o[i] > stop)) else stop
                px += -SE if pos == 1 else SE; done = True
            elif won:
                px = o[i] if ((pos == 1 and o[i] > tgt) or (pos == -1 and o[i] < tgt)) else tgt
                done = True
            elif m >= flat:
                px = c[i]; done = True
            if done:
                P.append(pos * (px - entry) * PV - COMM - 2 * EC * PV); pos = 0
        if pos != 0 or took >= 1 or not (RTH + 60 <= m < flat):
            continue
        if np.isnan(ibh) or ibh <= ibl:
            continue
        rng = ibh - ibl
        if armed != 0:
            d = armed
            touched = (l[i] <= ax) if d == 1 else (h[i] >= ax)
            if touched:
                pos = d; entry = ax; stop = astop; tgt = atgt; took += 1; armed = 0
            continue
        d = 1 if c[i] > ibh else (-1 if c[i] < ibl else 0)
        if d == 0:
            continue
        lvl = ibh if d == 1 else ibl
        ax = lvl - d * retr * rng
        astop = lvl - d * stop_pct * rng
        rk = abs(ax - astop)
        if rk <= 0:
            continue
        atgt = ax + d * rr * rk
        armed = d
    return np.array(P)


if __name__ == "__main__":
    d15 = prep(15); d5 = prep(5)
    rng = np.random.default_rng(20260823)
    sys.path.insert(0, "research")
    from sd_pine_mirror import pine_mirror as sd_mirror

    print("=" * 96)
    print("PERTURBATION TEST — the same market, a data feed that disagrees by half a tick")
    print("=" * 96)
    print("   Every bar's OHLC is moved by a Gaussian with a 0.5-tick standard deviation. That is")
    print("   SMALLER than the real disagreement between two futures data vendors. 40 draws.\n")
    print(f"   {'strategy':<34}{'baseline $':>12}{'mean $':>10}{'sd $':>9}"
          f"{'worst $':>10}{'% of draws +':>14}{'sd / mean':>11}")

    base_ivb = sim_ivb(d15["o"], d15["h"], d15["l"], d15["c"], d15["mod"], d15["sess"], d15["atr"])
    base_ib = sim_ib(d5["o"], d5["h"], d5["l"], d5["c"], d5["mod"], d5["sess"])
    rows = []
    for nm, fn, d in [("IVB  (close crosses a level)", "ivb", d15),
                      ("Initial Balance  (limit order)", "ib", d5)]:
        outs = []
        for k in range(40):
            oo, hh, ll, cc = jitter(d, rng)
            if fn == "ivb":
                p = sim_ivb(oo, hh, ll, cc, d["mod"], d["sess"], d["atr"])
            else:
                p = sim_ib(oo, hh, ll, cc, d["mod"], d["sess"])
            outs.append(p.sum())
        outs = np.array(outs)
        b = base_ivb.sum() if fn == "ivb" else base_ib.sum()
        rows.append((nm, b, outs))
        print(f"   {nm:<34}{b:>12,.0f}{outs.mean():>10,.0f}{outs.std():>9,.0f}"
              f"{outs.min():>10,.0f}{100*(outs>0).mean():>13.0f}%"
              f"{abs(outs.std()/outs.mean()) if outs.mean() else np.nan:>11.2f}")

    # supply/demand runs on its own mirror, which builds 4H bars internally
    d60 = prep(60)
    outs = []
    for k in range(12):
        oo, hh, ll, cc = jitter(d60, rng)
        sv = (d60["o"].copy(), d60["h"].copy(), d60["l"].copy(), d60["c"].copy())
        d60["o"][:], d60["h"][:], d60["l"][:], d60["c"][:] = oo, hh, ll, cc
        try:
            p, e, x = sd_mirror(H=240, L=60, bk=2, bm=0.9, dm=1.0, buf=0.5, tp_r=1.5,
                                age_bars=288)
            outs.append(p.sum())
        finally:
            d60["o"][:], d60["h"][:], d60["l"][:], d60["c"][:] = sv
    outs = np.array(outs)
    p0, _, _ = sd_mirror(H=240, L=60, bk=2, bm=0.9, dm=1.0, buf=0.5, tp_r=1.5, age_bars=288)
    print(f"   {'Supply/demand  (zones + close)':<34}{p0.sum():>12,.0f}{outs.mean():>10,.0f}"
          f"{outs.std():>9,.0f}{outs.min():>10,.0f}{100*(outs>0).mean():>13.0f}%"
          f"{abs(outs.std()/outs.mean()) if outs.mean() else np.nan:>11.2f}")
    print("\n   'sd / mean' is the coefficient of variation: how much of the result is noise.")
