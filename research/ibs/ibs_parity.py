"""The EA's order model written the slow way -- one M1/M15 bar at a time, exactly as the MQL5
`zfxProcessClosedBar` does it -- diffed trade-for-trade against the cached tensor in
`ibs_core`. A Pine or MQL port cannot be asserted by reading it (STUDY_PINE_PARITY), and
neither can a tensor that claims to be one."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from ibs import ibs_core as C  # noqa: E402


def naive(f, tf, market, entry=20.0, exit_=80.0, hold=5, mult=1.0, start=570, end=960,
          min_pct=75.0):
    c = C.cost_of(market)
    comm = getattr(c, "commission", 0.0)
    o, h, l, cl = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
    ix = f.index
    mod = (ix.hour * 60 + ix.minute).to_numpy()
    day = ix.normalize().to_numpy()
    expected = (end - start) // tf
    need = max(1, int(np.ceil(expected * min_pct / 100.0)))
    cur_day = None
    sh, sl, sc, n = -np.inf, np.inf, 0.0, 0
    pending = None          # ("buy", stop_dist) to fill at the next bar's open
    pos = None              # dict(entry, stop, held)
    trades = []
    last_in_session_bar = None
    for b in range(len(o)):
        # fills at the open of this bar, first
        if pending is not None:
            kind = pending[0]
            mm = mod[b]
            half = (c.spread_rth if 570 <= mm < 960 else
                    (c.spread_pre if 240 <= mm < 1080 else c.spread_off)) / 2.0
            if kind == "buy":
                px = o[b] + half + c.slip_entry
                pos = dict(entry=px, stop=o[b] - pending[1], held=0, ent_bar=b,
                           ent_day=pending[2])
            else:
                px = o[b] - half - c.slip_entry
                trades.append(dict(ent=pos["ent_day"], ex=pending[2], pnl=px - pos["entry"] - comm,
                                   stopped=0))
                pos = None
            pending = None
        # broker-side stop, live on every bar including the fill bar
        if pos is not None and l[b] <= pos["stop"]:
            fill = pos["stop"] if o[b] >= pos["stop"] else o[b]
            m = mod[b]
            tier = c.spread_rth if 570 <= m < 960 else (c.spread_pre if 240 <= m < 1080
                                                        else c.spread_off)
            trades.append(dict(ent=pos["ent_day"], ex=None, ex_bar=b,
                               pnl=fill - pos["entry"] - c.slip_stop - tier / 2.0 - comm,
                               stopped=1))
            pos = None
        if day[b] != cur_day:
            cur_day = day[b]
            sh, sl, sc, n = -np.inf, np.inf, 0.0, 0
        m = mod[b]
        if m < start or m >= end:
            continue
        sh = max(sh, h[b]); sl = min(sl, l[b]); sc = cl[b]; n += 1
        if m != end - tf:
            continue
        if n < need or sh <= sl:
            continue
        ibs = (sc - sl) / (sh - sl) * 100.0
        if pos is not None:
            pos["held"] += 1
            if ibs > exit_ or pos["held"] >= hold:
                pending = ("sell", 0.0, cur_day)
            continue
        if ibs < entry:
            pending = ("buy", (sh - sl) * mult, cur_day)
    return pd.DataFrame(trades)


def main(markets=("US100", "US30", "NQ"), cells=None):
    cells = cells or [C.DEFAULT, dict(entry=30.0, exit=70.0, hold=2, mult=0.5),
                      dict(entry=15.0, exit=90.0, hold=10, mult=3.0)]
    for mk in markets:
        f, tf = C.load(mk)
        s = C.sessions(f, tf)
        B = C.build(f, tf, s, mk)
        mask = np.ones(len(s), np.int64)
        for cell in cells:
            t = C.cell_trades(B, mask, cell)
            nv = naive(f, tf, mk, cell["entry"], cell["exit"], cell["hold"], cell["mult"])
            # the tensor cannot take a trade whose exit falls past the last session; the naive
            # walk leaves such a trade open. Compare closed trades only.
            nv = nv[nv["ent"] <= s["date"].to_numpy()[t["ent"].max()]] if len(t) else nv
            a = pd.DataFrame(dict(ent=s["date"].to_numpy()[t["ent"]], pnl=t["pnl"].to_numpy(),
                                  st=t["stopped"].to_numpy()))
            b = pd.DataFrame(dict(ent=pd.to_datetime(nv["ent"]), pnl=nv["pnl"].to_numpy(),
                                  st=nv["stopped"].to_numpy()))
            mg = a.merge(b, on="ent", how="outer", suffixes=("_t", "_n"), indicator=True)
            both = mg[mg["_merge"] == "both"]
            same = int(np.sum(np.isclose(both["pnl_t"], both["pnl_n"], atol=1e-6)))
            print(f"{mk:<6} {cell}  tensor {len(a):>4}  naive {len(b):>4}  matched {len(both):>4}"
                  f"  identical pnl {same:>4}  stop-flag agree "
                  f"{int((both['st_t'] == both['st_n']).sum()):>4}"
                  f"  corr {np.corrcoef(both['pnl_t'], both['pnl_n'])[0, 1]:.6f}")
            bad = mg[mg["_merge"] != "both"]
            if len(bad):
                print("      unmatched:", bad[["ent", "_merge"]].head(6).to_string(index=False))


if __name__ == "__main__":
    main()
