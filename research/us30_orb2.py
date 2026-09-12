"""US30 09:00 range, second pass: the TIME is fixed and every other rule is on the table.

The first pass (`us30_orb.py`, `docs/ib/STUDY_US30_ORB.md`) found nothing in the rule as asked for
or in its parameter neighbourhood. The user's instruction was to keep tweaking the rules, holding
the time: the range is the 09:00-09:30 pre-open and entries are 09:30-10:30 New York. So this
pass widens the RULE space rather than the parameter space, along axes that each name a
mechanism, and keeps the protocol in front of it:

    entry mechanic   close-break at the next open (the original); a STOP order resting at the
                     level plus a buffer, filled intrabar; a LIMIT at the level after a close-
                     break, filled on the retest; and the FADE -- a close back inside the range
                     after a break, traded against the break
    momentum         EMA 13/48 state (the original); EMA 8/34 state; a fresh 13/48 cross; none
    trend gate       EMA 200 on / off
    break distance   any close beyond the level; a close beyond it by >= 25% of the range width
    volume           none; the break bar's volume >= 1.5x the median of the 09:30-10:15 bars over
                     the prior 20 sessions (causal; this column was unused in pass one)
    range width      none; compressed (range <= 1.5 x ATR(14)); wide (>= 2 x ATR)
    gap              none; the break must be WITH the overnight gap; against it
    exits            fixed points (100/100, 75/75, 50/100, 100/200); range-anchored (stop at
                     the range midpoint or the far side, target 1x or 2x the range width beyond
                     the level); a break-even move after half the target; flat 12:00 or 16:00

That is 4 x 4 x 2 x 2 x 2 x 3 x 3 = 1,152 rules x 11 geometries = 12,672 cells on top of the
16,200 already tried, and the deflated Sharpe counts all of them.

The gates, fixed before running:
    research block only; >= 60 research trades; both sides traded (>= 25% on the minority side);
    matched control (same side, same fill minute, same stop/target, same block, random session)
    z >= 2.0; neighbour stability >= 0.7 (plateau); AND the rule must beat the same entry
    mechanic run on every session with no filter at all, because a mechanic that pays on random
    days is an execution effect, not a signal (STUDY_LIMIT_ENTRY.md).
Whatever passes is read on the locked block ONCE, the multiplicity stated first.

    python3 research/us30_orb2.py
"""
from __future__ import annotations

import argparse
import itertools
import math
from dataclasses import dataclass, asdict, replace

import numpy as np
import pandas as pd

import us30_orb as U
from us30_orb import (COST_PTS, STOP_SLIP, PT_VALUE, K, ANN, load, ema_of, sessions, split_days,
                      metrics, fmt, deflated_sharpe, bootstrap_ci, mc_drawdown, subperiods)

RANGE_START, RANGE_END, WIN_END = 540, 570, 630      # fixed by the user: 09:00-09:30, fills to 10:30


# ------------------------------------------------------------------------------------------------
# per-session facts, all known before 09:30
# ------------------------------------------------------------------------------------------------
def session_facts(d):
    days = sessions(d, RANGE_START)
    atr = ema_of(d, 14, "tr")
    rows = []
    prev_close = {}
    # prior session close: the last bar stamped < 16:00 of the previous eligible day
    for day in range(len(d["dates"])):
        j = d["pos"].get((day, 945))
        if j is not None:
            prev_close[day] = d["c"][j]
    win_vol = {}
    for day in range(len(d["dates"])):
        js = [d["pos"].get((day, m)) for m in range(570, 630, 15)]
        js = [j for j in js if j is not None]
        if js:
            win_vol[day] = float(np.median(d["v"][js]))
    for day in days:
        rs = [d["pos"][(day, m)] for m in range(RANGE_START, RANGE_END, 15)]
        hi, lo = d["h"][rs].max(), d["l"][rs].min()
        j930 = d["pos"][(day, 570)]
        pc = None
        for back in range(1, 5):
            if day - back in prev_close:
                pc = prev_close[day - back]
                break
        hist = [win_vol[k] for k in range(day - 30, day) if k in win_vol][-20:]
        rows.append(dict(day=day, hi=hi, lo=lo, width=hi - lo, atr=atr[rs[-1]],
                         gap=(d["o"][j930] - pc) if pc is not None else np.nan,
                         volbase=(float(np.median(hist)) if len(hist) >= 10 else np.nan)))
    return pd.DataFrame(rows).set_index("day")


