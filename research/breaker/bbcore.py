"""ICT breaker block on NQ 1-minute -- the spec, expressed as code.

THE SPEC AS FROZEN (nothing here was chosen after seeing a result):
    instrument   NQ 1-minute, data/NQ_1m.csv, 1,048,575 bars
    sample       2022-12-26 23:01 UTC .. 2025-12-12 01:52 UTC  (New York internally)
    M = 2.0      impulse size in ATR(20)
    K = 5        bars the impulse may take
    N = 20       swing lookback for the sweep
    sides        both
    exits        TWO declared primaries: (A) fixed 2R, (B) no target
    buffer       0.25 x ATR(20) read at the order block

THE FOUR STEPS, AND THE ONE THING DERIVED RATHER THAN GIVEN.

  The spec numbers the steps 1-4, so they are required IN THAT ORDER: ob < sweep <= violation <
  entry. The direction of the impulse is NOT stated and is DERIVED, not invented -- it is forced by
  steps 2 and 3 being mutually consistent. A bullish trade sweeps a swing LOW and then closes a body
  ABOVE the block, so the block must be one that was resistance on the way down: the last UP candle
  before a DOWN impulse (a bearish order block). Mirrored for shorts. Any other pairing makes step 3
  unreachable from step 2.

  1. IMPULSE       close[j] - close[j-K] <= -M * atr20[j-K]           (bullish setup: DOWN impulse)
                   the ATR is read at the bar the impulse STARTS from, so the displacement cannot
                   inflate its own denominator.
  2. ORDER BLOCK   the last opposing candle at or before j-K: for a down impulse, the last bar with
                   close > open. Zone = [low, high] of THAT bar -- the spec says "beyond the OB
                   RANGE", so the range is the candle's full high-low, not its body.
                   Searched back at most OB_SCAN bars; the binding rate is REPORTED, not assumed.
  3. SWEEP         s > i with low[s] < min(low[s-N .. s-1])           (bullish: takes out the low)
  4. VIOLATION     v >= s with min(open[v], close[v]) > high[i]
                   "full candle body close beyond the OB range. Wicks don't count." -- so the whole
                   BODY must clear the zone, which is the strict reading.
  5. ENTRY         first t > v with low[t] <= mid, mid = (high[i] + low[i]) / 2
                   Detection on the COMPLETED bar t; the fill is at open[t+1]. Never same-bar.
  6. STOP          low[i] - buffer * atr20[i]      (far edge of the zone plus the buffer)
     TARGET        entry + 2R  (primary A)  |  none (primary B)

TWO PARAMETERS THE SPEC DOES NOT PIN DOWN AND THIS MODULE DOES NOT CHOOSE:
    EXPIRY    how many bars a violated zone stays live before it is abandoned
    HOLD_CAP  the bar cap for primary B, which has no target
Both are arguments with no default that is treated as "the answer"; `event_scan` exists to measure
what each value costs in event count BEFORE either is fixed.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATH = os.path.join(ROOT, "data/NQ_1m.csv")

M_IMP = 2.0
K_IMP = 5
N_SWING = 20
BUF_ATR = 0.25
OB_SCAN = 50          # generous computational bound on the backward search; binding rate reported

# MNQ, this branch's cost model (STUDY_COSTS): broker commission + CME exchange fee + the NFA line,
# plus slippage. 1.72 index points all-in per round turn. Charged from the first run, never added
# later, and swept 0x / 1x / 2x / 4x so the breakeven is a measured number and not an assumption.
RT_POINTS = 1.72
POINT_VALUE = 2.0     # MNQ $/point


def load():
    """New York time. NQ_1m is stamped in UTC and every other feed on this branch is already NY --
    a loader that forgets the conversion puts a 09:30 window at 04:30 (CLAUDE.md)."""
    d = pd.read_csv(PATH)
    ix = pd.DatetimeIndex(pd.to_datetime(d["timestamp"], utc=True)) \
        .tz_convert("America/New_York").tz_localize(None)
    f = pd.DataFrame({"open": d["open"].to_numpy(float), "high": d["high"].to_numpy(float),
                      "low": d["low"].to_numpy(float), "close": d["close"].to_numpy(float),
                      "volume": d["volume"].to_numpy(float)}, index=ix).sort_index()
    return f[~f.index.duplicated(keep="first")]


def atr(f, n=20):
    """ema(TR, n) -- this branch's convention, not Wilder's. Causal: bar i's value uses bars <= i."""
    h, lo, c = f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy()
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - lo, np.maximum(np.abs(h - pc), np.abs(lo - pc)))
    return pd.Series(tr).ewm(span=n, adjust=False).mean().to_numpy()


