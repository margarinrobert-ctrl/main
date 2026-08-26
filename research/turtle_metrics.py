"""Scoring: what a configuration earned, and what the same geometry earned for no reason at all.

Two decisions here matter more than the arithmetic.

**Sessions with no trade count as zero, not as missing.**  A rule that trades 40 sessions out of
2,700 and wins on 30 of them has a superb per-trade record and an annual Sharpe near nothing.
Dropping the flat sessions from the denominator reports the first number and calls it the second.
Every Sharpe here is computed over every session in the block.

**Every headline number is reported against a matched control.**  On these three samples the
instrument roughly tripled, doubled and rose 5x respectively, so "the strategy made money" carries
almost no information: a random long entry inside 07:00-11:00 makes money too.  The control is the
same geometry, the same pyramiding, the same costs and the same minute-of-day distribution, with
the entry reason removed, and the number that means something is the difference.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turtle_sim as T
import turtle_tensor as X
from turtle_sim import P, Series

SESSIONS_PER_YEAR = {"US30": 252.0, "XAU": 252.0, "BTC": 365.0}


def session_pnl(s: Series, sc: X.Scan, net: np.ndarray, lo: int, hi: int,
                point_value: float) -> np.ndarray:
    """Net dollars per session over sessions [lo, hi), zero-filled for sessions with no trade."""
    out = np.zeros(hi - lo)
    if len(sc):
        sid = s.sess[sc.exit_bar]
        keep = (sid >= lo) & (sid < hi)
        if keep.any():
            np.add.at(out, sid[keep] - lo, net[keep] * point_value)
    return out


def drawdown(daily: np.ndarray) -> float:
    eq = np.cumsum(daily)
    return float(np.max(np.maximum.accumulate(eq) - eq)) if len(eq) else 0.0


def summarise(s: Series, sc: X.Scan, spec: dict, lo: int, hi: int, name: str,
              cost_mult: float = 1.0, tp_rests: bool = False) -> dict:
    """Everything worth reporting about one configuration on one block."""
    pv = spec["point_value"]
    net_all = sc.net(spec["cost_abs"] * cost_mult, spec["cost_bp"] * cost_mult,
                     spec["stop_slip"] * cost_mult, tp_rests)
    # Commission is a per-unit dollar charge, not a price move, so it is applied after conversion.
    if len(sc):
        net_all = net_all * pv - sc.units * spec.get("comm", 0.0) * cost_mult
    sid = s.sess[sc.exit_bar] if len(sc) else np.zeros(0, np.int64)
    keep = (sid >= lo) & (sid < hi)
    net = net_all[keep]
    n = int(keep.sum())

    daily = np.zeros(hi - lo)
    if n:
        np.add.at(daily, sid[keep] - lo, net)
    spy = SESSIONS_PER_YEAR.get(name, 252.0)
    sd = daily.std(ddof=1) if len(daily) > 1 else 0.0
    sharpe = float(daily.mean() / sd * np.sqrt(spy)) if sd > 0 else 0.0
    dn = daily[daily < 0]
    dsd = np.sqrt((dn ** 2).mean()) if len(dn) else 0.0
    sortino = float(daily.mean() / dsd * np.sqrt(spy)) if dsd > 0 else 0.0

    win = net[net > 0].sum() if n else 0.0
    loss = -net[net < 0].sum() if n else 0.0
    dd = drawdown(daily)
    r = np.where(sc.risk[keep] * sc.units[keep] > 0,
                 net / np.maximum(sc.risk[keep] * sc.units[keep] * pv, 1e-12), 0.0) if n else \
        np.zeros(0)

    out = {
        "n": n,
        "sessions": hi - lo,
        "trades_per_sess": n / max(hi - lo, 1),
        "units": float(sc.units[keep].mean()) if n else 0.0,
        "net": float(net.sum()),
        "per_trade": float(net.mean()) if n else 0.0,
        "per_trade_se": float(net.std(ddof=1) / np.sqrt(n)) if n > 1 else 0.0,
        "sharpe": sharpe,
        "sortino": sortino,
        "pf": float(win / loss) if loss > 0 else (float("inf") if win > 0 else 0.0),
        "win_rate": float((net > 0).mean()) if n else 0.0,
        "maxdd": dd,
        "mar": float(net.sum() / dd) if dd > 0 else 0.0,
        "r_mean": float(r.mean()) if n else 0.0,
        "hold_bars": float((sc.exit_bar[keep] - sc.entry_bar[keep]).mean()) if n else 0.0,
    }
    for k, nm in enumerate(T.EXIT_NAMES):
        out["x_" + nm] = float((sc.reason[keep] == k).mean()) if n else 0.0
    return out


def control_bank(s: Series, ex: X.Exits, ctrl: X.Control, p: P, spec: dict, lo: int, hi: int,
                 name: str, draws: int = 400, cost_mult: float = 1.0) -> dict:
    """Run the matched control `draws` times and return the distribution of each metric."""
    keys = ("per_trade", "sharpe", "pf", "net", "win_rate", "mar")
    acc = {k: np.empty(draws) for k in keys}
    acc["n"] = np.empty(draws)
    buf = None
    t = np.zeros(s.n, np.int64)
    for d in range(draws):
        ctrl.draw(t)
        sc = X.scan(s, ex, t, p, buf)
        st = summarise(s, sc, spec, lo, hi, name, cost_mult, p.tp_rests)
        for k in keys:
            acc[k][d] = st[k] if np.isfinite(st[k]) else np.nan
        acc["n"][d] = st["n"]
    return acc


def excess(real: dict, bank: dict) -> dict:
    """Where the rule lands in its own control's distribution, per metric."""
    out = {}
    for k, v in bank.items():
        if k == "n":
            out["ctrl_n"] = float(np.nanmean(v))
            continue
        good = v[np.isfinite(v)]
        if len(good) < 10:
            out[f"ex_{k}"] = 0.0
            out[f"p_{k}"] = 1.0
            continue
        mu = float(good.mean())
        out[f"ctrl_{k}"] = mu
        out[f"ex_{k}"] = float(real[k] - mu)
        # One-sided empirical p: the share of control draws at least as good as the rule.
        # (len+1) in numerator and denominator so a p of exactly zero is never reported.
        out[f"p_{k}"] = float((1 + (good >= real[k]).sum()) / (1 + len(good)))
    return out