# ------------------------------------------------------------------------------------------------
# the rule
# ------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Rule2:
    entry: str = "close"       # close | stop | limit | fade
    mom: str = "13/48"         # 13/48 | 8/34 | x13/48 (fresh cross within 2 bars) | none
    trend: int = 200           # 200 | 0
    dist: float = 0.0          # close beyond the level by >= dist x range width
    vol: float = 0.0           # break bar volume >= vol x baseline (0 = off)
    width: str = "any"         # any | tight (<= 1.5 ATR) | wide (>= 2 ATR)
    gap: str = "any"           # any | with | against
    buffer: float = 5.0        # stop-entry buffer in points

    def label(self):
        s = f"{self.entry} mom {self.mom} trend {self.trend or 'off'}"
        if self.dist:
            s += f" dist>={self.dist:g}w"
        if self.vol:
            s += f" vol>={self.vol:g}x"
        if self.width != "any":
            s += f" {self.width}"
        if self.gap != "any":
            s += f" gap-{self.gap}"
        return s


@dataclass(frozen=True)
class Geom2:
    kind: str = "pts"          # pts | range
    sl: float = 100.0          # pts: points; range: "mid" -> 0.5, "far" -> 1.0 of width
    tp: float = 100.0          # pts: points; range: multiple of width beyond the level
    flat: int = 960
    be: float = 0.0            # move the stop to entry after this fraction of the target (0 = off)

    def label(self):
        if self.kind == "pts":
            s = f"sl {self.sl:g} tp {self.tp:g} pt"
        else:
            s = f"sl {'mid' if self.sl == 0.5 else 'far'} tp {self.tp:g}x width"
        s += f" flat {self.flat // 60:02d}:{self.flat % 60:02d}"
        if self.be:
            s += f" BE@{self.be:g}"
        return s


def _mom_arrays(d, mom):
    if mom == "none":
        n = d["n"]
        return np.ones(n, bool), np.ones(n, bool)
    if mom.startswith("x"):
        f, s = (int(x) for x in mom[1:].split("/"))
        up = ema_of(d, f) > ema_of(d, s)
        xu = up & ~np.r_[False, up[:-1]]
        xd = ~up & np.r_[False, up[:-1]]
        k = 2
        fresh_up = np.zeros(len(up), bool)
        fresh_dn = np.zeros(len(up), bool)
        for i in range(k):
            fresh_up |= np.r_[np.zeros(i, bool), xu[:len(xu) - i]]
            fresh_dn |= np.r_[np.zeros(i, bool), xd[:len(xd) - i]]
        return up & fresh_up, ~up & fresh_dn
    f, s = (int(x) for x in mom.split("/"))
    up = ema_of(d, f) > ema_of(d, s)
    return up, ~up


_SIG = {}


