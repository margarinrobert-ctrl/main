"""Conditional edge: are there SESSIONS where the validated setup works better?

This is a different question from parameter search, and a safer one. Parameter search asks "what
geometry fits best", which is what overfits. This asks "given one fixed geometry, does its edge
concentrate in identifiable conditions" — where every condition is knowable BEFORE the entry.

Discipline carried over from the rest of the repo:
  * measured in DOLLARS, because R normalised by a small stop flatters (STUDY_VECTORBT.md)
  * Newey-West t-statistics, because trades cluster by session
  * Benjamini-Hochberg FDR across every test, because 30-odd slices produce winners by themselves
  * anything that survives is then read on a holdout it was not selected on

Usage: python3 research/anomalies.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from ib_sim import COMMISSION_PTS, POINT_VALUE, TAKER_SIDE, TICK, simulate
from nqdata import load_bars, minute_of_day, minutes_since_open, session_index, session_slice

EXIT_MSO = 149          # flatten on the 11:59 bar
IB_MIN = 60


def newey_west_t(x: np.ndarray, lag: int | None = None) -> float:
    x = np.asarray(x, float)
    n = len(x)
    if n < 5:
        return np.nan
    if lag is None:
        lag = max(1, int(round(4 * (n / 100) ** (2 / 9))))
    e = x - x.mean()
    s = (e @ e) / n
    for k in range(1, lag + 1):
        w = 1 - k / (lag + 1)
        s += 2 * w * (e[k:] @ e[:-k]) / n
    return np.nan if s <= 0 else x.mean() / np.sqrt(s / n)


def bh(pvals: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg adjusted q-values."""
    p = np.asarray(pvals, float)
    m = len(p)
    order = np.argsort(p)
    q = np.empty(m)
    prev = 1.0
    for rank in range(m - 1, -1, -1):
        i = order[rank]
        prev = min(prev, p[i] * m / (rank + 1))
        q[i] = prev
    return q


def build_session_features(df_full: pd.DataFrame, seg: pd.DataFrame, sess: np.ndarray) -> pd.DataFrame:
    """One row per session. Everything here is knowable by the time the IB has closed."""
    o = seg["open"].to_numpy(float); h = seg["high"].to_numpy(float)
    l = seg["low"].to_numpy(float);  c = seg["close"].to_numpy(float)
    v = seg["volume"].to_numpy(float)
    mso = minutes_since_open(minute_of_day(seg.index), 570).astype(np.int64)

    rows = {}
    for s in np.unique(sess):
        m = sess == s
        ib = m & (mso < IB_MIN)
        if ib.sum() < IB_MIN // 2:
            continue
        ib_h, ib_l = h[ib].max(), l[ib].min()
        rows[s] = {
            "session": s,
            "date": seg.index[m][0].normalize(),
            "ib_range": ib_h - ib_l,
            "ib_high": ib_h,
            "ib_low": ib_l,
            "open_px": o[m][0],
            # where the first hour CLOSED inside its own range: 0 = on the low, 1 = on the high
            "ib_close_pos": (c[ib][-1] - ib_l) / max(ib_h - ib_l, 1e-9),
            "ib_volume": v[ib].sum(),
            "weekday": seg.index[m][0].weekday(),
        }
    f = pd.DataFrame(rows.values()).sort_values("session").reset_index(drop=True)

    # Prior-session context, strictly shifted so nothing uses its own day.
    f["prev_range"] = f["ib_range"].shift(1)
    f["prev_ret"] = f["open_px"].pct_change()
    f["gap"] = f["open_px"] - f["open_px"].shift(1)
    # Trailing distribution, prior sessions only — the same rule the TypeScript filter uses.
    f["ib_pctile"] = f["ib_range"].shift(1).rolling(60, min_periods=20).rank(pct=True) * 100
    f["vol_pctile"] = f["prev_range"].rolling(60, min_periods=20).rank(pct=True) * 100
    f["vol_ratio"] = f["ib_range"] / f["prev_range"]
    f["volume_pctile"] = f["ib_volume"].shift(1).rolling(60, min_periods=20).rank(pct=True) * 100
    return f


