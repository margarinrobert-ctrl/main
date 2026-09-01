"""The Strat combo engine (Gleidson, MQL5 v3.10) on US30, US100 and NQ bars.

THE RULES AS SHIPPED. Bars are typed against the previous bar: 1 inside, 2U, 2D, 3 outside.
On every new bar the last three CLOSED bars (shifts 1..3) are scanned for four reversal combos,
each adding a weight to an up or down score: 3-2 (2), 1-3-2 (3), 2-1-2 (1), 3-1-2 (2), with a
colour rule on any type-3 bar (it must have closed AGAINST the direction of the trade) and a
+1 hammer / shooter bonus on the trigger bar when it agrees. Net score |up - down| >= 2 sets
the direction. A LOCATION score then has to reach 2 from four filters on the trigger bar's
extreme: swing fractal within 50 pts (weight 2), PMG cluster of >= 2 local extremes inside an
80-pt zone (2), a broken-then-reclaimed level within 50 pts (1), an HTF level within 50 pts --
prior day high/low, prior week high/low, overnight range, NY 08:00 open (1). Then a STOP order
20 pts beyond the trigger bar's extreme, stop-loss 20 pts beyond the other extreme, take-profit
2R, sized at 1% of balance, one trade at a time. The pending order is cancelled at the next new
bar (its setup bar is stale by then), so it LIVES FOR ONE BAR.

"POINTS" ARE BROKER POINTS. On the one-decimal index quotes these feeds carry, a point is 0.1,
so 20 pts is 2.0 index points and a 50-pt tolerance is 5.0 index points; NQ futures tick at
0.25. Both are inputs here (`point`) and the tolerance scale is swept, because a 2-decimal
broker would make every tolerance ten times tighter and the strategy is mostly its tolerances.

FILLS. A stop entry fills at the order price, or at the open if the bar opens through it (the
EA lifts the price to the market in that case). Stop and target are resolved on the bars that
decide them: a bar touching both is a STOP, and the share of such bars is reported. Costs are
the branch's retail CFD assumptions in index points (`scalp.core.COSTS`), a stop fill paying
the stop premium and a target fill paying half a spread.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from ibs import ibs_core as IC  # noqa: E402
from scalp.core import COSTS  # noqa: E402

MARKETS = ("US30", "US100", "NQ")
POINT = {"US30": 0.1, "US100": 0.1, "NQ": 0.25}

DEFAULTS = dict(w32=2, w132=3, w212=1, w312=2, w_hs=1, min_combo=2, wick=0.75,
                use_fractal=True, fractal_k=1, fractal_lb=200, fractal_tol=50.0, w_fractal=2,
                use_pmg=True, pmg_lb=150, pmg_zone=80.0, pmg_touches=2, w_pmg=2,
                use_reclaim=True, reclaim_lb=60, reclaim_tol=50.0, w_reclaim=1,
                use_htf=True, htf_tol=50.0, w_htf=1, min_loc=2,
                entry_buf=20.0, sl_buf=20.0, rr=2.0)


def bars(market, tf="15min"):
    f, native = IC.load(market)
    if tf == "native":
        return f
    r = f.resample(tf, label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    return r.dropna()


def session_idx(ny_hour):
    """The EA's own session table on a New York hour."""
    h = ny_hour
    out = np.full(len(h), 0, np.int64)      # 0 Asia
    out[h < 19] = 5                         # overnight 16-18
    out[h < 16] = 4                         # afternoon 13-15
    out[h < 13] = 3                         # lunch 12
    out[h < 12] = 2                         # NY open 08-11
    out[h < 8] = 1                          # London 00-07
    return out


def frame(b):
    """Everything the loop needs, as arrays."""
    ix = b.index
    o, h, l, c = (b[k].to_numpy() for k in ("open", "high", "low", "close"))
    hr = ix.hour.to_numpy()
    sess = session_idx(hr)
    # broker day = 00:00 server = 17:00 New York on these NY+7 feeds; broker week starts Monday
    shifted = ix + pd.Timedelta(hours=7)
    day_id = (shifted.normalize().to_numpy().astype("datetime64[D]").astype(np.int64))
    week_id = ((shifted - pd.Timedelta(days=0)).to_period("W-SUN").start_time
               .to_numpy().astype("datetime64[D]").astype(np.int64))
    mod = (ix.hour * 60 + ix.minute).to_numpy().astype(np.int64)
    return dict(o=o, h=h, l=l, c=c, sess=sess, day=day_id, week=week_id, mod=mod, n=len(b),
                dates=ix)


