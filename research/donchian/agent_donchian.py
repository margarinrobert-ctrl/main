#!/usr/bin/env python3
"""agent_donchian.py -- DONCHIAN DISCOVERY QUANT.

Owns the breakout DEFINITION itself.  Every experiment states a hypothesis,
sweeps a neighbourhood, and is scored ONLY against the matched control
(lab.sig_gate).  Research block, NAS, 07:00-11:00 New York.  The locked block
is never touched.

Experiments
  E0  reference: channel WIDTH as a function of lookback (calibration only)
  E1  session-ANCHORED channels vs rolling channels of matched width
  E2  CONFIRMATION: close-beyond vs trade-beyond x buffer_atr sweep
  E3  PERSISTENCE: N consecutive closes beyond / close-position in own range
  E4  channel WIDTH as a state variable (compression vs expansion)
  E5  breakout ORDINAL within the session (first vs later)
  E6  finalists: neighbourhood shape + US30 out-of-instrument replication
"""
import sys, numpy as np, pandas as pd
import lab
from engine import donchian, atr, ema

WIN = (420, 660)
NDRAWS = 200
RESULTS = []
NCFG = 0

_DF = {}
def get(sym="NAS"):
    if sym not in _DF:
        _DF[sym] = lab.research(sym)
    return _DF[sym]


# --------------------------------------------------------------- channels
def anchored(df, anchor, min_bars=1):
    """Running high/low since an anchor, EXCLUDING the current bar.

    anchor='sess' : since 00:00 New York
    anchor='fut'  : since 18:00 the previous day  (the futures day)
    anchor='win'  : since 07:00 New York          (the research window open)
    Returns (upper, lower, nbars_since_anchor).  nbars counts CLOSED bars that
    fed the channel; the channel is NaN until nbars >= min_bars.
    """
    h, l = df.high.values, df.low.values
    tod, sess = df.tod.values, df.sess.values
    if anchor == "sess":
        g = sess.astype(np.int64)
    elif anchor == "fut":
        g = sess.astype(np.int64) + (tod >= 1080).astype(np.int64)
    elif anchor == "win":
        g = np.where(tod >= WIN[0], sess.astype(np.int64), -(sess.astype(np.int64) + 1))
    else:
        raise ValueError(anchor)
    gs = pd.Series(g)
    cmx = pd.Series(h).groupby(gs).cummax().values
    cmn = pd.Series(l).groupby(gs).cummin().values
    cnt = gs.groupby(gs).cumcount().values + 1          # bars incl. current
    up = np.roll(cmx, 1).astype(float); dn = np.roll(cmn, 1).astype(float)
    nb = np.roll(cnt, 1).astype(float)
    first = np.concatenate([[True], g[1:] != g[:-1]])
    up[first] = np.nan; dn[first] = np.nan; nb[first] = 0.0
    up[0] = np.nan; dn[0] = np.nan
    bad = nb < min_bars
    up = up.copy(); dn = dn.copy(); up[bad] = np.nan; dn[bad] = np.nan
    return up, dn, nb


def trig(df, hi, lo, a, confirm="close", buffer_atr=0.0, win=WIN,
         extra=None, side_mask=None):
    """Turn a channel into triggers.  Everything read at the CLOSED bar i."""
    c, h, l, tod = df.close.values, df.high.values, df.low.values, df.tod.values
    px = c if confirm == "close" else h
    pxl = c if confirm == "close" else l
    up = px > (hi + buffer_atr * a)
    dn = pxl < (lo - buffer_atr * a)
    ok = ((tod >= win[0]) & (tod < win[1]) & ~np.isnan(hi) & ~np.isnan(lo)
          & ~np.isnan(a) & (a > 0))
    if extra is not None:
        upx, dnx = extra
        up = up & upx; dn = dn & dnx
    up = up & ok; dn = dn & ok
    if side_mask == "long":
        dn = np.zeros_like(dn)
    elif side_mask == "short":
        up = np.zeros_like(up)
    idx = np.where(up | dn)[0]
    return idx, np.where(up[idx], 1, -1).astype(np.int64)


def G(sym, idx, side, label, ndraws=None, **kw):
    global NCFG
    NCFG += 1
    if len(idx) < 25:
        print(f"  {label:<40} n={len(idx):>5,}  (too few)")
        return None, None
    g, tr = lab.sig_gate(sym, idx, side, label=label,
                         n_draws=ndraws or NDRAWS, **kw)
    RESULTS.append(dict(exp_label=label, **{k: g[k] for k in
                   ("n", "exp", "ctrl", "excess", "z", "p", "pf", "wr")}))
    return g, tr


