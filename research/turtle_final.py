"""The last stage: the ten gates, the robustness probes, and the single locked read.

`docs/RESEARCH_PROTOCOL.md` §3 lists ten conditions a strategy must clear to be called tradeable.
They are implemented here as a table rather than as prose, so a candidate cannot pass by being
described well.  Every threshold is the protocol's, unchanged.

The locked block is read exactly once, by `final()`, after every research-side number is fixed.
The multiplicity is printed before the result, and a candidate that scores BETTER on the holdout
than on research is flagged as a defect -- `CLAUDE.md` records that shape appearing twice on this
repository and being wrong both times.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats as sps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turtle_bars as B
import turtle_metrics as M
import turtle_search as S
import turtle_sim as T
import turtle_tensor as X
import turtle_validate as V
from turtle_sim import P


def newey_west_t(x: np.ndarray, lag: int | None = None) -> float:
    """t-statistic of the mean with a Newey-West covariance.

    Session P&L streams here do not overlap -- a scalp is flat by 11:00 -- so the dependence being
    corrected for is volatility clustering rather than label overlap, and the automatic
    4(n/100)^(2/9) lag is appropriate.  Where a study uses overlapping forward windows the lag
    must cover the overlap instead; that is a different situation and this is not it.
    """
    n = len(x)
    if n < 10:
        return 0.0
    if lag is None:
        lag = max(1, int(4 * (n / 100.0) ** (2.0 / 9.0)))
    e = x - x.mean()
    g0 = float((e * e).sum() / n)
    s = g0
    for k in range(1, lag + 1):
        gk = float((e[k:] * e[:-k]).sum() / n)
        s += 2.0 * (1.0 - k / (lag + 1.0)) * gk
    if s <= 0:
        return 0.0
    return float(x.mean() / math.sqrt(s / n))


def monte_carlo(trade_pnl: np.ndarray, reps: int = 5000, seed: int = 20250822) -> dict:
    """Reshuffle trade order: the drawdown distribution behind the one observed path."""
    if len(trade_pnl) < 20:
        return {}
    rng = np.random.default_rng(seed)
    dds = np.empty(reps)
    finals = np.empty(reps)
    for r in range(reps):
        v = rng.permutation(trade_pnl)
        eq = np.cumsum(v)
        dds[r] = float(np.max(np.maximum.accumulate(eq) - eq))
        finals[r] = eq[-1]
    return {"mc_dd_median": float(np.median(dds)), "mc_dd_p95": float(np.percentile(dds, 95)),
            "mc_p_loss": float((finals <= 0).mean()),
            "observed_dd": float(np.max(np.maximum.accumulate(np.cumsum(trade_pnl))
                                        - np.cumsum(trade_pnl)))}


def by_year(s, sc, net: np.ndarray, lo: int, hi: int) -> pd.DataFrame:
    sid = s.sess[sc.exit_bar]
    keep = (sid >= lo) & (sid < hi)
    if not keep.any():
        return pd.DataFrame()
    ts = s.ts[sc.exit_bar[keep]]
    yr = (np.datetime64("1970-01-01T00:00") +
          ts.astype("timedelta64[m]")).astype("datetime64[Y]").astype(int) + 1970
    d = pd.DataFrame({"year": yr, "net": net[keep]})
    g = d.groupby("year").agg(trades=("net", "size"), net=("net", "sum"),
                              per_trade=("net", "mean"),
                              win=("net", lambda v: float((v > 0).mean())))
    tot = g.net[g.net > 0].sum()
    g["share_of_gains"] = g.net.clip(lower=0) / tot if tot > 0 else 0.0
    return g


def cost_sensitivity(s, p: P, spec: dict, name: str, lo: int, hi: int,
                     mults=(0.5, 1.0, 1.5, 2.0, 3.0)) -> pd.DataFrame:
    """The same trades priced at several cost assumptions.

    Free, because the tensor caches the GROSS move and every cost term is affine in the unit
    count.  Protocol gate 6 asks for survival at 1.5x; the 0.5x column is here because the gold
    cost line is a retail spot spread and a futures desk pays about half of it.
    """
    ex = X.build(s, p)
    sc = X.scan(s, ex, T.signal_bars(s, p), p)
    sid = s.sess[sc.exit_bar] if len(sc) else np.zeros(0, np.int64)
    keep = (sid >= lo) & (sid < hi)
    rows = []
    for m in mults:
        net = sc.net(spec["cost_abs"] * m, spec["cost_bp"] * m, spec["stop_slip"] * m,
                     p.tp_rests) * spec["point_value"] - sc.units * spec.get("comm", 0.0) * m
        v = net[keep]
        daily = np.zeros(hi - lo)
        np.add.at(daily, sid[keep] - lo, v)
        sd = daily.std(ddof=1)
        win, loss = v[v > 0].sum(), -v[v < 0].sum()
        rows.append({"cost_x": m, "n": int(keep.sum()), "net": float(v.sum()),
                     "per_trade": float(v.mean()) if keep.any() else 0.0,
                     "sharpe": float(daily.mean() / sd * math.sqrt(M.SESSIONS_PER_YEAR[name]))
                     if sd > 0 else 0.0,
                     "pf": float(win / loss) if loss > 0 else float("inf")})
    return pd.DataFrame(rows)


def breakeven_cost(cost: pd.DataFrame) -> dict:
    """The cost multiple at which the per-trade result reaches zero.

    Net per-trade is affine in the cost multiplier -- `per_trade(m) = gross - m * cost` -- because
    every cost term scales with the unit count and none of them changes a decision.  Two points on
    the curve therefore give the whole line, and the intercept is the number that matters most for
    a marginal scalping result: `RESEARCH_PROTOCOL.md` calls it the safety margin, and on an
    instrument where the edge is real but smaller than the spread it is the difference between "no
    edge" and "wrong venue".
    """
    a = cost[cost.cost_x == 1.0]
    b = cost[cost.cost_x == 2.0]
    if not len(a) or not len(b):
        return {}
    p1, p2 = float(a.per_trade.iloc[0]), float(b.per_trade.iloc[0])
    c = p1 - p2                                  # cost charged per trade at 1x
    if c <= 0:
        return {"cost_per_trade": c, "breakeven_x": float("nan")}
    return {"cost_per_trade": c, "gross_per_trade": p1 + c, "breakeven_x": (p1 + c) / c}


def gates(research: dict, locked: dict, pbo: float, wf_eff: float, nb: dict,
          cost: pd.DataFrame, years: pd.DataFrame, hac_t: float) -> pd.DataFrame:
    """The protocol's ten gates, evaluated on the OUT-OF-SAMPLE record."""
    sub = years.net > 0
    rows = [
        ("1  >= 100 out-of-sample trades", locked["n"] >= 100, f"{locked['n']:,}"),
        ("2  positive net edge after costs", locked["per_trade"] > 0,
         f"${locked['per_trade']:.2f}/trade"),
        ("3  HAC t-stat > 2", hac_t > 2.0, f"{hac_t:.2f}"),
        ("4  Deflated Sharpe > 0.95", locked.get("dsr", 0) > 0.95, f"{locked.get('dsr', 0):.4f}"),
        ("5  PBO < 0.30", (pbo == pbo) and pbo < 0.30, f"{pbo:.3f}"),
        ("6  survives 1.5x modelled costs",
         bool((cost.loc[cost.cost_x == 1.5, "per_trade"] > 0).all()) if (cost.cost_x == 1.5).any()
         else False,
         f"${float(cost.loc[cost.cost_x == 1.5, 'per_trade'].iloc[0]):.2f}/trade"
         if (cost.cost_x == 1.5).any() else "n/a"),
        ("7  parameter surface is not a spike", nb.get("verdict") in ("plateau", "ridge"),
         f"{nb.get('verdict')} ({nb.get('stability', float('nan')):.2f})"),
        ("8  profitable in >= 60% of years", float(sub.mean()) >= 0.6 if len(years) else False,
         f"{float(sub.mean()):.0%}" if len(years) else "n/a"),
        ("9  no single year > 60% of gains",
         float(years.share_of_gains.max()) <= 0.6 if len(years) else False,
         f"{float(years.share_of_gains.max()):.0%}" if len(years) else "n/a"),
        ("10 walk-forward efficiency >= 0.4", (wf_eff == wf_eff) and wf_eff >= 0.4,
         f"{wf_eff:.2f}"),
    ]
    return pd.DataFrame(rows, columns=["gate", "pass", "value"])


