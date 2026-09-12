"""US30 15m: alpha discovery BEFORE a rule -- the protocol's stage 2, on the research block.

Three passes of rule search on the 09:00 range-break structure found nothing. The instruction now
is to find the MOST profitable design. The disciplined order is: first measure where the file has
any predictability at all, then build one rule on the largest surviving effect, then test it with
the same gates. This module is the first step.

Everything here is computed on the RESEARCH block (first 65% of sessions) only, with:
    * drift adjustment   edge = mean(side x fwd) - mean(side) x mean(fwd), so a condition that is
                         long more often than short on a rising file does not get credit for beta
    * HAC lag >= horizon overlapping h-bar forward windows are MA(h-1); Newey-West with lag = h
    * BH FDR             across every bucket / event / horizon tested
    * the LIFT           event mean minus non-event mean (never "event vs zero", which measures
                         the cost line, RESEARCH_PROTOCOL 4a)
    * the budget         the largest surviving drift-adjusted edge divided by the round turn

    python3 research/us30_alpha.py
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import norm

import us30_orb as U
from us30_orb import load, sessions, split_days, ema_of

COST_PTS = 3.0


def nw_t(x, lag):
    """Newey-West t-stat of the mean of x with `lag` lags."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 20:
        return np.nan, np.nan
    m = x.mean()
    e = x - m
    s = (e * e).sum()
    for L in range(1, lag + 1):
        w = 1 - L / (lag + 1)
        s += 2 * w * (e[L:] * e[:-L]).sum()
    se = math.sqrt(max(s, 1e-12)) / n
    return m, m / se


def bh(p):
    p = np.asarray(p, float)
    n = len(p)
    order = np.argsort(p)
    q = np.empty(n)
    prev = 1.0
    for rank, i in enumerate(reversed(order), 1):
        k = n - rank + 1
        prev = min(prev, p[i] * n / k)
        q[i] = prev
    return q


def rth_mask(d):
    return (d["mod"] >= 570) & (d["mod"] < 960)


def block_masks(d):
    cut = split_days(d)
    return d["day"] < cut, d["day"] >= cut


# ------------------------------------------------------------------------------------------------
def autocorrelation(d, res, lags=10):
    r = np.diff(d["c"]) / d["c"][:-1]
    r = np.r_[np.nan, r]
    same_day = np.r_[False, d["day"][1:] == d["day"][:-1]]
    m = res & rth_mask(d) & same_day & np.isfinite(r)
    x = r[m]
    n = len(x)
    rows = []
    xc = x - x.mean()
    for L in range(1, lags + 1):
        a = np.corrcoef(x[L:], x[:-L])[0, 1]
        # heteroskedasticity-robust standard error of the autocorrelation
        se = math.sqrt(((xc[L:] ** 2) * (xc[:-L] ** 2)).sum()) / (xc ** 2).sum()
        rows.append(dict(lag=L, rho=a, t_naive=a * math.sqrt(n), t_robust=a / se, n=n))
    return pd.DataFrame(rows)


def variance_ratio(d, res, qs=(2, 4, 8, 16)):
    r = np.diff(np.log(d["c"]))
    r = np.r_[np.nan, r]
    same_day = np.r_[False, d["day"][1:] == d["day"][:-1]]
    m = res & rth_mask(d) & same_day & np.isfinite(r)
    x = r[m] - r[m].mean()
    n = len(x)
    rows = []
    for q in qs:
        s = np.convolve(x, np.ones(q), "valid")
        vr = s.var() / (q * x.var())
        # Lo-MacKinlay heteroskedasticity-robust standard error
        theta = 0.0
        for j in range(1, q):
            num = ((x[j:] ** 2) * (x[:-j] ** 2)).sum()
            den = (x ** 2).sum() ** 2
            delta = n * num / den
            theta += (2 * (q - j) / q) ** 2 * delta
        z = math.sqrt(n) * (vr - 1) / math.sqrt(theta) if theta > 0 else np.nan
        rows.append(dict(q=q, VR=vr, z=z))
    return pd.DataFrame(rows)


