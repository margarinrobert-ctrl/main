"""Feature matrix and PURGED walk-forward splits for the breakout label.

WHAT IS BEING PREDICTED. Not the next return -- the OUTCOME OF THE TRADE THE RULE WOULD OPEN. For
every Donchian 30 breakout bar, the label is the R-multiple the 2.0N-stop / 20-bar-channel-exit
trade actually earned. That is the only label whose improvement is worth money: a model that
forecasts returns beautifully but not trade outcomes cannot be traded through this rule.

WHY A NAIVE K-FOLD IS INVALID HERE, AND WHAT REPLACES IT. Trades OVERLAP: a trade opened at bar i is
still live at bar j, so a training sample and a test sample can share the same price path and the
same outcome-determining bars. Standard cross-validation then trains on the answer. Two fixes,
both applied:
  PURGE    drop any training trade whose [signal bar, exit bar] interval overlaps ANY test trade's.
  EMBARGO  additionally drop training trades starting within a buffer after each test interval,
           because serial correlation leaks across the boundary even without overlap.
`STUDY_EDGELAB` recorded what happens without this: scoring bar-wise made 17,121 of 27,786 tests
"pass" BH at q 0.10, which was a symptom and not a discovery.

THE NULL THAT MATTERS MORE THAN ANY SCORE. Every model is also run on SHUFFLED LABELS. Whatever
accuracy or AUC the pipeline reports there is the floor produced by the pipeline itself -- leakage,
optimisation, class imbalance, lucky folds. A real result has to clear its own shuffled twin, not
0.5.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v21")
sys.path.insert(0, "research/v22")
sys.path.insert(0, "research/v24")
sys.path.insert(0, "research/v27")
import indicators as I        # noqa: E402
import v16core as C           # noqa: E402
import v16mom as M            # noqa: E402
import v21regime as RG        # noqa: E402
import v22vol as VV           # noqa: E402
import v24ma as V             # noqa: E402
import v27run as R27          # noqa: E402
import costs as CO            # noqa: E402


def prep_bars(b, entry_n=30, exit_n=20, broker="discount", cost_mult=1.0, atr_len=14):
    """`v16core.prep` for bars already in memory -- it loads NQ through fastbars and cannot take a
    second market. Same construction, same channel offsets, same cost arrays."""
    o, h, l, c, mod = b["o"], b["h"], b["l"], b["c"], b["mod"]
    atr = I.ema(I.true_range(h, l, c), atr_len)
    cost = CO.model("MNQ", broker)
    if cost_mult != 1.0:
        cost = cost.__class__(**{**cost.__dict__, "mult": cost_mult})
    f_taker, f_stop = CO.friction_arrays(cost, h, l, c, mod)
    return dict(b=b, o=o, h=h, l=l, c=c, mod=mod, sess=b["sess"], ts=b["ts"], atr=atr,
                ent_hi=I.shift(I.rmax(h, entry_n), 1), ent_lo=I.shift(I.rmin(l, entry_n), 1),
                ex_lo=I.shift(I.rmin(l, exit_n), 1), ex_hi=I.shift(I.rmax(h, exit_n), 1),
                fee2=2.0 * cost.fee_points(), f_taker=f_taker, f_stop=f_stop, cost=cost)


def build(market="NQ", tf=30, side=1):
    """Returns (X, y_R, y_win, meta) at breakout signal bars. Every column read at the SIGNAL bar."""
    if market == "NQ":
        P = C.prep(tf, entry_n=30, exit_n=20, cost_mult=1.44)
        b = dict(o=P["o"], h=P["h"], l=P["l"], c=P["c"], sess=P["sess"], mod=P["mod"], ts=P["ts"])
    else:
        b15 = R27.load_us30()
        df = pd.DataFrame(b15)
        df["blk"] = np.arange(len(df)) // (tf // 15)
        g = df.groupby("blk")
        b = dict(ts=g.ts.first().to_numpy(), o=g.o.first().to_numpy(), h=g.h.max().to_numpy(),
                 l=g.l.min().to_numpy(), c=g.c.last().to_numpy(),
                 sess=g.sess.first().to_numpy(), mod=g["mod"].first().to_numpy())
        P = prep_bars(b, entry_n=30, exit_n=20, cost_mult=1.44)
    sig = C.signals(P, side)
    O = C.outcomes(P, side, sig, stop_mult=2.0, tp_r=0.0)

    cols = {}
    # --- volatility state (71) ---
    for k, v in VV.build(b["o"], b["h"], b["l"], b["c"]).items():
        cols[f"vol.{k}"] = v
    # --- momentum pool ---
    for k, (arr, _cen, _off) in M.build(dict(h=b["h"], l=b["l"], c=b["c"])).items():
        cols[f"mom.{k}"] = arr
    # --- regime ---
    cols["reg.chop14"] = RG.chop(b["h"], b["l"], b["c"], 14)
    cols["reg.chop28"] = RG.chop(b["h"], b["l"], b["c"], 28)
    _p, _m, adx = I.adx_di(b["h"], b["l"], b["c"], 14)
    cols["reg.adx14"] = adx
    # --- HMM causal posteriors: the regime model as three more columns ---
    u = np.unique(b["sess"])
    cut = u[int(len(u) * 0.65)]
    s_lab, post, A, mu, nm = R27.hmm_states(b, cut, seed=3)
    order = [k for k in range(3) if nm[k] == "Bull"] + [k for k in range(3) if nm[k] == "Bear"] + \
            [k for k in range(3) if nm[k] == "Sideways"]
    for j, nme in zip(order, ("bull", "bear", "side")):
        cols[f"hmm.p_{nme}"] = post[:, j]
    # --- structure / session ---
    atr = P["atr"]
    cols["str.atr_pct"] = atr / np.maximum(b["c"], 1e-9)
    cols["str.bar_pos"] = (b["c"] - b["l"]) / np.maximum(b["h"] - b["l"], 1e-9)
    cols["str.ext_ent"] = (b["h"] - P["ent_hi"]) / np.maximum(atr, 1e-9)
    cols["str.chan_w"] = (P["ent_hi"] - P["ex_lo"]) / np.maximum(atr, 1e-9)
    cols["ses.mod"] = b["mod"].astype(float)
    cols["ses.dow"] = pd.to_datetime(b["ts"]).dayofweek.to_numpy().astype(float)

    X = pd.DataFrame({k: v[sig] for k, v in cols.items()})
    keep = np.isfinite(X.to_numpy()).all(axis=1) & (O["xb"] >= 0)
    X = X[keep].reset_index(drop=True)
    meta = dict(sig=sig[keep], xb=O["xb"][keep], sess=b["sess"][sig[keep]], P=P, O=O,
                keep=keep, full_sig=sig)
    return X, O["R"][keep], (O["R"][keep] > 0).astype(int), meta


def purged_folds(sig, xb, n_folds=6, embargo=50):
    """Contiguous test folds; training trades overlapping or near a test interval are DROPPED."""
    n = len(sig)
    edges = np.linspace(0, n, n_folds + 1).astype(int)
    for f in range(n_folds):
        te = np.zeros(n, bool)
        te[edges[f]:edges[f + 1]] = True
        t0, t1 = sig[te].min(), xb[te].max()
        overlap = (xb >= t0 - embargo) & (sig <= t1 + embargo)
        tr = (~te) & (~overlap)
        if tr.sum() > 200 and te.sum() > 50:
            yield np.flatnonzero(tr), np.flatnonzero(te)
