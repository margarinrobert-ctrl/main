"""V36 -- liquidity pools, defined so a machine can find them and a clock cannot cheat.

THE ONE RULE THAT GOVERNS THIS WHOLE FILE. A swing high at bar i with k bars either side is not
KNOWABLE at bar i. It is knowable at i + k, when the right-hand bars have closed. Nearly every
published swing/liquidity indicator marks the pivot at its occurrence, which back-tests beautifully
and cannot be traded. `STUDY_DIVERGENCE_CONFIRM` records this branch reading +37 full against +999
truncated on exactly that mistake. Every pivot here therefore carries a CONFIRMATION BAR and is
invisible before it.

The same rule governs session levels. `CLAUDE.md`: "FROM 18:00 THE NEXT OVERNIGHT HAS BEGUN, so an
evening bar reads its own still-forming group's running high/low -- future data." Each session
level is accumulated on its own bars and FROZEN at the session end; it is exposed only from the
freeze bar onward.

SESSIONS ARE MEASURED IN MINUTES SINCE THE 18:00 ROLL, NOT IN WALL-CLOCK MINUTES. The first
version of this file froze each session on `mod >= freeze`, and because the trading day rolls at
18:00 that condition ALSO catches the 18:00-23:59 bars of the SAME trading day -- so an evening bar
was handed London levels from a London session that happens the next morning. Expressed as `tmin`,
minutes since the roll, the windows are monotone and a freeze is simply a later tmin:

    ASIA     tmin    0 ->  540   (18:00 -> 03:00)        exposed from tmin 540
    LONDON   tmin  540 ->  930   (03:00 -> 09:30)        exposed from tmin 930
    NY RTH   tmin  930 -> 1320   (09:30 -> 16:00)        running; looking back only
    PREV DAY the last trading day whose RTH has ENDED    exposed for the whole next trading day

The previous-day levels leaked in the first version too, in a subtler way: they were assigned per
trading day only if that day appeared in the RTH groupby, so a bar at 02:00 on day D got its levels
because day D LATER had RTH bars. The value was causal; its EXISTENCE was not. They are now keyed
off the last trading day strictly before the current one, which cannot depend on the future.

LIQUIDITY POOLS are then: confirmed 1H and 4H swing highs/lows, Asia H/L, London H/L, previous-day
H/L, and the running session H/L. A pool is CONSUMED once swept, so the same level cannot be traded
twice.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from nqdata import load_bars                                          # noqa: E402

ROLL = 18 * 60                    # the trading day begins at 18:00 New York
ASIA_T = (0, 540)                 # tmin: minutes since the roll
LONDON_T = (540, 930)
RTH_T = (930, 1320)


def load(path="data/NQ_1m.csv"):
    """1-minute bars in New York wall-clock, with a data audit attached."""
    df = load_bars(path)
    idx = df.index
    mod = (idx.hour * 60 + idx.minute).to_numpy(np.int64)
    # the TRADING day rolls at 18:00, so an overnight session is one day
    roll = (idx + pd.Timedelta(hours=6))
    tday = (roll.year * 10000 + roll.month * 100 + roll.day).to_numpy(np.int64)
    cal = (idx.year * 10000 + idx.month * 100 + idx.day).to_numpy(np.int64)
    tmin = (mod - ROLL) % 1440    # minutes since the 18:00 roll; monotone within a trading day
    return dict(ts=idx, o=df["open"].to_numpy(float), h=df["high"].to_numpy(float),
                l=df["low"].to_numpy(float), c=df["close"].to_numpy(float),
                v=df["volume"].to_numpy(float), mod=mod, tmin=tmin, tday=tday, cal=cal)


def audit(d):
    """Is the file complete? 1,048,575 rows is 2^20 - 1, the Excel row limit, so truncation has to
    be ruled out rather than assumed away."""
    ts = d["ts"]
    gaps = pd.Series(ts).diff().dt.total_seconds().div(60).fillna(1)
    big = gaps[gaps > 60]
    per_day = pd.Series(d["cal"]).value_counts().sort_index()
    wk = pd.Series(ts).dt.dayofweek
    out = dict(
        n=len(ts), span=(ts[0], ts[-1]),
        exact_2p20=(len(ts) == 2 ** 20 - 1),
        gaps_over_1h=int(len(big)),
        largest_gap_min=float(gaps.max()),
        median_bars_per_cal_day=float(per_day.median()),
        days_under_500_bars=int((per_day < 500).sum()),
        weekend_bars=int(((wk >= 5) & (pd.Series(d["mod"]) > 17 * 60)).sum()),
        dup_ts=int(pd.Series(ts).duplicated().sum()),
        zero_range=int((d["h"] == d["l"]).sum()),
        nonfinite=int((~np.isfinite(d["c"])).sum()))
    return out


# ------------------------------------------------------------------------------------------------
# causal pivots
# ------------------------------------------------------------------------------------------------
def resample(d, tf):
    """1-minute bars grouped into tf-minute bars, keeping the index of each group's LAST 1m bar so
    a higher-timeframe level can be stamped with the exact minute it became knowable."""
    blk = np.arange(len(d["c"])) // tf
    g = pd.DataFrame(dict(blk=blk, o=d["o"], h=d["h"], l=d["l"], c=d["c"],
                          i=np.arange(len(d["c"])))).groupby("blk")
    return dict(o=g.o.first().to_numpy(), h=g.h.max().to_numpy(), l=g.l.min().to_numpy(),
                c=g.c.last().to_numpy(), last_i=g.i.max().to_numpy())


def pivots(h, l, k):
    """Pivot highs/lows with k bars either side. Returns, for each pivot, its PRICE and the bar it
    is CONFIRMED on -- which is k bars after it occurred, never the pivot bar itself."""
    n = len(h)
    hi_idx, lo_idx = [], []
    for i in range(k, n - k):
        w_h = h[i - k:i + k + 1]
        w_l = l[i - k:i + k + 1]
        if h[i] >= w_h.max():
            hi_idx.append(i)
        if l[i] <= w_l.min():
            lo_idx.append(i)
    hi_idx = np.array(hi_idx, np.int64); lo_idx = np.array(lo_idx, np.int64)
    return dict(hi_price=h[hi_idx], hi_conf=hi_idx + k, hi_at=hi_idx,
                lo_price=l[lo_idx], lo_conf=lo_idx + k, lo_at=lo_idx)


def htf_pools(d, tf, k):
    """Confirmed swing levels from a higher timeframe, mapped to the 1-MINUTE bar on which they
    become knowable."""
    r = resample(d, tf)
    p = pivots(r["h"], r["l"], k)
    return dict(
        hi_price=p["hi_price"], hi_conf_1m=r["last_i"][np.minimum(p["hi_conf"], len(r["c"]) - 1)],
        lo_price=p["lo_price"], lo_conf_1m=r["last_i"][np.minimum(p["lo_conf"], len(r["c"]) - 1)])


# ------------------------------------------------------------------------------------------------
# session levels, frozen at the session end
# ------------------------------------------------------------------------------------------------
def session_levels(d):
    """Asia, London, previous-day RTH and running-RTH levels, every one exposed only from the bar
    it is frozen on, with the freeze expressed in minutes since the 18:00 roll."""
    n = len(d["c"])
    tmin, tday, h, l, o, c = d["tmin"], d["tday"], d["h"], d["l"], d["o"], d["c"]
    out = {k: np.full(n, np.nan) for k in
           ("asia_h", "asia_l", "lon_h", "lon_l", "pd_h", "pd_l", "pd_o", "pd_c",
            "sess_h", "sess_l")}
    m_asia = (tmin >= ASIA_T[0]) & (tmin < ASIA_T[1])
    m_lon = (tmin >= LONDON_T[0]) & (tmin < LONDON_T[1])
    m_rth = (tmin >= RTH_T[0]) & (tmin < RTH_T[1])
    df = pd.DataFrame(dict(tday=tday, h=h, l=l, o=o, c=c))

    # --- Asia and London: frozen at the window end, exposed only at a LATER tmin ---------------
    for name, mask, freeze in (("asia", m_asia, ASIA_T[1]), ("lon", m_lon, LONDON_T[1])):
        g = df[mask].groupby("tday")
        hi, lo = g.h.max(), g.l.min()
        key = pd.Series(tday)
        exposed = tmin >= freeze
        out[f"{name}_h"] = np.where(exposed, key.map(hi).to_numpy(float), np.nan)
        out[f"{name}_l"] = np.where(exposed, key.map(lo).to_numpy(float), np.nan)

    # --- previous day: the last trading day whose RTH has ENDED, never the current one ---------
    grth = df[m_rth].groupby("tday")
    stats = pd.DataFrame(dict(h=grth.h.max(), l=grth.l.min(), o=grth.o.first(), c=grth.c.last()))
    sdays = stats.index.to_numpy()
    # for each bar, the position of the last stats day STRICTLY BEFORE this bar's trading day
    pos = np.searchsorted(sdays, tday, side="left") - 1
    ok = pos >= 0
    for col in ("h", "l", "o", "c"):
        v = np.full(n, np.nan)
        v[ok] = stats[col].to_numpy()[pos[ok]]
        out[f"pd_{col}"] = v

    # --- running RTH high/low, shifted so a bar is never inside its own reading ----------------
    s = pd.Series(np.where(m_rth, h, np.nan))
    out["sess_h"] = s.groupby(pd.Series(tday)).cummax().shift(1).to_numpy()
    s = pd.Series(np.where(m_rth, l, np.nan))
    out["sess_l"] = s.groupby(pd.Series(tday)).cummin().shift(1).to_numpy()
    return out


def truncation_check(d, L, at=(200000, 500000, 800000)):
    """Recompute the session levels on history ENDING at bar i and require a match. The only honest
    leakage audit -- it caught two real leaks on this branch that inspection missed."""
    bad = []
    for i in at:
        if i >= len(d["c"]):
            continue
        cut = {k: (v[:i + 1] if isinstance(v, np.ndarray) else v[:i + 1])
               for k, v in d.items() if k != "ts"}
        cut["ts"] = d["ts"][:i + 1]
        Lc = session_levels(cut)
        for k in L:
            a, b = L[k][i], Lc[k][i]
            if np.isfinite(a) != np.isfinite(b) or (np.isfinite(a) and abs(a - b) > 1e-9):
                bad.append((k, i, float(a), float(b)))
    return bad


if __name__ == "__main__":
    d = load()
    a = audit(d)
    print("=" * 104)
    print("DATA AUDIT -- NQ 1-minute")
    print("=" * 104)
    for k, v in a.items():
        print(f"   {k:<26}{v}")
    if a["exact_2p20"]:
        print("   !! row count is EXACTLY 2^20 - 1, the Excel row limit. Check the gaps above "
              "before trusting the span.")
    L = session_levels(d)
    print("\n   session levels built. non-nan coverage:")
    for k, v in L.items():
        print(f"      {k:<10}{float(np.isfinite(v).mean()):.3f}")
    bad = truncation_check(d, L)
    print(f"\n   TRUNCATION AUDIT on session levels: {'CLEAN' if not bad else f'{len(bad)} MISMATCHES'}")
    for k, i, x, y in bad[:10]:
        print(f"      {k} at {i}: full {x} truncated {y}")
    for tf, k in ((60, 3), (240, 2)):
        p = htf_pools(d, tf, k)
        print(f"   {tf}m pivots (k={k}): {len(p['hi_price'])} highs, {len(p['lo_price'])} lows")
