"""The full statistical profile of ONE configuration, across independent worlds.

`dbt50_report.py` answers "which parameters matter". This answers "if I traded the best one, what
would the track record look like" -- and it reports every number against the two things that decide
whether any of them mean anything: a minute-of-day matched control in the same world, and the same
configuration run in a martingale world where there is nothing to capture.

The default configuration is the one with the best MEAN out-of-sample R per trade across the twelve
realistic-trend worlds, not the winner of any single world. Picking the best of one world is how a
backtest gets its headline number; picking the best mean across independent worlds is the least
dishonest version of the same question.

Everything is reported per trade in R, where 1R is the risk actually taken on that trade
(1.5 x ATR x $20). That is the fixed-fractional interpretation: it assumes each trade risks the
same fraction of the account, which is also what makes the Sharpe ratio below meaningful.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dbt50 as B
import synth50 as S

BEST = (20, 30.0, 3.0, 24)          # don_n, adx_min, tp_r, max_hold
BARS_PER_SESSION = (S.SESS_CLOSE - S.SESS_OPEN) // 5


def _dd(x):
    """Max peak-to-trough of a cumulative series, and the index it bottoms at."""
    eq = np.cumsum(x)
    peak = np.maximum.accumulate(eq)
    d = peak - eq
    return (float(d.max()), int(np.argmax(d))) if len(d) else (0.0, 0)


def _streak(loss):
    best = cur = 0
    for v in loss:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def profile(w, bk, block="oos"):
    """Every statistic for one world's book, restricted to one block."""
    m = ~bk["is_mask"] if block == "oos" else (bk["is_mask"] if block == "is"
                                              else np.ones(bk["n"], bool))
    if m.sum() < 10:
        return None
    R = bk["R"][m]; net = bk["net"][m]; why = bk["why"][m]; side = bk["side"][m]
    sig = bk["sig"][m]; ex = bk["exit"][m]
    sess = w.d["sess"][sig]
    n_sess = len(np.unique(w.d["sess"][w.cut:])) if block == "oos" else len(np.unique(w.d["sess"]))
    years = n_sess / S.DAYS_PER_YEAR
    wins = R > 0
    gw = R[wins].sum(); gl = -R[~wins].sum()
    # session-level R, zero-filled for flat days, so the Sharpe is not computed on trade days only
    per_sess = np.zeros(n_sess)
    u, inv = np.unique(sess, return_inverse=True)
    np.add.at(per_sess, np.arange(len(u)) % n_sess, np.bincount(inv, weights=R))
    sd = per_sess.std(ddof=1)
    ddR, _ = _dd(R)
    dd_dollars, _ = _dd(net)
    hold = ex - sig
    out = dict(
        n=int(m.sum()), years=round(years, 1), trades_per_year=m.sum() / years,
        R_mean=float(R.mean()), R_se=float(R.std(ddof=1) / np.sqrt(len(R))),
        R_median=float(np.median(R)), R_sd=float(R.std(ddof=1)),
        R_total=float(R.sum()), R_per_year=float(R.sum() / years),
        win_pct=100.0 * float(wins.mean()),
        profit_factor=float(gw / gl) if gl > 0 else float("inf"),
        avg_win_R=float(R[wins].mean()) if wins.any() else 0.0,
        avg_loss_R=float(R[~wins].mean()) if (~wins).any() else 0.0,
        payoff=float(R[wins].mean() / abs(R[~wins].mean())) if (~wins).any() and wins.any() else 0.0,
        max_dd_R=ddR, max_dd_dollars=dd_dollars,
        return_over_dd=float(R.sum() / ddR) if ddR > 0 else float("inf"),
        max_consec_losses=_streak(~wins),
        sharpe=float(per_sess.mean() / sd * np.sqrt(S.DAYS_PER_YEAR)) if sd > 0 else 0.0,
        sortino=float(per_sess.mean() / per_sess[per_sess < 0].std(ddof=1)
                      * np.sqrt(S.DAYS_PER_YEAR)) if (per_sess < 0).sum() > 2 else 0.0,
        t_stat=float(R.mean() / (R.std(ddof=1) / np.sqrt(len(R)))),
        dollars=float(net.sum()), dollars_per_year=float(net.sum() / years),
        avg_hold_bars=float(hold.mean()),
        time_in_market_pct=100.0 * float(hold.sum()) / (n_sess * BARS_PER_SESSION),
        long_pct=100.0 * float((side > 0).mean()),
        R_long=float(R[side > 0].mean()) if (side > 0).any() else 0.0,
        R_short=float(R[side < 0].mean()) if (side < 0).any() else 0.0,
        skew=float(((R - R.mean()) ** 3).mean() / R.std() ** 3),
    )
    for code, name in ((B.STOP, "stop"), (B.TARGET, "target"), (B.FLAT, "flat"), (B.HOLD, "hold")):
        k = why == code
        out[f"{name}_pct"] = 100.0 * float(k.mean())
        out[f"{name}_R"] = float(R[k].mean()) if k.any() else 0.0
    # profitable-year share: the protocol's sub-period consistency probe
    yr = (sess - sess.min()) // S.DAYS_PER_YEAR
    ys = np.array([R[yr == y].sum() for y in np.unique(yr)])
    out["years_profitable_pct"] = 100.0 * float((ys > 0).mean())
    out["best_year_share"] = float(ys.max() / ys.sum()) if ys.sum() > 0 else float("nan")
    return out


