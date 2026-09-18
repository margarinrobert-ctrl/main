"""The shipped Pine's PROFILE, transliterated and diffed against `vpcore.sessions`.

One difference is real and is measured here rather than argued about: the research computes ATR on
the RTH-ONLY frame, and a script on a chart computes it on every bar it sees. That changes the bin
WIDTH, so it changes the bin count, the POC bin and the value area.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vpus30 import vpcore as V, vpdon as D  # noqa: E402

BIN, FRAC = 0.10, 0.70


def script_profile(hh, ll, vv, lo0, binw, nb, frac=FRAC):
    hist = np.zeros(nb)
    for i in range(len(hh)):
        a = max(int(np.floor((ll[i] - lo0) / binw)), 0)
        b = min(int(np.floor((hh[i] - lo0) / binw)), nb - 1)
        b = max(b, a)
        w = vv[i] / (b - a + 1)
        hist[a:b + 1] += w
    tot = hist.sum()
    poc = int(np.argmax(hist))
    lo = hi = poc
    got = hist[poc]
    while got < frac * tot and (lo > 0 or hi < nb - 1):
        dn = hist[lo - 1] if lo > 0 else -1.0
        up = hist[hi + 1] if hi < nb - 1 else -1.0
        if up >= dn:
            hi += 1; got += hist[hi]
        else:
            lo -= 1; got += hist[lo]
    return (lo0 + (poc + .5) * binw, lo0 + (lo + .5) * binw, lo0 + (hi + .5) * binw)


def main():
    f = V.load()
    g = D.frame(f)                       # FULL frame, script-style ATR
    d = V.sessions(f)                    # research profiles, RTH-only ATR
    rth = g[g.is_rth == 1]
    rows = []
    for sess, blk in rth.groupby(rth.index.normalize()):
        if len(blk) < 8:
            continue
        h = blk["high"].to_numpy(); l = blk["low"].to_numpy(); v = blk["tv"].to_numpy()
        a = blk["atr"].to_numpy()
        lo0, hi0 = l.min(), h.max()
        m = np.nanmean(a)
        if not np.isfinite(m) or m <= 0 or hi0 <= lo0:
            continue
        binw = max(BIN * m, 1e-6)
        nb = int(np.ceil((hi0 - lo0) / binw)) + 1
        if nb < 5 or nb > 4000:
            continue
        poc, val, vah = script_profile(h, l, v, lo0, binw, nb)
        cl = blk["close"].to_numpy()[-1]
        shape = 0 if (val <= cl <= vah) else (1 if (cl - lo0) / (hi0 - lo0) >= .5 else -1)
        rows.append(dict(sess=pd.Timestamp(sess), s_poc=poc, s_val=val, s_vah=vah,
                         s_nb=nb, s_shape=shape, s_atr=m))
    s = pd.DataFrame(rows)
    m = d.merge(s, on="sess")
    print(f"research sessions {len(d)}   script sessions {len(s)}   matched {len(m)}")
    r_shape = np.where(m.shape_ == "neutral", 0,
                       np.where(m.shape_ == "bullish", 1, -1)) if "shape_" in m else \
        np.where(m["shape"] == "neutral", 0, np.where(m["shape"] == "bullish", 1, -1))
    for nm, a, b in (("POC", m.poc, m.s_poc), ("VAL", m.val, m.s_val), ("VAH", m.vah, m.s_vah)):
        dif = (b - a).abs()
        print(f"  {nm}: corr {a.corr(b):.6f}   identical {float((dif < 1e-9).mean()):.4f}"
              f"   median |diff| {dif.median():.3f} pts = {(dif / m.atr).median():.4f} ATR")
    print(f"  bin count identical {float((m.nb == m.s_nb).mean()):.4f}"
          f"   ATR ratio (script/research) median {float((m.s_atr / m.atr).median()):.4f}")
    print(f"  SHAPE agrees {float((r_shape == m.s_shape).mean()):.4f}"
          f"   (research bullish {float((r_shape == 1).mean()):.3f},"
          f" script {float((m.s_shape == 1).mean()):.3f})")

    # what the disagreement costs the gate that uses it
    tol = 0.5
    stk_r, stk_s = [], []
    pr, ps = m.poc.to_numpy(), m.s_poc.to_numpy()
    cl = m.close.to_numpy(); at = m.atr.to_numpy()
    for i in range(20, len(m)):
        stk_r.append(int((np.abs(pr[i - 5:i] - cl[i]) <= tol * at[i]).sum()))
        stk_s.append(int((np.abs(ps[i - 5:i] - cl[i]) <= tol * at[i]).sum()))
    stk_r, stk_s = np.array(stk_r), np.array(stk_s)
    print(f"  stacked-POC(5) at the session close agrees {float((stk_r == stk_s).mean()):.4f}"
          f"   >=1 agrees {float(((stk_r >= 1) == (stk_s >= 1)).mean()):.4f}")


if __name__ == "__main__":
    main()