# =========================================================== E0 calibration
def E0():
    df, w, r = get("NAS")
    a = atr(df, 14)
    tod = df.tod.values
    inwin = (tod >= WIN[0]) & (tod < WIN[1]) & r & ~np.isnan(a) & (a > 0)
    print("=" * 104)
    print("E0  CALIBRATION (no gating, no selection): channel width in ATR units")
    print("    width = (upper-lower)/ATR(14) at eligible 07:00-11:00 research bars")
    print("=" * 104)
    print(f"  {'channel':<26}{'meanW':>8}{'medW':>8}{'p10':>8}{'p90':>8}{'bars':>9}")
    rows = {}
    for n in (3, 5, 8, 10, 15, 20, 30, 40, 60, 80, 120):
        hi, lo = lab.donchian(df, n)
        wd = (hi - lo) / a
        m = inwin & ~np.isnan(wd)
        rows[f"roll {n}"] = np.nanmean(wd[m])
        print(f"  {'rolling n='+str(n):<26}{np.nanmean(wd[m]):>8.2f}{np.nanmedian(wd[m]):>8.2f}"
              f"{np.nanpercentile(wd[m],10):>8.2f}{np.nanpercentile(wd[m],90):>8.2f}{m.sum():>9,}")
    for anc, nm in (("sess", "anchored 00:00 NY"), ("fut", "anchored 18:00 prev"),
                    ("win", "anchored 07:00 NY")):
        hi, lo, nb = anchored(df, anc, min_bars=1)
        wd = (hi - lo) / a
        m = inwin & ~np.isnan(wd)
        rows[anc] = np.nanmean(wd[m])
        print(f"  {nm:<26}{np.nanmean(wd[m]):>8.2f}{np.nanmedian(wd[m]):>8.2f}"
              f"{np.nanpercentile(wd[m],10):>8.2f}{np.nanpercentile(wd[m],90):>8.2f}{m.sum():>9,}")
    print("\n  matched rolling lookback for each anchor (nearest mean width):")
    rollk = {k: v for k, v in rows.items() if k.startswith("roll")}
    for anc in ("sess", "fut", "win"):
        best = min(rollk, key=lambda k: abs(rollk[k] - rows[anc]))
        print(f"    {anc:<6} meanW={rows[anc]:.2f}  ->  {best} (meanW={rollk[best]:.2f})")


# =================================================== E1 anchored vs rolling
def E1():
    """H1: a channel ANCHORED to a session boundary carries information that a
    rolling channel of the same average width does not -- the overnight range /
    the day's range so far is a level other participants watch, whereas a
    rolling n-bar window is an arbitrary reference.
    PREDICTION if true: anchored variants show excess > 0 over the matched
    control while the width-matched rolling channel does not."""
    df, w, r = get("NAS")
    a = atr(df, 14)
    print("\n" + "=" * 104)
    print("E1  SESSION-ANCHORED CHANNELS vs ROLLING CHANNELS OF MATCHED WIDTH")
    print("=" * 104)
    print("\n  -- rolling reference grid (the known baseline, re-gated here) --")
    for n in (5, 10, 20, 40, 80, 120):
        idx, sd = trig(df, *lab.donchian(df, n), a)
        G("NAS", idx, sd, f"rolling n={n}")
    print("\n  -- anchored, min_bars neighbourhood --")
    for anc, nm in (("sess", "anch 00:00"), ("fut", "anch 18:00p"), ("win", "anch 07:00")):
        for mb in (1, 2, 4, 8, 16):
            hi, lo, nb = anchored(df, anc, min_bars=mb)
            idx, sd = trig(df, hi, lo, a)
            G("NAS", idx, sd, f"{nm} min_bars={mb}")
        print()


# ================================================== E2 confirmation / buffer
def E2():
    """H2: the plain close-beyond trigger is contaminated by marginal pokes.
    Requiring the break to clear the channel by k*ATR should select breaks with
    real displacement behind them; requiring only a TOUCH (confirm='high')
    should be worse (it fires on wicks).
    PREDICTION if true: excess rises monotonically in buffer_atr up to some k,
    and confirm='high' sits below confirm='close' everywhere."""
    df, w, r = get("NAS")
    a = atr(df, 14)
    print("\n" + "=" * 104)
    print("E2  CONFIRMATION: close-beyond vs trade-beyond, x buffer_atr")
    print("=" * 104)
    for cf in ("close", "high"):
        for n in (10, 20, 40):
            print(f"\n  -- confirm={cf}  n={n} --")
            for b in (0.0, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0):
                hi, lo = lab.donchian(df, n)
                idx, sd = trig(df, hi, lo, a, confirm=cf, buffer_atr=b)
                G("NAS", idx, sd, f"{cf} n={n} buf={b:.2f}")


