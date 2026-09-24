"""Read a TradingView Strategy Tester "List of trades" export and judge it on its own terms.

WHY THIS EXISTS. The user's TradingView run of the 09:00-range configuration (`na_live.TV`) shows
305 trades from a span our 30-second file cannot reach -- our pre-open coverage begins 2026-04-30,
92 tradeable sessions. Their broker's history is the largest sample of this configuration anywhere,
and it is locked inside TradingView. The Strategy Tester exports it: List of trades -> the
download icon -> CSV. This module turns that CSV into the three things the research needs:

  1. A TRANSCRIPTION CHECK over the span both sides can see. Trades TradingView took inside our
     file's tradeable sessions must match the trades our walker takes -- same session, side and
     entry minute. A mismatch there means the two are not running the same rule, and nothing
     measured on the wider span can be credited to it.
  2. THE SAMPLE-SIZE STATISTICS the local file cannot give: day-block bootstrap on 305 trades, the
     MDE beside the delivered mean, the trades needed to resolve it.
  3. STABILITY BY PERIOD -- by year and by quarter -- because a PF over four years can be one good
     year, and the TradingView equity curve cannot say which.

It reads percent-of-entry and points, never only dollars: TradingView's dollar column depends on
the Properties sizing, and section 24a found the user's earlier run was sized at two contracts.

EXPORT FORMATS DIFFER BY TRADINGVIEW VERSION. Column names are matched loosely (see COLS) and every
row is reported if it cannot be parsed -- an export that silently drops rows is how a sample
shrinks without anyone noticing.
"""
from __future__ import annotations

import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
NA = os.path.dirname(HERE)
sys.path.insert(0, NA)
sys.path.insert(0, os.path.dirname(NA))

# TradingView has renamed these columns across versions; match on what the header CONTAINS.
COLS = {
    "trade": [r"^trade\s*#", r"^trade$"],
    "type": [r"^type$"],
    "signal": [r"^signal$"],
    "time": [r"date\s*/?\s*time", r"date and time", r"^date$", r"^time$"],
    "price": [r"^price"],
    "qty": [r"contracts", r"quantity", r"^qty", r"size"],
    "pnl": [r"^profit$", r"^p&l", r"net p&l", r"^profit\s*usd", r"^profit\s*\("],
    "pnl_pct": [r"profit\s*%", r"p&l\s*%", r"net p&l\s*%"],
}


def _find(cols, key):
    for c in cols:
        lc = c.strip().lower()
        if key == "pnl" and "%" in lc:          # "Net P&L %" must not be read as the dollar column
            continue
        for pat in COLS[key]:
            if re.search(pat, lc):
                return c
    return None


def load(path: str) -> pd.DataFrame:
    """One row per ROUND TRIP: entry time, side, entry and exit price, points, %."""
    raw = pd.read_csv(path) if path.endswith(".csv") else pd.read_excel(path)
    m = {k: _find(raw.columns, k) for k in COLS}
    need = ["trade", "type", "time", "price"]
    missing = [k for k in need if m[k] is None]
    if missing:
        raise SystemExit(f"export is missing {missing}; columns were {list(raw.columns)}")
    df = raw.rename(columns={v: k for k, v in m.items() if v is not None})
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    bad = df["time"].isna().sum()
    if bad:
        print(f"  WARNING: {bad} rows with an unparseable time -- they are dropped and counted")
    df = df.dropna(subset=["time"])

    # TradingView writes each trade as two rows (Entry and Exit), newest first.
    rows = []
    for tid, g in df.groupby("trade"):
        typ = g["type"].astype(str).str.lower()
        en = g[typ.str.contains("entry")]
        ex = g[typ.str.contains("exit")]
        if len(en) != 1 or len(ex) != 1:
            print(f"  WARNING: trade {tid} has {len(en)} entry / {len(ex)} exit rows -- skipped")
            continue
        side = 1 if "long" in str(en["type"].iloc[0]).lower() else -1
        ep, xp = float(en["price"].iloc[0]), float(ex["price"].iloc[0])
        rows.append(dict(
            trade=int(tid), side=side,
            entry_time=en["time"].iloc[0], exit_time=ex["time"].iloc[0],
            entry=ep, exit=xp,
            pts_gross=side * (xp - ep),
            pnl=float(ex["pnl"].iloc[0]) if m["pnl"] and "pnl" in ex else np.nan,
            pnl_pct=float(str(ex["pnl_pct"].iloc[0]).replace("%", ""))
                    if m["pnl_pct"] and "pnl_pct" in ex else np.nan,
            signal=str(ex["signal"].iloc[0]) if "signal" in ex else ""))
    out = pd.DataFrame(rows).sort_values("entry_time").reset_index(drop=True)
    out["pct_gross"] = 100.0 * out["pts_gross"] / out["entry"]
    return out