def final(name: str, tf: int, p: P, n_trials: int, trial_sd: float,
          candidates: pd.DataFrame | None = None, sweep_df: pd.DataFrame | None = None,
          draws: int = 500, label: str = "") -> dict:
    """Everything, in order, ending with the single locked read."""
    spec = B.INSTRUMENTS[name]
    full = B.load(name, tf)
    cut = B.split_session(full)
    n_sess = int(full.sess.max()) + 1
    s = full.window(S.WIN_LO, S.WIN_HI)
    spy = M.SESSIONS_PER_YEAR[name]

    print("=" * 108)
    print(f"FINAL -- {label or name} {tf}m")
    print("=" * 108)

    # --- research-side probes -------------------------------------------------
    res = {}
    if candidates is not None and len(candidates) >= 20:
        mat = V.daily_matrix(s.slice_sessions(0, cut), candidates, spec, cut)
        keep = mat.std(axis=0) > 0
        mat = mat[:, keep]
        res["pbo"] = V.pbo_cscv(mat)
        res["wf"] = V.walk_forward(mat, train=max(250, cut // 6), test=max(60, cut // 24))
        # Effective independent trials: the eigenvalue participation ratio of the candidate
        # correlation matrix.  645,120 cells are nothing like 645,120 independent bets, and the
        # protocol's cell-count deflation is correspondingly conservative.
        cm = np.corrcoef(mat, rowvar=False)
        cm = np.nan_to_num(cm, nan=0.0)
        ev = np.linalg.eigvalsh(cm)
        ev = ev[ev > 0]
        res["n_eff_candidates"] = float(ev.sum() ** 2 / (ev ** 2).sum()) if len(ev) else 1.0
        res["mean_corr"] = float((cm.sum() - len(cm)) / max(len(cm) ** 2 - len(cm), 1))
        usr = mat.mean(axis=0) / mat.std(axis=0, ddof=1) * math.sqrt(spy)
        res["universe_sharpe"] = {"min": float(usr.min()), "median": float(np.median(usr)),
                                  "max": float(usr.max()),
                                  "share_positive": float((usr > 0).mean())}
        print(f"  universe: {mat.shape[1]:,} uniformly sampled grid cells;  Sharpe "
              f"min {usr.min():.2f} / median {np.median(usr):.2f} / max {usr.max():.2f}, "
              f"{float((usr > 0).mean()):.0%} above zero")
        print(f"  they are one strategy with knobs: mean pairwise daily-P&L correlation "
              f"{res['mean_corr']:.2f}, effective independent configurations "
              f"{res['n_eff_candidates']:.1f}")
        print(f"  PBO {res['pbo']['pbo']:.3f} over {res['pbo']['n_splits']} splits   "
              f"walk-forward: {res['wf'].get('folds', 0)} folds, efficiency "
              f"{res['wf'].get('efficiency', float('nan')):.2f}, stitched OOS Sharpe "
              f"{res['wf'].get('oos_sharpe_per_sess', 0) * math.sqrt(spy):.2f} on "
              f"{res['wf'].get('oos_sessions', 0):,} sessions (net "
              f"${res['wf'].get('oos_net', 0):,.0f}), parameter stability "
              f"{res['wf'].get('param_stability', 0):.0%}")
    nb = V.neighbourhood_direct(name, tf, p, verbose=False)
    res["neighbourhood"] = nb
    print(f"  neighbourhood: {nb.get('neighbours', 0)} one-step neighbours, median "
          f"{nb.get('median', float('nan')):.3f} against a base of {nb.get('base', 0):.3f} "
          f"(stability {nb.get('stability', float('nan')):.2f}) -> {nb.get('verdict')}")

    # --- the locked read ------------------------------------------------------
    out = V.reveal(s, p, spec, name, cut, n_trials, trial_sd, draws=draws,
                   label=label or f"{name} {tf}m")
    res["research"], res["locked"] = out["research"], out["locked"]

    ex = X.build(s, p)
    sc = X.scan(s, ex, T.signal_bars(s, p), p)
    net = sc.net(spec["cost_abs"], spec["cost_bp"], spec["stop_slip"], p.tp_rests) \
        * spec["point_value"] - sc.units * spec.get("comm", 0.0)
    sid = s.sess[sc.exit_bar] if len(sc) else np.zeros(0, np.int64)
    lk = (sid >= cut)

    print("\n  --- locked block, exit-reason split ---")
    for k, nm in enumerate(T.EXIT_NAMES):
        sel = lk & (sc.reason == k)
        if sel.sum():
            print(f"    {nm:<16} {sel.sum():5,d} trades  net ${net[sel].sum():>10,.0f}  "
                  f"/trade ${net[sel].mean():>8.2f}  win {float((net[sel] > 0).mean()):>5.1%}")

    cost = cost_sensitivity(s, p, spec, name, cut, n_sess)
    print("\n  --- locked block, cost sensitivity ---")
    print(cost.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    be = breakeven_cost(cost)
    if be:
        print(f"    gross ${be.get('gross_per_trade', 0):.2f}/trade against "
              f"${be['cost_per_trade']:.2f} of modelled cost -> break-even at "
              f"{be.get('breakeven_x', float('nan')):.2f}x the modelled round turn")
    res["breakeven"] = be

    years = by_year(s, sc, net, cut, n_sess)
    print("\n  --- locked block, by year ---")
    print(years.to_string(float_format=lambda v: f"{v:.3f}"))

    mc = monte_carlo(net[lk])
    if mc:
        print(f"\n  --- locked block, Monte Carlo trade reshuffle ---")
        print(f"    observed max drawdown ${mc['observed_dd']:,.0f};  median of reshuffles "
              f"${mc['mc_dd_median']:,.0f};  95th percentile ${mc['mc_dd_p95']:,.0f};  "
              f"P(net <= 0) {mc['mc_p_loss']:.1%}")
    res["mc"] = mc
    res["cost"] = cost
    res["years"] = years

    dl = V.daily_series(s, p, spec, n_sess)[cut:]
    hac = newey_west_t(dl)
    g = gates(res["research"], res["locked"], res.get("pbo", {}).get("pbo", float("nan")),
              res.get("wf", {}).get("efficiency", float("nan")), nb, cost, years, hac)
    print("\n  --- the ten gates, on the locked block ---")
    for _, r in g.iterrows():
        print(f"    [{'PASS' if r['pass'] else 'FAIL'}] {r.gate:<38} {r.value}")
    print(f"\n    {int(g['pass'].sum())} / 10 gates passed")
    res["gates"] = g
    res["hac_t"] = hac
    return res


__all__ = ["final", "gates", "cost_sensitivity", "breakeven_cost", "by_year",
           "monte_carlo", "newey_west_t"]
