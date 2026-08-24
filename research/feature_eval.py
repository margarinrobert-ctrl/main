"""Which features actually predict, measured the way this repository measures everything else.

Building features is column-creation. The question is which of them carry information about what
happens next, and the honest answer needs four things that are usually skipped:

  1. AN OVERLAP-AWARE STANDARD ERROR. A forward return over h bars, evaluated at every bar,
     produces h-fold overlapping observations. A naive t-statistic on 35,000 of those is inflated
     by roughly sqrt(h). Newey-West with lag h is the minimum fix and is what is used here.

  2. MULTIPLICITY. 121 features x 4 horizons = 484 tests, so 24 clear p < 0.05 by chance.
     Benjamini-Hochberg over all of them, with the chance count stated before the results.

  3. REPLICATION, WHICH MATTERS MORE THAN EITHER. The research block chooses nothing here -- but
     a feature whose information coefficient has the SAME SIGN on both blocks has said something,
     and one that flips has not. Under the null that is a coin flip, so the count of sign
     agreements among significant features is the statistic worth reading.

  4. REDUNDANCY. 121 features is not 121 dimensions. Correlation clustering says how many
     independent things are actually being measured.

Then, separately: for the thirteen shipped strategies, which features SEPARATE WINNING TRADES FROM
LOSING ONES, read at the SIGNAL bar and not at `ent_bar` -- see `test_suite.sig_bar` and
STUDY_AUCTION.md for what reading them at the fill bar does to the answer.

Usage: python3 research/feature_eval.py [tf]
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from anomalies import bh, newey_west_t
from bos_choch import prep
from features2 import build_all

HORIZONS = (1, 3, 6, 12)
MIN_COV = 0.5


def targets(d, horizons=HORIZONS):
    """Forward return over h bars, normalised by the ATR known at the decision bar.

    ATR-normalised because every strategy here sizes its barriers in ATRs, so "how far did it go"
    only means something relative to how far it was moving anyway.
    """
    c, atr_ = d["c"], np.maximum(d["atr"], 1e-9)
    out = {}
    for h in horizons:
        fwd = np.r_[c[h:], np.full(h, np.nan)] - c
        out[h] = fwd / atr_
    return out


def ic_table(d, F, verbose=True):
    """Rank information coefficient per feature per horizon, on each block separately."""
    us = np.unique(d["sess"])
    si = np.searchsorted(us, d["sess"])
    cut = int(0.65 * len(us))
    res_m, lok_m = si < cut, si >= cut
    T = targets(d)
    rows = []
    for name, x in F.items():
        if np.isfinite(x).mean() < MIN_COV:
            continue
        for h, y in T.items():
            ok = np.isfinite(x) & np.isfinite(y)
            if ok.sum() < 500:
                continue
            rx = pd.Series(x).rank(pct=True).to_numpy()
            ry = pd.Series(y).rank(pct=True).to_numpy()
            rec = dict(feature=name, h=h)
            for tag, blk in (("res", res_m), ("lok", lok_m)):
                m = ok & blk
                if m.sum() < 300:
                    rec[f"ic_{tag}"] = np.nan; rec[f"t_{tag}"] = np.nan; continue
                a = rx[m] - rx[m].mean(); b = ry[m] - ry[m].mean()
                ic = float((a * b).mean() / max(a.std() * b.std(), 1e-12))
                rec[f"ic_{tag}"] = ic
                # Newey-West on the per-bar cross-product, lag = h, for the overlap
                rec[f"t_{tag}"] = float(newey_west_t(a * b / max(a.std() * b.std(), 1e-12), lag=h))
            rows.append(rec)
    R = pd.DataFrame(rows)
    R["p_res"] = 2 * (1 - _ncdf(np.abs(R.t_res)))
    R["p_lok"] = 2 * (1 - _ncdf(np.abs(R.t_lok)))
    R["q_res"] = bh(np.nan_to_num(R.p_res.to_numpy(), nan=1.0))
    R["agree"] = np.sign(R.ic_res) == np.sign(R.ic_lok)
    return R


def _ncdf(x):
    from scipy import stats as st
    return st.norm.cdf(np.asarray(x, float))


def report_ic(R, verbose=True):
    n = len(R)
    sig = R[R.q_res < 0.10]
    print(f"\nINFORMATION COEFFICIENT vs FORWARD RETURN\n  {n} feature x horizon tests; "
          f"{n*0.05:.0f} clear p < 0.05 by chance alone")
    print(f"  {len(sig)} survive Benjamini-Hochberg at q < 0.10 on the RESEARCH block")
    if len(sig):
        agree = int(sig.agree.sum())
        from scipy import stats as st
        pv = st.binomtest(agree, len(sig), 0.5, alternative="greater").pvalue
        print(f"  of those, {agree}/{len(sig)} keep the SAME SIGN on the locked block "
              f"(coin flip under the null, sign test p = {pv:.4f})")
        top = sig.reindex(sig.ic_res.abs().sort_values(ascending=False).index).head(18)
        print(f"\n  {'feature':<34}{'h':>3}{'IC res':>9}{'t res':>8}{'IC lok':>9}{'t lok':>8}"
              f"{'q':>8}  sign")
        for _, r in top.iterrows():
            print(f"  {r.feature[:32]:<34}{int(r.h):>3}{r.ic_res:>9.3f}{r.t_res:>8.2f}"
                  f"{r.ic_lok:>9.3f}{r.t_lok:>8.2f}{r.q_res:>8.3f}"
                  f"{'  same' if r.agree else '  FLIPS'}")
    return sig


def redundancy(F, thresh=0.9, verbose=True):
    """How many independent dimensions do these features actually span?"""
    ks = [k for k, v in F.items() if np.isfinite(v).mean() >= MIN_COV]
    M = np.column_stack([pd.Series(F[k]).rank(pct=True).to_numpy() for k in ks])
    ok = np.isfinite(M).all(1)
    C = np.corrcoef(M[ok].T)
    C = np.nan_to_num(C)
    # greedy clustering: a feature joins a cluster if it correlates above `thresh` with its head
    heads, member = [], {}
    order = np.argsort(-np.abs(C).sum(0))
    for i in order:
        for hd in heads:
            if abs(C[i, hd]) >= thresh:
                member.setdefault(hd, []).append(i); break
        else:
            heads.append(i); member[i] = [i]
    ev = np.linalg.eigvalsh(C)[::-1]
    ev = ev[ev > 0]
    frac = np.cumsum(ev) / ev.sum()
    if verbose:
        print(f"\nREDUNDANCY\n  {len(ks)} features -> {len(heads)} clusters at |rho| >= {thresh}")
        print(f"  principal components for 90% of variance: "
              f"{int(np.searchsorted(frac, 0.90)) + 1}; for 99%: "
              f"{int(np.searchsorted(frac, 0.99)) + 1}")
        big = sorted(member.items(), key=lambda kv: -len(kv[1]))[:5]
        for hd, mem in big:
            if len(mem) < 3:
                continue
            print(f"     {ks[hd][:30]:<32} absorbs {len(mem)-1} others "
                  f"({', '.join(ks[m][:18] for m in mem[1:4])}{'...' if len(mem) > 4 else ''})")
    return heads, member, ks


def trade_separation(F, d, tf, block="research", verbose=True):
    """Which features separate winning trades from losing ones, at the SIGNAL bar.

    `block` defaults to research and that default is the point. The first version of this ranked
    features over ALL trades, both blocks -- and then a family picked off the top of that ranking
    was carried to a "holdout" test whose data had already been used to choose it. That is the
    laundering CLAUDE.md records happening twice before. Rank on research; read locked once,
    afterwards, and only for what research chose.
    """
    from allstrats import all_strategies
    from oner_union import _cut, _sim
    from test_suite import sig_bar
    A = {k: v for k, v in all_strategies().items() if v["tf"] == tf}
    if not A:
        return None
    xs, ys = [], []
    for k, S in A.items():
        pnl, eb, *_ = _sim(S["d"], S["trig"], S["side"], S["am"], S["flat"])
        si, cut, _ = _cut(S["d"])
        keep = (si[eb] < cut) if block == "research" else (
            (si[eb] >= cut) if block == "locked" else np.ones(len(eb), bool))
        xs.append(sig_bar(eb)[keep]); ys.append((pnl > 0)[keep])
    sb = np.concatenate(xs); win = np.concatenate(ys)
    if len(sb) < 80:
        return None
    from scipy import stats as st
    rows = []
    for name, x in F.items():
        v = x[sb]
        m = np.isfinite(v)
        if m.sum() < 60 or len(set(win[m])) < 2:
            continue
        a, b = v[m & win], v[m & ~win]
        if len(a) < 20 or len(b) < 20:
            continue
        u = st.mannwhitneyu(a, b)
        rows.append(dict(feature=name, n=int(m.sum()), win_med=float(np.median(a)),
                         lose_med=float(np.median(b)), p=float(u.pvalue),
                         auc=float(u.statistic / (len(a) * len(b)))))
    R = pd.DataFrame(rows)
    if not len(R):
        return None
    R["q"] = bh(R.p.to_numpy())
    R = R.sort_values("p")
    if verbose:
        print(f"\nWHAT SEPARATES A WINNING TRADE FROM A LOSING ONE   ({len(sb)} {block} trades "
              f"across {len(A)} strategies at {tf}m,\n  every feature read at the SIGNAL bar)")
        print(f"  {len(R)} features tested, {int((R.q < 0.10).sum())} survive "
              f"Benjamini-Hochberg at q < 0.10")
        print(f"\n  {'feature':<34}{'AUC':>7}{'win med':>10}{'lose med':>10}{'p':>8}{'q':>8}")
        for _, r in R.head(12).iterrows():
            print(f"  {r.feature[:32]:<34}{r.auc:>7.3f}{r.win_med:>10.3f}{r.lose_med:>10.3f}"
                  f"{r.p:>8.3f}{r.q:>8.3f}" + ("  <-" if r.q < 0.10 else ""))
    return R


if __name__ == "__main__":
    tf = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    d = prep(tf)
    F = build_all(d, tf)
    print(f"FEATURE EVALUATION -- {len(F)} features, {tf}-minute bars, {len(d['c']):,} bars")
    R = ic_table(d, F)
    report_ic(R)
    redundancy(F)
    trade_separation(F, d, tf)