def run(regime="trend_realistic", cfg=BEST, paths=12, years=50, draws=400, verbose=True):
    kw = dict(trend_realistic=dict(trend=0.10, ann_drift=0.07),
              trend_strong=dict(trend=0.35, ann_drift=0.07),
              null_martingale=dict(trend=0.0, ann_drift=0.0))[regime]
    base = {"trend_realistic": 1000, "trend_strong": 2000, "null_martingale": 3000}[regime]
    dn, ax, tp, hd = cfg
    rows, ctrl, costs = [], [], {1.0: [], 1.5: [], 2.0: []}
    for p in range(paths):
        w = B.build_world(seed=base + p, years=years, **kw)
        Tl = B.tensors(w, 1); Ts = B.tensors(w, -1)
        tl = B.triggers(w, dn, ax, 1); ts = B.triggers(w, dn, ax, -1)
        for cm in costs:
            bk = B.combined_book(w, Tl, Ts, tl, ts, tp, hd, cost_mult=cm)
            costs[cm].append(bk["per_oos"])
        bk = B.combined_book(w, Tl, Ts, tl, ts, tp, hd)
        pr = profile(w, bk, "oos")
        if pr:
            pr["per_is"] = bk["per_is"]
            rows.append(pr)
        ci_l, co_l = B.control(w, Tl, tl, tp, hd, draws=draws, seed=11)
        ci_s, co_s = B.control(w, Ts, ts, tp, hd, draws=draws, seed=12)
        wl, ws = len(tl), len(ts)
        co = (co_l * wl + co_s * ws) / (wl + ws)
        ctrl.append((float(co.mean()), float((co >= pr["R_mean"]).mean())))
        if verbose:
            print(f"  world {p:>2}  {pr['n']:>5,} OOS trades  {pr['R_mean']:+.4f}R  "
                  f"sharpe {pr['sharpe']:.2f}  pf {pr['profit_factor']:.2f}  "
                  f"maxDD {pr['max_dd_R']:.1f}R  control {co.mean():+.4f}R p={ctrl[-1][1]:.3f}")
        del Tl, Ts
    return rows, ctrl, costs


def agg(rows, key):
    v = np.array([r[key] for r in rows], float)
    v = v[np.isfinite(v)]
    return v.mean(), (v.std(ddof=1) / np.sqrt(len(v)) if len(v) > 1 else 0.0), np.median(v)