def stats(r: np.ndarray) -> dict:
    import na_core as N
    w = r > 0
    sd = r.std(ddof=1) if len(r) > 1 else np.nan
    mde = N.mde(sd, len(r)) if len(r) > 1 else np.nan
    return dict(n=len(r), mean=r.mean(), pf=r[w].sum() / -r[~w].sum() if (~w).any() else np.nan,
                win=w.mean(), sd=sd, mde=mde, ratio=r.mean() / mde if mde else np.nan,
                n_needed=int(np.ceil((2.802 * sd / r.mean()) ** 2)) if r.mean() > 0 else None)


def report(path: str, cost_pts: float = 2.29):
    tv = load(path)
    print("=" * 92)
    print(f"TRADINGVIEW TRADE LIST -- {len(tv)} round trips, "
          f"{tv.entry_time.min():%Y-%m-%d} .. {tv.entry_time.max():%Y-%m-%d}")
    print("=" * 92)
    # net of the research's round turn, so the two sides are costed identically
    tv["pct"] = 100.0 * (tv["pts_gross"] - cost_pts) / tv["entry"]
    s = stats(tv["pct"].to_numpy())
    print(f"  mean {s['mean']:+.4f} %/trade   PF {s['pf']:.3f}   win {s['win']:.3f}   "
          f"(net of {cost_pts} pts round turn)")
    print(f"  MDE {s['mde']:.4f} -> delivered/MDE {s['ratio']:.2f}x   "
          f"trades needed to resolve it: {s['n_needed']}")
    import na_core as N
    # `_day`, NOT `eday`: na_core.boot_edge falls back to a per-TRADE grouping when `_day` is absent
    tv["_day"] = tv["entry_time"].dt.normalize().astype("int64")
    bo = np.asarray(N.boot_edge(tv, n=4000, seed=3, col="pct"))
    print(f"  day-block bootstrap 95% CI [{np.percentile(bo,2.5):+.4f}, {np.percentile(bo,97.5):+.4f}]"
          f"   P(mean<=0) {float((bo<=0).mean()):.4f}")

    print("\n  BY YEAR -- a four-year PF can be one good year")
    for y, g in tv.groupby(tv.entry_time.dt.year):
        t = stats(g["pct"].to_numpy())
        print(f"    {y}  n {t['n']:4d}  mean {t['mean']:+.4f}  PF {t['pf']:.3f}  win {t['win']:.3f}")
    print("\n  BY QUARTER")
    q = tv.groupby(tv.entry_time.dt.to_period("Q"))["pct"].agg(["size", "mean", "sum"])
    q["pos"] = q["sum"] > 0
    print(q.to_string(float_format=lambda v: f"{v:+.4f}"))
    print(f"    quarters positive {int(q.pos.sum())} of {len(q)}")
    return tv


def reconcile(tv: pd.DataFrame, tol_min: float = 1.0):
    """Trades both sides can see must MATCH, or the wider span measures a different rule."""
    import na_30s as T, na_s30 as S, na_live as L
    f = T.frame(tf=0.5, atr_n=14)
    c = S.Ctx30(name="US30L", tf=0.5, fix=1, frame=f, block_name="ALL")
    ours = c.trades(dict(L.TV))
    ours = ours.assign(entry_time=f.index[ours["eb"].to_numpy()])
    lo, hi = f.index.min(), f.index.max()
    have = set(pd.to_datetime(np.unique(c.day[(c.mod >= 540) & (c.mod < 545)]), unit="D").date)
    tvw = tv[(tv.entry_time >= lo) & (tv.entry_time <= hi)]
    tvw = tvw[tvw.entry_time.dt.date.isin(have)]
    print("\n" + "=" * 92)
    print(f"TRANSCRIPTION CHECK over the {len(have)} sessions both sides can see")
    print("=" * 92)
    print(f"  TradingView trades there {len(tvw)}   ours {len(ours)}")
    matched = 0
    for _, t in tvw.iterrows():
        d = (ours["entry_time"] - t.entry_time).abs().dt.total_seconds() / 60.0
        k = d.idxmin() if len(d) else None
        if k is not None and d[k] <= tol_min and int(ours.loc[k, "side"]) == t.side:
            matched += 1
    print(f"  matched on session, side and entry within {tol_min:g} min: {matched} of {len(tvw)}"
          f" ({matched/max(len(tvw),1):.1%})")
    print("  Below ~90% the two are not the same rule and the wider span cannot be credited to ours.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python tv_trades.py <List-of-trades export .csv>")
    tv = report(sys.argv[1])
    reconcile(tv)
