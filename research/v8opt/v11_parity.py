"""The V11-MARKET Pine's order model in Python, diffed against the engine.

A Pine port cannot be asserted by reading it. One unit, a market order at the next open and a
bracket placed with the entry make this nearly exact -- there is no ladder to re-anchor and no
limit fill to order against the exits, which were the two things that broke the earlier ports.
Anything that still differs is the bracket reading the SIGNAL bar's channel for the entry bar,
one bar staler than the engine.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
sys.path.insert(0,"research"); sys.path.insert(0,"research/turtleshort")
sys.path.insert(0,"research/turtle15"); sys.path.insert(0,"research/v8opt")
import eem  # noqa: E402


def run_pine(d, atr, C, mask, *, atr_mult=2.5, cost, flat_mod=None):
    o, h, l, c, mod = d["o"], d["h"], d["l"], d["c"], d["mod"]
    n = len(c); rows = []; exit_bar = -1; i = 1
    while i < n - 1:
        if (not mask[i] or not np.isfinite(atr[i]) or atr[i] <= 0 or i <= exit_bar
                or not np.isfinite(C["hi1"][i]) or h[i] <= C["hi1"][i]):
            i += 1
            continue
        eb = i + 1
        a = atr[i]
        px0 = o[eb]
        ch_sig = C["lo1"][i]                      # the bracket reads the SIGNAL bar
        pnl = -cost
        j = eb
        while j < n:
            a_stop = px0 - atr_mult * a
            ch = ch_sig if j == eb else C["lo1"][j - 1]
            lvl = a_stop if not np.isfinite(ch) else max(a_stop, ch)
            lvl = min(lvl, px0 if j == eb else c[j - 1])   # a sell stop cannot rest above market
            if l[j] <= lvl:
                pnl += lvl - px0
                rows.append((i, eb, j, px0, lvl, pnl, "stop"))
                break
            if flat_mod is not None and mod[j] >= flat_mod:
                k = min(j + 1, n - 1)
                pnl += o[k] - px0
                rows.append((i, eb, k, px0, o[k], pnl, "flat")); j = k
                break
            j += 1
        else:
            break
        exit_bar = j
        i = j + 1
    return pd.DataFrame(rows, columns=["sig","ent","exit","px0","exitpx","pnl","reason"])


if __name__ == "__main__":
    import nq, mirror
    K = nq.load(); d, atr, F, cost = K["d"], K["atr"], K["F"], K["cost"]
    C = mirror.channels(d["h"], d["l"], 55, 55, 20, 20)
    g = np.nan_to_num(F["adx"] >= 25.0, nan=False)
    P = dict(atr_mult=2.5, max_units=1, tp_r=None)
    print("V11-MARKET: engine vs the shipped script's order model, NQ 15m\n")
    hdr = (f"{'block':<12}{'eng n':>7}{'pine n':>8}{'sig match':>11}{'exit bar':>10}"
           f"{'eng PF':>9}{'pine PF':>9}{'eng pts':>10}{'pine pts':>10}{'corr':>8}")
    print(hdr); print("-" * len(hdr))
    for tag, m in [("research", g & K["res"]), ("LOCKED", g & K["lock"]), ("full", g)]:
        e = eem.run(d, atr, C, m, cost=cost, **P)
        q = run_pine(d, atr, C, m, cost=cost)
        se, sq = set(e.sig), set(q.sig)
        j = e.set_index("sig").join(q.set_index("sig"), how="inner", lsuffix="_e", rsuffix="_q")
        pf = lambda x: x[x > 0].sum() / abs(x[x < 0].sum())
        same_x = float((j["exit_e"] == j["exit_q"]).mean()) if len(j) else np.nan
        corr = np.corrcoef(j.pnl_e, j.pnl_q)[0, 1] if len(j) > 2 else np.nan
        print(f"{tag:<12}{len(e):>7}{len(q):>8}{len(se & sq)/max(len(se),1):>10.1%}{same_x:>10.1%}"
              f"{pf(e.pnl.to_numpy()):>9.2f}{pf(q.pnl.to_numpy()):>9.2f}"
              f"{e.pnl.mean():>+10.2f}{q.pnl.mean():>+10.2f}{corr:>8.4f}")
