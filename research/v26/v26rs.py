"""Cross-index relative strength as a breakout filter: take the long only if THIS index is the
strongest one on the day.

THE IDEA, AND WHY IT IS GENUINELY NEW HERE. Every filter this branch has tested -- momentum, ADX,
CHOP, MA crossovers, linear regression, volatility state -- reads ONE instrument's own history.
A relative-strength gate is CROSS-SECTIONAL: it asks whether the thing breaking out is leading its
peers, which is information no single-instrument feature contains. Nothing on this branch has
tested it.

THE MECHANISM CONCERN, STATED UP FRONT. 15-minute return correlation is US30/US100 0.758,
US30/NQ 0.679, NQ/US100 0.874 (`STUDY_US100`, `research/edgelab/feeds.py`). Two series that
correlated share most of their variance, so the SPREAD between their daily percentage moves is a
small residual on top of a large common factor -- and a filter built on that residual may be
selecting noise. That is exactly what this file is for: measuring it rather than assuming either way.

IT CANNOT BE RUN TODAY. A relative-strength filter needs at least two instruments by construction,
and repeated container recycles have left `data/` holding NQ 1-minute and 5-minute only. Every
other feed -- US30, US100, XAU, EURUSD, BTC -- was wiped and needs re-uploading. This module is
written so the test is one command once a second index is on disk; it is NOT a result and no number
from it appears anywhere yet.

WHAT IT WILL TEST, DECLARED NOW SO THE GRID IS FIXED BEFORE THE DATA ARRIVES:
   anchor      prior daily close, or the session open at a chosen New York time      =  2
   margin      own% - other% >= 0.0, 0.1, 0.25, 0.5                                  =  4
   comparison  beat ONE named index, beat the BEST of two, beat their AVERAGE        =  3
   plus        filter off                                                            = +1 -> 25
   CHOP        <= 40 (V24's winner) and off                                          =  2
   timeframe   15m, 30m                                                              =  2
   -> 100 cells, scored on V24's base with the same-selectivity control as the gate.

THE ANCHOR CHOICE IS NOT COSMETIC. "Percent on the day" from a DAILY BAR is the 24-hour change on a
futures feed and the broker's day on a cash index -- `STUDY_TICK_RECALC` records that
`request.security` on a daily bar returns the 24-hour futures range, not the session. Comparing a
futures symbol's 24h change against a cash index's day is comparing two different windows, which is
a distortion, not a signal. The SESSION-ANCHORED reading measures both from the same New York
minute and is apples-to-apples; it is the default here and in the shipped script for that reason.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v21")
sys.path.insert(0, "research/v24")
import v16core as C           # noqa: E402
import v24ma as V             # noqa: E402

ANCHORS = ("prior daily close", "session open")
MARGINS = (0.0, 0.10, 0.25, 0.50)
MODES = ("beat one", "beat best of two", "beat average")
CHOPS = (40.0, None)
SESSION_ANCHOR_MOD = 9 * 60 + 30      # 09:30 New York


def pct_since_prior_close(c, sess):
    """Percent change from the LAST COMPLETED session's close. Causal by construction."""
    s = pd.Series(c)
    last = s.groupby(pd.Series(sess)).last()
    prev = last.shift(1).reindex(pd.Series(sess)).to_numpy()
    return (c / prev - 1.0) * 100.0


def pct_since_session_open(c, sess, mod, anchor_mod=SESSION_ANCHOR_MOD):
    """Percent change from the first bar at or after `anchor_mod` in the CURRENT session."""
    df = pd.DataFrame(dict(c=c, sess=sess, mod=mod))
    elig = df.mod >= anchor_mod
    first = df.where(elig).groupby(df.sess).c.transform("first")
    return (df.c.to_numpy() / first.to_numpy() - 1.0) * 100.0


def align(base_ts, other_ts, other_c):
    """Put another feed's close on the base feed's timestamps, WITHOUT reading into the future.

    `searchsorted(side='right') - 1` takes the most recent other-feed bar at or before each base
    timestamp. A forward fill would be equivalent; an interpolation or a nearest-match would not,
    because nearest can pick a bar that closes AFTER the base bar and that is leakage.
    """
    idx = np.searchsorted(np.asarray(other_ts), np.asarray(base_ts), side="right") - 1
    out = np.full(len(base_ts), np.nan)
    ok = idx >= 0
    out[ok] = np.asarray(other_c)[idx[ok]]
    return out