# =========================================================== E3 persistence
def E3():
    """H3a: a breakout that is still beyond the channel N bars later has been
    accepted by the market; a one-bar poke has not.
    H3b: a breakout bar that closes in the top third of its OWN range shows the
    buyers held the move into the close; one that closes mid-bar was faded.
    PREDICTION if true: excess increases with N (up to 2-3) and with the
    close-position threshold, smoothly."""
    df, w, r = get("NAS")
    a = atr(df, 14)
    c, h, l = df.close.values, df.high.values, df.low.values
    print("\n" + "=" * 104)
    print("E3  PERSISTENCE: consecutive closes beyond the channel; close position in bar")
    print("=" * 104)
    for n in (10, 20, 40):
        hi, lo = lab.donchian(df, n)
        bu = np.nan_to_num(c > hi, nan=False) & ~np.isnan(hi)
        bd = np.nan_to_num(c < lo, nan=False) & ~np.isnan(lo)
        print(f"\n  -- H3a consecutive closes beyond, n={n} --")
        for k in (1, 2, 3, 4):
            up = bu.copy(); dn = bd.copy()
            for j in range(1, k):
                up &= np.roll(bu, j); dn &= np.roll(bd, j)
            if k > 1:
                up[:k] = False; dn[:k] = False
            idx, sd = trig(df, hi, lo, a, extra=(up, dn))
            G("NAS", idx, sd, f"n={n} consec>={k}")
    rng = np.maximum(h - l, 1e-9)
    pos_u = (c - l) / rng          # 1.0 = closed on the high
    pos_d = (h - c) / rng
    for n in (10, 20, 40):
        hi, lo = lab.donchian(df, n)
        print(f"\n  -- H3b close position in own range, n={n} --")
        for t in (0.0, 0.5, 0.6667, 0.8, 0.9):
            idx, sd = trig(df, hi, lo, a, extra=(pos_u >= t, pos_d >= t))
            G("NAS", idx, sd, f"n={n} closepos>={t:.2f}")


# =========================================================== E4 channel width
def E4():
    """H4: breakouts out of a COMPRESSED channel (width/ATR low) continue
    better than breakouts out of an already-wide channel -- the classic
    volatility-contraction premise.  The null is that width is just a proxy for
    how far the barriers are relative to recent movement, which the matched
    control already prices.
    PREDICTION if true: excess falls monotonically across width quantiles."""
    df, w, r = get("NAS")
    a = atr(df, 14)
    print("\n" + "=" * 104)
    print("E4  CHANNEL WIDTH AS A STATE VARIABLE  (width = (upper-lower)/ATR at signal bar)")
    print("=" * 104)
    for n in (10, 20, 40):
        hi, lo = lab.donchian(df, n)
        wd = (hi - lo) / a
        idx0, _ = trig(df, hi, lo, a)
        idx0 = idx0[r[idx0]]          # RESEARCH-BLOCK triggers only: the cut
        pool = wd[idx0]               # points must not be read off the holdout
        pool = pool[np.isfinite(pool)]
        qs = np.percentile(pool, [20, 40, 60, 80])
        print(f"\n  -- n={n}  width quintile cuts (research triggers): "
              f"{' '.join(f'{q:.2f}' for q in qs)} --")
        edges = [-np.inf] + list(qs) + [np.inf]
        for i in range(5):
            lo_, hi_ = edges[i], edges[i + 1]
            m = (wd >= lo_) & (wd < hi_)
            idx, sd = trig(df, hi, lo, a, extra=(m, m))
            G("NAS", idx, sd, f"n={n} width Q{i+1} [{lo_:.2f},{hi_:.2f})")
        # cumulative "narrow-only" thresholds - the shippable form of the rule
        for q, lbl in zip(qs, ("<=p20", "<=p40", "<=p60", "<=p80")):
            m = wd <= q
            idx, sd = trig(df, hi, lo, a, extra=(m, m))
            G("NAS", idx, sd, f"n={n} width {lbl} ({q:.2f})")


