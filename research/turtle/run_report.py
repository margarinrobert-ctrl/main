"""Stage 3: walk-forward, Monte Carlo, and feature/anomaly analysis of the surviving settings."""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from turtle import core, data as td
from turtle.run_validate import cfg_of

SPEC = dict(entry1=20, entry2=55, exit1=10, exit2=20, atr_mult=2.0,
            pyramid_step=0.5, max_units=4, skip_after_winner=True)


def walk_forward(inst, tf, cfg, n_folds=6, draws=120):
    """Rolling folds over the whole series. Thresholds are FIXED, so every fold is honest."""
    ck = td.COSTS[inst]
    d = td.bars(inst, tf)
    r = core.backtest(d, atr_len=20, cost_pts=ck["cost_pts"], slip_pts=ck["slip_pts"], **cfg)
    ix = pd.DatetimeIndex(d["idx"])
    n = len(d["c"]); edges = np.linspace(0, n, n_folds + 1).astype(int)
    rows = []
    for f in range(n_folds):
        blk = np.zeros(n, bool); blk[edges[f]:edges[f + 1]] = True
        sel = td.split_trades(r, blk)
        s = td.stats(r, sel, ck["point_value"])
        if s is None or s["n"] < 10:
            rows.append(dict(fold=f, start=str(ix[edges[f]].date()),
                             end=str(ix[edges[f + 1] - 1].date()), n=int(sel.sum())))
            continue
        c = core.control(d, cfg, blk, s["n"], draws=draws,
                         cost_pts=ck["cost_pts"], slip_pts=ck["slip_pts"])
        rows.append(dict(fold=f, start=str(ix[edges[f]].date()), end=str(ix[edges[f + 1] - 1].date()),
                         n=s["n"], win=s["win"], expR=s["expR"], pf=s["pf"],
                         ctrl=float(c.mean()) if c is not None else np.nan,
                         exc=s["expR"] - float(c.mean()) if c is not None else np.nan))
    return pd.DataFrame(rows)


def monte_carlo(R, n=20000, seed=3):
    """Permute for path risk; bootstrap with replacement for edge uncertainty."""
    R = np.asarray(R, float)
    if len(R) < 10:
        return None
    rng = np.random.default_rng(seed); m = len(R)
    dds = np.empty(n)
    for i in range(n):
        eq = np.cumsum(rng.permutation(R))
        dds[i] = np.max(np.maximum.accumulate(eq) - eq)
    boot = rng.choice(R, size=(n, m), replace=True)
    means = boot.mean(axis=1)
    return dict(trades=m, median_dd_R=float(np.percentile(dds, 50)),
                p95_dd_R=float(np.percentile(dds, 95)), worst_dd_R=float(dds.max()),
                mean_p05=float(np.percentile(means, 5)),
                mean_p50=float(np.percentile(means, 50)),
                mean_p95=float(np.percentile(means, 95)),
                p_edge_negative=float((means <= 0).mean()))


def trade_features(inst, tf, cfg, block_name="research"):
    """What distinguishes a winning Turtle trade from a losing one, read at the SIGNAL bar."""
    from edgelab import features as ef
    ck = td.COSTS[inst]
    d = td.bars(inst, tf)
    if "idx" not in d:
        return None
    F = ef.build(d)
    B = td.blocks(inst, d)
    r = core.backtest(d, atr_len=20, cost_pts=ck["cost_pts"], slip_pts=ck["slip_pts"], **cfg)
    sel = td.split_trades(r, B[block_name])
    sig = r["bar_in"][sel] - 1                      # entry fills at bar_in, signal is the bar before
    R = r["R"][sel]
    win = R > 0
    rows = []
    for name, arr in F.items():
        a = np.asarray(arr, float)[sig]
        m = np.isfinite(a)
        if m.sum() < 40 or len(np.unique(a[m])) < 5:
            continue
        w = a[m & win]; l = a[m & ~win]
        if len(w) < 15 or len(l) < 15:
            continue
        pooled = np.sqrt((w.var(ddof=1) + l.var(ddof=1)) / 2.0)
        if pooled <= 0:
            continue
        rows.append(dict(feature=name, d=(w.mean() - l.mean()) / pooled,
                         win_mean=w.mean(), loss_mean=l.mean(), n=int(m.sum())))
    df = pd.DataFrame(rows)
    return df.reindex(df["d"].abs().sort_values(ascending=False).index) if len(df) else df


def main():
    pd.set_option("display.width", 220)
    print("=" * 96)
    print("WALK-FORWARD, spec defaults, fixed thresholds -- every fold is out of sample")
    for inst, tf in (("NQ", 60), ("US100", 240)):
        print(f"\n{inst} {tf}m")
        print(walk_forward(inst, tf, SPEC).to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    print("\n" + "=" * 96)
    print("MONTE CARLO on the spec, US100 240m, out-of-sample trades")
    ck = td.COSTS["US100"]; d = td.bars("US100", 240); B = td.blocks("US100", d)
    r = core.backtest(d, atr_len=20, cost_pts=ck["cost_pts"], slip_pts=ck["slip_pts"], **SPEC)
    R = r["R"][td.split_trades(r, B["oos"])]
    mc = monte_carlo(R)
    for k, v in mc.items():
        print(f"  {k:<18} {v:+.3f}")

    print("\n" + "=" * 96)
    print("FEATURE SEPARATION of winning vs losing Turtle trades (US100 240m, research)")
    print("Cohen's d at the SIGNAL bar. This is descriptive, not a filter test.")
    tfx = trade_features("US100", 240, SPEC)
    print(tfx.head(15).to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print("\n  weakest 5 (nothing to see):")
    print(tfx.tail(5).to_string(index=False, float_format=lambda x: f"{x:.3f}"))


if __name__ == "__main__":
    main()