@njit(cache=True)
def _prev_period_hl(h, l, pid):
    """High/low of the PREVIOUS completed period (day or week) for every bar, looking only at
    bars that closed before the current bar."""
    n = len(h)
    ph = np.full(n, np.nan); pl = np.full(n, np.nan)
    cur_id = pid[0]; cur_h = h[0]; cur_l = l[0]
    last_h = np.nan; last_l = np.nan
    for i in range(n):
        if pid[i] != cur_id:
            last_h = cur_h; last_l = cur_l
            cur_id = pid[i]; cur_h = h[i]; cur_l = l[i]
        else:
            if i > 0:
                cur_h = max(cur_h, h[i]); cur_l = min(cur_l, l[i])
        ph[i] = last_h; pl[i] = last_l
    return ph, pl


@njit(cache=True)
def _bar_types(h, l):
    n = len(h)
    t = np.zeros(n, np.int64)          # 1 inside, 2 up, 3 down, 4 outside
    for i in range(1, n):
        hh = h[i] > h[i - 1]; ll = l[i] < l[i - 1]
        if not hh and not ll:
            t[i] = 1
        elif hh and ll:
            t[i] = 4
        elif hh:
            t[i] = 2
        else:
            t[i] = 3
    return t


@njit(cache=True)
def _combo_scores(o, h, l, c, typ, w32, w132, w212, w312, w_hs, wick):
    """Up and down score with shift 1 = bar i, shift 2 = i-1, shift 3 = i-2."""
    n = len(o)
    up = np.zeros(n, np.int64); dn = np.zeros(n, np.int64)
    for i in range(3, n):
        t1 = typ[i]; t2 = typ[i - 1]; t3 = typ[i - 2]
        b2 = c[i - 1] >= o[i - 1]; b3 = c[i - 2] >= o[i - 2]
        u = 0; d = 0
        if t2 == 4 and t1 == 2 and not b2:
            u += w32
        if t2 == 4 and t1 == 3 and b2:
            d += w32
        if t3 == 1 and t2 == 4 and t1 == 2 and not b2:
            u += w132
        if t3 == 1 and t2 == 4 and t1 == 3 and b2:
            d += w132
        if t3 == 3 and t2 == 1 and t1 == 2:
            u += w212
        if t3 == 2 and t2 == 1 and t1 == 3:
            d += w212
        if t3 == 4 and t2 == 1 and t1 == 2 and not b3:
            u += w312
        if t3 == 4 and t2 == 1 and t1 == 3 and b3:
            d += w312
        # hammer / shooter on the trigger bar, bonus only when reinforcing
        rng = h[i] - l[i]
        if t1 != 1 and rng > 0:
            hb = l[i] + rng * wick
            st = h[i] - rng * wick
            if o[i] > hb and c[i] > hb and u > 0:
                u += w_hs
            if o[i] < st and c[i] < st and d > 0:
                d += w_hs
        up[i] = u; dn[i] = d
    return up, dn


@njit(cache=True)
def _near_fractal(h, l, i, want_high, ref, k, lb, tol):
    # shifts s = k+1 .. lb-1 relative to the NEW bar (shift 0 = i+1), so bar index i+1-s
    for s in range(k + 1, lb):
        j = i + 1 - s
        if j - k < 0:
            break
        v = h[j] if want_high else l[j]
        ok = True
        for m in range(1, k + 1):
            lv = h[j - m] if want_high else l[j - m]
            rv = h[j + m] if want_high else l[j + m]
            if want_high:
                if not (v > lv and v > rv):
                    ok = False; break
            else:
                if not (v < lv and v < rv):
                    ok = False; break
        if ok and abs(ref - v) <= tol:
            return True
    return False


@njit(cache=True)
def _pmg_touches(h, l, i, want_high, ref, lb, half):
    cnt = 0
    for s in range(2, lb):
        j = i + 1 - s
        if j - 1 < 0:
            break
        v = h[j] if want_high else l[j]
        lv = h[j - 1] if want_high else l[j - 1]
        rv = h[j + 1] if want_high else l[j + 1]
        ext = (v >= lv and v >= rv) if want_high else (v <= lv and v <= rv)
        if ext and abs(ref - v) <= half:
            cnt += 1
    return cnt


