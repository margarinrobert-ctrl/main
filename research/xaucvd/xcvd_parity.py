"""THE SHIPPED PINE'S OWN ORDER MODEL, IN PYTHON, DIFFED AGAINST THE RESEARCH ENGINE.

`STUDY_PINE_PARITY` and `STUDY_V56_PARITY_ADX_TP` both recorded the same thing: a Pine port that is
transcribed carefully, read back twice and lint-clean can still be a different strategy. The only
thing that settles it is writing the SCRIPT'S order model out and diffing it trade for trade.

FOUR PLACES THIS PORT COULD DIVERGE, and each is checked rather than argued:

 1. PIVOT DEFINITION. The research uses `v54cvd.pivots`, which takes bar i when x[i] equals the
    window extreme AND is its FIRST occurrence -- ties allowed. Pine's `ta.pivotlow(src, k, k)`
    requires the bar to be STRICTLY beyond every neighbour. On a tick-quantised series like gold
    those are not the same set, and the difference is measured below rather than assumed.
 2. THE BREAK TEST. The research walker uses a STRICT `high > channel`; the script exposes a touch
    option. Parity is run with it OFF, which is why it ships OFF.
 3. THE STOP ANCHOR. Both anchor the ATR at the SIGNAL bar and the stop level at the FILL price.
 4. THE EXIT ORDER. Both take max(ATR stop, prior-bar exit channel) capped at the previous close.

Run twice: once with the research's own pivot definition (the TRANSCRIPTION check, which must come
back near-identical) and once with Pine's (the ORDER-MODEL gap, which is what a user would get).
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (HERE, os.path.join(ROOT, "research"), os.path.join(ROOT, "research/xau"),
          os.path.join(ROOT, "research/v54")):
    sys.path.insert(0, p)

import xcvd                     # noqa: E402
import xau_core as X            # noqa: E402
import v54cvd as V54            # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 240)


def line(t):
    print("\n" + "=" * 122)
    print(t)
    print("=" * 122, flush=True)


def pine_pivotlow(x, k):
    """Pine's ta.pivotlow(src, k, k): STRICTLY lower than every bar within k on both sides.
    Returns a boolean array stamped at the CONFIRMATION bar i+k, as Pine emits it."""
    n = len(x)
    out = np.zeros(n, bool)
    piv = np.zeros(n, np.int64)
    for i in range(k, n - k):
        v = x[i]
        ok = True
        for j in range(1, k + 1):
            if not (x[i - j] > v and x[i + j] > v):
                ok = False
                break
        if ok:
            out[i + k] = True
            piv[i + k] = i
    return out, piv


def research_pivotlow(x, k):
    """v54cvd.pivots' low set, in the same stamped-at-confirmation form."""
    n = len(x)
    out = np.zeros(n, bool)
    piv = np.zeros(n, np.int64)
    _hi, lo = V54.pivots(x, k)
    for conf, p in lo:
        if conf < n:
            out[conf] = True
            piv[conf] = p
    return out, piv


def gate_flag(D, k, w, pivot_fn):
    """EXHAUSTED SELLERS -- price Lower Low with CVD Higher Low at consecutive confirmed pivot
    lows -- as a 'fired within the last w bars' flag, exactly as the script's barssince test."""
    l, cvd, n = D["l"], D["cvd"], D["n"]
    conf, piv = pivot_fn(l, k)
    fired = np.zeros(n, bool)
    prevP = prevC = None
    for i in np.flatnonzero(conf):
        curP, curC = l[piv[i]], cvd[piv[i]]
        if prevP is not None and curP < prevP and curC > prevC:
            fired[i] = True
        prevP, prevC = curP, curC
    return pd.Series(fired.astype(float)).rolling(w).max().to_numpy() > 0


