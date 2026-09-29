"""Can the strategy be made to show PF 2-3? Yes, on paper -- and here is exactly how, and why not live.

(a) TRADINGVIEW'S MECHANISM: fill at the intrabar EMA8 touch, on bars where the rule confirms at the
    close. The fill is conditioned on a %K/%D cross that has not happened yet -- lookahead.
(b) THE IMPLEMENTABLE VERSION: a resting limit at the EMA8 that fills on EVERY eligible touch,
    because at touch time the cross is unknown. One live order, one position.
Both walked on the true 1-minute path, research block, NQ 5m signals."""
from __future__ import annotations
import os, sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s89_core as M
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 122 + f"\n{t}\n" + "=" * 122)
def hdr(): print(f"  {'':60s}{'n':>6s}{'PF':>8s}{'win%':>7s}{'%/trade':>10s}{'$ 5 MNQ':>11s}   exits")
def row(nm, t):
    s = M.stats(t); mix = t["exit"].value_counts(normalize=True).mul(100).round(0).to_dict() if len(t) else {}
    print(f"  {nm:60s}{s['n']:>6d}{s['pf']:>8.3f}{s['win']:>7.1f}{s['pct']:>10.4f}{s['usd_tot']:>11,.0f}   " + " ".join(f"{k}{int(v)}%" for k, v in mix.items()))

D5 = M.build("NQ", 5); D1 = M.build("NQ", 1)
sig5 = M.signals(D5); n5 = D5["n"]
t5 = pd.DatetimeIndex(D5["ts"]); t1 = D1["ts"]
start1 = np.searchsorted(t1, t5.to_numpy(), side="left")                 # first 1m bar of each 5m bar
end1 = np.searchsorted(t1, (t5 + pd.Timedelta(minutes=5)).to_numpy(), side="left")  # one past the last
ins5 = (D5["mod"] >= M.CFG["sess_start"]) & (D5["mod"] < M.CFG["sess_end"])
res5 = D5["blocks"]["research"]
l1, h1 = D1["l"], D1["h"]

def touch_entries(confirmed_only, side):
    """1m-indexed side/fill/atr arrays for the touch entries of one side."""
    side1 = np.zeros(D1["n"], np.int64); fill = np.full(D1["n"], np.nan); atr1 = np.full(D1["n"], np.nan)
    for i in range(300, n5 - 2):
        if not (ins5[i] and res5[i]): continue
        if confirmed_only and sig5[i] != side: continue
        # eligibility from the LAST COMPLETED 5m bar -- what a resting limit could know
        j = i - 1
        if side == 1:
            if not (D5["c"][j] > D5["e_tr"][j] and D5["k_lo"][j] <= M.CFG["os_lvl"] and (D5["sw_hi"][j] - D5["e_f"][j]) >= M.CFG["min_pb"]): continue
            lvl = D5["e_f"][j]
        else:
            if not (D5["c"][j] < D5["e_tr"][j] and D5["k_hi"][j] >= M.CFG["ob_lvl"] and (D5["e_f"][j] - D5["sw_lo"][j]) >= M.CFG["min_pb"]): continue
            lvl = D5["e_f"][j]
        if not np.isfinite(lvl) or not np.isfinite(D5["atr"][j]): continue
        a, b = start1[i], end1[i]
        if b <= a: continue
        seg = l1[a:b] if side == 1 else h1[a:b]
        hit = np.flatnonzero(seg <= lvl) if side == 1 else np.flatnonzero(seg >= lvl)
        if len(hit) == 0: continue
        k = a + hit[0]
        side1[k] = side; fill[k] = lvl; atr1[k] = D5["atr"][j]
    return side1, fill, atr1

line("THE SCREENSHOT'S NUMBER, REPRODUCED -- and taken apart. NQ 5m signals, exits on the true 1-minute path, research block")
for cfg_nm, cfg in (("as configured: 15/8 trail, 1.5/2.5 ATR", M.CFG), ("trail OFF: 1.5/2.5 ATR bracket", dict(M.CFG, trail_on=0))):
    print(f"\n  [{cfg_nm}]"); hdr()
    # bar-close reference on the 1m path (from run_tv)
    t5c = t5 + pd.Timedelta(minutes=5); i1 = np.searchsorted(t1, t5c.to_numpy(), side="left") - 1
    ok = (i1 >= 0) & (i1 < D1["n"] - 2); s_bc = np.zeros(D1["n"], np.int64); a_bc = np.full(D1["n"], np.nan)
    s_bc[i1[ok]] = sig5[ok]; a_bc[i1[ok]] = D5["atr"][ok]
    row("bar-close fill at the next open (a live market order)", M.run(dict(D1, atr=a_bc), cfg=cfg, side_override=s_bc).query("block=='research'"))
    for lab, conf in (("(a) fill AT the EMA8 touch, only on bars that CONFIRM at the close", True),
                      ("(b) resting limit at the EMA8, fills on EVERY eligible touch", False)):
        sL, fL, aL = touch_entries(conf, 1); sS, fS, aS = touch_entries(conf, -1)
        side1 = np.where(sL == 1, 1, np.where(sS == -1, -1, 0)); fill = np.where(sL == 1, fL, fS); atr1 = np.where(sL == 1, aL, aS)
        t = M.run(dict(D1, atr=atr1), cfg=cfg, side_override=side1, fill_px=fill); t = t[t.block == "research"]
        row(lab, t)
        if conf:
            # how far below the next open did the touch fill?
            j = t["entry_bar"].to_numpy(); nxt5 = np.searchsorted(t5.to_numpy(), t1[j], side="right")
            nxt_open = D5["o"][np.minimum(nxt5, n5 - 1)]
            adv = t["side"].to_numpy() * (nxt_open - t["entry_px"].to_numpy())
            print(f"      touch fill sits a median {np.median(adv):+.2f} pts ({np.median(adv)/np.median(atr1[j]):+.2f} ATR) better than the bar-close fill -- that is the whole difference")
print("\n  (a) is what an unguarded script does with an intrabar execution option ticked: it buys the touch on bars it")
print("  will only know CONFIRMED at the close. (b) is the only order that can buy the touch, and it cannot see the")
print("  close either -- so it also fills the touches that never confirm. The gap between them is lookahead, and it")
print("  is the screenshot.")