@njit(cache=True)
def _reclaim_level(h, l, c, i, want_above, lb):
    """First (nearest) bar whose high was broken then reclaimed (want_above) or whose low was
    broken then reclaimed. Returns (found, level)."""
    for s in range(3, lb):
        j = i + 1 - s
        if j < 0:
            break
        rh = h[j]; rl = l[j]
        ba = False; rb = False; bb = False; ra = False
        for jj in range(j + 1, i + 1):
            cc = c[jj]
            if cc > rh:
                ba = True
            if ba and cc <= rh:
                rb = True
            if cc < rl:
                bb = True
            if bb and cc >= rl:
                ra = True
        if want_above and rb:
            return True, rh
        if (not want_above) and ra:
            return True, rl
    return False, 0.0


@njit(cache=True)
def _overnight_range(h, l, sess, i, tf_min):
    """Most recent overnight/Asia block (NY 16:00-24:00) scanning back from the trigger bar,
    within 48 hours."""
    oh = -1e300; ol = 1e300; found = False
    max_bars = int(48 * 60 / tf_min)
    for s in range(1, min(500, max_bars)):
        j = i + 1 - s
        if j < 0:
            break
        if sess[j] == 5 or sess[j] == 0:
            if h[j] > oh:
                oh = h[j]
            if l[j] < ol:
                ol = l[j]
            found = True
        elif found:
            break
    return found, oh, ol


@njit(cache=True)
def _session_open(o, sess, i):
    for s in range(1, 300):
        j = i + 1 - s
        if j - 1 < 0:
            break
        if sess[j] == 2 and sess[j - 1] != 2:
            return True, o[j]
    return False, 0.0


@njit(cache=True)
def _location(o, h, l, c, sess, pdh, pdl, pwh, pwl, i, want_high, ref, tf_min,
              use_fr, fr_k, fr_lb, fr_tol, w_fr, use_pmg, pmg_lb, pmg_half, pmg_min, w_pmg,
              use_rc, rc_lb, rc_tol, w_rc, use_htf, htf_tol, w_htf):
    score = 0
    flags = 0
    if use_fr and _near_fractal(h, l, i, want_high, ref, fr_k, fr_lb, fr_tol):
        score += w_fr; flags |= 1
    if use_pmg and _pmg_touches(h, l, i, want_high, ref, pmg_lb, pmg_half) >= pmg_min:
        score += w_pmg; flags |= 2
    if use_rc:
        f, lvl = _reclaim_level(h, l, c, i, want_high, rc_lb)
        if f and abs(ref - lvl) <= rc_tol:
            score += w_rc; flags |= 4
    if use_htf:
        hit = False
        if pdh[i] == pdh[i] and abs(ref - pdh[i]) <= htf_tol:
            hit = True
        elif pdl[i] == pdl[i] and abs(ref - pdl[i]) <= htf_tol:
            hit = True
        elif pwh[i] == pwh[i] and abs(ref - pwh[i]) <= htf_tol:
            hit = True
        elif pwl[i] == pwl[i] and abs(ref - pwl[i]) <= htf_tol:
            hit = True
        else:
            f, oh, ol = _overnight_range(h, l, sess, i, tf_min)
            if f and (abs(ref - oh) <= htf_tol or abs(ref - ol) <= htf_tol):
                hit = True
            else:
                f2, so = _session_open(o, sess, i)
                if f2 and abs(ref - so) <= htf_tol:
                    hit = True
        if hit:
            score += w_htf; flags |= 8
    return score, flags


