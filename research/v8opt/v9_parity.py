"""The V9-PROP Pine's ORDER MODEL in Python, diffed against the research engine.

A Pine port cannot be asserted by reading it -- see docs/ib/STUDY_PINE_PARITY.md, where exactly
that assumption shipped a script that did not compile and had three wrong rules. This transcribes
what the SCRIPT can do -- orders placed at a bar's close and live from the next bar, a bracket
placed with the entry so the entry bar is covered, a trailing level that may only read bars that
have closed -- and runs it against `eem.run` on the same bars.

ONE UNIT MAKES THIS NEARLY EXACT. The whole gap in the four-finalist port was the ladder: the
engine adds rungs and re-anchors the stop to each new fill WITHIN a bar, which Pine cannot see
until the bar closes. With no ladder there is nothing to re-anchor, so the two should agree
closely rather than approximately -- and if they do not, the port is wrong, not "structurally
different".
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/turtleshort")
sys.path.insert(0, "research/turtle15"); sys.path.insert(0, "research/v8opt")
import eem  # noqa: E402


def run_pine(d, atr, C, mask, *, atr_mult=2.0, cost, tp_pts=200.0, part_frac=None,
             part_pts=None, trail_pts=100.0, flat_mod=None, skip_win=True):
    """One unit, bracketed from the signal bar, flattened at `flat_mod`'s NEXT open."""
    o, h, l, c, mod = d["o"], d["h"], d["l"], d["c"], d["mod"]
    n = len(c)
    rows = []
    last_win = False
    exit_bar = -1
    i = 1
    while i < n - 1:
        if (not mask[i] or not np.isfinite(atr[i]) or atr[i] <= 0 or i <= exit_bar
                or (flat_mod is not None and mod[i] >= flat_mod)):
            i += 1
            continue
        s2 = np.isfinite(C["hi2"][i]) and h[i] > C["hi2"][i]
        s1 = np.isfinite(C["hi1"][i]) and h[i] > C["hi1"][i]
        sys_on = 2 if s2 else (1 if s1 else 0)
        if sys_on == 0:
            i += 1
            continue
        if sys_on == 1 and skip_win and last_win:
            last_win = False
            i += 1
            continue

        eb = i + 1
        a = atr[i]
        px0 = o[eb]
        size = 1.0
        pnl = -cost
        peak_prev = px0
        ch_sig = C["lo1"][i] if sys_on == 1 else C["lo2"][i]   # bracket reads the SIGNAL bar
        part_done = False
        j = eb
        while j < n:
            # levels live on THIS bar were fixed at the previous close (or with the entry)
            a_stop = px0 - atr_mult * a
            if j == eb:
                lvl = a_stop if not np.isfinite(ch_sig) else max(a_stop, ch_sig)
            else:
                ch = C["lo1"][j - 1] if sys_on == 1 else C["lo2"][j - 1]
                lvl = a_stop if not np.isfinite(ch) else max(a_stop, ch)
                if trail_pts is not None:
                    lvl = max(lvl, peak_prev - trail_pts)
            hit_sl = l[j] <= lvl
            if (part_frac is not None and part_pts is not None and not part_done
                    and not hit_sl and h[j] >= px0 + part_pts):
                closed = size * part_frac
                pnl += part_pts * closed - 0.5 * cost * closed
                size -= closed
                part_done = True
            if h[j] >= px0 + tp_pts and not hit_sl:
                pnl += tp_pts * size
                rows.append((i, eb, j, px0, px0 + tp_pts, pnl, "tp"))
                break
            if flat_mod is not None and mod[j] >= flat_mod:
                # a market order placed at THIS close fills at the NEXT open
                k = min(j + 1, n - 1)
                pnl += (o[k] - px0) * size
                rows.append((i, eb, k, px0, o[k], pnl, "flat"))
                j = k
                break
            if hit_sl:
                pnl += (lvl - px0) * size
                rows.append((i, eb, j, px0, lvl, pnl, "stop"))
                break
            peak_prev = max(peak_prev, h[j])
            j += 1
        else:
            break
        last_win = pnl > 0
        exit_bar = j
        i = j + 1
    return pd.DataFrame(rows, columns=["sig", "ent", "exit", "px0", "exitpx", "pnl", "reason"])


if __name__ == "__main__":
    import ctx as CX
    K = CX.load()
    d, atr, C, g, cost, mod = K["d"], K["atr"], K["C"], K["gate"], K["cost"], K["mod"]
    w = CX.win(mod, 420, 600)
    CFG = dict(atr_mult=2.0, tp_pts=200, trail_pts=100, max_units=1)
    print("V9-PROP: research engine vs the shipped script's order model, US30 15m\n")
    hdr = (f"{'block':<22}{'eng n':>7}{'pine n':>8}{'sig match':>11}{'eng PF':>9}{'pine PF':>9}"
           f"{'eng pts':>10}{'pine pts':>10}{'corr':>8}")
    print(hdr); print("-" * len(hdr))
    for tag, m, fl in [("all hours train", g & K["train"], None), ("all hours OOS", g & K["oos"], None),
                       ("all hours full", g, None), ("window full", g & w, 600)]:
        e = eem.run(d, atr, C, m, cost=cost, flat_mod=fl, **CFG)
        q = run_pine(d, atr, C, m, cost=cost, flat_mod=fl)
        se, sq = set(e.sig), set(q.sig)
        j = e.set_index("sig").join(q.set_index("sig"), how="inner", lsuffix="_e", rsuffix="_q")
        pf = lambda x: x[x > 0].sum() / abs(x[x < 0].sum())
        corr = np.corrcoef(j.pnl_e, j.pnl_q)[0, 1] if len(j) > 2 else np.nan
        print(f"{tag:<22}{len(e):>7}{len(q):>8}{len(se & sq)/max(len(se),1):>10.1%}"
              f"{pf(e.pnl.to_numpy()):>9.2f}{pf(q.pnl.to_numpy()):>9.2f}"
              f"{e.pnl.mean():>+10.2f}{q.pnl.mean():>+10.2f}{corr:>8.4f}")
