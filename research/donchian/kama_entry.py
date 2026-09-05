"""KAMA(9) and other moving-average crossovers as ENTRY LOCATION, not as a signal.

TWO DIFFERENT QUESTIONS, and conflating them is how this kind of test goes wrong:

  Q1  Does a KAMA crossover EARN anything as a trigger of its own?
  Q2  Given a trade you were going to take anyway, does waiting for a KAMA condition give a
      BETTER LOCATION -- a cheaper fill, and a better outcome from it?

They are answered separately below because they have different controls. `STUDY_LIMIT_ENTRY.md`
already established the shape of the answer to Q2 on this branch: a resting limit 0.75xATR in your
favour beats a market order on every timeframe and both sides with NO RULE AT ALL, and yet applied
to nine validated strategies it destroyed most of the book -- because a good signal's edge is in the
IMMEDIACY of the move, and waiting discards exactly the trades that ran. So a location test must
report the trades it LOSES, not just the fills it improves.

THE CONTROL THAT MATTERS FOR Q2 IS NOT A RANDOM ENTRY. It is the same trade, waiting the same
number of bars, entered by a rule that carries no information: a RANDOM WAIT drawn from the KAMA
tap's own realised wait distribution, and a FIXED wait of the same median. If the KAMA tap only
matches those, then what is being measured is the waiting, not the moving average.

Every MA is read on the SIGNAL bar and every fill is on a later bar's open or at a resting limit.
No condition anywhere reads the bar it fills on.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/donchian")
import indicators as I, trendind as T, dcs, sweep  # noqa: E402

RT = sweep.RT


def ma(kind, c, h, l, n):
    if kind == "kama":
        return T.kama(c, n)
    if kind == "ema":
        return I.ema(c, n)
    if kind == "sma":
        return I.sma(c, n)
    if kind == "hull":
        return T.hull(c, n)
    if kind == "dema":
        return T.dema(c, n)
    if kind == "tema":
        return T.tema(c, n)
    raise ValueError(kind)


def walk(d, atr, ent_bar, side, mult, cost=RT, entry_px=None):
    """The same 3xATR trailing exit as `dcs.run`, from an ARBITRARY entry bar and price.

    Split out so the entry mechanic can vary while the exit stays bit-identical to the baseline --
    otherwise a location test silently measures a different exit."""
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    n = len(c)
    rows = []
    for eb, s, a, px in zip(ent_bar, side, atr, entry_px):
        if eb >= n - 1 or not np.isfinite(a) or a <= 0 or not np.isfinite(px):
            continue
        stop = px - s * mult * a
        ext = px
        j, out = eb, None
        while j < n:
            if s > 0 and l[j] <= stop:
                out = stop; break
            if s < 0 and h[j] >= stop:
                out = stop; break
            ext = max(ext, h[j]) if s > 0 else min(ext, l[j])
            stop = max(stop, ext - mult * a) if s > 0 else min(stop, ext + mult * a)
            j += 1
        if out is None:
            continue
        pnl = s * (out - px) - cost
        rows.append((eb, j, s, px, out, pnl, pnl / (mult * a)))
    return pd.DataFrame(rows, columns=["ent_bar", "exit_bar", "side", "entry", "exit", "pnl", "R"])


# ---------------------------------------------------------------------------------------------
# The taps. Each takes the SIGNAL bars and returns, for every one, the bar it would fill on and
# the price -- or NaN if the condition never came inside the window, which is a trade NOT TAKEN.
# ---------------------------------------------------------------------------------------------

def tap_market(d, sig, side, atr, **kw):
    """The baseline the source uses: next bar's open, no waiting."""
    eb = sig + 1
    return eb, d["o"][np.minimum(eb, len(d["c"]) - 1)].copy()


def tap_touch(d, sig, side, atr, line=None, window=5, **kw):
    """Rest a limit AT the moving average and wait for price to come back to it."""
    h, l, o = d["h"], d["l"], d["o"]
    n = len(o)
    eb = np.full(len(sig), -1); px = np.full(len(sig), np.nan)
    for k, (i, s) in enumerate(zip(sig, side)):
        lv = line[i]                                   # the level as known at the SIGNAL bar
        if not np.isfinite(lv):
            continue
        for j in range(i + 1, min(i + 1 + window, n)):
            if (s > 0 and l[j] <= lv) or (s < 0 and h[j] >= lv):
                # a gap through the level fills at the open, not at the level
                eb[k] = j; px[k] = (min(o[j], lv) if s > 0 else max(o[j], lv)); break
    return eb, px