def signals2(d, F, rule: Rule2):
    """Per session: (fill bar, fill price, side, signal bar, level, width). One trade a session.

    Conditions are read on the bar BEFORE the fill for every mechanic: for `close`, `limit` and
    `fade` that is the signal bar close; for `stop` it is the prior bar, because the fill is
    intrabar and the bar it fills on has not closed."""
    key = (id(d), rule)
    if key in _SIG:
        return _SIG[key]
    mom_up, mom_dn = _mom_arrays(d, rule.mom)
    trend = ema_of(d, rule.trend) if rule.trend else None
    c, h, l, o, v = d["c"], d["h"], d["l"], d["o"], d["v"]
    out = []
    for day, fx in F.iterrows():
        hi, lo, w = fx.hi, fx.lo, fx.width
        if rule.width == "tight" and not (w <= 1.5 * fx.atr):
            continue
        if rule.width == "wide" and not (w >= 2.0 * fx.atr):
            continue
        bars = [(m, d["pos"].get((day, m))) for m in range(RANGE_END, WIN_END + 15, 15)]
        bars = [(m, j) for m, j in bars if j is not None]
        if len(bars) < 2:
            continue
        broke = {1: False, -1: False}
        done = False
        for bi, (m, j) in enumerate(bars):
            if m >= WIN_END:            # 10:30 is only ever a fill bar
                break
            f = bars[bi + 1][1] if bi + 1 < len(bars) else None
            if f is None:
                break
            for side, lvl in ((1, hi), (-1, lo)):
                if rule.gap == "with" and not (np.isfinite(fx.gap) and np.sign(fx.gap) == side):
                    continue
                if rule.gap == "against" and not (np.isfinite(fx.gap) and np.sign(fx.gap) == -side):
                    continue
                if rule.entry == "stop":
                    # decision on bar j-1 (closed); the order rests at lvl +/- buffer through bar j
                    q = j - 1
                    t_ok = trend is None or (side * (c[q] - trend[q]) > 0)
                    m_ok = mom_up[q] if side == 1 else mom_dn[q]
                    trig = lvl + side * rule.buffer
                    hit = (h[j] >= trig) if side == 1 else (l[j] <= trig)
                    if not (hit and t_ok and m_ok):
                        continue
                    if rule.vol and not (np.isfinite(fx.volbase) and v[j] >= rule.vol * fx.volbase):
                        continue
                    px = max(o[j], trig) if side == 1 else min(o[j], trig)
                    out.append(dict(day=day, fill=j, px=px + side * 1.0, side=side, sig=q, lvl=lvl, w=w))
                    done = True
                    break
                # close-based mechanics: a close beyond the level on bar j
                beyond = side * (c[j] - lvl)
                if beyond > rule.dist * w:
                    broke[side] = True
                if not broke[side]:
                    continue
                t_ok = trend is None or (side * (c[j] - trend[j]) > 0)
                m_ok = mom_up[j] if side == 1 else mom_dn[j]
                v_ok = (not rule.vol) or (np.isfinite(fx.volbase) and v[j] >= rule.vol * fx.volbase)
                if rule.entry == "close":
                    if beyond > rule.dist * w and t_ok and m_ok and v_ok:
                        out.append(dict(day=day, fill=f, px=o[f], side=side, sig=j, lvl=lvl, w=w))
                        done = True
                        break
                elif rule.entry == "limit":
                    # after a qualifying break bar, rest a limit at the level; fills on the first
                    # later bar (up to the last fill bar) that trades THROUGH it by a point
                    if not (beyond > rule.dist * w and t_ok and m_ok and v_ok):
                        continue
                    for m2, k2 in bars[bi + 1:]:
                        if m2 > WIN_END:
                            break
                        through = (l[k2] <= lvl - 1.0) if side == 1 else (h[k2] >= lvl + 1.0)
                        if through:
                            out.append(dict(day=day, fill=k2, px=lvl, side=side, sig=j, lvl=lvl, w=w))
                            done = True
                            break
                    if done:
                        break
                elif rule.entry == "fade":
                    # a close back INSIDE the range after a break: trade against the break at the
                    # next open. Momentum, trend, volume and distance are read on the failure bar
                    # in the FADE direction.
                    inside = side * (c[j] - lvl) < 0
                    if not inside:
                        continue
                    fs = -side
                    t_ok = trend is None or (fs * (c[j] - trend[j]) > 0)
                    m_ok = mom_up[j] if fs == 1 else mom_dn[j]
                    if t_ok and m_ok and v_ok:
                        out.append(dict(day=day, fill=f, px=o[f], side=fs, sig=j, lvl=lvl, w=w))
                        done = True
                        break
            if done:
                break
    df = pd.DataFrame(out)
    _SIG[key] = df
    return df


# ------------------------------------------------------------------------------------------------
# outcomes for arbitrary fills: bar index, entry price, per-trade stop and target
# ------------------------------------------------------------------------------------------------
K2 = 30


