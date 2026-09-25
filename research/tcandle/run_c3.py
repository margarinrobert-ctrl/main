"""Gate 2 -- every candlestick reading as a VETO, against a random gate of the same selectivity.

THREE THINGS THIS DOES THAT A NAIVE FEATURE SCREEN DOES NOT.

1. IT SCORES A VETO, NOT A SUBSET.  Splitting the unfiltered run's realised trades by a feature is
   not what a script does: a script decides which bars may OPEN a trade, so refusing one releases
   the position lock and admits a LATER breakout the unfiltered run never saw.  Every arm here is
   re-simulated end to end.  `STUDY_XAU_CVD_FEATURES` measured the two framings disagreeing.

2. THE NULL IS A RANDOM GATE OF THE SAME SELECTIVITY, NOT ZERO.  Restrictiveness alone raises
   profit factor -- `STUDY_V12` found an ATR-expansion filter taking PF 1.42 -> 1.77 and being
   indistinguishable from a coin flip keeping the same number of bars.

3. BOTH POLARITIES ARE ON THE GRID.  A pattern is tested as "require it" and as "refuse it".  On a
   long-only breakout the bullish readings are the ones expected to be inert and the REJECTION
   readings are the ones with a prior, so testing only the textbook direction would answer the
   easier half of the question.

The screen cell is chosen by TRADE COUNT among the 240m cells -- a sample-size criterion that
cannot see an outcome -- and fixed before anything is scored.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research/tcandle")
import tc_core as T, tc_feat as CF                      # noqa: E402

N_DRAW = 200
MIN_TRADES = 25


def prep(mkt, tf, adx_max=22.0, ext_max=0.0, reach="carried"):
    d = T.frame(mkt, tf)
    atr, adx, dist = T.context(d)
    if reach == "matched":
        from run_c2 import lengths
        e1, e2, x1, x2 = lengths(tf, "matched")
    else:
        e1, e2, x1, x2 = T.SPEC["e1"], T.SPEC["e2"], T.SPEC["x1"], T.SPEC["x2"]
    C = T.channels(d, e1, e2, x1, x2)
    base = T.gate_mask(adx, dist, adx_max, ext_max) & np.isfinite(atr) & (atr > 0)
    return d, atr, C, base, T.split(d)


def masks_for(F, sig, thr=None):
    """Turn each feature into a pair of boolean bar masks: require it, refuse it.

    A continuous feature is cut at its RESEARCH-BLOCK median over the SIGNAL BARS and that number
    is carried unchanged to every later block -- a whole-sample quantile reads the future."""
    out, cuts = {}, {}
    for k, v in F.items():
        u = np.unique(v[np.isfinite(v)])
        if len(u) <= 2 and set(u.tolist()) <= {0.0, 1.0}:
            on = np.nan_to_num(v, nan=0.0) > 0.5
        else:
            t = float(np.nanmedian(v[sig])) if thr is None else thr[k]
            cuts[k] = t
            on = np.nan_to_num(v, nan=-np.inf) >= t
        out[f"{k} [require]"] = on
        out[f"{k} [refuse]"] = ~on
    return out, cuts


def screen(mkt, tf, n_draw=N_DRAW, reach="carried"):
    d, atr, C, base, cut = prep(mkt, tf, reach=reach)
    cost = T.COST[mkt]
    m0 = base.copy(); m0[cut:] = False
    tr0 = T.run(d, C, atr, m0, cost)
    sig0 = T.signal_bars(d, C, m0, atr)
    F = CF.build(d, atr)
    M, cuts = masks_for(F, sig0)
    pnl0 = tr0["pnl"].to_numpy(float)
    pf0 = pnl0[pnl0 > 0].sum() / max(-pnl0[pnl0 < 0].sum(), 1e-9)
    # The null depends on the arm ONLY through its selectivity, so the draws are cached by the
    # kept fraction rounded to 2 decimals.  That turns 96 sets of 200 re-simulations into ~25 and
    # changes nothing about the test -- a random gate keeping 37% of bars is the same null whichever
    # feature happens to keep 37%.
    ctl_cache: dict = {}

    def null_for(keep):
        k = round(float(keep), 2)
        if k not in ctl_cache:
            ctl_cache[k] = T.random_gate(d, C, atr, m0, k, cost, seed=int(k * 1000) + 7,
                                         n_draw=n_draw)
        return ctl_cache[k]

    rows = []
    for name, on in M.items():
        m = m0 & on
        keep = float(on[sig0].mean())
        if keep <= 0.02 or keep >= 0.995:
            rows.append(dict(arm=name, keep=keep, n=np.nan, pct=np.nan, pf=np.nan,
                             ctl=np.nan, p=np.nan, note="inert"))
            continue
        tr = T.run(d, C, atr, m, cost)
        if len(tr) < MIN_TRADES:
            rows.append(dict(arm=name, keep=keep, n=len(tr), pct=np.nan, pf=np.nan,
                             ctl=np.nan, p=np.nan, note="thin"))
            continue
        ctl = null_for(keep)
        pnl = tr["pnl"].to_numpy(float)
        rows.append(dict(arm=name, keep=keep, n=len(tr), pct=tr["pct"].mean(),
                         pf=pnl[pnl > 0].sum() / max(-pnl[pnl < 0].sum(), 1e-9),
                         ctl=float(np.median(ctl)), p=T.pval(tr["pct"].mean(), ctl),
                         delta=tr["pct"].mean() - tr0["pct"].mean(),
                         mde=mde(tr["pct"].std(ddof=1), len(tr)), note=""))
    base_row = dict(arm="<< no filter >>", keep=1.0, n=len(tr0), pct=tr0["pct"].mean(),
                    pf=pf0, ctl=np.nan, p=np.nan, delta=0.0,
                    mde=mde(tr0["pct"].std(ddof=1), len(tr0)), note="baseline")
    return pd.DataFrame([base_row] + rows), cuts, (d, atr, C, base, cut, F)


def mde(sd, n, alpha_t=2.802):
    """Minimum detectable effect: `t * sd / sqrt(n)`.  The branch's own instrument for reading a
    null -- an arm inside its own MDE has not been shown to be absent, only to be unresolvable, and
    saying which of the two a result is the difference between evidence and a shrug."""
    return alpha_t * sd / np.sqrt(max(n, 1))


def e_max_normal(n):
    from scipy.stats import norm
    g = 0.5772156649015329
    return (1 - g) * norm.ppf(1 - 1.0 / n) + g * norm.ppf(1 - 1.0 / (n * np.e))


def bh(p, q=0.10):
    p = np.asarray(p, float)
    ok = np.isfinite(p)
    idx = np.where(ok)[0][np.argsort(p[ok])]
    m = len(idx)
    keep = np.zeros(len(p), bool)
    for i, j in enumerate(idx, 1):
        if p[j] <= q * i / m:
            keep[idx[:i]] = True
    return keep


def collapse(F, sig, thresh=0.98):
    """Correlation ON THE SIGNAL BARS.  A filter only ever acts on the bars the base fires on, and
    this branch has caught its own pool duplicating seven times -- twice at rho exactly 1.0000."""
    names = list(F)
    X = np.column_stack([np.nan_to_num(F[k][sig], nan=0.0) for k in names])
    sd = X.std(0)
    keep = sd > 0
    R = np.corrcoef(X[:, keep].T)
    nm = [n for n, k in zip(names, keep) if k]
    pairs = []
    for i in range(len(nm)):
        for j in range(i + 1, len(nm)):
            if abs(R[i, j]) >= thresh:
                pairs.append((nm[i], nm[j], float(R[i, j])))
    return sorted(pairs, key=lambda t: -abs(t[2])), int((~keep).sum())


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    # THE SCREEN CELL MUST PASS GATE 1.  A meta layer on a primary with no edge produces a primary
    # with no edge and fewer trades, so the pool of candidate cells is restricted to the ones whose
    # RESEARCH block cleared a matched random entry, and the one with the most trades is taken --
    # a sample-size criterion, which cannot see an outcome.
    g1 = pd.read_csv("research/tcandle/c1_gate1.csv").assign(reach="carried")
    try:
        g1b = pd.read_csv("research/tcandle/c1b_gate1_matched.csv").assign(reach="matched")
        g1 = pd.concat([g1, g1b], ignore_index=True)
    except FileNotFoundError:
        pass
    r = g1[(g1.block == "A_research") & (g1.p <= 0.05)].sort_values("n", ascending=False)
    print("cells that PASSED Gate 1 on research:")
    print(r[["mkt", "tf", "reach", "n", "pct", "pf", "p"]].to_string(
        index=False, float_format=lambda x: f"{x:,.4f}"))
    if not len(r):
        print("\nNO CELL PASSES GATE 1 -- the feature screen is not run and no block is spent.")
        sys.exit(0)
    b = r.iloc[0]
    mkt, tf, reach = str(b["mkt"]), int(b["tf"]), str(b["reach"])
    sd = float(np.nan)
    print(f"\nscreen cell (most trades among Gate-1 passes): {mkt} {tf}m {reach}, "
          f"{int(b['n'])} research trades\n")

    df, cuts, ctx = screen(mkt, tf, reach=reach)
    df.to_csv("research/tcandle/c3_screen.csv", index=False)
    d, atr, C, base, cut, F = ctx

    sig0 = T.signal_bars(d, C, (base & (np.arange(len(d["c"])) < cut)), atr)
    dup, const = collapse(F, sig0)
    print("=" * 96)
    print(f"POOL AUDIT -- {len(F)} features, {const} constant on the signal bars")
    print("=" * 96)
    for a, b, r in dup[:12]:
        print(f"  rho {r:+.4f}   {a}   vs   {b}")
    print(f"  ({len(dup)} pairs at |rho| >= 0.98)")

    print("\n" + "=" * 96)
    print(f"GATE 2 SCREEN -- {mkt} {tf}m {reach} research, veto vs a random gate of same selectivity")
    print("=" * 96)
    s = df[df.note == ""].copy()
    s["bh"] = bh(s.p.to_numpy())
    s = s.sort_values("p")
    print(df[df.note == "baseline"].to_string(index=False, float_format=lambda x: f"{x:,.4f}"))
    print(s.head(16).to_string(index=False, float_format=lambda x: f"{x:,.4f}"))
    n_sc = len(s)
    print(f"\nscorable arms: {n_sc}   inert: {(df.note=='inert').sum()}   thin: {(df.note=='thin').sum()}")
    print(f"clearing p<=0.05: {(s.p<=0.05).sum()}   expected by chance: {0.05*n_sc:.1f}"
          f"   surviving BH q=0.10: {int(s.bh.sum())}")
    print(f"E[max t | pure noise] over {n_sc} arms: {e_max_normal(max(n_sc,2)):.3f}"
          f"   (detection needs t >= 2.802)")
    inside = (np.abs(s.delta) < s.mde).sum()
    print(f"arms whose |delta vs the unfiltered base| is INSIDE their own MDE: {inside} of {n_sc}"
          f"   -- median MDE {s.mde.median():.4f} %/trade against a median |delta| of "
          f"{np.abs(s.delta).median():.4f}")
    import json
    json.dump({"mkt": mkt, "tf": tf, "reach": reach, "cuts": cuts,
               "survivors": s[s.p <= 0.05].arm.tolist(),
               "bh": s[s.bh].arm.tolist()},
              open("research/tcandle/c3_survivors.json", "w"), indent=1)