# ============================================================== E5 ordinal
def E5():
    """H5: the FIRST breakout of the session is the informative one (it defines
    the day's direction); later ones are chasing.  Or the reverse -- the first
    is the noise trade and acceptance shows up later.
    PREDICTION: one_per_session=True beats all-signals, and the 2nd+ breakouts
    are worse than the 1st."""
    df, w, r = get("NAS")
    a = atr(df, 14)
    sess = df.sess.values
    print("\n" + "=" * 104)
    print("E5  BREAKOUT ORDINAL WITHIN THE SESSION")
    print("=" * 104)
    for n in (10, 20, 40):
        hi, lo = lab.donchian(df, n)
        idx0, sd0 = trig(df, hi, lo, a)
        s = sess[idx0]
        ordn = np.zeros(len(idx0), dtype=int)
        seen = {}
        for j, ss in enumerate(s):
            seen[ss] = seen.get(ss, 0) + 1
            ordn[j] = seen[ss]
        print(f"\n  -- n={n} --")
        G("NAS", idx0, sd0, f"n={n} ALL signals", one_per_session=False)
        for k in (1, 2, 3):
            m = ordn == k
            if m.sum() < 25: continue
            G("NAS", idx0[m], sd0[m], f"n={n} ordinal=={k}", one_per_session=False)
        m = ordn >= 2
        if m.sum() >= 25:
            G("NAS", idx0[m], sd0[m], f"n={n} ordinal>=2", one_per_session=False)


EXP = dict(E0=E0, E1=E1, E2=E2, E3=E3, E4=E4, E5=E5)

# ============================== E6  DISSECTION OF THE ONE LIVE SURFACE ======
def _prep(sym):
    df, w, r = get(sym)
    a = lab.atr(df, 14)
    c, o, h, l = (df.close.values, df.open.values, df.high.values, df.low.values)
    trg = lab.true_range(h, l, c)
    return df, w, r, a, c, o, h, l, trg


def E6a():
    """The FULL buffer surface: is the E2 result a plateau or a spike?
    A real effect decays smoothly across BOTH the lookback and the buffer."""
    df, w, r, a, c, o, h, l, trg = _prep("NAS")
    print("\n" + "=" * 104)
    print("E6a  FULL BUFFER x LOOKBACK SURFACE (confirm=close).  excess / z / n")
    print("=" * 104)
    bufs = (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
    ns = (5, 10, 15, 20, 30, 40, 60)
    grid = {}
    for n in ns:
        hi, lo = lab.donchian(df, n)
        for b in bufs:
            idx, sd = trig(df, hi, lo, a, buffer_atr=b)
            g, _ = G("NAS", idx, sd, f"n={n} buf={b}", ndraws=300)
            grid[(n, b)] = g
    for tag, key, f in (("EXCESS (pts/trade)", "excess", "{:>8.2f}"),
                        ("Z vs matched control", "z", "{:>8.2f}"),
                        ("N trades", "n", "{:>8,d}"),
                        ("control p", "p", "{:>8.3f}")):
        print(f"\n  {tag}")
        print("    n\\buf " + "".join(f"{b:>8.2f}" for b in bufs))
        for n in ns:
            row = f"    {n:>5} "
            for b in bufs:
                g = grid[(n, b)]
                row += ("      --" if g is None else f.format(g[key]))
            print(row)


def E6b():
    """DECOMPOSITION.  `close > upper + b*ATR` implies TR/ATR > b, so it is a
    channel break AND a volatility shock in the same direction.  Which half is
    doing the work?
      (1) big-bar continuation with NO channel at all
      (2) plain channel break AND a big bar (buffer replaced by a bar-size test)
      (3) the buffered break, but scored against a VOL-MATCHED control - random
          entries drawn only from bars that also had TR/ATR >= b."""
    df, w, r, a, c, o, h, l, trg = _prep("NAS")
    tod = df.tod.values
    inwin = (tod >= WIN[0]) & (tod < WIN[1]) & ~np.isnan(a) & (a > 0)
    mv = (c - o) / a
    trr = trg / a
    print("\n" + "=" * 104)
    print("E6b  DECOMPOSITION: channel, or just a big directional bar?")
    print("=" * 104)
    print("\n  (1) BIG-BAR CONTINUATION, no Donchian channel anywhere")
    print("      side = sign(close-open); require |close-open| >= t*ATR")
    for t in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5):
        up = mv >= t; dn = mv <= -t
        idx = np.where((up | dn) & inwin)[0]
        sd = np.where(up[idx], 1, -1).astype(np.int64)
        G("NAS", idx, sd, f"bigbar |c-o|>={t}*ATR", ndraws=300)
    print("\n  (2) BIG BAR *AND* a channel break (n=20, buffer=0)")
    hi, lo = lab.donchian(df, 20)
    for t in (0.0, 0.25, 0.5, 0.75, 1.0, 1.25):
        idx, sd = trig(df, hi, lo, a, extra=(mv >= t, mv <= -t))
        G("NAS", idx, sd, f"n=20 brk & |c-o|>={t}*ATR", ndraws=300)
    print("\n  (3) VOL-MATCHED CONTROL: buffered break vs random entries drawn")
    print("      ONLY from window bars that also had TR/ATR >= b  (same minute-of-day)")
    for n in (10, 20, 40):
        for b in (0.5, 0.75, 1.0):
            hi, lo = lab.donchian(df, n)
            idx, sd = trig(df, hi, lo, a, buffer_atr=b)
            pool = r & inwin & (trr >= b)
            g, _ = G("NAS", idx, sd, f"n={n} buf={b} VOLMATCHED pool={pool.sum():,}",
                     ndraws=300, mask=pool)
    print("\n  (3b) same, but the control pool is a BAND  b <= TR/ATR < b+0.75")
    for n in (10, 20, 40):
        for b in (0.75, 1.0):
            hi, lo = lab.donchian(df, n)
            idx, sd = trig(df, hi, lo, a, buffer_atr=b)
            pool = r & inwin & (trr >= b) & (trr < b + 0.75)
            g, _ = G("NAS", idx, sd, f"n={n} buf={b} BAND pool={pool.sum():,}",
                     ndraws=300, mask=pool)