def tap_cross(d, sig, side, atr, fast=None, slow=None, window=5, **kw):
    """Wait for the fast MA to cross the slow one in the trade's direction, fill at the next open."""
    o = d["o"]; n = len(o)
    eb = np.full(len(sig), -1); px = np.full(len(sig), np.nan)
    up = (fast > slow) & (I.shift(fast, 1) <= I.shift(slow, 1))
    dn = (fast < slow) & (I.shift(fast, 1) >= I.shift(slow, 1))
    for k, (i, s) in enumerate(zip(sig, side)):
        want = up if s > 0 else dn
        for j in range(i + 1, min(i + 1 + window, n - 1)):
            if want[j]:
                eb[k] = j + 1; px[k] = o[j + 1]; break
    return eb, px


def tap_reclaim(d, sig, side, atr, line=None, window=5, **kw):
    """Wait for the close to dip through the MA and RECLAIM it -- a pullback that resumed."""
    o, c = d["o"], d["c"]; n = len(o)
    eb = np.full(len(sig), -1); px = np.full(len(sig), np.nan)
    for k, (i, s) in enumerate(zip(sig, side)):
        dipped = False
        for j in range(i + 1, min(i + 1 + window, n - 1)):
            if not np.isfinite(line[j]):
                continue
            below = c[j] < line[j] if s > 0 else c[j] > line[j]
            if below:
                dipped = True
            elif dipped:
                eb[k] = j + 1; px[k] = o[j + 1]; break
    return eb, px


def tap_limit_atr(d, sig, side, atr, dist=1.0, window=5, **kw):
    """THE CONTROL THAT DECIDES IT: a resting limit `dist` x ATR in your favour from the signal
    close, with no moving average anywhere in it. If a touch of KAMA 9 only matches a blind limit
    at the same distance, then the adaptive average is not choosing a location -- the DISTANCE is,
    and the average is an expensive way to specify a number."""
    h, l, o, c = d["h"], d["l"], d["o"], d["c"]
    n = len(o)
    eb = np.full(len(sig), -1); px = np.full(len(sig), np.nan)
    for k, (i, s, a) in enumerate(zip(sig, side, atr)):
        if not np.isfinite(a) or a <= 0:
            continue
        lv = c[i] - s * dist * a
        for j in range(i + 1, min(i + 1 + window, n)):
            if (s > 0 and l[j] <= lv) or (s < 0 and h[j] >= lv):
                eb[k] = j; px[k] = (min(o[j], lv) if s > 0 else max(o[j], lv)); break
    return eb, px


def tap_random_wait(d, sig, side, atr, waits=None, rng=None, **kw):
    """The control: wait a number of bars DRAWN FROM the tap's own realised wait distribution."""
    o = d["o"]; n = len(o)
    w = rng.choice(waits, size=len(sig)) if len(waits) else np.ones(len(sig), int)
    eb = np.minimum(sig + w, n - 1)
    return eb, o[eb].copy()


def tap_fixed_wait(d, sig, side, atr, wait=1, **kw):
    """The other control: always wait the same number of bars, the tap's median."""
    o = d["o"]; n = len(o)
    eb = np.minimum(sig + int(wait), n - 1)
    return eb, o[eb].copy()


# ---------------------------------------------------------------------------------------------
# Q2: the location test.
# ---------------------------------------------------------------------------------------------