@njit(cache=True)
def _detect(o, h, l, c, a, m, k, n, ob_scan, expiry, side):
    """Emit one row per completed setup. side=+1 bullish (down impulse, sweep low, close above).

    Returns (ob, imp_end, sweep, viol, trig, zlo, zhi, ob_capped) -- trig is the COMPLETED bar on
    which price traded to the midpoint; the caller fills at trig+1.
    """
    nb = len(c)
    out_ob = np.full(nb, -1, np.int64)
    out_imp = np.full(nb, -1, np.int64)
    out_sw = np.full(nb, -1, np.int64)
    out_vi = np.full(nb, -1, np.int64)
    out_tr = np.full(nb, -1, np.int64)
    out_zl = np.zeros(nb, np.float64)
    out_zh = np.zeros(nb, np.float64)
    out_cap = np.zeros(nb, np.int64)
    cnt = 0

    for j in range(k + ob_scan + n + 2, nb):
        # ---- step 1: impulse of >= m * ATR(20) within k bars, ATR read BEFORE the leg
        st = j - k
        if a[st] <= 0:
            continue
        disp = c[j] - c[st]
        if side > 0:
            if disp > -m * a[st]:
                continue
        else:
            if disp < m * a[st]:
                continue

        # ---- step 2: last OPPOSING candle at or before the impulse start
        ob = -1
        capped = 1
        for q in range(st, max(st - ob_scan, 0) - 1, -1):
            if side > 0:
                if c[q] > o[q]:          # down impulse -> last UP candle
                    ob = q
                    capped = 0
                    break
            else:
                if c[q] < o[q]:          # up impulse -> last DOWN candle
                    ob = q
                    capped = 0
                    break
        if ob < 0:
            out_cap[cnt if cnt < nb else nb - 1] += 0
            continue
        zlo = l[ob]
        zhi = h[ob]
        if zhi <= zlo:
            continue

        # ---- step 3: sweep of the prior n-bar swing, strictly after the order block
        sw = -1
        lim = min(j + expiry, nb)
        for s in range(ob + 1, lim):
            if s - n < 0:
                continue
            if side > 0:
                mn = l[s - n]
                for q in range(s - n + 1, s):
                    if l[q] < mn:
                        mn = l[q]
                if l[s] < mn:
                    sw = s
                    break
            else:
                mx = h[s - n]
                for q in range(s - n + 1, s):
                    if h[q] > mx:
                        mx = h[q]
                if h[s] > mx:
                    sw = s
                    break
        if sw < 0:
            continue

        # ---- step 4: full BODY close beyond the zone, at or after the sweep
        vi = -1
        lim2 = min(sw + expiry, nb)
        for v in range(sw, lim2):
            bl = o[v] if o[v] < c[v] else c[v]
            bh = o[v] if o[v] > c[v] else c[v]
            if side > 0:
                if bl > zhi:
                    vi = v
                    break
            else:
                if bh < zlo:
                    vi = v
                    break
        if vi < 0:
            continue

        # ---- step 5: first later bar trading back to the 50% midpoint
        mid = 0.5 * (zlo + zhi)
        tr = -1
        lim3 = min(vi + expiry, nb - 1)
        for t in range(vi + 1, lim3):
            if side > 0:
                if l[t] <= mid:
                    tr = t
                    break
            else:
                if h[t] >= mid:
                    tr = t
                    break
        if tr < 0:
            continue

        out_ob[cnt] = ob
        out_imp[cnt] = j
        out_sw[cnt] = sw
        out_vi[cnt] = vi
        out_tr[cnt] = tr
        out_zl[cnt] = zlo
        out_zh[cnt] = zhi
        out_cap[cnt] = capped
        cnt += 1

    return (out_ob[:cnt], out_imp[:cnt], out_sw[:cnt], out_vi[:cnt], out_tr[:cnt],
            out_zl[:cnt], out_zh[:cnt], out_cap[:cnt])