@njit(cache=True)
def _simulate(o, h, l, c, mod, sig, loc_ok, entry_buf, sl_buf, rr, sp_rth, sp_pre, sp_off,
              slip_stop, comm, mask):
    """sig[i] in {-1, 0, +1} is the combo direction on trigger bar i (order placed for bar
    i+1). Returns trades[n, 9]: trigger bar, fill bar, exit bar, side, entry, exit, R, reason
    (1 stop, 2 target), ambiguous (both touched on the exit bar)."""
    n = len(o)
    tr = np.zeros((n, 9))
    nt = 0
    i = 0
    while i < n - 1:
        if mask[i] == 0 or sig[i] == 0 or not loc_ok[i]:
            i += 1
            continue
        side = sig[i]
        if side > 0:
            ent = h[i] + entry_buf; sl = l[i] - sl_buf
        else:
            ent = l[i] - entry_buf; sl = h[i] + sl_buf
        risk = abs(ent - sl)
        tp = ent + side * risk * rr
        f = i + 1
        filled = False; px = 0.0
        if side > 0:
            if o[f] >= ent:
                filled = True; px = o[f]
            elif h[f] >= ent:
                filled = True; px = ent
        else:
            if o[f] <= ent:
                filled = True; px = o[f]
            elif l[f] <= ent:
                filled = True; px = ent
        if not filled:
            i += 1
            continue
        m = mod[f]
        tier = sp_rth if (m >= 570 and m < 960) else (sp_pre if (m >= 240 and m < 1080) else sp_off)
        px_in = px + side * (tier / 2.0 + slip_stop)
        # walk forward for the exit, starting on the fill bar itself
        j = f
        done = False
        while j < n and not done:
            hit_sl = (l[j] <= sl) if side > 0 else (h[j] >= sl)
            hit_tp = (h[j] >= tp) if side > 0 else (l[j] <= tp)
            if hit_sl or hit_tp:
                m2 = mod[j]
                t2 = sp_rth if (m2 >= 570 and m2 < 960) else (sp_pre if (m2 >= 240 and m2 < 1080)
                                                               else sp_off)
                if hit_sl:
                    xs = sl
                    if side > 0 and o[j] < sl and j > f:
                        xs = o[j]
                    if side < 0 and o[j] > sl and j > f:
                        xs = o[j]
                    px_out = xs - side * (t2 / 2.0 + slip_stop)
                    reason = 1.0
                else:
                    px_out = tp - side * (t2 / 2.0)
                    reason = 2.0
                pnl = side * (px_out - px_in) - comm
                tr[nt, 0] = i; tr[nt, 1] = f; tr[nt, 2] = j; tr[nt, 3] = side
                tr[nt, 4] = px_in; tr[nt, 5] = px_out; tr[nt, 6] = pnl / risk
                tr[nt, 7] = reason; tr[nt, 8] = 1.0 if (hit_sl and hit_tp) else 0.0
                nt += 1
                done = True
                i = j              # flat at bar j's close: the new-bar event can trigger on j
            else:
                j += 1
        if not done:
            break
    return tr[:nt]