def E6c():
    """ROBUSTNESS of the buffered break: prior-bar ATR (so the signal bar cannot
    inflate its own yardstick), long/short split, sub-period stability, cost
    stress, and OUT-OF-INSTRUMENT replication on US30 (research block)."""
    df, w, r, a, c, o, h, l, trg = _prep("NAS")
    print("\n" + "=" * 104)
    print("E6c  ROBUSTNESS OF THE BUFFERED BREAK")
    print("=" * 104)
    aprev = np.roll(a, 1); aprev[0] = np.nan
    print("\n  (1) buffer measured in the PRIOR bar's ATR (a[i-1]) - the signal bar")
    print("      can no longer inflate the yardstick it is measured against")
    for n in (10, 20, 40):
        hi, lo = lab.donchian(df, n)
        for b in (0.5, 0.75, 1.0, 1.25):
            up = c > hi + b * aprev; dn = c < lo - b * aprev
            idx, sd = trig(df, hi, lo, a, extra=(up, dn))
            G("NAS", idx, sd, f"n={n} buf={b} in PRIOR atr", ndraws=300)
    print("\n  (2) side split, n=20 buf=1.0 (control matches the side MIX, so a")
    print("      one-sided result is still gated - but report it)")
    hi, lo = lab.donchian(df, 20)
    for sm in ("long", "short"):
        idx, sd = trig(df, hi, lo, a, buffer_atr=1.0, side_mask=sm)
        G("NAS", idx, sd, f"n=20 buf=1.0 {sm} only", ndraws=300)
    print("\n  (3) research sub-period thirds, n=20 buf=1.0 (stability, not selection)")
    sess = df.sess.values
    rs = sess[r]; lo_s, hi_s = rs.min(), rs.max()
    cuts = np.linspace(lo_s, hi_s + 1, 4).astype(int)
    idx, sd = trig(df, hi, lo, a, buffer_atr=1.0)
    for i in range(3):
        m = r & (sess >= cuts[i]) & (sess < cuts[i + 1])
        G("NAS", idx, sd, f"n=20 buf=1.0 third {i+1} (sess {cuts[i]}-{cuts[i+1]})",
          ndraws=300, mask=m)
    print("\n  (4) US30, RESEARCH block - a different instrument, not the holdout")
    d2, w2, r2 = get("US30")
    a2 = lab.atr(d2, 14)
    for n in (10, 20, 40):
        h2, l2 = lab.donchian(d2, n)
        for b in (0.0, 0.5, 0.75, 1.0, 1.25):
            idx, sd = trig(d2, h2, l2, a2, buffer_atr=b)
            G("US30", idx, sd, f"US30 n={n} buf={b}", ndraws=300)