def time_of_day(d, res, h=1):
    """Mean signed forward move (points) per 15m slot in RTH, drift-adjusted within the block,
    HAC t with lag h, BH across slots. Also mean absolute move."""
    c, mod = d["c"], d["mod"]
    n = d["n"]
    fwd = np.full(n, np.nan)
    ok = np.arange(n - h)
    same = d["day"][ok + h] == d["day"][ok]
    fwd[ok[same]] = c[ok + h][same] - c[ok][same]
    m = res & rth_mask(d) & np.isfinite(fwd)
    drift = fwd[m].mean()
    rows = []
    for s in range(570, 960, 15):
        mm = m & (mod == s)
        x = fwd[mm] - drift
        mean, t = nw_t(x, h)
        rows.append(dict(slot=f"{s // 60:02d}:{s % 60:02d}", n=int(mm.sum()), mean_pt=mean, t=t,
                         p=2 * (1 - norm.cdf(abs(t))) if np.isfinite(t) else np.nan,
                         abs_move=np.abs(fwd[mm]).mean()))
    df = pd.DataFrame(rows)
    df["q"] = bh(df.p.fillna(1.0))
    return df, drift


def events(d, F, res, horizons=(1, 2, 4, 8)):
    """Event studies at the open. Each event has a SIDE (+1/-1) and fires at a signal bar; the
    outcome is side x forward move over h bars from the next bar's open, drift-adjusted, and the
    statistic is the LIFT over the non-event bars in the same slot, HAC lag h."""
    c, o, h_, l, mod, day = d["c"], d["o"], d["h"], d["l"], d["mod"], d["day"]
    n = d["n"]
    atr = ema_of(d, 14, "tr")
    out = []
    # per-session facts
    facts = F
    def fwd_from_open(h):
        f = np.full(n, np.nan)
        ok = np.arange(n - h - 1)
        same = day[ok + 1 + h - 1] == day[ok]   # h bars starting at the next bar's open
        f[ok[same]] = c[ok + h][same] - o[ok + 1][same]
        return f
    defs = {}
    # 1. gap: at the 09:30 bar close, side = toward the prior close (gap fill)
    g = {}
    for dd, row in facts.iterrows():
        j = d["pos"].get((dd, 570))
        if j is None or not np.isfinite(row.gap):
            continue
        if abs(row.gap) >= 0.5 * row.atr:
            g[j] = -np.sign(row.gap)
    defs["gap fill (|gap| >= 0.5 ATR, side toward prior close)"] = (g, 570)
    # 2. first 30 minutes: side = against the 09:30-10:00 move (reversal) measured at the 09:45 close
    g = {}
    for dd in facts.index:
        j0, j1 = d["pos"].get((dd, 570)), d["pos"].get((dd, 585))
        if j0 is None or j1 is None:
            continue
        mv = c[j1] - o[j0]
        if abs(mv) >= 0.75 * atr[j1]:
            g[j1] = -np.sign(mv)
    defs["first 30 min reversal (|move| >= 0.75 ATR, side against)"] = (g, 585)
    # 3. 09:00 range break on close, side WITH the break (the user's structure, no filters)
    g = {}
    for dd, row in facts.iterrows():
        for m in range(570, 630, 15):
            j = d["pos"].get((dd, m))
            if j is None:
                continue
            if c[j] > row.hi:
                g[j] = 1; break
            if c[j] < row.lo:
                g[j] = -1; break
    defs["09:00 range break (first close beyond, side with)"] = (g, None)
    # 4. overnight range break on close in the first hour, side with
    g = {}
    on = {}
    for dd in facts.index:
        js = [d["pos"].get((dd - 1, m)) for m in range(1080, 1440, 15)] + [d["pos"].get((dd, m)) for m in range(0, 540, 15)]
        js = [j for j in js if j is not None]
        if len(js) < 20:
            continue
        on[dd] = (h_[js].max(), l[js].min())
    for dd, (oh, ol) in on.items():
        for m in range(570, 630, 15):
            j = d["pos"].get((dd, m))
            if j is None:
                continue
            if c[j] > oh:
                g[j] = 1; break
            if c[j] < ol:
                g[j] = -1; break
    defs["overnight range break (first close beyond, side with)"] = (g, None)
    # 5. large bar continuation in RTH: |bar| >= 2 ATR, side with
    g = {}
    for j in np.where(rth_mask(d))[0]:
        b = c[j] - o[j]
        if abs(b) >= 2.0 * atr[j - 1]:
            g[j] = np.sign(b)
    defs["large bar (>= 2 ATR) continuation, side with"] = (g, None)
    # 6. prior-close cross in the first hour: side with the cross
    g = {}
    for dd, row in facts.iterrows():
        pc = row.get("pc", np.nan) if "pc" in row else np.nan
    defs_h = {}
    rows = []
    for name, (g, slot) in defs.items():
        if not g:
            continue
        idx = np.array(sorted(g)); side = np.array([g[i] for i in idx], float)
        m_res = res[idx]
        idx, side = idx[m_res], side[m_res]
        for h in horizons:
            f = fwd_from_open(h)
            ev = f[idx]
            ok = np.isfinite(ev)
            y = side[ok] * ev[ok]
            # non-event comparison: every research RTH bar in the same slot(s), drift-adjusted
            if slot is not None:
                base_m = res & (mod == slot) & np.isfinite(f)
            else:
                base_m = res & rth_mask(d) & (mod < 630) & np.isfinite(f)
            base_m[idx] = False
            # drift adjustment: signed-side expectation of a random side is zero; subtract the
            # mean of (side x f) over the base with the event's side mix
            pbar = side[ok].mean()
            base_f = f[base_m]
            drift_term = pbar * base_f.mean()
            lift = y.mean() - drift_term
            _, t = nw_t(y - drift_term, h)
            rows.append(dict(event=name, h=h, n=int(ok.sum()), long_share=100 * (side[ok] > 0).mean(),
                             raw_pt=y.mean(), drift_adj_pt=lift, t=t,
                             p=2 * (1 - norm.cdf(abs(t))) if np.isfinite(t) else np.nan,
                             net_of_cost=lift - COST_PTS))
    df = pd.DataFrame(rows)
    df["q"] = bh(df.p.fillna(1.0))
    return df