def outcomes2(d, fill, px, side, sl, tp, flat, be=0.0):
    K = K2
    n = d["n"]
    fill = np.asarray(fill, np.int64)
    idx = np.minimum(fill[:, None] + np.arange(K)[None, :], n - 1)
    H, L, C = d["h"][idx], d["l"][idx], d["c"][idx]
    valid = (d["day"][idx] == d["day"][fill][:, None]) & (d["mod"][idx] < flat)
    valid[:, 0] = True
    last = valid.shape[1] - 1 - np.argmax(valid[:, ::-1], axis=1)
    s = side[:, None]
    fav = s * (np.where(s > 0, H, L) - px[:, None])        # best excursion per bar
    adv = s * (px[:, None] - np.where(s > 0, L, H))        # worst excursion per bar
    tp_hit = (fav >= tp[:, None]) & valid
    sl_hit = (adv >= sl[:, None]) & valid
    ft = np.where(tp_hit.any(1), tp_hit.argmax(1), K + 1)
    fs = np.where(sl_hit.any(1), sl_hit.argmax(1), K + 1)
    if be:
        be_hit = (fav >= be * tp[:, None]) & valid
        tb = np.where(be_hit.any(1), be_hit.argmax(1), K + 1)
        # after the break-even bar the stop sits at the entry; a touch on a LATER bar exits at 0
        later = np.arange(K)[None, :] > tb[:, None]
        be_stop = (adv >= 0) & valid & later
        fb = np.where(be_stop.any(1), be_stop.argmax(1), K + 1)
    else:
        tb = np.full(len(fill), K + 1)
        fb = np.full(len(fill), K + 1)
    rows = np.arange(len(fill))
    gross = s[:, 0] * (C[rows, last] - px)
    reason = np.full(len(fill), 2, np.int8)
    xb = last.copy()
    # ordering: the original stop only counts before the break-even bar; ties book the stop
    sl_eff = np.where(fs <= tb, fs, K + 1)
    cand = np.stack([ft, sl_eff, fb], axis=1)
    first = cand.min(1)
    has = first <= K
    is_sl = has & (sl_eff == first)
    is_be = has & ~is_sl & (fb == first)
    is_tp = has & ~is_sl & ~is_be & (ft == first)
    reason[is_tp] = 0; gross[is_tp] = tp[is_tp]; xb[is_tp] = ft[is_tp]
    reason[is_sl] = 1; gross[is_sl] = -sl[is_sl]; xb[is_sl] = fs[is_sl]
    reason[is_be] = 3; gross[is_be] = 0.0; xb[is_be] = fb[is_be]
    net = gross - COST_PTS - STOP_SLIP * (reason == 1)
    amb = has & (ft == fs)
    return dict(gross=gross, net=net, reason=reason, held=xb, amb=amb)


def geometry_arrays(sig, g: Geom2):
    if g.kind == "pts":
        return np.full(len(sig), g.sl, float), np.full(len(sig), g.tp, float)
    w = sig.w.to_numpy(float)
    # stop distance measured from the FILL: the level's far side or midpoint, plus how far the
    # fill sits beyond the level
    beyond = (sig.side * (sig.px - sig.lvl)).to_numpy(float)
    sl = g.sl * w + beyond
    tp = g.tp * w - beyond
    return sl, tp


def trades2(d, F, rule: Rule2, g: Geom2):
    sig = signals2(d, F, rule)
    if len(sig) == 0:
        return pd.DataFrame()
    sl, tp = geometry_arrays(sig, g)
    if g.kind == "range":
        # a range-anchored trade with no room (the fill already sits near the target, or the stop
        # would be a few points) is not taken; a fade that closed back deep inside the range is
        # the usual case
        room = (sl >= 25.0) & (tp >= 25.0)
        sig = sig[room].reset_index(drop=True)
        sl, tp = sl[room], tp[room]
        if len(sig) == 0:
            return pd.DataFrame()
    o = outcomes2(d, sig.fill.to_numpy(), sig.px.to_numpy(float), sig.side.to_numpy(), sl, tp, g.flat, g.be)
    cut = split_days(d)
    df = sig.copy()
    for k in ("gross", "net", "reason", "held", "amb"):
        df[k] = o[k]
    df["sl"], df["tp"] = sl, tp
    df["mod"] = d["mod"][df.fill.to_numpy()]
    df["block"] = np.where(df.day < cut, "research", "locked")
    df["date"] = d["dates"][df.day.to_numpy()]
    return df