def E6d():
    """Is the consec>=3 bump (E3a) the SAME trade set as the buffered break?
    Both say 'price has already moved a long way'.  Overlap + a combined rule."""
    df, w, r, a, c, o, h, l, trg = _prep("NAS")
    print("\n" + "=" * 104)
    print("E6d  IS PERSISTENCE THE SAME EFFECT AS DISPLACEMENT?")
    print("=" * 104)
    for n in (10, 20, 40):
        hi, lo = lab.donchian(df, n)
        bu = (c > hi) & ~np.isnan(hi); bd = (c < lo) & ~np.isnan(lo)
        up3 = bu & np.roll(bu, 1) & np.roll(bu, 2)
        dn3 = bd & np.roll(bd, 1) & np.roll(bd, 2)
        up3[:3] = False; dn3[:3] = False
        i_p, _ = trig(df, hi, lo, a, extra=(up3, dn3))
        i_b, _ = trig(df, hi, lo, a, buffer_atr=1.0)
        sp, sb = set(i_p.tolist()), set(i_b.tolist())
        print(f"  n={n:<3} persistence(consec>=3) n={len(sp):>5,}  buffer(1.0 ATR) n={len(sb):>5,}"
              f"  overlap={len(sp & sb):>5,}  jaccard={len(sp&sb)/max(len(sp|sb),1):.3f}")
    print("\n  persistence measured in the LOOSER geometry: does it survive a buffer sweep?")
    hi, lo = lab.donchian(df, 20)
    bu = (c > hi) & ~np.isnan(hi); bd = (c < lo) & ~np.isnan(lo)
    for k in (2, 3):
        up = bu.copy(); dn = bd.copy()
        for j in range(1, k):
            up = up & np.roll(bu, j); dn = dn & np.roll(bd, j)
        up[:k] = False; dn[:k] = False
        for b in (0.0, 0.5):
            idx, sd = trig(df, hi, lo, a, buffer_atr=b, extra=(up, dn))
            G("NAS", idx, sd, f"n=20 consec>={k} buf={b}", ndraws=300)


EXP.update(E6a=E6a, E6b=E6b, E6c=E6c, E6d=E6d)


# ================= E7  DOES THE CHANNEL DO ANY WORK, AND IS THE P HONEST? ===
def E7():
    """Four things the E6 result still has to survive.
    (a) LOOKBACK -> 1.  `close > upper(n) + b*ATR` implies `close - close[i-1]
        > b*ATR`.  If n=1 works as well as n=20 the 'channel' is a one-bar
        return in disguise and this is not a Donchian finding at all.
    (b) the pure ONE-BAR RETURN rule, no channel: |c - c[-1]| >= t*ATR.
    (c) one_per_session=False - does the effect need the first-of-day filter?
    (d) cluster-robust inference: a 20-session BLOCK bootstrap of the excess,
        plus the exit-reason split (earning at the TIME stop = a direction bet)
        and a 2x cost / 3x slippage stress."""
    df, w, r, a, c, o, h, l, trg = _prep("NAS")
    tod = df.tod.values
    inwin = (tod >= WIN[0]) & (tod < WIN[1]) & ~np.isnan(a) & (a > 0)
    cp = np.roll(c, 1); cp[0] = np.nan
    ret1 = (c - cp) / a
    print("\n" + "=" * 104)
    print("E7  DOES THE CHANNEL DO ANY WORK?")
    print("=" * 104)
    print("\n  (a) lookback -> 1 at buf=1.0 (n=1 is just 'close 1 ATR above the last bar's high')")
    for n in (1, 2, 3, 5, 8, 20):
        hi, lo = lab.donchian(df, n)
        idx, sd = trig(df, hi, lo, a, buffer_atr=1.0)
        G("NAS", idx, sd, f"n={n} buf=1.0", ndraws=300)
    print("\n  (b) ONE-BAR RETURN only, no channel: side=sign(c-c[-1]), |ret|>=t*ATR")
    for t in (0.5, 0.75, 1.0, 1.25, 1.5):
        up = ret1 >= t; dn = ret1 <= -t
        idx = np.where((up | dn) & inwin & ~np.isnan(ret1))[0]
        sd = np.where(up[idx], 1, -1).astype(np.int64)
        G("NAS", idx, sd, f"ret1 >= {t}*ATR (no channel)", ndraws=300)
    print("\n  (c) EVERY qualifying break, not just the first of the session")
    for n in (10, 20, 40):
        hi, lo = lab.donchian(df, n)
        idx, sd = trig(df, hi, lo, a, buffer_atr=1.0)
        G("NAS", idx, sd, f"n={n} buf=1.0 ALL breaks", ndraws=300, one_per_session=False)
    print("\n  (d) cost / slippage stress on n=20 buf=1.0 (excess is cost-INVARIANT -")
    print("      the control pays the same - so this only moves exp)")
    hi, lo = lab.donchian(df, 20)
    idx, sd = trig(df, hi, lo, a, buffer_atr=1.0)
    for cm, lb in ((1.0, "1x cost"), (2.0, "2x cost"), (3.0, "3x cost")):
        tr = lab.book("NAS", idx, sd, cost_mult=cm)
        tr = tr[np.isin(tr.sig_bar, np.where(r)[0])]
        print(f"      {lb:<10} n={len(tr):>5,} exp={tr.net.mean():>+7.2f} "
              f"wr={(tr.net>0).mean():>5.1%}")
    tr = lab.book("NAS", idx, sd)
    tr = tr[np.isin(tr.sig_bar, np.where(r)[0])].reset_index(drop=True)
    print("\n      exit split (a rule earning at the TIME stop is a direction bet):")
    for rr in sorted(tr.reason.unique()):
        sl = tr[tr.reason == rr]
        print(f"        {lab.REASONS[rr]:<9} n={len(sl):>5,} ({len(sl)/len(tr):>5.1%})"
              f"  exp={sl.net.mean():>+8.2f}  contrib={sl.net.sum()/len(tr):>+7.2f}")
    print("\n      BLOCK BOOTSTRAP of mean net (20-session blocks, 4,000 draws)")
    sess = df.sess.values[tr.sig_bar.values]
    blk = sess // 20
    ub = np.unique(blk)
    rng = np.random.default_rng(7)
    vals = tr.net.values
    by = {b: vals[blk == b] for b in ub}
    bs = np.empty(4000)
    for i in range(4000):
        pick = rng.choice(ub, size=len(ub), replace=True)
        bs[i] = np.concatenate([by[b] for b in pick]).mean()
    print(f"        mean={vals.mean():+.2f}  block-bootstrap sd={bs.std(ddof=1):.2f} "
          f" 5-95% [{np.percentile(bs,5):+.2f}, {np.percentile(bs,95):+.2f}]")
    ctrl = -2.46
    print(f"        P(mean <= matched-control mean {ctrl:+.2f}) = {(bs<=ctrl).mean():.4f}"
          f"   <- cluster-robust one-sided p")
    print("\n  (e) BAND control done properly (pool banded, trades NOT subset)")
    from control import matched_control
    trr_ = trg / a
    for n in (10, 20, 40):
        hi, lo = lab.donchian(df, n)
        idx, sd = trig(df, hi, lo, a, buffer_atr=1.0)
        tb = lab.book("NAS", idx, sd)
        tb = tb[np.isin(tb.sig_bar, np.where(r)[0])].reset_index(drop=True)
        pool = r & inwin & (trr_ >= 1.0) & (trr_ < 2.5)
        mn, p = matched_control(df, w, tb, n_draws=400, seed=3, cost_pts=2.0,
                                slip_pts=0.25, stop_mult=1.5, targ_mult=2.0,
                                pool_idx=pool)
        z = (tb.net.mean() - mn.mean()) / mn.std(ddof=1)
        print(f"      n={n:<3} buf=1.0  n_tr={len(tb):>5,} exp={tb.net.mean():>+7.2f} "
              f"ctrl={mn.mean():>+7.2f} excess={tb.net.mean()-mn.mean():>+7.2f} "
              f"z={z:>+6.2f} p={p:.4f}   (pool {pool.sum():,} bars, 1.0<=TR/ATR<2.5)")