def locate(tf=30, dc=20, ema_n=50, adx_min=20.0, chop_max=40.0, mult=3.0,
           block="research", windows=(3, 5, 10), verbose=True, seed=3):
    """Every tap against the market-order baseline AND against wait-matched controls."""
    d, si, cut = sweep.blocks(tf)
    h, l, c = d["h"], d["l"], d["c"]
    atrv = dcs.wilder_atr(h, l, c, 14)
    m = (si < cut) if block == "research" else (si >= cut)
    sl, ss = dcs.signals(d, dc=dc, ema_n=ema_n, adx_min=adx_min, chop_max=chop_max)
    sl, ss = sl & m, ss & m
    sig = np.flatnonzero(sl | ss)
    side = np.where(sl[sig], 1, -1)
    a = atrv[sig]
    rng = np.random.default_rng(seed)

    K9 = T.kama(c, 9)
    lines = {"KAMA 9": K9, "EMA 9": I.ema(c, 9), "EMA 21": I.ema(c, 21),
             "HULL 9": T.hull(c, 9), "SMA 20": I.sma(c, 20)}
    pairs = {"KAMA 9 x KAMA 21": (K9, T.kama(c, 21)),
             "KAMA 9 x KAMA 30": (K9, T.kama(c, 30)),
             "KAMA 9 x EMA 21":  (K9, I.ema(c, 21)),
             "KAMA 9 x EMA 50":  (K9, I.ema(c, 50)),
             "EMA 9 x EMA 21":   (I.ema(c, 9), I.ema(c, 21)),
             "EMA 9 x SMA 20":   (I.ema(c, 9), I.sma(c, 20))}

    base_eb, base_px = tap_market(d, sig, side, a)
    base = walk(d, a, base_eb, side, mult, entry_px=base_px)
    rows = [dict(tap="market next open (baseline)", win_bars=0, taken=len(base), rate=1.0,
                 med_wait=1.0, edge_atr=0.0, R=float(base.R.mean()), pf=_pf(base),
                 winr=float((base.pnl > 0).mean()), ctlR=np.nan, p=np.nan)]

    def add(name, w, eb, px):
        ok = eb >= 0
        if ok.sum() < 25:
            return
        t = walk(d, a[ok], eb[ok], side[ok], mult, entry_px=px[ok])
        if not len(t):
            return
        waits = (eb[ok] - sig[ok])
        # how much better is the FILL, in ATR, than the market order would have been?
        edge = np.mean(side[ok] * (base_px[ok] - px[ok]) / a[ok])
        # controls: random wait from the tap's own distribution, and a fixed wait at its median
        # THE CONTROL DEPENDS ON WHAT THE TAP DID. A tap that fills at a LEVEL is compared with a
        # blind limit the same distance away -- otherwise the comparison hands the tap a better
        # fill and calls the difference an edge. A tap that fills at an OPEN after waiting is
        # compared with a random wait of the same length.
        if edge > 0.05:
            eb2, px2 = tap_limit_atr(d, sig, side, a, dist=edge, window=w)
            ok2 = eb2 >= 0
            t2 = walk(d, a[ok2], eb2[ok2], side[ok2], mult, entry_px=px2[ok2])
            ctlR = float(t2.R.mean()) if len(t2) else np.nan
            ctl_n = int(ok2.sum())
            ctl_kind = f"limit {edge:.2f}xATR"
            # bootstrap the difference rather than a permutation: the two samples overlap
            pv = _boot_p(t.R.to_numpy(), t2.R.to_numpy(), rng)
        else:
            ctl = []
            for _ in range(200):
                eb2, px2 = tap_random_wait(d, sig[ok], side[ok], a[ok], waits=waits, rng=rng)
                t2 = walk(d, a[ok], eb2, side[ok], mult, entry_px=px2)
                if len(t2):
                    ctl.append(t2.R.mean())
            ctl = np.array(ctl)
            ctlR = float(ctl.mean()) if len(ctl) else np.nan
            ctl_n = int(ok.sum())
            ctl_kind = "random wait"
            pv = float((ctl >= t.R.mean()).mean()) if len(ctl) else np.nan
        rows.append(dict(tap=name, win_bars=w, taken=int(ok.sum()), rate=float(ok.mean()),
                         med_wait=float(np.median(waits)), edge_atr=float(edge),
                         R=float(t.R.mean()), pf=_pf(t), winr=float((t.pnl > 0).mean()),
                         ctlR=ctlR, ctl_n=ctl_n, ctl_kind=ctl_kind, p=pv))

    for w in windows:
        for nm, ln in lines.items():
            add(f"touch {nm}", w, *tap_touch(d, sig, side, a, line=ln, window=w))
        for nm, (f, s) in pairs.items():
            add(f"cross {nm}", w, *tap_cross(d, sig, side, a, fast=f, slow=s, window=w))
        add("reclaim KAMA 9", w, *tap_reclaim(d, sig, side, a, line=K9, window=w))
        add(f"fixed wait {w}", w, *tap_fixed_wait(d, sig, side, a, wait=w))

    R = pd.DataFrame(rows)
    if verbose:
        print(f"\n  {tf}m {block}: {len(sig)} breakout signals, 3xATR trail, MNQ costs")
        print(f"  {'tap':<26}{'w':>3}{'taken':>7}{'rate':>6}{'fill+ATR':>10}"
              f"{'R':>9}{'control':<17}{'ctl R':>9}{'p':>7}{'win':>7}{'PF':>6}")
        for r in R.itertuples():
            ck = getattr(r, "ctl_kind", "")
            print(f"  {r.tap:<26}{r.win_bars:>3}{r.taken:>7}{100*r.rate:>5.0f}%"
                  f"{r.edge_atr:>+10.3f}{r.R:>+9.4f}  {ck if isinstance(ck,str) else '':<15}"
                  f"{('%+.4f' % r.ctlR) if np.isfinite(r.ctlR) else '--':>9}"
                  f"{('%.3f' % r.p) if np.isfinite(r.p) else '--':>7}"
                  f"{100*r.winr:>6.1f}%{r.pf:>6.2f}")
    return R