_POOL = {}


def _pool(d, block, mod):
    key = (id(d), block, mod)
    if key not in _POOL:
        cut = split_days(d)
        days = sessions(d, RANGE_START)
        pool_days = days[days < cut] if block == "research" else days[days >= cut]
        _POOL[key] = np.array([d["pos"][(dd, mod)] for dd in pool_days if (dd, mod) in d["pos"]])
    return _POOL[key]


_TENS = {}


def _tensor2(d, g: Geom2):
    """Every pool bar (09:30..10:30 on every eligible session), both sides, one fixed-point geometry."""
    key = (id(d), g)
    if key not in _TENS:
        fills = np.concatenate([_pool(d, b, m) for b in ("research", "locked") for m in range(570, 645, 15)])
        fills = np.unique(fills)
        nets = []
        for side in (1, -1):
            o = outcomes2(d, fills, d["o"][fills], np.full(len(fills), side), np.full(len(fills), g.sl),
                          np.full(len(fills), g.tp), g.flat, g.be)
            nets.append(o["net"])
        _TENS[key] = dict(where={int(f): i for i, f in enumerate(fills)}, net=np.stack(nets, axis=1))
    return _TENS[key]


def control2(d, df, g: Geom2, draws=400, seed=7, block="research"):
    """Random sessions in the same block, same side, same fill minute, the trade's OWN stop and
    target, entry at that bar's open. Returns the observed vs control net, z and p."""
    sub = df[df.block == block]
    if len(sub) < 10:
        return None
    rng = np.random.default_rng(seed)
    fills = np.empty((len(sub), draws), np.int64)
    mods = sub["mod"].to_numpy()
    for m in np.unique(mods):
        rows = np.where(mods == m)[0]
        cand = _pool(d, block, int(m))
        fills[rows] = cand[rng.integers(0, len(cand), size=(len(rows), draws))]
    side = np.repeat(sub.side.to_numpy(), draws)
    if g.kind == "pts":
        T = _tensor2(d, g)
        rows = np.vectorize(T["where"].__getitem__)(fills.ravel())
        net = T["net"][rows, (side == -1).astype(int)].reshape(len(sub), draws)
    else:
        sl = np.repeat(sub.sl.to_numpy(float), draws)
        tp = np.repeat(sub.tp.to_numpy(float), draws)
        f = fills.ravel()
        o = outcomes2(d, f, d["o"][f], side, sl, tp, g.flat, g.be)
        net = o["net"].reshape(len(sub), draws)
    nets = net.sum(0)
    wins = 100 * (net > 0).mean(0)
    on, ow = sub.net.sum(), 100 * (sub.net > 0).mean()
    sd = nets.std()
    return dict(n=len(sub), net=on, win=ow, c_net=nets.mean(), c_sd=sd, c_win=wins.mean(),
                p_net=((nets >= on).sum() + 1) / (draws + 1), p_win=((wins >= ow).sum() + 1) / (draws + 1),
                z=(on - nets.mean()) / sd if sd > 0 else 0.0)


def mechanic_baseline(d, F, rule: Rule2, g: Geom2, block="research"):
    """The same entry mechanic with every filter off, both sides, every session."""
    bare = Rule2(entry=rule.entry, mom="none", trend=0, buffer=rule.buffer)
    df = trades2(d, F, bare, g)
    sub = df[df.block == block] if len(df) else df
    return dict(n=len(sub), per=sub.net.mean() if len(sub) else np.nan,
                win=100 * (sub.net > 0).mean() if len(sub) else np.nan)


# ------------------------------------------------------------------------------------------------
# the search
# ------------------------------------------------------------------------------------------------
GRID2 = dict(entry=["close", "stop", "limit", "fade"], mom=["13/48", "8/34", "x13/48", "none"],
             trend=[200, 0], dist=[0.0, 0.25], vol=[0.0, 1.5], width=["any", "tight", "wide"],
             gap=["any", "with", "against"])