EXP.update(E7=E7)


# ============ E8  PERMUTATION NULL, SUB-WINDOWS, GEOMETRY NEIGHBOURHOOD =====
def E8():
    """(a) DAY-SHIFT PERMUTATION.  Take the real rule's (session, minute-of-day)
        signal stamps and apply them D sessions later.  This preserves the
        minute-of-day histogram EXACTLY, preserves the rule's day-level
        clustering, and destroys only the link to the actual bar.  60 shifts
        give a null distribution of mean net that the matched control's
        i.i.d. resampling cannot produce.
    (b) does the effect live in one half of the window?
    (c) is it specific to stop 1.5 / targ 2.0 / max_hold 16?"""
    df, w, r, a, c, o, h, l, trg = _prep("NAS")
    sess, tod = df.sess.values, df.tod.values
    print("\n" + "=" * 104)
    print("E8  PERMUTATION NULL / SUB-WINDOWS / GEOMETRY NEIGHBOURHOOD")
    print("=" * 104)
    hi, lo = lab.donchian(df, 20)
    idx, sd = trig(df, hi, lo, a, buffer_atr=1.0)
    tb = lab.book("NAS", idx, sd)
    keep = np.isin(tb.sig_bar, np.where(r)[0])
    tb = tb[keep].reset_index(drop=True)
    real = tb.net.mean()
    # (session, tod) -> bar
    key = sess.astype(np.int64) * 10000 + tod
    order = np.argsort(key); ks = key[order]
    def barof(s_, t_):
        kk = s_.astype(np.int64) * 10000 + t_
        pos = np.searchsorted(ks, kk)
        pos = np.clip(pos, 0, len(ks) - 1)
        ok = ks[pos] == kk
        return order[pos], ok
    s0, t0 = sess[tb.sig_bar.values], tod[tb.sig_bar.values]
    sides = tb.side.values.astype(np.int64)
    rmax = sess[r].max()
    nulls = []
    for D in list(range(-60, 0)) + list(range(1, 61)):
        b2, ok = barof(s0 + D, t0)
        b2, sd2 = b2[ok], sides[ok]
        b2m = r[b2] & ~np.isnan(a[b2]) & (a[b2] > 0)
        b2, sd2 = b2[b2m], sd2[b2m]
        if len(b2) < 100: continue
        u, ui = np.unique(b2, return_index=True)
        tn = lab.book("NAS", u, sd2[ui], one_per_session=False)
        if len(tn) > 50: nulls.append(tn.net.mean())
    nulls = np.array(nulls)
    print(f"\n  (a) day-shift permutation, {len(nulls)} shifts of +/-1..60 sessions")
    print(f"      REAL mean net = {real:+.2f}")
    print(f"      null mean = {nulls.mean():+.2f}  sd = {nulls.std(ddof=1):.2f}"
          f"  min={nulls.min():+.2f}  max={nulls.max():+.2f}")
    print(f"      z = {(real-nulls.mean())/nulls.std(ddof=1):+.2f}"
          f"   p(one-sided) = {(nulls>=real).mean():.4f}"
          f"   [{(nulls>=real).sum()} of {len(nulls)} shifts beat the real rule]")
    print("\n  (b) window halves (diagnostic, both gated against their own control)")
    for lbl, win in (("07:00-09:30", (420, 570)), ("09:30-11:00", (570, 660))):
        for b in (0.0, 1.0):
            i2, s2 = trig(df, hi, lo, a, buffer_atr=b, win=win)
            G("NAS", i2, s2, f"n=20 buf={b} {lbl}", ndraws=300, flat_tod=win[1])
    print("\n  (c) geometry neighbourhood at n=20 buf=1.0 (stop/targ/max_hold)")
    for sm, tm, mh in ((1.5, 2.0, 16), (1.0, 1.5, 16), (2.0, 2.5, 16),
                       (1.5, 3.0, 16), (1.5, 2.0, 8), (1.5, 2.0, 24)):
        G("NAS", idx, sd, f"stop={sm} targ={tm} hold={mh}", ndraws=300,
          stop_mult=sm, targ_mult=tm, max_hold=mh)
    print("\n      same geometry neighbourhood at buf=0.0 (the dead baseline)")
    i0, s0b = trig(df, hi, lo, a, buffer_atr=0.0)
    for sm, tm, mh in ((1.0, 1.5, 16), (2.0, 2.5, 16), (1.5, 3.0, 16),
                       (1.5, 2.0, 8), (1.5, 2.0, 24)):
        G("NAS", i0, s0b, f"BASE stop={sm} targ={tm} hold={mh}", ndraws=300,
          stop_mult=sm, targ_mult=tm, max_hold=mh)


