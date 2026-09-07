"""Auction-theory conditions on any strategy timeframe, from the 1-minute volume profile.

Every condition here is a boolean per bar, knowable at that bar's close, and expressed in the
same vocabulary as the rest of the condition pool so it can be ANDed onto an existing rule and
tested by the machinery that already exists.

Two families:

  ACCEPTANCE -- where the auction spent time. Prior session value area and point of control,
  developing value area, value migration, balance versus imbalance, unfinished ("poor") extremes.
  The claim being tested is that a trade taken from outside accepted value behaves differently
  from one taken inside it.

  INEFFICIENCY -- where it did not. Low-volume nodes are prices the auction moved through quickly.
  Auction theory says they get revisited; `research/inefficiency.py` measures whether that is
  true here before any of it is used as a filter.

CAUSALITY. Prior-session features come from the profile of the session BEFORE the current one and
are constant within a session. Developing features come from the 1-minute profile up to and
including the current bar's close, found by searchsorted on the 1-minute index -- never the bar
after. `leakage_check()` rebuilds both on truncated data and compares.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
import volprofile as VP

def signal_bars(ent_bar, lag=0):
    """The bar a trade was DECIDED on. See test_suite.sig_bar, which this defers to."""
    from test_suite import sig_bar
    return sig_bar(ent_bar, lag)


NEAR = 0.25               # "at" a level means within this many ATRs of it
FAR = 1.0                 # "away from" a level means more than this many ATRs


def _map(d, P):
    """For each bar of `d`, the row of its OWN session's profile and its PRIOR session's."""
    us = P["sess"]
    own = np.searchsorted(us, d["sess"])
    own = np.where((own < len(us)) & (us[np.clip(own, 0, len(us) - 1)] == d["sess"]), own, -1)
    prior = np.where(own > 0, own - 1, -1)

    # developing profile: the last 1-minute bar at or before this bar's close.
    t_bar = d["df"].index.to_numpy()
    t_min = P["bar_idx"].to_numpy()
    j = np.searchsorted(t_min, t_bar, side="right") - 1
    ok = j >= 0
    # and it must belong to the same session, or the "developing" profile is yesterday's
    same = ok & (P["bar_sess"][np.clip(j, 0, len(t_min) - 1)] == d["sess"])
    return own, prior, np.where(same, j, -1)


def _pick(arr, idx):
    out = np.full(len(idx), np.nan)
    m = idx >= 0
    out[m] = arr[idx[m]]
    return out


def _near_any(c, table, idx, tol):
    """Is the close within `tol` of any node in the prior session's node table?"""
    out = np.zeros(len(c), bool)
    m = np.flatnonzero(idx >= 0)
    for i in m:
        row = table[idx[i]]
        row = row[np.isfinite(row)]
        if len(row) and np.abs(row - c[i]).min() <= tol[i]:
            out[i] = True
    return out


def _nearest_signed(c, table, idx, above):
    """Distance to the nearest node strictly above (or below) the close. inf when there is none."""
    out = np.full(len(c), np.inf)
    m = np.flatnonzero(idx >= 0)
    for i in m:
        row = table[idx[i]]
        row = row[np.isfinite(row)]
        row = row[row > c[i]] if above else row[row < c[i]]
        if len(row):
            out[i] = (row.min() - c[i]) if above else (c[i] - row.max())
    return out


def _naked_dist(c, P, own, above):
    """Distance to the nearest POC of an earlier session that has never been traded through."""
    out = np.full(len(c), np.inf)
    poc = P["poc"]
    for r in np.unique(own[own > 0]):
        rows = np.flatnonzero(P["naked"][r])
        rows = rows[rows < r]
        if not len(rows):
            continue
        lv = poc[rows]
        lv = lv[np.isfinite(lv)]
        if not len(lv):
            continue
        sel = np.flatnonzero(own == r)
        cc = c[sel]
        for k, x in zip(sel, cc):
            v = lv[lv > x] if above else lv[lv < x]
            if len(v):
                out[k] = (v.min() - x) if above else (x - v.max())
    return out