def detect(f, a, expiry, side, m=M_IMP, k=K_IMP, n=N_SWING, ob_scan=OB_SCAN):
    o = f["open"].to_numpy(); h = f["high"].to_numpy()
    l = f["low"].to_numpy(); c = f["close"].to_numpy()
    ob, imp, sw, vi, tr, zl, zh, cap = _detect(o, h, l, c, a, float(m), int(k), int(n),
                                               int(ob_scan), int(expiry), int(side))
    d = pd.DataFrame(dict(ob=ob, imp=imp, sweep=sw, viol=vi, trig=tr, zlo=zl, zhi=zh,
                          ob_capped=cap))
    d["side"] = side
    # one setup per (order block, side): the same block re-detected by a later overlapping impulse
    # is the SAME zone, and counting it twice would inflate every event count in the study
    d = d.drop_duplicates(subset=["ob", "side"], keep="first").reset_index(drop=True)
    # TOTAL order, not just by trig. Several distinct order blocks can be triggered by the SAME
    # bar, so sorting on `trig` alone leaves ties in an arbitrary order -- which made the first
    # truncation audit report 2,928 differing rows that were the same setups swapped pairwise.
    return d.sort_values(["trig", "side", "ob"], kind="mergesort").reset_index(drop=True)


EXPIRY = 240          # frozen by the user after the event scan in run_b1
HOLD_CAP = 240        # primary B: no target, time out after EXPIRY bars


@njit(cache=True)
def _walk(o, h, l, c, a, trig, side, zlo, zhi, buf_atr, ob, rr, cap, cost, lock):
    """Fill at open[trig+1]. NEVER same-bar: the trigger bar is completed before the order exists.

    The stop is a level known BEFORE the fill (the zone's far edge, fixed at the order block), so it
    is live on the fill bar itself -- the fill bar is not naked here, unlike a bracket that has to
    reference the fill price. Within one bar the STOP is taken first (pessimistic); the share of
    bars where both barriers are reachable is returned so the reader can price that choice.
    """
    n = len(c)
    m = len(trig)
    e_bar = np.full(m, -1, np.int64)
    x_bar = np.full(m, -1, np.int64)
    e_px = np.zeros(m, np.float64)
    x_px = np.zeros(m, np.float64)
    stop_px = np.zeros(m, np.float64)
    tgt_px = np.zeros(m, np.float64)
    why = np.zeros(m, np.int64)          # 0 stop, 1 target, 2 cap
    amb = np.zeros(m, np.int64)
    took = np.zeros(m, np.int64)
    last_exit = -1
    for q in range(m):
        eb = trig[q] + 1
        if eb >= n - 1:
            continue
        if lock == 1 and eb <= last_exit:
            continue
        sd = side[q]
        mid = 0.5 * (zlo[q] + zhi[q])
        bf = buf_atr * a[ob[q]]
        far = zlo[q] - bf if sd > 0 else zhi[q] + bf
        ent = o[eb]
        risk = (ent - far) if sd > 0 else (far - ent)
        if risk <= 0:
            continue
        tgt = ent + sd * rr * risk if rr > 0 else 0.0
        xb = -1
        xp = 0.0
        w = 2
        lim = eb + cap
        if lim > n - 1:
            lim = n - 1
        for t in range(eb, lim + 1):
            hit_s = (l[t] <= far) if sd > 0 else (h[t] >= far)
            hit_t = False
            if rr > 0:
                hit_t = (h[t] >= tgt) if sd > 0 else (l[t] <= tgt)
            if hit_s and hit_t:
                amb[q] = 1
            if hit_s:
                xb = t
                xp = far
                w = 0
                break
            if hit_t:
                xb = t
                xp = tgt
                w = 1
                break
        if xb < 0:
            xb = lim
            xp = c[lim]
            w = 2
        e_bar[q] = eb
        x_bar[q] = xb
        e_px[q] = ent
        x_px[q] = xp
        stop_px[q] = far
        tgt_px[q] = tgt
        why[q] = w
        took[q] = 1
        last_exit = xb
    return e_bar, x_bar, e_px, x_px, stop_px, tgt_px, why, amb, took