def pine_walk(D, gate, entN=20, exN=20, stopN=2.0, tpATR=0.0, maxHold=480,
              cost=X.COST_RT, slip=X.SLIP, touch=False):
    """The SCRIPT'S order model. Entry at the next open, ATR frozen at the signal bar, the bracket
    live from the fill, then max(ATR stop, prior-bar channel) capped at the previous close."""
    o, h, l, c, atr = D["o"], D["h"], D["l"], D["c"], D["atr"]
    ehi = D["ent_hi"][entN - 2]
    elo = D["ex_lo"][exN - 2]
    n = D["n"]
    last = int(D["last_bar"])
    rows = []
    busy = -1
    for i in range(300, last):
        if i <= busy or not gate[i]:
            continue
        if not np.isfinite(ehi[i]) or not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        brk = (h[i] >= ehi[i]) if touch else (h[i] > ehi[i])
        if not brk:
            continue
        a = i + 1
        if a >= n - 1:
            break
        px = o[a] + slip
        anchor = atr[i]
        fixed = px - stopN * anchor
        tgt = px + tpATR * anchor if tpATR > 0 else 1e18
        end = min(a + maxHold, n - 2)
        out = np.nan
        j = a
        while j <= end:
            lvl = fixed
            ch = elo[j]
            if np.isfinite(ch) and ch > lvl:
                lvl = ch
            cp = c[j - 1]
            if np.isfinite(cp) and lvl > cp:
                lvl = cp
            if l[j] <= lvl:
                out = (lvl if o[j] > lvl else o[j]) - slip
                break
            if h[j] >= tgt:
                out = (tgt if o[j] < tgt else o[j]) - slip
                break
            j += 1
        if not np.isfinite(out):
            j = end
            out = c[j] - slip
        g = out - px - cost
        rows.append(dict(sig=i, exit_bar=j, pct=100.0 * g / px, blk=D["blk"][i]))
        busy = j
    return pd.DataFrame(rows)


K, W = 2, 20
G = dict(ent=20, exN=20, stop=2.0, tp=0.0, hold=480, side=1)
print(__doc__)
D = xcvd.build(60)

line("PIVOT DEFINITIONS -- how much do the two disagree on gold's tick-quantised lows?")
cr, _ = research_pivotlow(D["l"], K)
cp, _ = pine_pivotlow(D["l"], K)
both = int((cr & cp).sum())
print(f"  research pivots {int(cr.sum()):>6}   Pine pivots {int(cp.sum()):>6}   shared {both:>6}   "
      f"Jaccard {both / max((cr | cp).sum(), 1):.4f}")

for tag, fn in (("RESEARCH pivot definition (the TRANSCRIPTION check)", research_pivotlow),
                ("PINE pivot definition (what the script actually does)", pine_pivotlow)):
    line(tag)
    gate = gate_flag(D, K, W, fn)
    E = X.run(D, G, gate=gate)                 # the research engine, gated
    P = pine_walk(D, gate)                     # the script's own order model
    print(f"  {'block':10s} {'engine n':>9} {'script n':>9} {'ratio':>7} {'engine %/ev':>12} "
          f"{'script %/ev':>12} {'gap':>9} {'same exit bar':>14} {'corr':>7}")
    for i, bn in enumerate(X.BLOCKS):
        e = E[E.blk == i]
        p = P[P.blk == i]
        if len(e) < 10:
            continue
        m = pd.merge(e[["sig", "exit_bar", "pct"]], p[["sig", "exit_bar", "pct"]],
                     on="sig", suffixes=("_e", "_p"))
        same = 100.0 * (m.exit_bar_e == m.exit_bar_p).mean() if len(m) else np.nan
        cc = m.pct_e.corr(m.pct_p) if len(m) > 3 else np.nan
        gap = (p.pct.mean() - e.pct.mean()) / abs(e.pct.mean()) * 100 if e.pct.mean() else np.nan
        print(f"  {bn:10s} {len(e):>9} {len(p):>9} {len(p)/max(len(e),1):>7.3f} {e.pct.mean():>12.5f} "
              f"{p.pct.mean():>12.5f} {gap:>+8.1f}% {same:>13.2f}% {cc:>7.4f}")

line("VERDICT")
gr = gate_flag(D, K, W, research_pivotlow)
gp = gate_flag(D, K, W, pine_pivotlow)
Er = X.run(D, G, gate=gr)
Pp = pine_walk(D, gp)
for i, bn in enumerate(X.BLOCKS):
    e = Er[Er.blk == i]
    p = Pp[Pp.blk == i]
    if len(e) < 10:
        continue
    print(f"  {bn:10s} research-as-published {e.pct.mean():+.5f} %/ev on {len(e):>4} events   "
          f"-> the shipped script {p.pct.mean():+.5f} on {len(p):>4}   "
          f"({'CONSERVATIVE' if p.pct.mean() <= e.pct.mean() else 'the script reads BETTER'})")
print("\n  A script that reads BETTER than the research is reporting the order-model gap, not an edge")
print("  (STUDY_V56: the first V55 draft read +15.2% better and that was the naked fill bar).")
