"""The IVB leg's daily P&L, for the book correlation matrix."""
from __future__ import annotations
import sys
import numpy as np
sys.path.insert(0, "research")
from bos_choch import prep
from ivb import session_context, run
import ivb_ladder as LAD

BEST = dict(tf=30, iv_min=60, use_ib=1, entry_mode=0, stop_mode=1, atr_mult=1.5,
            tgt_mode=1, tp=1.5, buf_atr=0.0, trend_mode=1, rng_filter=1,
            flat_min=945, side_mode=0)


def daily_pnl():
    """Per-session P&L of the best IVB version, aligned to the 30m session index."""
    d, us, poc, vah, val, ivh, ivl, pct, trend, sidx = LAD.setup(BEST["tf"], BEST["iv_min"])
    o, h, l, c, mod, atr_ = d["o"], d["h"], d["l"], d["c"], d["mod"].astype(np.int64), d["atr"]
    per = np.zeros(len(us))
    for i, s in enumerate(us):                       # one session at a time, so P&L is attributable
        m = sidx == i
        if m.sum() < 5:
            continue
        out = np.zeros((1, 20))
        run(o[m], h[m], l[m], c[m], mod[m], np.zeros(int(m.sum()), np.int64), atr_[m],
            vah[i:i+1], val[i:i+1], poc[i:i+1], ivh[i:i+1], ivl[i:i+1],
            pct[i:i+1], trend[i:i+1],
            BEST["iv_min"], BEST["use_ib"], BEST["entry_mode"], BEST["stop_mode"],
            BEST["atr_mult"], BEST["tgt_mode"], BEST["tp"], BEST["buf_atr"],
            BEST["trend_mode"], BEST["rng_filter"], BEST["flat_min"], BEST["side_mode"],
            10 ** 9, out, 0)
        per[i] = out[0, 1]
    return us, per


if __name__ == "__main__":
    us, per = daily_pnl()
    print(f"IVB leg: {int((per != 0).sum())} trading days, net ${per.sum():,.0f}")
    sys.path.insert(0, "research")
    from tf_60m import trades as bos_trades
    from sd_pine_mirror import pine_mirror
    IX = {s: i for i, s in enumerate(us)}

    def dly(p, ss):
        x = np.zeros(len(us))
        for v, q in zip(p, ss):
            if q in IX:
                x[IX[q]] += v
        return x

    legs = {}
    for nm, kw in [("BOS 30m", dict(m=30)), ("BOS 60m", dict(m=60, dn=0.0))]:
        p, e, s_, sess, _ = bos_trades(**kw)
        legs[nm] = dly(p, sess[e])
    for nm, cfg, L in [("S/D preset A", dict(H=240, L=60, bk=2, bm=0.9, dm=1.0, buf=0.5,
                                             tp_r=1.5, age_bars=288), 60),
                       ("S/D preset B", dict(H=240, L=30, bk=3, bm=0.9, dm=1.0, buf=1.0,
                                             tp_r=1.0, age_bars=576, zt=2, slo=570, shi=960), 30)]:
        p, e, x = pine_mirror(**cfg)
        dL = prep(L)
        legs[nm] = dly(p, dL["sess"][np.array(e)])
    legs["IVB"] = per
    names = list(legs)
    D = np.array([legs[k] for k in names])
    C = np.corrcoef(D)
    print()
    print(f"   {'':<16}" + "".join(f"{n[:11]:>13}" for n in names))
    for i, k in enumerate(names):
        print(f"   {k:<16}" + "".join(f"{C[i, j]:>13.2f}" for j in range(len(names))))
    ev = np.linalg.eigvalsh(C)[::-1]; ev = ev[ev > 0]; w = ev / ev.sum()
    print(f"\n   effective number of bets = {np.exp(-(w*np.log(w)).sum()):.2f} of {len(names)}"
          f"   PC1 {100*w[0]:.0f}%")
    cut = us[int(0.65 * len(us))]
    tot = D.sum(0)
    for nm, x in [("book without IVB", D[:4].sum(0)), ("book WITH IVB", tot)]:
        for bn, m in [("full", np.ones(len(us), bool)), ("research", us < cut), ("LOCKED", us >= cut)]:
            y = x[m]; eq = np.cumsum(y)
            dd = (np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()
            sh = y.mean() / y.std(ddof=1) * np.sqrt(252) if y.std() > 0 else 0
            print(f"   {nm:<20}{bn:<10}{y.sum():>10,.0f}  DD {dd:>7,.0f}  Sharpe {sh:>5.2f}")