def walk(f, a, D, rr, cap=HOLD_CAP, cost=RT_POINTS, lock=True, buf_atr=BUF_ATR):
    """`rr` = 0 means primary B (no target). Returns one row per TAKEN trade."""
    o = f["open"].to_numpy(); h = f["high"].to_numpy()
    l = f["low"].to_numpy(); c = f["close"].to_numpy()
    D = D.sort_values(["trig", "side", "ob"], kind="mergesort").reset_index(drop=True)
    eb, xb, ep, xp, sp, tp, w, amb, took = _walk(
        o, h, l, c, a, D.trig.to_numpy(), D.side.to_numpy(), D.zlo.to_numpy(), D.zhi.to_numpy(),
        float(buf_atr), D.ob.to_numpy(), float(rr), int(cap), float(cost), 1 if lock else 0)
    k = took == 1
    t = pd.DataFrame(dict(ob=D.ob.to_numpy()[k], trig=D.trig.to_numpy()[k], e_bar=eb[k],
                          x_bar=xb[k], side=D.side.to_numpy()[k], ent=ep[k], out=xp[k],
                          stop=sp[k], tgt=tp[k], why=w[k], amb=amb[k]))
    t["risk"] = np.abs(t.ent - t.stop)
    t["gross_pts"] = t.side * (t.out - t.ent)
    t["net_pts"] = t.gross_pts - cost
    t["R"] = t.net_pts / t.risk
    t["gross_R"] = t.gross_pts / t.risk
    t["pct"] = 100.0 * t.net_pts / t.ent
    t["gross_pct"] = 100.0 * t.gross_pts / t.ent
    t["cost_frac"] = cost / t.risk
    t["hold"] = t.x_bar - t.e_bar
    t["ts"] = f.index[t.e_bar.to_numpy()]
    return t


def both_sides(f, a, expiry=None, **kw):
    """Long and short in one deterministically ordered frame."""
    e = EXPIRY if expiry is None else expiry
    d = pd.concat([detect(f, a, e, +1, **kw), detect(f, a, e, -1, **kw)])
    return d.sort_values(["trig", "side", "ob"], kind="mergesort").reset_index(drop=True)


def stats(t, col="pct"):
    if len(t) < 5:
        return dict(n=len(t), win=np.nan, pf=np.nan, mean=np.nan, total=np.nan, sharpe=np.nan,
                    dd=np.nan)
    x = t[col].to_numpy()
    eq = np.cumsum(x)
    return dict(n=len(t), win=float((x > 0).mean()),
                pf=float(x[x > 0].sum() / max(-x[x < 0].sum(), 1e-12)),
                mean=float(x.mean()), total=float(eq[-1]),
                sharpe=float(x.mean() / max(x.std(ddof=1), 1e-12)),
                dd=float(np.max(np.maximum.accumulate(eq) - eq)))


