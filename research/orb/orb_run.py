"""Turn signals into trades, and score them."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import orb_core as C  # noqa: E402


def blocks_of(D, dev=0.50, val=0.15):
    """Chronological development / validation / out-of-sample, by SESSION.

    dev+val is exactly the 65% research block every other study on this branch uses, and the OOS
    block is exactly its locked block -- nothing new is cut, so the reserved data stays reserved.
    """
    us = np.unique(D["sess"])
    c1, c2 = us[int(dev * len(us))], us[int((dev + val) * len(us))]
    return {"development": (D["sess"] < c1),
            "validation": (D["sess"] >= c1) & (D["sess"] < c2),
            "out-of-sample": (D["sess"] >= c2)}, (c1, c2)


def run(D, first_per_session=True, conservative=True, slip=None, spread=None,
        fee_pts=None, risk_pct=C.RISK_PCT, stop_atr=C.STOP_ATR, equity0=C.EQUITY0,
        slip_mult=1.0, **sig_kw):
    spread = D["spread"] if spread is None else spread
    slip = D["slip"] * slip_mult if slip is None else slip * slip_mult
    fee_pts = D["fee"] if fee_pts is None else fee_pts
    side, ratio = C.signals(D, **sig_kw)
    idx = np.flatnonzero(side != 0)
    if len(idx) == 0:
        return pd.DataFrame(), side
    if first_per_session:                      # "no trade has already been taken this session"
        ss = D["sess"][idx]
        keep = np.r_[True, ss[1:] != ss[:-1]]
        idx = idx[keep]
    if len(idx) == 0:
        return pd.DataFrame(), side

    tf = D["trade_tf"]
    sig_close = pd.DatetimeIndex(D["ts"][idx]) + pd.Timedelta(minutes=tf)
    m1 = D["m1_ts"]
    i0 = np.searchsorted(m1, sig_close.to_numpy(), side="left")

    # the liquidation bar of each signal's session; the walk ends the bar before it
    liq = pd.DataFrame({"s": D["m1_sess"], "m": D["m1_mod"], "i": np.arange(len(m1))})
    liq = liq[liq["m"] >= D["liquidate"]].groupby("s", sort=True)["i"].first()
    lb = liq.reindex(D["sess"][idx]).to_numpy()
    good = np.isfinite(lb.astype(float)) & (i0 < len(m1))
    idx, i0 = idx[good], i0[good]
    lb = lb[good].astype(np.int64)
    t_end = lb - 1
    ok = i0 <= t_end
    idx, i0, t_end = idx[ok], i0[ok], t_end[ok]

    e_bar, e_px, qty, q1, pnl, code, rmul, amb, eq = C._walk(
        i0, side[idx], D["atr"][idx], t_end,
        D["m1_o"], D["m1_h"], D["m1_l"], D["m1_c"], D["m1_mod"],
        float(equity0), float(risk_pct), D["pv"], float(spread), float(slip),
        float(fee_pts), float(stop_atr), D["liquidate"], 1 if conservative else 0)

    took = qty > 0
    t = pd.DataFrame(dict(
        sig_bar=idx[took], sess=D["sess"][idx][took], ts=D["ts"][idx][took],
        side=side[idx][took], atr=D["atr"][idx][took], ratio=ratio[idx][took],
        entry_bar=e_bar[took], entry_px=e_px[took], qty=qty[took], scale_qty=q1[took],
        net=pnl[took], code=code[took], R=rmul[took], ambiguous=amb[took], equity=eq[took]))
    t["exit_reason"] = pd.Categorical(t["code"].map(
        {0: "stop", 1: "target", 2: "liquidation", 3: "breakeven"}))
    t["skipped_size"] = 0
    t.attrs["skipped_for_size"] = int((~took).sum())
    return t, side


def stats(t, sessions):
    if len(t) == 0:
        return dict(trades=0)
    n = t["net"].to_numpy()
    w, l = n[n > 0], n[n <= 0]
    eq = C.EQUITY0 + np.cumsum(n)
    dd = eq - np.maximum.accumulate(eq)
    d = pd.Series(n, index=pd.DatetimeIndex(t["ts"]).normalize()).groupby(level=0).sum()
    d = d.reindex(pd.DatetimeIndex(sessions)).fillna(0.0)
    streak = mx = 0
    for x in n:
        streak = streak + 1 if x <= 0 else 0
        mx = max(mx, streak)
    gp, gl = w.sum(), -l.sum()
    return dict(
        trades=len(t), sessions=len(sessions), traded_pct=100 * len(t) / max(1, len(sessions)),
        expectancy=n.mean(), total=n.sum(),
        pf=gp / gl if gl > 0 else np.inf,
        win_pct=100 * len(w) / len(n),
        avg_win=w.mean() if len(w) else np.nan,
        avg_loss=l.mean() if len(l) else np.nan,
        max_dd=dd.min(),
        sharpe=np.sqrt(252) * d.mean() / d.std(ddof=1) if d.std(ddof=1) > 0 else np.nan,
        losing_streak=mx,
        avg_R=t["R"].mean(),
        amb_pct=100 * (t["ambiguous"] > 0).mean(),
        long_pct=100 * (t["side"] > 0).mean())


ORDER = ["trades", "traded_pct", "expectancy", "total", "pf", "win_pct", "avg_win", "avg_loss",
         "max_dd", "sharpe", "losing_streak", "avg_R", "amb_pct", "long_pct"]
LABEL = {"trades": "trades", "traded_pct": "% of sessions traded", "expectancy": "expectancy $/trade",
         "total": "net $", "pf": "profit factor", "win_pct": "win rate %", "avg_win": "average win $",
         "avg_loss": "average loss $", "max_dd": "max drawdown $", "sharpe": "Sharpe (daily, ann.)",
         "losing_streak": "longest losing streak", "avg_R": "mean R", "amb_pct": "% trades with an ambiguous bar",
         "long_pct": "% long"}


def table(rows, names):
    print(f"  {'metric':32s}" + "".join(f"{x:>18s}" for x in names))
    for k in ORDER:
        vals = []
        for r in rows:
            v = r.get(k, np.nan)
            vals.append("-" if v is None else (f"{v:,.0f}" if k in ("trades", "losing_streak")
                        else f"{v:,.3f}" if abs(v) < 100 else f"{v:,.1f}"))
        print(f"  {LABEL[k]:32s}" + "".join(f"{x:>18s}" for x in vals))
