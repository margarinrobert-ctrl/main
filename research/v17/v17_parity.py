"""The V17 Pine's order model AND its prior-session high, both diffed against the engine.

Two things have to match here, not one. The order model is V16's, already exact. The new risk is
the FEATURE: research reads the last completed RTH session's high by aggregating 1-minute bars in
`daily_trend.py` and mapping each intraday bar to the last session whose close timestamp is
strictly earlier. A script cannot do that -- it has to accumulate the session high on the chart's
own bars and freeze it when the session ends. If those two constructions disagree by a bar or by a
tick, every number in the study belongs to a rule the script does not run.

So the Pine-side series is built here from the timeframe's bars, exactly as the script does, and
compared element by element against the research array before any trade is simulated.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v17")
import v16core as C          # noqa: E402

RTH_LO, RTH_HI = 570, 960


def pine_session_high(P):
    """`lastHi` as the script builds it: accumulate the RTH high, freeze it when the session ends.

    The freeze lands on the FIRST bar outside the session, and that bar may use it -- which is the
    same instant the research mapping makes it visible, because `known_at` is the last minute
    INSIDE the session and the comparison is strictly-before.
    """
    mod, h = P["mod"], P["h"]
    n = len(h)
    out = np.full(n, np.nan)
    cur = np.nan
    last = np.nan
    for i in range(n):
        ins = RTH_LO <= mod[i] < RTH_HI
        prev = RTH_LO <= mod[i - 1] < RTH_HI if i else False
        if ins and not prev:
            cur = h[i]
        elif ins:
            cur = h[i] if not np.isfinite(cur) else max(cur, h[i])
        if (not ins) and prev and np.isfinite(cur):
            last = cur
        out[i] = last
    return out


def run_pine(P, pdh, exit_n=20, stop_mult=2.5, adx_min=25.0, block=None, use_pdh=True):
    o, h, l, c, atr, adx = P["o"], P["h"], P["l"], P["c"], P["atr"], P["adx"]
    ent, ex = P["ent_hi"], P["ex_lo"]
    fee2, f_taker, f_stop = P["fee2"], P["f_taker"], P["f_stop"]
    n = len(c)
    rows = []
    i = 1
    closed_bar = -1
    while i < n - 1:
        ok = (np.isfinite(atr[i]) and atr[i] > 0 and np.isfinite(ent[i]) and h[i] > ent[i]
              and (block is None or block[i]) and i > closed_bar
              and np.nan_to_num(adx[i], nan=-1.0) >= adx_min
              and (not use_pdh or (np.isfinite(pdh[i]) and c[i] >= pdh[i])))
        if not ok:
            i += 1
            continue
        a = atr[i]
        eb = i + 1
        px0 = o[eb]
        stop = px0 - stop_mult * a
        j = eb
        while j < n:
            ch = ex[j]
            lvl = stop if not np.isfinite(ch) else max(stop, ch)
            lvl = min(lvl, c[j - 1])            # a sell stop cannot rest above the market
            if l[j] <= lvl:
                pnl = (lvl - px0) - fee2 - f_taker[eb] - f_stop[j]
                rows.append((i, eb, j, px0, lvl, pnl / (stop_mult * a)))
                break
            j += 1
        else:
            break
        closed_bar = j
        i = j + 1
    return pd.DataFrame(rows, columns=["sig", "ent", "exit", "px0", "exitpx", "R"])


if __name__ == "__main__":
    import v17run as R
    import v17feat as F
    import v17judge as J
    P, daily, res, lock = R.context()
    pool = F.build(P, entry_n=R.SPEC["entry_n"], daily=daily)

    print("A. THE FEATURE ITSELF -- the script's session tracker vs the research mapping\n")
    ph = pine_session_high(P)
    both = np.isfinite(ph) & np.isfinite(P["pdh"])
    same = np.isclose(ph[both], P["pdh"][both])
    print(f"   bars where both are defined : {int(both.sum())} of {len(ph)}")
    print(f"   identical to the tick        : {same.mean():.4%}")
    if not same.all():
        d = np.flatnonzero(both)[~same][:5]
        for k in d:
            print(f"      bar {k} mod {P['mod'][k]}: pine {ph[k]} vs research {P['pdh'][k]}")
    # and the condition they produce
    cp = np.isfinite(ph) & (P["c"] >= ph)
    cr = np.isfinite(P["pdh"]) & (P["c"] >= P["pdh"])
    print(f"   the CONDITION agrees on      : {float((cp == cr).mean()):.4%} of bars\n")

    print("B. THE ORDER MODEL -- engine vs the script, with the filter on and off\n")
    hdr = (f"   {'case':<30}{'eng n':>7}{'pine n':>8}{'sig match':>11}{'exit bar':>10}"
           f"{'eng R':>9}{'pine R':>9}{'corr':>9}")
    print(hdr); print("   " + "-" * (len(hdr) - 3))
    for bn, bb in (("research", res), ("locked", lock)):
        for lab, use in ((f"base only, {bn}", False), (f"+ prior-session high, {bn}", True)):
            O, idx = J.leg(P, pool, bb, "C_dist_pdh" if use else None, 0.0, +1)
            e = pd.DataFrame(dict(sig=O["sig"][idx], exit=O["xb"][idx], R=O["R"][idx]))
            q = run_pine(P, ph, block=bb, use_pdh=use)
            j = e.set_index("sig").join(q.set_index("sig"), how="inner", lsuffix="_e", rsuffix="_q")
            sx = float((j["exit_e"] == j["exit_q"]).mean()) if len(j) else np.nan
            cr2 = np.corrcoef(j.R_e, j.R_q)[0, 1] if len(j) > 2 else np.nan
            ov = len(set(e.sig) & set(q.sig)) / max(len(set(e.sig)), 1)
            print(f"   {lab:<30}{len(e):>7}{len(q):>8}{ov:>10.1%}{sx:>10.1%}"
                  f"{e.R.sum():>+9.1f}{q.R.sum():>+9.1f}{cr2:>9.4f}")