def daily_sharpe(t, f, col="pct"):
    """Annualised over EVERY trading day in the span, zero-filled -- CLAUDE.md's rule: over traded
    days only, a filter is paid for trading less."""
    days = pd.Series(f.index.normalize().unique()).sort_values()
    if not len(t):
        return np.nan, np.nan
    p = t.groupby(pd.DatetimeIndex(t.ts).normalize())[col].sum().reindex(days).fillna(0.0)
    return float(p.mean() / max(p.std(ddof=1), 1e-12) * np.sqrt(252)), float(p.mean())


def split_date(f, frac=0.75):
    days = pd.Series(f.index.normalize().unique()).sort_values().to_numpy()
    return pd.Timestamp(days[int(frac * len(days))])


@njit(cache=True)
def _walk_random(o, h, l, c, ebar, side, risk, rr, cap, lock):
    """The matched control: entries at GIVEN bars with GIVEN risk, everything else identical.

    `ebar` MUST arrive sorted. STUDY_V59 recorded the failure mode -- sampled bars fed in signal
    order rather than chronological order make the position lock reject an arbitrary share, the
    spread explodes and the null stops rejecting anything.
    """
    n = len(c)
    m = len(ebar)
    out_g = np.full(m, np.nan)
    out_e = np.zeros(m, np.float64)
    out_w = np.zeros(m, np.int64)
    took = np.zeros(m, np.int64)
    last_exit = -1
    for q in range(m):
        eb = ebar[q]
        if eb >= n - 1 or eb < 1:
            continue
        if lock == 1 and eb <= last_exit:
            continue
        sd = side[q]
        ent = o[eb]
        rk = risk[q]
        if rk <= 0:
            continue
        far = ent - sd * rk
        tgt = ent + sd * rr * rk if rr > 0 else 0.0
        xb = -1
        xp = 0.0
        w = 2
        lim = eb + cap
        if lim > n - 1:
            lim = n - 1
        for t in range(eb, lim + 1):
            hit_s = (l[t] <= far) if sd > 0 else (h[t] >= far)
            hit_t = False
            if rr > 0:
                hit_t = (h[t] >= tgt) if sd > 0 else (l[t] <= tgt)
            if hit_s:
                xb = t; xp = far; w = 0
                break
            if hit_t:
                xb = t; xp = tgt; w = 1
                break
        if xb < 0:
            xb = lim; xp = c[lim]; w = 2
        out_g[q] = sd * (xp - ent)
        out_e[q] = ent
        out_w[q] = w
        took[q] = 1
        last_exit = xb
    return out_g, out_e, out_w, took


def random_control(f, t_real, rr, seed, cap=HOLD_CAP, cost=RT_POINTS, lo=None, hi=None):
    """Random entries at the SAME average frequency, same side mix, same risk distribution.

    Risk is matched trade for trade by resampling the real risk distribution: STUDY_TURTLE_YOUTUBE
    established that matching only the exits lets the entry set the risk, and a control whose risk
    denominator differs from the rule's flatters or damns it for the wrong reason.
    """
    rng = np.random.default_rng(seed)
    o = f["open"].to_numpy(); h = f["high"].to_numpy()
    l = f["low"].to_numpy(); c = f["close"].to_numpy()
    lo = 1 if lo is None else lo
    hi = (len(c) - cap - 2) if hi is None else hi
    m = len(t_real)
    eb = np.sort(rng.integers(lo, hi, size=m))
    side = rng.permutation(t_real.side.to_numpy())
    risk = rng.choice(t_real.risk.to_numpy(), size=m, replace=True)
    g, ent, w, took = _walk_random(o, h, l, c, eb, side, risk, float(rr), int(cap), 1)
    k = took == 1
    return pd.DataFrame(dict(gross_pts=g[k], ent=ent[k], why=w[k],
                             pct=100.0 * (g[k] - cost) / ent[k],
                             gross_pct=100.0 * g[k] / ent[k], ts=f.index[eb[k]]))
