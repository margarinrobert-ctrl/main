"""Where does the stop anchor -- and can a real script protect the ENTRY bar?

`v16core._walk` anchors the stop to px0 = the OPEN OF THE ENTRY BAR, and tests the exit from that
same bar onward. A Pine script cannot do both. Orders placed at the close of the signal bar execute
on the next bar, so at the moment the exit order must be written the entry fill price does not exist
yet. STUDY_PINE_PARITY measured what happens when you give up and place the exit a bar late: no exit
order is live during the entry bar, 4.4-13.0% of trades, averaging -33 to -118 points.

The alternative is to anchor the stop to the SIGNAL BAR'S CLOSE, which IS known when the order is
written, so entry and exit can be placed together and the entry bar is protected. That is a
different rule. This file measures how different, before anything is shipped -- because if the gap
is material the script must not claim the research numbers.
"""
from __future__ import annotations

import sys
import numpy as np
from numba import njit

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v22")
import v16core as C           # noqa: E402
import v22vol as V            # noqa: E402
from v22stop import STATE, blocks  # noqa: E402


@njit(cache=True)
def _walk_anchor(o, h, l, c, sig, ex_lo, atr, smult, fee2, f_taker, f_stop,
                 anchor_close, out_xb, out_pnl, out_why):
    """anchor_close=1 anchors the stop to the SIGNAL bar's close and arms it on the ENTRY bar."""
    n = len(c)
    for k in range(len(sig)):
        i = sig[k]
        a = atr[i]
        eb = i + 1
        out_xb[k] = -1
        if eb >= n or not np.isfinite(a) or a <= 0.0:
            continue
        px0 = o[eb]
        base = c[i] if anchor_close == 1 else px0
        stop = base - smult[k] * a
        for j in range(eb, n):
            lvl = stop
            why = 0
            ch = ex_lo[j]
            if np.isfinite(ch) and ch > lvl:
                lvl = ch
                why = 1
            cap = c[j - 1]
            if lvl > cap:
                lvl = cap
            if l[j] <= lvl:
                out_xb[k] = j
                out_pnl[k] = (lvl - px0) - fee2 - f_taker[eb] - f_stop[j]
                out_why[k] = why
                break


def run(P, sig, smult, anchor_close):
    xb = np.full(len(sig), -1, np.int64)
    pnl = np.zeros(len(sig))
    why = np.zeros(len(sig), np.int64)
    _walk_anchor(P["o"], P["h"], P["l"], P["c"], sig, P["ex_lo"], P["atr"], smult,
                 float(P["fee2"]), P["f_taker"], P["f_stop"], int(anchor_close), xb, pnl, why)
    return dict(sig=sig, xb=xb, pnl=pnl, why=why,
                R=pnl / (smult * P["atr"][sig]))


if __name__ == "__main__":
    for tf in (15, 30):
        P = C.prep(tf, entry_n=30, exit_n=20, cost_mult=1.44)
        sig = C.signals(P, 1)
        s = V.build(P["o"], P["h"], P["l"], P["c"])[STATE][sig]
        good = np.isfinite(s)
        smult = np.where(np.where(good, s <= 0.5, False), 2.5, 1.5)
        res, lk = blocks(P["sess"])
        res, lk = res[sig], lk[sig]

        A = run(P, sig, smult, 0)   # engine convention: anchored to the entry-bar OPEN
        B = run(P, sig, smult, 1)   # script convention: anchored to the SIGNAL bar CLOSE

        both = (A["xb"] >= 0) & (B["xb"] >= 0) & good
        print("\n" + "=" * 104)
        print(f"NQ {tf}m   STOP ANCHOR: entry-bar open (engine) vs signal-bar close (a script can "
              f"place this)")
        print("=" * 104)
        print(f"   trades resolved   engine {int((A['xb']>=0).sum())}   script "
              f"{int((B['xb']>=0).sum())}   shared {int(both.sum())}")
        print(f"   SAME EXIT BAR on the shared set: {float((A['xb'][both]==B['xb'][both]).mean()):.2%}")
        print(f"   per-trade R correlation:        {np.corrcoef(A['R'][both], B['R'][both])[0,1]:.4f}")
        print(f"   median |anchor difference| in ATR: "
              f"{np.nanmedian(np.abs(P['c'][sig]-P['o'][sig+1])/P['atr'][sig]):.4f}")
        print()
        print(f"   {'block':<10}{'':<10}{'n':>7}{'R/trade':>11}{'PF':>9}")
        for lab, O in (("engine", A), ("script", B)):
            for tag, blk in (("research", res), ("locked", lk)):
                idx = C.take(O, blk & good & (O["xb"] >= 0))
                r = O["R"][idx]
                p = r[r > 0].sum() / abs(r[r < 0].sum()) if (r < 0).any() else np.nan
                print(f"   {tag:<10}{lab:<10}{len(idx):>7}{r.mean():>+11.4f}{p:>9.3f}")