def _armed(d, pv_h, pv_l, own):
    """The 80% rule's armed state, built forward through each session from completed periods."""
    c, mod, sess = d["c"], d["mod"], d["sess"]
    n = len(c)
    out = np.zeros(n, bool)
    inside = np.isfinite(pv_h) & (c >= pv_l) & (c <= pv_h)
    period = (mod // 30).astype(np.int64)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sess[j + 1] == sess[i]:
            j += 1
        if own[i] > 0 and np.isfinite(pv_h[i]):
            # did it OPEN outside value? the first bar of the session settles that
            if not inside[i]:
                run_p, last_p, live = 0, -1, False
                for k in range(i, j + 1):
                    if inside[k]:
                        if period[k] != last_p:
                            run_p += 1; last_p = period[k]
                    else:
                        run_p, last_p = 0, -1
                    if run_p >= 2:
                        live = True
                    out[k] = live
        i = j + 1
    return out


def _naked_level(c, P, own, tab, lvl, above):
    """Distance to the nearest still-untested VAH or VAL from an earlier session."""
    out = np.full(len(c), np.inf)
    for r in np.unique(own[own > 0]):
        rows = np.flatnonzero(tab[r])
        rows = rows[rows < r]
        if not len(rows):
            continue
        v = lvl[rows]
        v = v[np.isfinite(v)]
        if not len(v):
            continue
        for k in np.flatnonzero(own == r):
            x = c[k]
            w = v[v > x] if above else v[v < x]
            if len(w):
                out[k] = (w.min() - x) if above else (x - w.max())
    return out


def conditions(d, P=None, src_tf=1):
    """{name: bool array} aligned to d's bars. `d` is a bos_choch.prep dictionary."""
    P = P if P is not None else VP.build(src_tf=src_tf)
    c, atr_ = d["c"], np.maximum(d["atr"], 1e-9)
    own, prior, j = _map(d, P)
    S = {}

    pv_h, pv_l, pv_p = _pick(P["vah"], prior), _pick(P["val"], prior), _pick(P["poc"], prior)
    p_hi, p_lo = _pick(P["hi"], prior), _pick(P["lo"], prior)
    have = np.isfinite(pv_h) & np.isfinite(pv_l)

    # ---- acceptance: the prior session's value ------------------------------------------------
    S["above prior value"] = have & (c > pv_h)
    S["below prior value"] = have & (c < pv_l)
    S["inside prior value"] = have & (c >= pv_l) & (c <= pv_h)
    S["above prior POC"] = np.isfinite(pv_p) & (c > pv_p)
    S["below prior POC"] = np.isfinite(pv_p) & (c < pv_p)
    dp = np.abs(c - pv_p) / atr_
    S["at prior POC"] = np.isfinite(dp) & (dp <= NEAR)
    S["far from prior POC"] = np.isfinite(dp) & (dp > FAR)
    S["above prior session high"] = np.isfinite(p_hi) & (c > p_hi)
    S["below prior session low"] = np.isfinite(p_lo) & (c < p_lo)

    # ---- the shape of the prior auction --------------------------------------------------------
    vaw = P["vah"] - P["val"]
    ref = np.full(len(vaw), np.nan)
    for i in range(20, len(vaw)):
        ref[i] = np.nanmean(vaw[i - 20:i])
    w = _pick(vaw, prior); wr = _pick(ref, prior)
    S["prior value narrow"] = np.isfinite(w) & np.isfinite(wr) & (w < 0.8 * wr)
    S["prior value wide"] = np.isfinite(w) & np.isfinite(wr) & (w > 1.2 * wr)
    S["prior poor high"] = _pick(P["poor_hi"].astype(float), prior) > 0.5
    S["prior poor low"] = _pick(P["poor_lo"].astype(float), prior) > 0.5
    poc2 = np.r_[np.nan, P["poc"][:-1]]
    mig = P["poc"] - poc2
    m2 = _pick(mig, prior)
    S["value migrated up"] = np.isfinite(m2) & (m2 > 0)
    S["value migrated down"] = np.isfinite(m2) & (m2 < 0)

    # ---- the developing auction, today ---------------------------------------------------------
    dvh, dvl_, dvp = _pick(P["dev_vah"], j), _pick(P["dev_val"], j), _pick(P["dev_poc"], j)
    S["above developing value"] = np.isfinite(dvh) & (c > dvh)
    S["below developing value"] = np.isfinite(dvl_) & (c < dvl_)
    S["inside developing value"] = np.isfinite(dvh) & (c >= dvl_) & (c <= dvh)
    S["above developing POC"] = np.isfinite(dvp) & (c > dvp)
    S["below developing POC"] = np.isfinite(dvp) & (c < dvp)

    # ---- the value-area EDGES as levels, not just as a container --------------------------------
    # Above/below/inside prior value answers "where is price relative to value". These answer
    # "is price AT the edge", which is the question every value-area setup actually asks: VAH and
    # VAL are where responsive sellers and buyers are supposed to be waiting.
    dh = np.abs(c - pv_h) / atr_
    dl = np.abs(c - pv_l) / atr_
    S["at prior VAH"] = np.isfinite(dh) & (dh <= NEAR)
    S["at prior VAL"] = np.isfinite(dl) & (dl <= NEAR)
    S["above prior VAH by 1 ATR"] = have & (c > pv_h + atr_)
    S["below prior VAL by 1 ATR"] = have & (c < pv_l - atr_)

    ddh = np.abs(c - dvh) / atr_
    ddl = np.abs(c - dvl_) / atr_
    S["at developing VAH"] = np.isfinite(ddh) & (ddh <= NEAR)
    S["at developing VAL"] = np.isfinite(ddl) & (ddl <= NEAR)

    # crossing the developing edges. `shift` is one bar of the STRATEGY timeframe, so both the
    # previous state and the current close are known at this bar's close.
    prev_above = np.r_[False, (c[:-1] > dvh[:-1])]
    prev_below = np.r_[False, (c[:-1] < dvl_[:-1])]
    prev_in = np.r_[False, ((c[:-1] >= dvl_[:-1]) & (c[:-1] <= dvh[:-1]))]
    same_sess = np.r_[False, d["sess"][1:] == d["sess"][:-1]]
    inside_now = np.isfinite(dvh) & (c >= dvl_) & (c <= dvh)
    S["re-entered value from above"] = same_sess & prev_above & inside_now
    S["re-entered value from below"] = same_sess & prev_below & inside_now
    S["broke above developing VAH"] = same_sess & prev_in & np.isfinite(dvh) & (c > dvh)
    S["broke below developing VAL"] = same_sess & prev_in & np.isfinite(dvl_) & (c < dvl_)

    # ---- how the session OPENED relative to prior value -----------------------------------------
    # Constant within a session and known from its first bar. Auction theory treats opening
    # outside value as the fundamental classification of a day.
    op = _pick(P["open_px"], own)
    S["open above prior VAH"] = have & np.isfinite(op) & (op > pv_h)
    S["open below prior VAL"] = have & np.isfinite(op) & (op < pv_l)
    S["open inside prior value"] = have & np.isfinite(op) & (op >= pv_l) & (op <= pv_h)

    # ---- today's value against yesterday's -------------------------------------------------------
    S["developing value above prior"] = have & np.isfinite(dvl_) & (dvl_ > pv_h)
    S["developing value below prior"] = have & np.isfinite(dvh) & (dvh < pv_l)
    S["developing value overlaps prior"] = (have & np.isfinite(dvh) & np.isfinite(dvl_)
                                            & (dvl_ <= pv_h) & (dvh >= pv_l))

    # ---- the 80% rule ------------------------------------------------------------------------------
    # "Open outside value, trade back inside, and hold two consecutive 30-minute periods inside,
    # and the market has about an 80% chance of traversing the whole value area." Armed state is
    # built forward through the session from completed periods only. `inefficiency.eighty_rule`
    # measures whether the 80% is anywhere near true here.
    S["80% rule armed"] = _armed(d, pv_h, pv_l, own)

    # ---- naked value-area edges ---------------------------------------------------------------------
    for nm, tab, above in (("naked VAH within 2 ATR above", P["naked_vah"], True),
                           ("naked VAH within 2 ATR below", P["naked_vah"], False),
                           ("naked VAL within 2 ATR above", P["naked_val"], True),
                           ("naked VAL within 2 ATR below", P["naked_val"], False)):
        S[nm] = _naked_level(c, P, own, tab, P["vah"] if "VAH" in nm else P["val"], above) / atr_ <= 2.0

    # ---- inefficiency: low-volume nodes ---------------------------------------------------------
    tolN = NEAR * atr_
    S["at a prior LVN"] = _near_any(c, P["LVN"], prior, tolN)
    S["at a prior HVN"] = _near_any(c, P["HVN"], prior, tolN)
    up = _nearest_signed(c, P["LVN"], prior, True) / atr_
    dn = _nearest_signed(c, P["LVN"], prior, False) / atr_
    S["LVN within 1 ATR above"] = up <= 1.0
    S["LVN within 1 ATR below"] = dn <= 1.0
    S["no LVN within 1 ATR"] = (up > 1.0) & (dn > 1.0)
    hup = _nearest_signed(c, P["HVN"], prior, True) / atr_
    hdn = _nearest_signed(c, P["HVN"], prior, False) / atr_
    S["HVN within 1 ATR above"] = hup <= 1.0
    S["HVN within 1 ATR below"] = hdn <= 1.0

    # ---- naked points of control -----------------------------------------------------------------
    nu = _naked_dist(c, P, own, True) / atr_
    nd = _naked_dist(c, P, own, False) / atr_
    S["naked POC within 2 ATR above"] = nu <= 2.0
    S["naked POC within 2 ATR below"] = nd <= 2.0

    for k in S:
        S[k] = np.nan_to_num(np.asarray(S[k], float), nan=0.0) > 0.5
        S[k][:300] = False
    return S


def leakage_check(tf=30, cuts=(0.4, 0.6, 0.8)):
    """Rebuild every condition from a prefix of the 1-minute data and compare before the cut."""
    from bos_choch import prep
    d = prep(tf)
    full = conditions(d)
    bad = []
    for f in cuts:
        T = int(f * len(d["c"]))
        dt = {k: (v[:T] if isinstance(v, np.ndarray) else v) for k, v in d.items()}
        dt["df"] = d["df"].iloc[:T]
        cut_time = d["df"].index[T - 1]
        P2 = _truncated_profile(cut_time)
        sub = conditions(dt, P2)
        for k in full:
            diff = int((full[k][:T] != sub[k]).sum())
            if diff:
                bad.append((f, k, diff))
    return bad


def _truncated_profile(cut_time):
    """A profile built only from 1-minute bars at or before `cut_time`."""
    from nqdata import load_bars, minute_of_day, session_index
    df = load_bars("data/NQ_1m.csv")
    df = df[df.index <= cut_time]
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
        out = df.reset_index().rename(columns={"ny": "timestamp"})
        out.to_csv(fh.name, index=False)
        return VP.build(fh.name)


if __name__ == "__main__":
    from bos_choch import prep
    d = prep(30)
    S = conditions(d)
    print(f"{len(S)} auction conditions on {len(d['c']):,} 30-minute bars\n")
    print(f"  {'condition':<32}{'fires':>9}{'share':>8}")
    for k, v in S.items():
        print(f"  {k:<32}{int(v.sum()):>9,}{100*v.mean():>7.1f}%")
    bad = leakage_check()
    print(f"\n  leakage check across 3 truncations: {'CLEAN' if not bad else bad[:6]}")