def main() -> None:
    df = load_bars("data/NQ_1m.csv")
    seg = session_slice(df, 570, 960)
    mod = minute_of_day(seg.index)
    sess = session_index(seg.index, 570)
    mso = minutes_since_open(mod, 570).astype(np.int64)
    arrs = (seg["open"].to_numpy(float), seg["high"].to_numpy(float),
            seg["low"].to_numpy(float), seg["close"].to_numpy(float), sess, mso, np.zeros(len(seg)))

    res = simulate(*arrs, IB_MIN, 50.0, 80.0, 2.0, 0, 0, 0, 1.5, 40.0, 0, 10.0, 50.0, EXIT_MSO,
                   TICK, POINT_VALUE, TAKER_SIDE, COMMISSION_PTS)
    t = pd.DataFrame({"entryIndex": res[0], "exitIndex": res[1], "side": res[2],
                      "pnl": res[5], "r": res[6]})
    t["session"] = sess[t.entryIndex.to_numpy()]
    t["entry_mso"] = mso[t.entryIndex.to_numpy()]

    feats = build_session_features(df, seg, sess)
    t = t.merge(feats, on="session", how="left")
    n = len(seg)
    cut = int(n * 0.7)
    t["is_research"] = t.exitIndex < cut

    print(f"validated config on full RTH bars, flatten {EXIT_MSO}m: {len(t)} trades, "
          f"${t.pnl.sum():,.0f}, mean ${t.pnl.mean():,.1f}/trade, E={t.r.mean():+.4f}R")
    print(f"  research {t.is_research.sum()} trades  |  holdout {(~t.is_research).sum()} trades\n")

    base = t.pnl.mean()
    tests = []

    def add(name, mask):
        sub = t[mask]
        if len(sub) < 25:
            return
        rest = t[~mask]
        diff = sub.pnl.mean() - rest.pnl.mean()
        tt = newey_west_t(sub.pnl.to_numpy() - base)
        if np.isnan(tt):
            return
        from scipy import stats as st
        p = 2 * (1 - st.norm.cdf(abs(tt)))
        r_sub, h_sub = sub[sub.is_research], sub[~sub.is_research]
        tests.append({
            "condition": name, "n": len(sub),
            "mean$": sub.pnl.mean(), "lift$": diff, "t": tt, "p": p,
            "res$": r_sub.pnl.mean() if len(r_sub) >= 10 else np.nan,
            "hold$": h_sub.pnl.mean() if len(h_sub) >= 10 else np.nan,
        })

    add("side == long", t.side == 1)
    add("side == short", t.side == -1)
    for d, nm in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"]):
        add(f"weekday == {nm}", t.weekday == d)
    for col, label in [("ib_pctile", "IB range pctile"), ("vol_pctile", "prior-range pctile"),
                       ("volume_pctile", "IB volume pctile")]:
        add(f"{label} < 33", t[col] < 33)
        add(f"33 <= {label} < 67", (t[col] >= 33) & (t[col] < 67))
        add(f"{label} >= 67", t[col] >= 67)
    add("IB closed in lower third", t.ib_close_pos < 0.333)
    add("IB closed in middle third", (t.ib_close_pos >= 0.333) & (t.ib_close_pos <= 0.667))
    add("IB closed in upper third", t.ib_close_pos > 0.667)
    add("break agrees with IB close (long & high)", (t.side == 1) & (t.ib_close_pos > 0.5))
    add("break fades IB close (long & low)", (t.side == 1) & (t.ib_close_pos <= 0.5))
    add("break agrees with IB close (short & low)", (t.side == -1) & (t.ib_close_pos < 0.5))
    add("break fades IB close (short & high)", (t.side == -1) & (t.ib_close_pos >= 0.5))
    add("gap up", t.gap > 0)
    add("gap down", t.gap <= 0)
    add("IB range wider than prior", t.vol_ratio > 1)
    add("IB range narrower than prior", t.vol_ratio <= 1)
    add("entry within 30m of IB close", t.entry_mso < IB_MIN + 30)
    add("entry 30-90m after IB close", (t.entry_mso >= IB_MIN + 30) & (t.entry_mso < IB_MIN + 90))
    add("entry >90m after IB close", t.entry_mso >= IB_MIN + 90)
    add("prior session up", t.prev_ret > 0)
    add("prior session down", t.prev_ret <= 0)

    res_df = pd.DataFrame(tests)
    res_df["q"] = bh(res_df.p.to_numpy())
    res_df = res_df.sort_values("p")
    pd.set_option("display.width", 200)
    print(f"  {len(res_df)} conditions tested, Benjamini-Hochberg across all of them")
    print(f"  baseline: ${base:,.1f} per trade\n")
    print(f"  {'condition':<42}{'n':>5}{'mean$':>9}{'lift$':>9}{'t':>7}{'p':>8}{'q':>8}{'res$':>9}{'hold$':>9}")
    for _, r in res_df.iterrows():
        star = " *" if r.q < 0.10 else ""
        print(f"  {r.condition:<42}{int(r.n):>5}{r['mean$']:>9,.0f}{r['lift$']:>9,.0f}"
              f"{r.t:>7.2f}{r.p:>8.3f}{r.q:>8.3f}{r['res$']:>9,.0f}{r['hold$']:>9,.0f}{star}")

    surv = res_df[res_df.q < 0.10]
    print(f"\n  {len(surv)} condition(s) survive FDR at q < 0.10")
    if len(surv):
        both = surv[surv["res$"] * surv["hold$"] > 0]
        print(f"  of those, {len(both)} have the same sign in BOTH halves — the only ones worth anything")


if __name__ == "__main__":
    main()