EXP.update(E8=E8)


# ================================= E9  LAST CHECKS + FINALIST SUMMARY ======
def E9():
    """(a) does the buffer resurrect the anchored channels of E1?
       (b) does the buffer need confirm='close'?  (E2 said yes - restate cleanly)
       (c) plateau statistics: mean excess over the (n, buf) region, and the
           same statistic for the dead buf<=0.25 region, so the reader can see
           the surface is a PLATEAU and not a spike."""
    df, w, r, a, c, o, h, l, trg = _prep("NAS")
    print("\n" + "=" * 104)
    print("E9  LAST CHECKS")
    print("=" * 104)
    print("\n  (a) session-ANCHORED channels + the 1.0 ATR buffer")
    for anc, nm in (("sess", "anch 00:00"), ("fut", "anch 18:00p"), ("win", "anch 07:00")):
        for b in (0.5, 1.0, 1.25):
            hu, hl, nb = anchored(df, anc, min_bars=2)
            idx, sd = trig(df, hu, hl, a, buffer_atr=b)
            G("NAS", idx, sd, f"{nm} buf={b}", ndraws=300)
    print("\n  (b) confirm=high (TOUCH beyond) at the same buffers - the close is")
    print("      what carries the information, not reaching the level")
    for n in (10, 20, 40):
        hu, hl = lab.donchian(df, n)
        for b in (1.0, 1.25):
            idx, sd = trig(df, hu, hl, a, confirm="high", buffer_atr=b)
            G("NAS", idx, sd, f"TOUCH n={n} buf={b}", ndraws=300)


EXP.update(E9=E9)


if __name__ == "__main__":
    which = sys.argv[1:] or ["E0"]
    for k in which:
        EXP[k]()
    print(f"\n  configurations gated in this run: {NCFG}")