class Strat:
    def __init__(self, market, tf="15min", point=None, **over):
        self.market = market
        self.tf = tf
        self.point = POINT[market] if point is None else point
        self.P = dict(DEFAULTS); self.P.update(over)
        self.b = bars(market, tf)
        self.F = frame(self.b)
        self.tf_min = int(pd.Timedelta(tf).total_seconds() // 60)
        F = self.F
        self.typ = _bar_types(F["h"], F["l"])
        self.pdh, self.pdl = _prev_period_hl(F["h"], F["l"], F["day"])
        self.pwh, self.pwl = _prev_period_hl(F["h"], F["l"], F["week"])
        self.cost = COSTS[market]
        self._loc_cache = {}

    def signals(self, P=None):
        P = self.P if P is None else P
        F = self.F
        up, dn = _combo_scores(F["o"], F["h"], F["l"], F["c"], self.typ, P["w32"], P["w132"],
                               P["w212"], P["w312"], P["w_hs"], P["wick"])
        net = up - dn
        sig = np.where(np.abs(net) >= P["min_combo"], np.sign(net), 0).astype(np.int64)
        return sig, up, dn

    def location(self, sig, P=None, scale=1.0):
        """Location score and flags on every trigger bar. `scale` multiplies every tolerance."""
        P = self.P if P is None else P
        F = self.F
        pt = self.point * scale
        n = F["n"]
        score = np.zeros(n, np.int64); flags = np.zeros(n, np.int64)
        idx = np.where(sig != 0)[0]
        for i in idx:
            want_high = sig[i] < 0
            ref = F["h"][i] if want_high else F["l"][i]
            s, fl = _location(F["o"], F["h"], F["l"], F["c"], F["sess"], self.pdh, self.pdl,
                              self.pwh, self.pwl, int(i), want_high, ref, self.tf_min,
                              P["use_fractal"], P["fractal_k"], P["fractal_lb"],
                              P["fractal_tol"] * pt, P["w_fractal"], P["use_pmg"], P["pmg_lb"],
                              P["pmg_zone"] * pt / 2.0, P["pmg_touches"], P["w_pmg"],
                              P["use_reclaim"], P["reclaim_lb"], P["reclaim_tol"] * pt,
                              P["w_reclaim"], P["use_htf"], P["htf_tol"] * pt, P["w_htf"])
            score[i] = s; flags[i] = fl
        return score, flags

    def run(self, sig, loc_ok, mask=None, P=None, cost_mult=1.0):
        P = self.P if P is None else P
        F = self.F
        c = self.cost
        if mask is None:
            mask = np.ones(F["n"], np.int64)
        tr = _simulate(F["o"], F["h"], F["l"], F["c"], F["mod"], sig, loc_ok,
                       P["entry_buf"] * self.point, P["sl_buf"] * self.point, P["rr"],
                       c.spread_rth * cost_mult, c.spread_pre * cost_mult,
                       c.spread_off * cost_mult, c.slip_stop * cost_mult,
                       getattr(c, "commission", 0.0) * cost_mult, mask.astype(np.int64))
        t = pd.DataFrame(tr, columns=["trig", "fill", "ex", "side", "px_in", "px_out", "r",
                                      "reason", "amb"])
        for k in ("trig", "fill", "ex", "side", "reason", "amb"):
            t[k] = t[k].astype(int)
        t["pts"] = t["side"] * (t["px_out"] - t["px_in"])
        t["risk"] = t["pts"] / t["r"].replace(0, np.nan)
        return t


def metrics(t, n_days=None):
    if len(t) == 0:
        return dict(n=0, R=np.nan, pf=np.nan, win=np.nan, dd=np.nan, pts=np.nan, amb=np.nan,
                    tp_share=np.nan)
    r = t.r.to_numpy()
    g = r[r > 0].sum(); l = -r[r <= 0].sum()
    eq = np.cumsum(r)
    return dict(n=int(len(t)), R=float(r.mean()), pf=float(g / l) if l else np.inf,
                win=float((r > 0).mean()), dd=float(np.max(np.maximum.accumulate(eq) - eq)),
                pts=float(t.pts.mean()), amb=float(t.amb.mean()),
                tp_share=float((t.reason == 2).mean()),
                fillbar=float((t.ex == t.fill).mean()), hold=float((t.ex - t.fill).median()))


def control(S, sig, loc_ok, mask, n_draws=300, seed=0):
    """Random trigger bars with the same long / short counts of TRADES TAKEN, same one-bar stop
    order, same buffers, stop and 2R target, same lock. The location filter is dropped for the
    control (a random bar has no location), so the comparison is 'this trigger at this
    location' against 'any bar'. Returns the draws' mean R and mean trade count."""
    rng = np.random.default_rng(seed)
    t = S.run(sig, loc_ok, mask)
    n_long = int((t.side > 0).sum()); n_short = int((t.side < 0).sum())
    n = S.F["n"]
    pool = np.where(mask == 1)[0]
    pool = pool[pool > 300]
    ones = np.ones(n, dtype=bool)
    K_l, K_s = n_long, n_short
    for _ in range(5):
        cl = []; cs = []
        for _d in range(6):
            s2 = np.zeros(n, np.int64)
            s2[rng.choice(pool, min(K_l, len(pool)), replace=False)] = 1
            s2[rng.choice(pool, min(K_s, len(pool)), replace=False)] = -1
            td = S.run(s2, ones, mask)
            cl.append((td.side > 0).sum()); cs.append((td.side < 0).sum())
        K_l = int(round(K_l * n_long / max(np.mean(cl), 1))) if n_long else 0
        K_s = int(round(K_s * n_short / max(np.mean(cs), 1))) if n_short else 0
    out = np.empty(n_draws); cnt = np.empty(n_draws)
    for d in range(n_draws):
        s2 = np.zeros(n, np.int64)
        s2[rng.choice(pool, min(K_l, len(pool)), replace=False)] = 1
        s2[rng.choice(pool, min(K_s, len(pool)), replace=False)] = -1
        td = S.run(s2, ones, mask)
        out[d] = td.r.mean() if len(td) else 0.0
        cnt[d] = len(td)
    return out, float(cnt.mean()), t
