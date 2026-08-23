"""Every leg's trades in one place, with the information an execution model needs.

Each leg returns, per trade: P&L under the engine's flat cost model, the entry bar index, the
entry timestamp, the session, the side, and the ATR at entry. Everything downstream -- the
execution overlay, walk-forward, Monte Carlo and portfolio construction -- works off this.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from bos_choch import prep
from tf_60m import trades as bos_trades
from sd_pine_mirror import pine_mirror
from ivb import session_context, run as ivb_run

PV = 2.0
TICK = 0.25

SD_A = dict(H=240, L=60, bk=2, bm=0.9, dm=1.0, buf=0.5, tp_r=1.5, age_bars=288)
SD_B = dict(H=240, L=30, bk=3, bm=0.9, dm=1.0, buf=1.0, tp_r=1.0, age_bars=576,
            zt=2, slo=570, shi=960)
IVB_BEST = dict(tf=30, iv_min=60, use_ib=1, entry_mode=0, stop_mode=1, atr_mult=1.5,
                tgt_mode=1, tp=1.5, buf_atr=0.0, trend_mode=1, rng_filter=1,
                flat_min=945, side_mode=0)


def _pack(tf, pnl, ent, side):
    d = prep(tf)
    ent = np.asarray(ent, np.int64)
    return dict(pnl=np.asarray(pnl, float), ent=ent, side=np.asarray(side, np.int64),
                sess=d["sess"][ent], mod=d["mod"][ent], atr=d["atr"][ent],
                time=d["df"].index[ent], tf=tf)


def leg_bos(m, **kw):
    p, e, s_, sess, _ = bos_trades(m=m, **kw)
    return _pack(m, p, e, s_)


def leg_sd(cfg, L):
    p, e, x = pine_mirror(**cfg)
    e = np.asarray(e, np.int64)
    d = prep(L)
    # recover the side from the direction of the move against the entry bar's close
    side = np.sign(np.asarray(p, float))
    return _pack(L, p, e, side)


def leg_ivb():
    import ivb_ladder as LAD
    d, us, poc, vah, val, ivh, ivl, pct, trend, sidx = LAD.setup(IVB_BEST["tf"],
                                                                 IVB_BEST["iv_min"])
    o, h, l, c, mod, atr_ = d["o"], d["h"], d["l"], d["c"], d["mod"].astype(np.int64), d["atr"]
    pnl = []; ent = []; side = []
    B = IVB_BEST
    for i in range(len(us)):
        m = np.where(sidx == i)[0]
        if len(m) < 5:
            continue
        out = np.zeros((1, 20))
        ivb_run(o[m], h[m], l[m], c[m], mod[m], np.zeros(len(m), np.int64), atr_[m],
                vah[i:i+1], val[i:i+1], poc[i:i+1], ivh[i:i+1], ivl[i:i+1],
                pct[i:i+1], trend[i:i+1],
                B["iv_min"], B["use_ib"], B["entry_mode"], B["stop_mode"], B["atr_mult"],
                B["tgt_mode"], B["tp"], B["buf_atr"], B["trend_mode"], B["rng_filter"],
                B["flat_min"], B["side_mode"], 10 ** 9, out, 0)
        if out[0, 0] >= 1:
            pnl.append(out[0, 1])
            # the entry is the first bar after the initial value window in that session
            after = m[mod[m] >= 570 + B["iv_min"]]
            ent.append(int(after[0]) if len(after) else int(m[0]))
            side.append(int(np.sign(out[0, 1])) or 1)
    return _pack(B["tf"], pnl, ent, side)


def all_legs():
    return {
        "BOS 30m": leg_bos(30),
        "BOS 60m": leg_bos(60, dn=0.0),
        "S/D A": leg_sd(SD_A, 60),
        "S/D B": leg_sd(SD_B, 30),
        "IVB": leg_ivb(),
    }


if __name__ == "__main__":
    L = all_legs()
    print(f"   {'leg':<10}{'trades':>8}{'net $':>10}{'first':>13}{'last':>13}"
          f"{'% outside RTH':>15}")
    for k, v in L.items():
        out_rth = ((v["mod"] < 570) | (v["mod"] >= 960)).mean()
        print(f"   {k:<10}{len(v['pnl']):>8}{v['pnl'].sum():>10,.0f}"
              f"{str(v['time'][0].date()):>13}{str(v['time'][-1].date()):>13}"
              f"{100*out_rth:>14.1f}%")
