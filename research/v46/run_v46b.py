"""V46 -- freeze, then read the holdout ONCE: locked US100, two held-back markets, control, MC.

TWO CANDIDATES, both declared before anything outside the research block is opened.

  CONSENSUS  the modal setting of each axis over the top 1000 by fold median -- STUDY_V14's rule,
             because the top ROW of a 999,717-cell grid is the maximum of ~613,000 positive draws
             and its own neighbourhood is what decides whether it is a ridge or a spike.
  TOP ROW    the single best cell, carried only so the gap between the two can be read.

THE CONTROL is a random entry at matched trade count with the IDENTICAL exit rule, stop, target,
max hold, fill convention and costs. It prices drift, the cost floor and the exit geometry at once,
so what is left is the Carver trigger. A trend-following system on a market that rose is a drift
harvester until proven otherwise, and this is what proves it either way.

MONTE CARLO, both kinds, because they answer different questions: a day-block BOOTSTRAP resamples
whole days with their trades attached and prices the EDGE; a PERMUTATION reorders the realised
trades and prices the PATH. Permuting cannot change the endpoint, so an endpoint distribution from
it would be meaningless.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle")
sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v46")
import v38feeds as FD        # noqa: E402
import v46grid as G          # noqa: E402
import carver as CV          # noqa: E402

SPLIT = 0.65
COSTS = {"US100L": (0.72, 0.25), "US30L": (1.50, 0.50), "NQ": (0.72, 0.25)}
PV = {"US100L": 2.0, "US30L": 5.0, "NQ": 2.0}

CONSENSUS = dict(tf=60, span=320, sd=8, exit_thr=None, stop=3.0, tp=0.0, hold=480,
                 entry_thr=5.0, mode="cross", chop=100.0)
TOPROW = dict(tf=60, span=80, sd=2, exit_thr=None, stop=3.0, tp=0.0, hold=480,
              entry_thr=0.0, mode="cross", chop=100.0)


def nq_frame(tf):
    import data as TD
    d = TD.bars("NQ", 15 if tf == 15 else 15)
    f = pd.DataFrame({"open": d["o"], "high": d["h"], "low": d["l"], "close": d["c"]},
                     index=pd.to_datetime(pd.Series(d["idx"])).dt.tz_localize(None))
    if tf != 15:
        f = f.resample(f"{tf}min").agg({"open": "first", "high": "max", "low": "min",
                                        "close": "last"}).dropna()
    return dict(o=f["open"].to_numpy(float), h=f["high"].to_numpy(float),
                l=f["low"].to_numpy(float), c=f["close"].to_numpy(float),
                ts=f.index.values.astype("datetime64[ns]").astype(np.int64),
                mod=(f.index.hour * 60 + f.index.minute).to_numpy(np.int64))


def prep_any(market, tf):
    cost, slip = COSTS[market]
    if market == "NQ":
        d = nq_frame(tf)
        atr = G.rma(G.true_range(d["h"], d["l"], d["c"]), 14)
        ch = G.chop_idx(d["h"], d["l"], d["c"], 14)
        fc = {(s, sd): CV.forecast(d["c"], s, sd) for s in G.SPANS for sd in G.SMOOTH_DIV}
        ts = d["ts"]
        fold = np.searchsorted(np.quantile(ts, np.linspace(0, 1, G.N_FOLDS + 1)[1:-1]),
                               ts).astype(np.int64)
        return dict(o=d["o"], h=d["h"], l=d["l"], c=d["c"], atr=atr, chop=ch, fc=fc,
                    n=len(d["c"]), ts=ts, fold=fold, cost=cost, slip=slip, tf=tf, market=market)
    return G.prep(market, tf, cost, slip)


def run_cfg(P, cfg, block):
    ex = cfg["exit_thr"]
    xb, pnl, amb = G.walk_exits(P["o"], P["h"], P["l"], P["c"], P["atr"],
                                P["fc"][(cfg["span"], cfg["sd"])],
                                0.0 if ex is None else float(ex), ex is not None,
                                cfg["stop"], cfg["tp"], cfg["hold"], P["cost"], P["slip"])
    sb = G.signal_bars(P, cfg["span"], cfg["sd"], cfg["entry_thr"], cfg["mode"],
                       cfg["chop"], block)
    keep, last = [], -1
    for i in sb:
        if i <= last or xb[i] < 0 or not np.isfinite(pnl[i]):
            continue
        keep.append(i); last = xb[i]
    keep = np.asarray(keep, np.int64)
    return keep, pnl[keep], xb, pnl, amb


def control(P, cfg, block, xb, pnl, n_target, draws=400, seed=17):
    pool = np.flatnonzero(block & np.isfinite(pnl) & (xb >= 0))
    if len(pool) < n_target * 3:
        return None
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(draws):
        pick = np.sort(rng.choice(pool, min(n_target * 3, len(pool)), replace=False))
        keep, last, got = [], -1, 0
        for i in pick:
            if i <= last:
                continue
            keep.append(i); last = xb[i]; got += 1
            if got >= n_target:
                break
        if len(keep) >= max(20, n_target // 2):
            out.append(pnl[np.asarray(keep, np.int64)].mean())
    return np.asarray(out) if out else None


def boot_days(ts, p, draws=2000, seed=5):
    day = (ts // 86_400_000_000_000).astype(np.int64)
    ud = np.unique(day)
    idx = {u: np.flatnonzero(day == u) for u in ud}
    rng = np.random.default_rng(seed)
    out = np.empty(draws)
    for k in range(draws):
        pick = rng.choice(ud, len(ud), replace=True)
        v = np.concatenate([p[idx[u]] for u in pick])
        out[k] = v.mean() if len(v) else 0.0
    return out


def perm_dd(p, draws=2000, seed=9):
    rng = np.random.default_rng(seed)
    out = np.empty(draws)
    for k in range(draws):
        q = rng.permutation(p)
        eq = np.cumsum(q)
        out[k] = float(np.max(np.maximum.accumulate(eq) - eq))
    eq = np.cumsum(p)
    real = float(np.max(np.maximum.accumulate(eq) - eq))
    return real, out


def main():
    rows = []
    for cname, cfg in (("CONSENSUS", CONSENSUS), ("TOP ROW", TOPROW)):
        print("\n" + "=" * 104)
        print(f"  {cname}:  {cfg['tf']}m  Carver span {cfg['span']} / smooth {cfg['sd']}  "
              f"entry {cfg['mode']} >= {cfg['entry_thr']}  stop {cfg['stop']}N  "
              f"tp {'none' if cfg['tp']==0 else str(cfg['tp'])+'R'}  hold {cfg['hold']}  "
              f"chop {'off' if cfg['chop']>=100 else cfg['chop']}  forecast-exit "
              f"{'off' if cfg['exit_thr'] is None else cfg['exit_thr']}")
        print("=" * 104)
        for market in ("US100L", "US30L", "NQ"):
            P = prep_any(market, cfg["tf"])
            n = P["n"]
            res = np.arange(n) < int(n * SPLIT)
            blocks = ([("research", res), ("LOCKED", ~res)] if market == "US100L"
                      else [("ALL (never seen)", np.ones(n, bool))])
            for bname, blk in blocks:
                keep, p, xb, pnl_all, amb = run_cfg(P, cfg, blk)
                if len(p) < 25:
                    print(f"    {market:<7} {bname:<16} {len(p)} trades -- too few"); continue
                gw = p[p > 0].sum(); gl = -p[p < 0].sum()
                pf = gw / gl if gl > 0 else np.nan
                pv = PV[market]
                ctl = control(P, cfg, blk, xb, pnl_all, len(p))
                cmean = float(np.mean(ctl)) if ctl is not None else np.nan
                pval = float(np.mean(ctl >= p.mean())) if ctl is not None else np.nan
                bs = boot_days(P["ts"][keep], p)
                p_le0 = float(np.mean(bs <= 0))
                real_dd, dds = perm_dd(p)
                amb_share = float(amb[keep].mean())
                print(f"    {market:<7} {bname:<16} n {len(p):>5}  PF {pf:5.3f}  "
                      f"pts {p.mean():+8.2f}  (${p.mean()*pv:+9.2f})  win {(p>0).mean():5.1%}")
                print(f"            control {cmean:+8.2f} pts   p {pval:.3f}   |  "
                      f"bootstrap P(mean<=0) {p_le0:.3f}  [{np.percentile(bs,5):+.1f}, "
                      f"{np.percentile(bs,95):+.1f}]")
                print(f"            drawdown realised {real_dd:,.0f} pts   MC median "
                      f"{np.median(dds):,.0f}  p95 {np.percentile(dds,95):,.0f}  "
                      f"p99 {np.percentile(dds,99):,.0f}   |  intrabar-ambiguous "
                      f"{amb_share:.1%} of trades")
                rows.append(dict(cfg=cname, market=market, block=bname, n=len(p), pf=float(pf),
                                 pts=float(p.mean()), usd=float(p.mean()*pv),
                                 win=float((p>0).mean()), ctl=cmean, p=pval,
                                 boot_p=p_le0, dd=real_dd, dd_p99=float(np.percentile(dds,99)),
                                 amb=amb_share))
    pd.DataFrame(rows).to_csv("results/v46/v46_frozen.csv", index=False)
    return rows


if __name__ == "__main__":
    main()