def rs_masks(P, sig, others, anchor):
    """Own-vs-peer percent-change masks at every declared margin and comparison mode.

    `others` is {name: (ts, close)} for each comparison index, already loaded. Every series is put
    on the base feed's clock with `align`, then converted to a percent change with the SAME anchor
    as the base, so the two numbers are measuring the same window.
    """
    sess, mod, ts, c = P["sess"], P["mod"], P["ts"], P["c"]
    f = pct_since_prior_close if anchor == "prior daily close" else (
        lambda x, s, m=mod: pct_since_session_open(x, s, m))
    own = f(c, sess) if anchor == "prior daily close" else f(c, sess)
    peer = {}
    for name, (ots, oc) in others.items():
        aligned = align(ts, ots, oc)
        peer[name] = f(aligned, sess) if anchor == "prior daily close" else f(aligned, sess)
    names = list(peer)
    out = {}
    for mode in MODES:
        if mode == "beat one":
            refs = {n: peer[n] for n in names}
        elif mode == "beat best of two" and len(names) >= 2:
            refs = {"best of " + "+".join(names): np.nanmax(np.vstack(list(peer.values())), axis=0)}
        elif mode == "beat average" and len(names) >= 2:
            refs = {"avg of " + "+".join(names): np.nanmean(np.vstack(list(peer.values())), axis=0)}
        else:
            continue
        for rname, ref in refs.items():
            for mg in MARGINS:
                m = np.isfinite(own) & np.isfinite(ref) & ((own - ref) >= mg)
                out[f"{anchor} | {rname} | margin {mg:g}"] = m[sig]
    return out


def run(others, tfs=(30, 15)):
    """The declared grid. `others` must be {name: (timestamps, close)} for >= 1 comparison index."""
    rows = []
    for tf in tfs:
        P, sig, O, ch, res, lk = V.prep(tf)
        ok = O["xb"] >= 0
        masks = {}
        for anchor in ANCHORS:
            masks.update(rs_masks(P, sig, others, anchor))
        masks["RS filter off"] = np.ones(len(sig), bool)
        for cc in CHOPS:
            cm = np.ones(len(sig), bool) if cc is None else (np.isfinite(ch) & (ch <= cc))
            clab = "off" if cc is None else f"<={cc:g}"
            bb = V.stat(P, O, ok & cm & lk)
            for lab, m in masks.items():
                a = V.stat(P, O, ok & m & cm & res)
                b = V.stat(P, O, ok & m & cm & lk)
                if a is None:
                    continue
                rows.append(dict(
                    tf=tf, cond=lab, chop=clab, n=a["n"], pf=a["pf"], sharpe=a["sharpe"],
                    R=a["R"], dd=a["dd"],
                    n_lk=(b["n"] if b else 0), pf_lk=(b["pf"] if b else np.nan),
                    sharpe_lk=(b["sharpe"] if b else np.nan), R_lk=(b["R"] if b else np.nan),
                    dd_lk=(b["dd"] if b else np.nan),
                    base_pf=bb["pf"], base_sh=bb["sharpe"]))
    df = pd.DataFrame(rows)
    df["edge_pf"] = df.pf_lk - df.base_pf
    df["edge_sh"] = df.sharpe_lk - df.base_sh
    return df


if __name__ == "__main__":
    import os
    V.hdr("V26 -- CROSS-INDEX RELATIVE STRENGTH. Status check.")
    present = sorted(f for f in os.listdir("data") if f.endswith(".csv"))
    print(f"   feeds on disk: {present}")
    print()
    print("   A relative-strength filter needs at least TWO instruments by construction, and only")
    print("   NQ is present. Repeated container recycles wiped US30, US100, XAU, EURUSD and BTC.")
    print("   THIS MODULE PRODUCES NO RESULT UNTIL A SECOND INDEX IS RE-UPLOADED.")
    print()
    print("   To run it, load the second feed and call:")
    print("       import v26rs; df = v26rs.run({'US100': (ts, close)})")
    print("   The grid is already fixed: 2 anchors x 4 margins x 3 modes + off, x 2 CHOP x 2 tf.")
    print()
    print("   The SESSION-ANCHORED reading is the default and the reason is not cosmetic: a daily")
    print("   bar is the 24-hour range on a futures feed and the broker's day on a cash index, so")
    print("   'percent on the day' compares two different windows across those two symbol types.")
