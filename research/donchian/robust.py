"""Phase-3 robustness battery: walk-forward, Monte Carlo, cost stress, regimes.

Applied to a candidate AFTER it survives the research-block gate and the
adversarial audit. Walk-forward is the first genuinely out-of-sample record
because it includes the cost of HAVING TO CHOOSE parameters.
"""
import numpy as np, pandas as pd
from engine import stats
import lab


# ------------------------------------------------------------- walk-forward
def walk_forward(sym, build_fn, grid, train_sess=250, test_sess=80, mask=None,
                 objective="excess", n_draws=120, verbose=True):
    """Rolling TRAIN -> TEST. `build_fn(param) -> (idx, side, geom)` where geom
    is a dict of stop_mult/targ_mult/max_hold/flat_tod. Re-optimises on each
    training window and trades the next `test_sess` sessions with the winner.

    Returns the stitched out-of-sample trade record plus per-fold diagnostics.
    """
    df, w, r, h = lab.bars(sym)
    if mask is None:
        mask = r
    sess = df.sess.values
    lo, hi = int(sess[mask].min()), int(sess[mask].max())
    books = {}
    for p in grid:
        idx, side, geom = build_fn(p)
        books[str(p)] = (lab.book(sym, idx, side, **geom), geom, p)

    folds, oos = [], []
    s0 = lo
    while s0 + train_sess + test_sess <= hi:
        tr_lo, tr_hi = s0, s0 + train_sess
        te_lo, te_hi = tr_hi, tr_hi + test_sess
        best, best_v = None, -np.inf
        for k, (bk, geom, p) in books.items():
            bs = sess[bk.sig_bar.values]
            sub = bk[(bs >= tr_lo) & (bs < tr_hi)]
            if len(sub) < 20:
                continue
            v = sub.net.mean()
            if v > best_v:
                best_v, best = v, k
        if best is None:
            s0 += test_sess; continue
        bk, geom, p = books[best]
        bs = sess[bk.sig_bar.values]
        te = bk[(bs >= te_lo) & (bs < te_hi)]
        folds.append(dict(train=(tr_lo, tr_hi), test=(te_lo, te_hi), param=p,
                          is_exp=float(best_v), oos_exp=float(te.net.mean()) if len(te) else np.nan,
                          n_oos=len(te)))
        if len(te):
            oos.append(te)
        s0 += test_sess
    oos = pd.concat(oos).reset_index(drop=True) if oos else pd.DataFrame(columns=["net"])
    fd = pd.DataFrame(folds)
    if verbose and len(fd):
        pos = (fd.oos_exp > 0).mean()
        is_med, oos_med = fd.is_exp.median(), fd.oos_exp.median()
        eff = (oos_med / is_med) if is_med > 0 else np.nan
        print(f"  walk-forward: {len(fd)} folds  train={train_sess}/test={test_sess} sessions")
        print(f"    OOS trades           : {len(oos):,}")
        print(f"    profitable folds     : {pos:.1%}")
        print(f"    median IS exp        : {is_med:+.2f}")
        print(f"    median OOS exp       : {oos_med:+.2f}")
        print(f"    WF efficiency        : {'undefined (IS median <= 0)' if is_med<=0 else f'{eff:.2f}'}")
        print(f"    worst fold           : {fd.oos_exp.min():+.2f}")
        pc = fd.param.astype(str).value_counts()
        print(f"    parameter stability  : modal choice kept in {pc.iloc[0]/len(fd):.0%} of folds ({pc.index[0]})")
    return oos, fd


# --------------------------------------------------------------- monte carlo
def monte_carlo(tr, n=5000, seed=0, pt_value=1.0):
    """Bootstrap the TRADE SEQUENCE. Answers: how much of the equity curve's
    shape is ordering luck, and what drawdown should be expected."""
    if len(tr) < 20:
        return {}
    net = tr.net.values * pt_value
    rng = np.random.default_rng(seed)
    tot = np.empty(n); mdd = np.empty(n)
    for i in range(n):
        s = rng.permutation(net)          # reshuffle order: same trades, new path
        eq = np.cumsum(s); pk = np.maximum.accumulate(eq)
        tot[i] = eq[-1]; mdd[i] = (pk - eq).max()
    boot = np.empty(n)                     # resample WITH replacement: new trades
    for i in range(n):
        boot[i] = rng.choice(net, len(net), replace=True).mean()
    return dict(
        median_total=float(np.median(tot)), p05_total=float(np.percentile(tot, 5)),
        p95_total=float(np.percentile(tot, 95)),
        median_mdd=float(np.median(mdd)), p95_mdd=float(np.percentile(mdd, 95)),
        prob_profit=float((boot > 0).mean()),
        exp_ci=(float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))),
        risk_of_ruin_2x_mdd=float((mdd > 2*np.median(mdd)).mean()),
    )


def cost_stress(sym, idx, side, geom, mults=(0.5, 1.0, 1.5, 2.0, 3.0), mask=None):
    """Where does the edge die? Report the break-even cost multiple."""
    df, w, r, h = lab.bars(sym)
    if mask is None: mask = r
    out = []
    for m in mults:
        bk = lab.book(sym, idx, side, cost_mult=m, **geom)
        sub = bk[np.isin(bk.sig_bar, np.where(mask)[0])]
        out.append((m, len(sub), float(sub.net.mean()) if len(sub) else np.nan))
    return out


def subperiods(sym, tr, k=3, mask=None):
    """Is the P&L delivered throughout, or in one lucky window?"""
    df, w, r, h = lab.bars(sym)
    if mask is None: mask = r
    tr = tr[np.isin(tr.sig_bar, np.where(mask)[0])]
    if len(tr) < 30: return []
    sess = df.sess.values[tr.sig_bar.values]
    qs = np.quantile(sess, np.linspace(0, 1, k+1))
    out = []
    for i in range(k):
        m = (sess >= qs[i]) & (sess <= qs[i+1]) if i == k-1 else (sess >= qs[i]) & (sess < qs[i+1])
        s = tr[m]
        out.append((i, len(s), float(s.net.mean()) if len(s) else np.nan))
    return out