def report(rows, ctrl, costs, cfg, regime, out=None):
    L = []
    P = L.append
    dn, ax, tp, hd = cfg
    P(f"\n{'=' * 78}")
    P(f"FULL STATISTICS  --  Donchian {dn} / ADX>{ax:.0f} / stop 1.5xATR / target {tp:g}R / "
      f"max hold {hd} bars")
    P("                     07:00-11:00 New York, both sides, NQ costs "
      "($4 + 1 tick each side + 1 tick stop slippage)")
    P(f"                     regime: {regime}, {len(rows)} independent worlds x 50 years, "
      f"OUT-OF-SAMPLE block only")
    P(f"{'=' * 78}")
    groups = [
        ("RETURN", [("R_mean", "mean R per trade", "{:+.4f}"),
                    ("R_median", "median R per trade", "{:+.4f}"),
                    ("t_stat", "t-statistic (within world)", "{:+.2f}"),
                    ("R_per_year", "R per year", "{:+.1f}"),
                    ("dollars_per_year", "$ per year, 1 contract", "{:+,.0f}"),
                    ("R_total", "R over the block", "{:+.0f}")]),
        ("RISK", [("R_sd", "sd of trade R", "{:.3f}"),
                  ("skew", "skew of trade R", "{:+.2f}"),
                  ("max_dd_R", "max drawdown, R", "{:.1f}"),
                  ("max_dd_dollars", "max drawdown, $", "{:,.0f}"),
                  ("return_over_dd", "total R / max drawdown", "{:.2f}"),
                  ("max_consec_losses", "longest losing streak", "{:.0f}"),
                  ("sharpe", "Sharpe (session R, ann.)", "{:.2f}"),
                  ("sortino", "Sortino (session R, ann.)", "{:.2f}")]),
        ("TRADE MIX", [("n", "trades", "{:,.0f}"),
                       ("trades_per_year", "trades per year", "{:,.0f}"),
                       ("win_pct", "win rate %", "{:.1f}"),
                       ("profit_factor", "profit factor", "{:.2f}"),
                       ("avg_win_R", "average win, R", "{:+.3f}"),
                       ("avg_loss_R", "average loss, R", "{:+.3f}"),
                       ("payoff", "payoff ratio", "{:.2f}"),
                       ("avg_hold_bars", "average hold, bars", "{:.1f}"),
                       ("time_in_market_pct", "time in market %", "{:.1f}"),
                       ("long_pct", "long share %", "{:.1f}"),
                       ("R_long", "long R per trade", "{:+.4f}"),
                       ("R_short", "short R per trade", "{:+.4f}")]),
        ("EXITS", [("stop_pct", "stop %", "{:.1f}"), ("stop_R", "  its mean R", "{:+.3f}"),
                   ("target_pct", "target %", "{:.1f}"), ("target_R", "  its mean R", "{:+.3f}"),
                   ("flat_pct", "11:00 flat %", "{:.1f}"), ("flat_R", "  its mean R", "{:+.3f}"),
                   ("hold_pct", "max-hold %", "{:.1f}"), ("hold_R", "  its mean R", "{:+.3f}")]),
        ("CONSISTENCY", [("years_profitable_pct", "profitable years %", "{:.0f}"),
                         ("best_year_share", "best year's share of R", "{:.2f}"),
                         ("per_is", "in-sample R per trade", "{:+.4f}")]),
    ]
    for title, items in groups:
        P(f"\n  {title}")
        for k, label, fmt in items:
            m, se, md = agg(rows, k)
            P(f"    {label:<28} {fmt.format(m):>12}  +- {fmt.format(se).lstrip('+'):<10}"
              f" median {fmt.format(md)}")
    co = np.array([c[0] for c in ctrl]); pv = np.array([c[1] for c in ctrl])
    rm = np.array([r["R_mean"] for r in rows])
    exc = rm - co
    P("\n  MATCHED CONTROL (random entries, same side, geometry and minute-of-day mix)")
    P(f"    control R per trade          {co.mean():+.4f}  +- {co.std(ddof=1)/np.sqrt(len(co)):.4f}")
    P(f"    EXCESS over control          {exc.mean():+.4f}  +- {exc.std(ddof=1)/np.sqrt(len(exc)):.4f}"
      f"   t={exc.mean()/(exc.std(ddof=1)/np.sqrt(len(exc))):+.2f}")
    P(f"    worlds beating control       {int((exc > 0).sum())}/{len(exc)}")
    P(f"    median per-world control p   {np.median(pv):.3f}")
    P("\n  COST SENSITIVITY (out-of-sample R per trade, mean over worlds)")
    for cm in sorted(costs):
        v = np.array(costs[cm], float)
        P(f"    {cm:g}x modelled costs           {v.mean():+.4f}  +- "
          f"{v.std(ddof=1)/np.sqrt(len(v)):.4f}")
    txt = "\n".join(L)
    print(txt)
    if out:
        with open(out, "w") as fh:
            fh.write(txt + "\n")
    return txt


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--regime", default="trend_realistic")
    ap.add_argument("--paths", type=int, default=12)
    ap.add_argument("--years", type=int, default=50)
    ap.add_argument("--cfg", default=",".join(str(x) for x in BEST))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    c = a.cfg.split(",")
    cfg = (int(c[0]), float(c[1]), float(c[2]), int(c[3]))
    print(f"config {cfg}  regime {a.regime}")
    rows, ctrl, costs = run(a.regime, cfg, a.paths, a.years)
    report(rows, ctrl, costs, cfg, a.regime, a.out)