GEOMS2 = [Geom2("pts", 100, 100), Geom2("pts", 75, 75), Geom2("pts", 50, 100), Geom2("pts", 100, 200),
          Geom2("pts", 100, 100, flat=720), Geom2("pts", 100, 100, be=0.5),
          Geom2("range", 0.5, 1.0), Geom2("range", 1.0, 1.0), Geom2("range", 0.5, 2.0),
          Geom2("range", 1.0, 2.0), Geom2("range", 0.5, 1.0, be=0.5)]


def sweep2(d, F, draws=300, seed=11, min_n=60):
    rules = [Rule2(**dict(zip(GRID2, v))) for v in itertools.product(*GRID2.values())]
    rows = []
    for i, r in enumerate(rules):
        sig = signals2(d, F, r)
        if len(sig) == 0:
            continue
        for g in GEOMS2:
            df = trades2(d, F, r, g)
            if len(df) == 0:
                continue
            res = df[df.block == "research"]
            if len(res) < min_n:
                continue
            m = metrics(res)
            c = control2(d, df, g, draws=draws, seed=seed)
            rows.append(dict(**asdict(r), geom=g.label(), n=m["n"], win=m["win"], net=m["net"], per=m["per"],
                             pf=m["pf"], sharpe=m["sharpe"], longs=m["longs"], shorts=m["shorts"],
                             z=c["z"], p=c["p_net"], c_net=c["c_net"], amb=m["amb"]))
        if i % 100 == 0:
            print(f"    ... {i}/{len(rules)} rules, {len(rows)} cells", flush=True)
    out = pd.DataFrame(rows).sort_values("z", ascending=False).reset_index(drop=True)
    print(f"\n  sweep: {len(rules)} rules x {len(GEOMS2)} geometries = {len(rules) * len(GEOMS2):,} cells, "
          f"{len(out):,} with >= {min_n} research trades")
    return out


AXES = list(GRID2)


def stability2(out, row):
    nb = []
    for a in AXES:
        vals = GRID2[a]
        i = vals.index(row[a])
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                mm = out.geom == row.geom
                for b in AXES:
                    mm &= out[b] == (vals[j] if b == a else row[b])
                nb.append(out[mm])
    nb = pd.concat(nb) if nb else pd.DataFrame()
    if len(nb) == 0 or row.z <= 0:
        return np.nan, 0
    return float(nb.z.median() / row.z), len(nb)


def rule_of(row):
    return Rule2(entry=row.entry, mom=row.mom, trend=int(row.trend), dist=float(row.dist), vol=float(row.vol),
                 width=row.width, gap=row.gap, buffer=float(row.buffer))


def geom_of(label):
    return next(g for g in GEOMS2 if g.label() == label)


def describe2(d, F, df, rule, g, block, draws=2000):
    sub = df[df.block == block]
    print(f"\n  {rule.label()} | {g.label()}  [{block}]")
    print("     " + fmt(metrics(sub)))
    for s, nm in ((1, "long"), (-1, "short")):
        ss = sub[sub.side == s]
        if len(ss):
            print(f"     {nm:<6}" + fmt(metrics(ss)))
    for r, nm in ((0, "target"), (1, "stop"), (2, "flat"), (3, "break-even")):
        ss = sub[sub.reason == r]
        if len(ss):
            print(f"     exit={nm:<11} n {len(ss):>4}  net {ss.net.sum():>8,.0f} pt  mean {ss.net.mean():6.1f}")
    c = control2(d, df, g, draws=draws, block=block)
    print("     control  " + U.fmt_ctrl(c))
    b = mechanic_baseline(d, F, rule, g, block)
    print(f"     mechanic alone, no filters, {block}: n {b['n']}  {b['per']:.1f} pt/trade  win {b['win']:.1f}%")
    return c


