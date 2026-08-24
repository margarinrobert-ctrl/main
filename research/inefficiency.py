"""Does auction theory's inefficiency claim hold on this instrument, and is it worth money?

Two claims, stated before they were measured, because a volume profile offers dozens of ways to
slice a sample and only a pre-registered claim is worth a p-value.

  H1  REVISIT. A low-volume node is a price the auction moved through quickly and left unfinished.
      Theory says it gets traded through again sooner than a price picked at random. Control:
      a level at the SAME DISTANCE from the same session's close, on a random side -- because
      distance to a level dominates how soon it is reached, and an unmatched control would show
      an "edge" that is only the LVNs sitting nearer the close.

  H2  TRAVERSE, which is the one that could be worth money. A 1R target sitting in a low-volume
      area should be reached more often than one sitting at a high-volume node, because there is
      less resting interest between price and it. Every trade of every shipped strategy is
      labelled by the volume density at its TARGET and at its STOP, taken from the PRIOR
      session's profile, and split by that.

H2 is a labelling of trades that already exist, not a new search: it cannot pick a rule, and the
label is fixed before the trade opens. The research block chooses nothing here either -- the split
is by tercile of a measured quantity, and both blocks are reported.

Usage: python3 research/inefficiency.py
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
import volprofile as VP
from allstrats import all_strategies
from oner_union import _cut, _sim

HORIZON = 20              # sessions allowed for a revisit


def density(P, row, price):
    """Smoothed prior-session volume at `price`, as a share of that session's POC volume.

    0.0 means the session never traded there. The smoothing is the same one node detection uses,
    so "low density" here and "low-volume node" there mean the same thing.
    """
    if row < 0 or not np.isfinite(price):
        return np.nan
    h = P["H"][row]
    live = np.flatnonzero(h > 0)
    if not len(live):
        return np.nan
    k = int((price - P["base"]) / VP.BIN)
    if k < live[0] or k > live[-1]:
        return 0.0                      # beyond what the prior session traded at all
    s = VP._smooth(h)
    peak = s[live[0]:live[-1] + 1].max()
    return float(s[k] / peak) if peak > 0 else np.nan


# ---- H1 -----------------------------------------------------------------------------------------
def revisit(P, seed=11, verbose=True):
    hi, lo = P["hi"], P["lo"]
    n = len(hi)
    rng = np.random.default_rng(seed)
    close = np.array([P["bar_c"][P["bar_sess"] == s][-1] if (P["bar_sess"] == s).any() else np.nan
                      for s in P["sess"]])

    def first_touch(r, price):
        """Sessions until a LATER session trades through `price`; HORIZON+1 if it never does."""
        end = min(n, r + 1 + HORIZON)
        for j in range(r + 1, end):
            if lo[j] <= price <= hi[j]:
                return j - r
        return HORIZON + 1

    real, ctrl, dists = [], [], []
    for r in range(n - HORIZON - 1):
        if not np.isfinite(close[r]):
            continue
        nodes = P["LVN"][r]
        nodes = nodes[np.isfinite(nodes)]
        for x in nodes:
            dlt = abs(x - close[r])
            if dlt <= 0:
                continue
            real.append(first_touch(r, x))
            side = 1 if rng.random() < 0.5 else -1
            ctrl.append(first_touch(r, close[r] + side * dlt))
            dists.append(dlt)
    real = np.array(real); ctrl = np.array(ctrl); dists = np.array(dists)
    if verbose:
        print("H1  DO LOW-VOLUME NODES GET REVISITED SOONER THAN A DISTANCE-MATCHED LEVEL?")
        print(f"    {len(real):,} low-volume nodes across {n - HORIZON - 1} sessions, "
              f"median distance from the session close {np.median(dists):.0f} points")
        print(f"    {'':<22}{'revisited <=1':>15}{'<=5':>8}{'<=20':>8}{'median sessions':>18}")
        for nm, a in (("low-volume node", real), ("distance-matched", ctrl)):
            fin = a[a <= HORIZON]
            print(f"    {nm:<22}{100*(a<=1).mean():>14.1f}%{100*(a<=5).mean():>7.1f}%"
                  f"{100*(a<=HORIZON).mean():>7.1f}%"
                  f"{np.median(fin) if len(fin) else np.nan:>18.1f}")
        from scipy import stats as st
        u = st.mannwhitneyu(real, ctrl, alternative="less")
        print(f"    Mann-Whitney (LVN revisited sooner): p = {u.pvalue:.4f}"
              + ("   <- holds" if u.pvalue < 0.05 else "   <- does not hold"))
    return real, ctrl


# ---- H2 -----------------------------------------------------------------------------------------
def label_trades(key, S, P, verbose=False):
    """Every trade of one strategy, labelled by prior-session volume density at target and stop."""
    d = S["d"]
    si, cut, _ = _cut(d)
    pnl, eb, xb, why, gap = _sim(d, S["trig"], S["side"], S["am"], S["flat"])
    o, atr_ = d["o"], d["atr"]
    us = P["sess"]
    rows = np.searchsorted(us, d["sess"])
    ok = (rows < len(us)) & (us[np.clip(rows, 0, len(us) - 1)] == d["sess"])
    prior = np.where(ok & (rows > 0), rows - 1, -1)

    sb = np.maximum(eb - 1, 0)          # the signal bar; eb is already the FILL bar
    entry = o[eb]
    risk = S["am"] * atr_[sb]
    tgt = entry + S["side"] * risk
    stp = entry - S["side"] * risk
    dt = np.array([density(P, prior[b], x) for b, x in zip(sb, tgt)])
    ds = np.array([density(P, prior[b], x) for b, x in zip(sb, stp)])
    return dict(key=key, pnl=pnl, eb=eb, why=why, lok=si[eb] >= cut, dt=dt, ds=ds,
                side=S["side"])


def h2(verbose=True):
    P = VP.build()
    A = all_strategies()
    L = {k: label_trades(k, S, P) for k, S in A.items()}
    allt = np.concatenate([L[k]["dt"] for k in L])
    alls = np.concatenate([L[k]["ds"] for k in L])
    pnl = np.concatenate([L[k]["pnl"] for k in L])
    lok = np.concatenate([L[k]["lok"] for k in L])
    why = np.concatenate([L[k]["why"] for k in L])

    print("\n\nH2  IS A TARGET IN A LOW-VOLUME AREA REACHED MORE OFTEN?")
    print(f"    {len(pnl):,} trades across {len(L)} strategies, each labelled by the PRIOR "
          f"session's\n    volume density at its target price (1.0 = the point of control)\n")
    inside = np.isfinite(allt) & (allt > 0)
    out = np.isfinite(allt) & (allt == 0)
    qs = np.nanquantile(allt[inside], [1 / 3, 2 / 3]) if inside.sum() > 30 else [0, 0]
    groups = [
        ("target beyond prior range", out),
        (f"target density < {qs[0]:.2f}", inside & (allt < qs[0])),
        (f"target density {qs[0]:.2f}-{qs[1]:.2f}", inside & (allt >= qs[0]) & (allt < qs[1])),
        (f"target density > {qs[1]:.2f}", inside & (allt >= qs[1])),
    ]
    print(f"    {'':<30}{'n':>6}{'win%':>7}{'$/trade':>10}{'net $':>10}{'hit tgt':>9}"
          f"{'lok n':>7}{'lok win%':>10}")
    for nm, m in groups:
        if m.sum() < 20:
            print(f"    {nm:<30}{int(m.sum()):>6}   (too few)"); continue
        p = pnl[m]; w = p > 0
        print(f"    {nm:<30}{int(m.sum()):>6}{100*w.mean():>7.1f}{p.mean():>10,.0f}"
              f"{p.sum():>10,.0f}{100*(why[m]==2).mean():>8.0f}%"
              f"{int((m&lok).sum()):>7}{100*(pnl[m&lok]>0).mean():>10.1f}")

    print(f"\n    the same split on the STOP price -- a stop at a high-volume node should hold")
    ins = np.isfinite(alls) & (alls > 0)
    outs = np.isfinite(alls) & (alls == 0)
    qs2 = np.nanquantile(alls[ins], [1 / 3, 2 / 3]) if ins.sum() > 30 else [0, 0]
    for nm, m in [("stop beyond prior range", outs),
                  (f"stop density < {qs2[0]:.2f}", ins & (alls < qs2[0])),
                  (f"stop density {qs2[0]:.2f}-{qs2[1]:.2f}", ins & (alls >= qs2[0]) & (alls < qs2[1])),
                  (f"stop density > {qs2[1]:.2f}", ins & (alls >= qs2[1]))]:
        if m.sum() < 20:
            print(f"    {nm:<30}{int(m.sum()):>6}   (too few)"); continue
        p = pnl[m]; w = p > 0
        print(f"    {nm:<30}{int(m.sum()):>6}{100*w.mean():>7.1f}{p.mean():>10,.0f}"
              f"{p.sum():>10,.0f}{100*(why[m]==1).mean():>8.0f}%"
              f"{int((m&lok).sum()):>7}{100*(pnl[m&lok]>0).mean():>10.1f}")
    print("    (the 'hit tgt' column is the share exiting at the target; on the stop table it is\n"
          "     the share exiting at the stop)")

    print(f"\n    per strategy, low-density target versus high-density target, win rate:")
    print(f"    {'':<6}{'n low':>7}{'win low':>9}{'n high':>8}{'win high':>10}{'gap':>7}"
          f"{'$ low':>9}{'$ high':>9}")
    for k in L:
        t = L[k]["dt"]; p = L[k]["pnl"]
        i = np.isfinite(t)
        if i.sum() < 30:
            continue
        q = np.nanquantile(t[i], [1 / 3, 2 / 3])
        a = i & (t <= q[0]); b = i & (t >= q[1])
        if a.sum() < 8 or b.sum() < 8:
            continue
        print(f"    {k:<6}{int(a.sum()):>7}{100*(p[a]>0).mean():>9.1f}{int(b.sum()):>8}"
              f"{100*(p[b]>0).mean():>10.1f}{100*(p[a]>0).mean()-100*(p[b]>0).mean():>+7.1f}"
              f"{p[a].sum():>9,.0f}{p[b].sum():>9,.0f}")
    return L


# ---- H3: the 80% rule ----------------------------------------------------------------------------
def eighty_rule(P=None, verbose=True):
    """"Open outside value, trade back inside, hold two consecutive 30-minute periods inside, and
    the market has an ~80% chance of traversing the whole value area."

    The control is the part that decides the answer. Being inside yesterday's value area at 11:00
    with five hours left gives you a decent chance of reaching either edge whatever the rule says,
    so the control is every session that was ALSO inside value at the SAME time of day -- matched
    on how much session is left and on where price sits relative to value -- without having opened
    outside it. What the rule claims to add is the opening context.
    """
    P = P if P is not None else VP.build()
    us = P["sess"]; sess = P["bar_sess"]; mod = P["bar_mod"]
    c = P["bar_c"]; h = P["bar_h"]; l = P["bar_l"]
    vah, val, op = P["vah"], P["val"], P["open_px"]
    armed, ctrl = [], []
    for r in range(1, len(us)):
        if not (np.isfinite(vah[r - 1]) and np.isfinite(val[r - 1])):
            continue
        sel = np.flatnonzero(sess == us[r])
        if len(sel) < 60:
            continue
        hi_, lo_ = vah[r - 1], val[r - 1]
        cc, hh, ll, mm = c[sel], h[sel], l[sel], mod[sel]
        inside = (cc >= lo_) & (cc <= hi_)
        opened_out = not (lo_ <= op[r] <= hi_)
        above = op[r] > hi_
        # first bar at which two consecutive completed 30-minute periods have closed inside
        per = mm // 30
        run, last, tidx = 0, -1, None
        for i in range(len(sel)):
            if inside[i]:
                if per[i] != last:
                    run += 1; last = per[i]
            else:
                run, last = 0, -1
            if run >= 2:
                tidx = i; break
        if tidx is None:
            continue
        far = lo_ if above else hi_          # the OPPOSITE edge, which the rule says gets reached
        # for a control session we do not know a direction, so score both edges and take the one
        # matching the armed session it is being compared against
        rest_h, rest_l = hh[tidx:], ll[tidx:]
        hit_lo = bool((rest_l <= lo_).any()); hit_hi = bool((rest_h >= hi_).any())
        rec = dict(t=int(mm[tidx]), hit_lo=hit_lo, hit_hi=hit_hi,
                   trav=(hit_lo if above else hit_hi), above=above,
                   left=len(sel) - tidx)
        (armed if opened_out else ctrl).append(rec)

    if not armed:
        return None
    A = armed
    # time-matched control: for each armed session, controls that reached "inside value" at a
    # similar time of day and with a similar amount of session left
    rate = []
    for a in A:
        pool = [x for x in ctrl if abs(x["t"] - a["t"]) <= 30]
        if len(pool) < 10:
            continue
        got = np.mean([(x["hit_lo"] if a["above"] else x["hit_hi"]) for x in pool])
        rate.append(got)
    obs = float(np.mean([a["trav"] for a in A]))
    exp = float(np.mean(rate)) if rate else np.nan
    if verbose:
        from scipy import stats as st
        n = len(A)
        print("\n\nH3  THE 80% RULE")
        print(f"    {n} sessions opened outside the prior value area and then held two "
              f"consecutive\n    30-minute periods inside it")
        print(f"    {'':<44}{'traversed':>11}")
        print(f"    {'the 80% rule, as claimed':<44}{'80%':>11}")
        print(f"    {'measured on these sessions':<44}{100*obs:>10.1f}%")
        print(f"    {'time-matched control (opened INSIDE value)':<44}{100*exp:>10.1f}%")
        if np.isfinite(exp):
            k = int(round(obs * n))
            pv = st.binomtest(k, n, exp, alternative="greater").pvalue
            print(f"\n    lift over the matched control {100*(obs-exp):+.1f} points, "
                  f"binomial p = {pv:.3f}"
                  + ("   <- holds" if pv < 0.05 else "   <- does not hold"))
            print(f"    and against the claimed 80%: "
                  f"p = {st.binomtest(k, n, 0.80, alternative='less').pvalue:.4f} that the true "
                  f"rate is below 80%")
    return obs, exp, len(A)


if __name__ == "__main__":
    P = VP.build()
    revisit(P)
    h2()
    eighty_rule(P)
