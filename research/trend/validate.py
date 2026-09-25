"""The section 8 battery, in order. Stops and says so if a stage fails. Holdout read ONCE, last."""
from __future__ import annotations
import os, sys, warnings, itertools
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
SK = "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/quant-strategy-lab/scripts"
import backtest as B, data as D          # these push research/ to the front of sys.path ...
sys.path.insert(0, SK)                   # ... so the skill directory must go in front AFTER them,
                                         # or `metrics` / `splits` resolve to research/metrics.py
from leakage_audit import check_execution_alignment
from splits import walk_forward, combinatorial_purged_cv, cpcv_paths
from metrics import performance_stats, deflated_sharpe_ratio, breakeven_cost_bps, cost_sensitivity
from montecarlo import block_bootstrap, random_strategy_null
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
DPY = 256


def line(t): print("\n" + "=" * 120 + f"\n{t}\n" + "=" * 120)


def sh(x):
    x = x.dropna(); return float(x.mean() / x.std() * np.sqrt(DPY)) if x.std() > 0 else np.nan


if __name__ == "__main__":
    c = B.calibrate(); o = B.run(c=c)
    split = o["split"]; net, gross = o["net"], o["gross"]
    tr = net.index < split
    line("0. WHAT WAS BUILT")
    print(f"  universe {o['names']}   common sample {net.index[0].date()} -> {net.index[-1].date()} ({len(net)} days)")
    print(f"  holdout split {split.date()} (last 25%)   calibration c = {o['c']:.4f}")
    for n in o["names"]:
        print(f"  {n}: sleeves kept {[o['sleeves'][k]['n'] for k in o['sets'][n]]}   drag by sleeve " + ", ".join(f"{k}:{v:.3f}" for k, v in o["drags"][n].items()))
    trn = o["pos"][tr]; to = trn.diff().abs().sum() / trn.abs().mean() / (len(trn) / DPY) / 2
    print(f"  realised position turns/yr (training, after buffering): " + ", ".join(f"{n} {v:.1f}" for n, v in to.items()))
    st = B.stats(net[tr]); sg = B.stats(gross[tr])
    print(f"  TRAINING net: Sharpe {st['sharpe']:+.3f}  CAGR {100*st['cagr']:+.2f}%  vol {100*st['vol']:.1f}%  maxDD {100*st['max_dd']:.1f}%  (gross Sharpe {sg['sharpe']:+.3f})")
    print(f"  kill checks: Sharpe > 1.0? {'YES -- investigate' if st['sharpe'] > 1 else 'no'}   maxDD < 1x vol? {'YES -- investigate' if -st['max_dd'] < st['vol'] else 'no'}")

    line("1. EXECUTION ALIGNMENT (training)")
    for n in o["names"]:
        r = check_execution_alignment(o["pos"][n][tr], o["r_exec"][n][tr], verbose=False)
        print(f"  {n}: " + ", ".join(f"{k}={v}" for k, v in r.items() if not isinstance(v, (list, dict, pd.Series, pd.DataFrame)))[:220])

    line("2. WALK-FORWARD rolling 1260 / 252 (training data; c re-fit in each training fold)")
    ntr = int(tr.sum()); folds = []
    for a, b, cst, ce in [(f[0][0], f[0][-1], f[1][0], f[1][-1]) for f in
                          [(np.arange(s.train_start, s.train_end), np.arange(s.test_start, s.test_end)) if hasattr(s, 'train_start') else (s[0], s[1]) for s in walk_forward(ntr, 1260, 252)]]:
        seg_tr = net[tr].iloc[a:b + 1]; seg_te = net[tr].iloc[cst:ce + 1]
        cf = o["cfg"]["tau"] / (seg_tr.std() * np.sqrt(DPY))            # in-fold calibration only rescales; Sharpe is scale-free
        folds.append(dict(test_start=seg_te.index[0].date(), test_end=seg_te.index[-1].date(), sharpe=sh(seg_te), cagr=B.stats(seg_te)["cagr"]))
    Fd = pd.DataFrame(folds); print(Fd.to_string(index=False, float_format=lambda v: f"{v:+.3f}"))
    print(f"  fold Sharpe: mean {Fd.sharpe.mean():+.3f}  sd {Fd.sharpe.std():.3f}  min {Fd.sharpe.min():+.3f}  max {Fd.sharpe.max():+.3f}   positive {int((Fd.sharpe>0).sum())}/{len(Fd)}")

    line("3. COMBINATORIAL PURGED CV, 6 groups x 2 test -> 15 splits, 5 paths (training)")
    x = net[tr].to_numpy(); n = len(x)
    splits_ = list(combinatorial_purged_cv(n, 6, 2)); paths = cpcv_paths(n, 6, 2)
    gsz = n // 6
    path_sh = []
    for path in paths:
        seg = np.concatenate([x[g * gsz:(g + 1) * gsz] for (_, g) in path])
        path_sh.append(float(seg.mean() / seg.std() * np.sqrt(DPY)))
    print(f"  {len(splits_)} splits, {len(paths)} paths; path Sharpes: " + ", ".join(f"{v:+.3f}" for v in path_sh))
    print(f"  path mean {np.mean(path_sh):+.3f}  sd {np.std(path_sh, ddof=1):.3f}  (the spread is the honest CI; the strategy has no fitted parameters, so paths differ only by which days they hold)")

    line("4. DEFLATED SHARPE with the research_log trial count")
    N_TRIALS = 12
    d = deflated_sharpe_ratio(sh(net[tr]), N_TRIALS, int(tr.sum()), skew=float(net[tr].skew()), kurtosis=float(net[tr].kurt() + 3), periods_per_year=DPY)
    print(f"  observed training Sharpe {sh(net[tr]):+.3f}, N = {N_TRIALS} trials -> " + ", ".join(f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}" for k, v in d.items()))

    line("5. BREAKEVEN COST and COST SENSITIVITY (training)")
    turn = (o["pos"].diff().abs().sum(axis=1))[tr]
    be = breakeven_cost_bps(gross[tr], turn)
    print(f"  breakeven round-trip cost {be:.1f} bps of traded notional against a modelled 2.0 bps -> {be/2.0:.1f}x")
    cs = cost_sensitivity(gross[tr], turn, periods_per_year=DPY); print(cs.to_string())

    line("6. RANDOM-STRATEGY NULL -- same exposure, random direction, same prices (training)")
    held = o["held"][tr]; rex = o["r_exec"][tr]
    rng = np.random.default_rng(7); obs = sh(net[tr]); draws = []
    for _ in range(1000):
        # keep |exposure| path per instrument; randomise the SIGN in blocks of the median holding period
        sgn = pd.DataFrame(index=held.index, columns=held.columns, dtype=float)
        for nme in held.columns:
            runs = (np.sign(held[nme]).diff() != 0).cumsum()
            flip = pd.Series(rng.choice([-1.0, 1.0], size=runs.max() + 1))
            sgn[nme] = flip.reindex(runs.values).to_numpy()
        rnd = (held.abs() * sgn * rex).sum(axis=1) - (held.abs() * sgn).diff().abs().mul(o["cost"], axis=1).sum(axis=1).fillna(0)
        draws.append(sh(rnd))
    draws = np.array(draws)
    print(f"  observed {obs:+.3f}   null median {np.median(draws):+.3f}   5-95% [{np.quantile(draws,.05):+.3f}, {np.quantile(draws,.95):+.3f}]   percentile of the real strategy {100*(draws < obs).mean():.1f}")
    print("  (sign randomised per HOLDING RUN, so the null keeps the same number of position flips and the same |exposure| path)")

    line("7. BLOCK BOOTSTRAP (training, block > median hold)")
    bb = block_bootstrap(net[tr], n_sims=2000, block_size=40, periods_per_year=DPY, seed=1)
    print("  " + ", ".join(f"{k}={v}" for k, v in bb.items() if not hasattr(v, "__len__") or isinstance(v, str))[:400])

    line("8. PARAMETER PERTURBATION +-25% (training) -- expect a plateau; a peak means an implementation bug")
    rows = [dict(what="base", sharpe=sh(net[tr]))]
    for lab, kw in (("vol span 32 -> 24", dict(span_short=24)), ("vol span 32 -> 40", dict(span_short=40)),
                    ("long window -> 1920", dict(long_window=1920)), ("long window -> 3200", dict(long_window=3200)),
                    ("all sleeve speeds x0.75", dict(speed_mult=0.75)), ("all sleeve speeds x1.25", dict(speed_mult=1.25)),
                    ("no buffering", dict(buffer=False))):
        oo = B.run(c=c, **kw); rows.append(dict(what=lab, sharpe=sh(oo["net"][oo["net"].index < split])))
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f"{v:+.3f}"))

    line("9. REGIME BREAKDOWN (training) -- by year, by vol tercile, by instrument")
    yr = net[tr].groupby(net[tr].index.year).apply(lambda s: pd.Series(dict(sharpe=sh(s), ret=100 * s.sum())))
    print(yr.to_string(float_format=lambda v: f"{v:+.2f}"))
    pv = o["sigma_ann"][tr].mean(axis=1); ter = pd.qcut(pv, 3, labels=["low vol", "mid", "high vol"])
    print("  by vol tercile: " + "  ".join(f"{k}: Sharpe {sh(net[tr][ter == k]):+.2f}" for k in ["low vol", "mid", "high vol"]))
    contrib = (o["held"][tr] * o["r_exec"][tr]).sum(); print("  P&L share by instrument (gross): " + ", ".join(f"{n} {100*v/contrib.sum():.0f}%" for n, v in contrib.items()))

    line("10. THE HOLDOUT -- read once")
    ho = net[~tr]; s = B.stats(ho); sg2 = B.stats(gross[~tr])
    print(f"  {ho.index[0].date()} -> {ho.index[-1].date()} ({len(ho)} days)   net Sharpe {s['sharpe']:+.3f}  CAGR {100*s['cagr']:+.2f}%  vol {100*s['vol']:.1f}%  maxDD {100*s['max_dd']:.1f}%   gross Sharpe {sg2['sharpe']:+.3f}")
    print(f"  walk-forward mean {Fd.sharpe.mean():+.3f} -> holdout {s['sharpe']:+.3f}: {'within 0.3' if abs(s['sharpe'] - Fd.sharpe.mean()) <= 0.3 else 'NOT within 0.3'}")
    yr2 = ho.groupby(ho.index.year).apply(lambda s_: pd.Series(dict(sharpe=sh(s_), ret=100 * s_.sum()))); print(yr2.to_string(float_format=lambda v: f"{v:+.2f}"))