def main():
    d = load()
    import us30_orb2 as M2
    F = M2.session_facts(d)
    res, loc = block_masks(d)
    cut = split_days(d)
    print(f"US30 15m, research block = sessions before {d['dates'][cut]}; RTH bars in research: {int((res & rth_mask(d)).sum()):,}")
    print(f"round turn assumed {COST_PTS:g} pt; median 15m RTH bar range on research: {np.median((d['h']-d['l'])[res & rth_mask(d)]):.1f} pt")

    print("\n== 1. RETURN AUTOCORRELATION, 15m RTH bars, research (|t| > 2 is 2 sd) ==")
    ac = autocorrelation(d, res)
    print(ac.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    print("\n== 2. LO-MACKINLAY VARIANCE RATIOS, heteroskedasticity-robust (VR<1 reversal, >1 momentum) ==")
    vr = variance_ratio(d, res)
    print(vr.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    for h in (1, 4):
        print(f"\n== 3. TIME OF DAY, {h}-bar forward move, drift-adjusted, HAC lag {h}, BH q ==")
        tod, drift = time_of_day(d, res, h)
        print(f"  block drift per {h} bar(s): {drift:+.2f} pt")
        print(tod.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
        sig = tod[tod.q < 0.10]
        print(f"  slots with q < 0.10: {len(sig)}")

    print("\n== 4. EVENT STUDIES at the open, research, lift over non-event bars, drift-adjusted, HAC lag h ==")
    ev = events(d, F, res)
    print(ev.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    sig = ev[(ev.q < 0.10)]
    print(f"\n  events with q < 0.10: {len(sig)} of {len(ev)}")
    if len(sig):
        print(sig[["event", "h", "n", "drift_adj_pt", "net_of_cost", "t", "q"]].to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    best = ev.sort_values("drift_adj_pt", ascending=False).iloc[0]
    print(f"\n== 5. PREDICTABILITY BUDGET ==")
    surv = ev[ev.q < 0.10]
    if len(surv):
        b = surv.sort_values("drift_adj_pt", ascending=False).iloc[0]
        print(f"  largest surviving drift-adjusted edge: {b.drift_adj_pt:.1f} pt ({b.event}, h={b.h}) -> budget {b.drift_adj_pt / COST_PTS:.2f}x the round turn")
    else:
        print(f"  no event survives FDR. Largest raw drift-adjusted edge: {best.drift_adj_pt:.1f} pt ({best.event}, h={best.h}, q {best.q:.2f}) "
              f"-> budget {best.drift_adj_pt / COST_PTS:.2f}x the round turn, unreliable")
    return ac, vr, ev


if __name__ == "__main__":
    main()