def main(seed=11, out_csv=None, draws=300):
    d = load()
    F = session_facts(d)
    cut = split_days(d)
    days = sessions(d, RANGE_START)
    print(f"US30 15m  sessions {len(days)}  research {int((days < cut).sum())} / locked {int((days >= cut).sum())}")
    print(f"range width median {F.width.median():.0f} pt, range/ATR median {(F.width / F.atr).median():.2f}; "
          f"tight (<=1.5 ATR) {100 * ((F.width / F.atr) <= 1.5).mean():.0f}% of sessions, wide (>=2) "
          f"{100 * ((F.width / F.atr) >= 2).mean():.0f}%")

    print("\n== 1. MECHANICS ALONE, no filters, both sides, research: is any entry mechanic paying on its own? ==")
    for e in GRID2["entry"]:
        for g in (Geom2("pts", 100, 100), Geom2("range", 0.5, 1.0)):
            r = Rule2(entry=e, mom="none", trend=0)
            df = trades2(d, F, r, g)
            res = df[df.block == "research"]
            c = control2(d, df, g, draws=1000)
            print(f"  {e:<6} {g.label():<32} " + fmt(metrics(res)))
            print(f"         control: " + U.fmt_ctrl(c))

    print("\n== 2. THE SWEEP, research only ==")
    out = sweep2(d, F, draws=draws, seed=seed)
    if out_csv:
        out.to_csv(out_csv, index=False)
    cols = ["entry", "mom", "trend", "dist", "vol", "width", "gap", "geom", "n", "win", "per", "longs", "shorts", "z", "p"]
    print("  top 20 by control z:")
    print(out[cols].head(20).to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
    print(f"\n  z over all cells: median {out.z.median():.2f}, 90th {out.z.quantile(.9):.2f}, "
          f"share z>2: {100 * (out.z > 2).mean():.1f}% ({int((out.z > 2).sum())} cells; 2.3% = {0.023 * len(out):.0f} expected by chance)")
    print("  median z by axis value:")
    for a in AXES + ["geom"]:
        g = out.groupby(a).z.median().round(2)
        print(f"     {a:<7}" + "  ".join(f"{k}: {v}" for k, v in g.items()))

    # gates
    out["minority"] = np.minimum(out.longs, out.shorts) / out.n
    stab = [stability2(out, r) for _, r in out.head(300).iterrows()]
    out["stab"] = np.nan
    out.loc[:299, "stab"] = [s for s, _ in stab]
    out["nb"] = 0
    out.loc[:299, "nb"] = [k for _, k in stab]
    cand = out[(out.z >= 2.0) & (out.minority >= 0.25) & (out.stab >= 0.7)].copy()
    print(f"\n  gates: z>=2 -> {int((out.z >= 2).sum())}; + both sides (minority >= 25%) -> "
          f"{int(((out.z >= 2) & (out.minority >= 0.25)).sum())}; + plateau (stability >= 0.7) -> {len(cand)}")
    # mechanic baseline gate
    keep = []
    for i, r in cand.iterrows():
        rule, g = rule_of(r), geom_of(r.geom)
        b = mechanic_baseline(d, F, rule, g)
        keep.append(r.per > b["per"] + 5.0)      # must beat the bare mechanic by 5 pt/trade
        cand.loc[i, "mech_per"] = b["per"]
    cand = cand[np.array(keep, bool)] if len(cand) else cand
    print(f"  + beats the bare mechanic by 5 pt/trade -> {len(cand)}")
    if len(cand):
        print(cand[cols + ["stab", "mech_per"]].head(15).to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

    # the deflated Sharpe hurdle across BOTH passes
    n_trials = 13425 + len(out)
    trial_sr = []
    samp = out.sample(min(300, len(out)), random_state=1)
    for _, r in samp.iterrows():
        x = trades2(d, F, rule_of(r), geom_of(r.geom))
        x = x[x.block == "research"].net
        trial_sr.append(x.mean() / x.std() if x.std() > 0 else 0)

    picks = []
    if len(cand):
        # one per entry mechanic, best z, so the locked read is at most four cells
        for e, grp in cand.groupby("entry"):
            picks.append(grp.sort_values("z", ascending=False).iloc[0])
    else:
        print("\n  NOTHING PASSED THE RESEARCH GATES. The best plateau cells are shown on research only; "
              "the locked block is read for the single best plateau cell so the shape is on record.")
        top = out.head(300)
        top = top[(top.minority >= 0.25) & (top.stab >= 0.7)]
        if len(top):
            picks.append(top.iloc[0])

    print("\n== 3. THE CANDIDATES on research ==")
    for r in picks:
        rule, g = rule_of(r), geom_of(r.geom)
        df = trades2(d, F, rule, g)
        describe2(d, F, df, rule, g, "research")
        res = df[df.block == "research"]
        # DSR with N = every cell ever tried on this file
        sr = res.net.mean() / res.net.std()
        em = 0.5772156649
        from scipy.stats import norm
        v = np.var(trial_sr)
        sr0 = math.sqrt(v) * ((1 - em) * norm.ppf(1 - 1 / n_trials) + em * norm.ppf(1 - 1 / (n_trials * math.e)))
        g3 = ((res.net - res.net.mean()) ** 3).mean() / res.net.std() ** 3
        g4 = ((res.net - res.net.mean()) ** 4).mean() / res.net.std() ** 4
        dsr = norm.cdf((sr - sr0) * math.sqrt(len(res) - 1) / math.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr * sr, 1e-9)))
        bs = bootstrap_ci(res)
        mc = mc_drawdown(res)
        print(f"     deflated Sharpe {dsr:.3f} (per-trade SR {sr:.3f}, hurdle {sr0:.3f}, N {n_trials:,} trials over both passes)")
        print(f"     bootstrap 95% CI Sharpe [{bs['sharpe_lo']:.2f}, {bs['sharpe_hi']:.2f}]  net [{bs['net_lo']:,.0f}, {bs['net_hi']:,.0f}]  P(net<=0) {bs['p_neg']:.3f}")
        print(f"     Monte Carlo drawdown: observed {mc['dd_obs']:,.0f}, median {mc['dd_med']:,.0f}, 95th {mc['dd95']:,.0f}")
        sp = subperiods(df)
        rs = sp.loc["research"]
        print(f"     quarters profitable (research): {int((rs['sum'] > 0).sum())} of {len(rs)}  "
              + "  ".join(f"{q}: {v:,.0f}" for q, v in rs["sum"].items()))
        # cost sweep: outcomes2 reads this module's COST_PTS
        line = "     cost sweep (research):"
        for cst in (0, 3, 6, 10):
            globals()["COST_PTS"] = float(cst)
            x = trades2(d, F, rule, g)
            x = x[x.block == "research"]
            line += f"  {cst}pt: {x.net.mean():5.1f}/trade"
        globals()["COST_PTS"] = 3.0
        print(line)

    print("\n== 4. LOCKED BLOCK, read once ==")
    for r in picks:
        rule, g = rule_of(r), geom_of(r.geom)
        df = trades2(d, F, rule, g)
        print(f"\n  ===== chosen from {n_trials:,} cells over two passes; research z {r.z:.2f}, stability {r.stab:.2f} =====")
        describe2(d, F, df, rule, g, "locked")
        rm, lm = metrics(df[df.block == "research"]), metrics(df[df.block == "locked"])
        if lm.get("n", 0):
            if lm["per"] > rm["per"]:
                print("     SHAPE WARNING: better on locked than research -- a defect, not a result.")
            else:
                print(f"     shape: research {rm['per']:.1f} -> locked {lm['per']:.1f} pt/trade")
        sp = subperiods(df)
        if "locked" in sp.index.get_level_values(0):
            ls = sp.loc["locked"]
            print(f"     quarters profitable (locked): {int((ls['sum'] > 0).sum())} of {len(ls)}  "
                  + "  ".join(f"{q}: {v:,.0f}" for q, v in ls["sum"].items()))
    return d, F, out, picks


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--draws", type=int, default=300)
    ap.add_argument("--sweep-csv", default=None)
    a = ap.parse_args()
    main(seed=a.seed, out_csv=a.sweep_csv, draws=a.draws)