def _boot_p(a, b, rng, draws=4000):
    """P(control mean >= tap mean) under independent resampling of the two R samples."""
    if len(a) < 5 or len(b) < 5:
        return np.nan
    da = rng.choice(a, (draws, len(a))).mean(axis=1)
    db = rng.choice(b, (draws, len(b))).mean(axis=1)
    return float((db >= da).mean())


def _pf(t):
    gp = t.pnl[t.pnl > 0].sum(); gl = -t.pnl[t.pnl < 0].sum()
    return float(gp / gl) if gl > 0 else np.inf


# ---------------------------------------------------------------------------------------------
# Q1: the crossover as a TRIGGER of its own, with no Donchian breakout underneath it.
# ---------------------------------------------------------------------------------------------

def as_trigger(tf=30, mult=3.0, block="research", draws=1500, verbose=True):
    """Every crossover fired on its own, scored against the same matched control as everything else."""
    d, si, cut = sweep.blocks(tf)
    c, h, l = d["c"], d["h"], d["l"]
    atrv = dcs.wilder_atr(h, l, c, 14)
    m = (si < cut) if block == "research" else (si >= cut)
    K9 = T.kama(c, 9)
    pairs = {
        "KAMA 9 x price":  (c, K9),
        "KAMA 9 x KAMA 21": (K9, T.kama(c, 21)),
        "KAMA 9 x KAMA 30": (K9, T.kama(c, 30)),
        "KAMA 9 x KAMA 50": (K9, T.kama(c, 50)),
        "KAMA 9 x EMA 21":  (K9, I.ema(c, 21)),
        "KAMA 9 x EMA 50":  (K9, I.ema(c, 50)),
        "KAMA 9 x SMA 20":  (K9, I.sma(c, 20)),
        "EMA 9 x EMA 21":   (I.ema(c, 9), I.ema(c, 21)),
        "EMA 9 x SMA 20":   (I.ema(c, 9), I.sma(c, 20)),
        "EMA 50 x EMA 200": (I.ema(c, 50), I.ema(c, 200)),
        "HULL 9 x HULL 21": (T.hull(c, 9), T.hull(c, 21)),
        "TEMA 9 x TEMA 21": (T.tema(c, 9), T.tema(c, 21)),
    }
    rows = []
    for nm, (f, s) in pairs.items():
        fin = np.isfinite(f) & np.isfinite(s)
        up = (f > s) & (I.shift(f, 1) <= I.shift(s, 1)) & fin & m
        dn = (f < s) & (I.shift(f, 1) >= I.shift(s, 1)) & fin & m
        t = dcs.run(d, up, dn, atrv, mult=mult, cost=RT)
        if not len(t):
            continue
        ctl = sweep.control_fast(d, atrv, up, dn, mult, m, draws=draws, match_risk=True)
        r = float(t.R.mean())
        rows.append(dict(cross=nm, n=len(t), per=float(t.pnl.mean()), R=r,
                         ctl=float(ctl.mean()) if ctl is not None else np.nan,
                         p=float((ctl >= r).mean()) if ctl is not None else np.nan,
                         win=float((t.pnl > 0).mean()), pf=_pf(t)))
    R = pd.DataFrame(rows).sort_values("R", ascending=False)
    if verbose:
        print(f"\n  {tf}m {block}: crossover as the trigger, {mult}xATR trail, MNQ costs")
        print(f"  {'crossover':<20}{'n':>7}{'pts/tr':>9}{'R':>9}{'ctl':>9}{'excess':>9}"
              f"{'p':>7}{'win':>7}{'PF':>6}")
        for r in R.itertuples():
            print(f"  {r.cross:<20}{r.n:>7,}{r.per:>+9.2f}{r.R:>+9.4f}{r.ctl:>+9.4f}"
                  f"{r.R - r.ctl:>+9.4f}{r.p:>7.3f}{100*r.win:>6.1f}%{r.pf:>6.2f}")
    return R