def analytic_control(s: Series, ex: X.Exits, trigger: np.ndarray, spec: dict,
                     block: np.ndarray, cost_mult: float = 1.0,
                     tp_rests: bool = False) -> float:
    """Expected per-trade dollars of a matched control, without drawing anything.

    For a given geometry the tensor already holds what an entry from EVERY bar would have earned.
    The matched control draws its entries uniformly within each (block, minute-of-day, system)
    bucket, so its expected per-trade result is just the rule's trigger histogram weighted by each
    bucket's mean -- exact in expectation, and O(buckets) instead of O(draws x bars).

    That is what makes the control affordable as a SWEEP objective rather than a post-hoc check.
    It ignores the no-overlap thinning, so it is the per-trade expectation and not the Sharpe; the
    full draw-based control in `control_bank` is what the surviving candidates are scored on.
    """
    pv = spec["point_value"]
    tot_w = 0.0
    tot = 0.0
    key = block * 30_000 + s.ny_min * 3
    for sysno in (1, 2):
        k = sysno - 1
        net = ex.net(k, spec["cost_abs"] * cost_mult, spec["cost_bp"] * cost_mult,
                     spec["stop_slip"] * cost_mult, tp_rests) * pv \
            - ex.units[k] * spec.get("comm", 0.0) * cost_mult
        ok = ex.exit_bar[k] >= 0
        kk = key + sysno
        cnt = np.bincount(kk[trigger == sysno], minlength=kk.max() + 1)
        if cnt.sum() == 0:
            continue
        tot_n = np.bincount(kk[ok], minlength=len(cnt))
        tot_s = np.bincount(kk[ok], weights=net[ok], minlength=len(cnt))
        use = (cnt > 0) & (tot_n > 0)
        tot += float((cnt[use] * tot_s[use] / tot_n[use]).sum())
        tot_w += float(cnt[use].sum())
    return tot / tot_w if tot_w > 0 else 0.0


def fmt(st: dict) -> str:
    return (f"n {st['n']:5,d}  net ${st['net']:>11,.0f}  /trade ${st['per_trade']:>7.2f}  "
            f"Sharpe {st['sharpe']:>6.2f}  PF {st['pf']:>5.2f}  win {st['win_rate']:>5.1%}  "
            f"maxDD ${st['maxdd']:>9,.0f}  MAR {st['mar']:>6.2f}")


__all__ = ["summarise", "control_bank", "excess", "analytic_control", "session_pnl",
           "drawdown", "fmt", "SESSIONS_PER_YEAR"]
