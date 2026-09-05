"""The Initial Balance, reverse-engineered as a MECHANISM and generalised to every hour.

WHAT IS ACTUALLY BEING ASKED. `research/ib_features.py` already settled the strategy question: 14
causal IB features x 8 pre-declared candidates, matched control as the gate, BH at FDR 0.10 -- 3
passed research, 2 LOST money on the holdout, the third decayed to the do-nothing baseline, and
M4's own condition restated at day scale failed its research control at p 0.305. So "why does the
IB strategy work" has no subject.

The question underneath it does. The Initial Balance is ONE ARBITRARY WINDOW -- 09:30 to 10:30 --
and no one here has asked whether the thing it is supposed to measure exists at other hours, or
whether 09:30 is special at all. That is a mechanism question with a decomposable structure, and it
is answerable without another parameter search.

THE MECHANISM, STATED SO IT CAN FAIL. A window W forms a range. Three things can follow:
    BREAKOUT   price leaves the range and extends
    REVERSION  price leaves the range and comes back (the "80% rule" / failed break)
    NOTHING    the range carries no information about what follows
The literature asserts the first two conditionally. This branch has already measured the 80% rule
at 50.6% against a TIME-MATCHED CONTROL's 59.9% -- i.e. the rule is WORSE than the control, which
is the shape of "nothing".

THE CONTROL IS THE WHOLE DESIGN. "Price moves after 10:30" is not a finding; every hour is
followed by movement. The null here is A WINDOW OF THE SAME LENGTH STARTING AT A RANDOM TIME IN THE
SAME SESSION, with the same amount of session left after it. That holds range width, volatility,
time-of-day drift and time-remaining fixed, and asks the only question that matters: does THIS
window's range predict better than ANY window's range?

CAUSALITY. Every feature is computed from bars inside W and closes at W's end. The signal bar is
the last bar of W; a trade fills at the NEXT bar's open. Rolling normalisations are shifted by one
session so a day is never inside its own baseline. Nothing reads a bar that has not closed.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
import indicators as I        # noqa: E402

TF = 5
RTH_OPEN, RTH_CLOSE = 570, 960          # 09:30 - 16:00 New York
FLAT = 955                              # positions flat at 15:55
STOP_MULT = 2.0
SPLIT = 0.65
MIN_TAIL = 60                           # minutes of session that must remain after a window


def bars(tf=TF):
    import fastbars
    b = fastbars.bars(tf)
    atr = I.ema(I.true_range(b["h"], b["l"], b["c"]), 14)
    return dict(o=b["o"], h=b["h"], l=b["l"], c=b["c"], v=b["v"], mod=b["mod"],
                sess=b["sess"], ts=b["ts"], atr=atr)


def blocks(sess):
    u = np.unique(sess)
    cut = u[int(len(u) * SPLIT)]
    return sess < cut, sess >= cut


# ------------------------------------------------------------------------------------------------
# the window table
# ------------------------------------------------------------------------------------------------
def window_table(d, start, length):
    """One row per session for the window [start, start+length). Features close at the window's
    end; outcomes are measured strictly after it, to the 15:55 flatten."""
    mod, sess, o, h, l, c, v, atr = (d["mod"], d["sess"], d["o"], d["h"], d["l"], d["c"],
                                     d["v"], d["atr"])
    end = start + length
    if end + MIN_TAIL > RTH_CLOSE:
        return None
    rows = []
    for s in np.unique(sess):
        day = np.flatnonzero(sess == s)
        if len(day) < 20:
            continue
        w = day[(mod[day] >= start) & (mod[day] < end)]
        post = day[(mod[day] >= end) & (mod[day] < FLAT)]
        if len(w) < max(3, length // TF - 1) or len(post) < 6:
            continue
        k = w[-1]
        if not np.isfinite(atr[k]) or atr[k] <= 0:
            continue
        wh, wl = h[w].max(), l[w].min()
        rng = wh - wl
        if rng <= 0:
            continue
        wo, wc = o[w[0]], c[k]
        half = len(w) // 2
        # --- where and when the extremes formed, inside the window ---
        i_hi, i_lo = int(np.argmax(h[w])), int(np.argmin(l[w]))
        # --- edge touches: bars whose extreme sits in the top/bottom 15% of the range ---
        band = 0.15 * rng
        touch_hi = int((h[w] >= wh - band).sum())
        touch_lo = int((l[w] <= wl + band).sum())
        vol = v[w].astype(float)
        up = vol[np.r_[True, np.diff(c[w]) > 0][:len(w)]].sum()
        dn = vol[np.r_[True, np.diff(c[w]) < 0][:len(w)]].sum()
        vwap = float((((h[w] + l[w] + c[w]) / 3.0) * vol).sum() / max(vol.sum(), 1e-9))
        prev_close = c[day[0] - 1] if day[0] > 0 else np.nan
        rows.append(dict(
            sess=s, sig=k, w_hi=wh, w_lo=wl, rng=rng, atr=atr[k],
            # ---- 24 causal window features, all scale-free ----
            f_rng_atr=rng / atr[k],
            f_close_pos=(wc - wl) / rng,
            f_open_pos=(wo - wl) / rng,
            f_body=(wc - wo) / rng,
            f_dir=float(np.sign(wc - wo)),
            f_upwick=(wh - max(wo, wc)) / rng,
            f_dnwick=(min(wo, wc) - wl) / rng,
            f_hi_when=i_hi / max(len(w) - 1, 1),
            f_lo_when=i_lo / max(len(w) - 1, 1),
            f_extreme_order=float(np.sign(i_hi - i_lo)),
            f_touch_hi=touch_hi / len(w),
            f_touch_lo=touch_lo / len(w),
            f_touch_bal=(touch_hi - touch_lo) / len(w),
            f_vol_bal=(up - dn) / max(up + dn, 1e-9),
            f_vol_2h=vol[half:].sum() / max(vol.sum(), 1e-9),
            f_vwap_pos=(vwap - wl) / rng,
            f_close_vs_vwap=(wc - vwap) / atr[k],
            f_eff=abs(wc - wo) / max(np.abs(np.diff(c[w])).sum(), 1e-9),
            f_maxbar=float(np.max(h[w] - l[w]) / rng),
            f_gap=(wo - prev_close) / atr[k] if np.isfinite(prev_close) else 0.0,
            f_atr_z=atr[k] / max(I.sma(atr, 100)[k], 1e-9),
            f_bars=len(w),
            wvol=vol.sum(), post0=post[0], postn=post[-1]))
    T = pd.DataFrame(rows)
    if len(T) < 60:
        return None
    # trailing normalisations, today EXCLUDED from its own baseline
    for col in ("f_rng_atr", "wvol"):
        T["z_" + col] = T[col] / T[col].shift(1).rolling(20).mean()
    T["z_prev_rng"] = T["f_rng_atr"].shift(1)
    return T.dropna().reset_index(drop=True)


# ------------------------------------------------------------------------------------------------
# what happens after the window
# ------------------------------------------------------------------------------------------------
def outcomes(d, T):
    """First break, extension, reversion, and the R of a break trade. All measured strictly after
    the window closes, and everything is flat by 15:55."""
    h, l, c, o, atr = d["h"], d["l"], d["c"], d["o"], d["atr"]
    n = len(T)
    brk = np.zeros(n); ext = np.zeros(n); back = np.zeros(n)
    R = np.full(n, np.nan); held = np.zeros(n)
    for i, r in enumerate(T.itertuples()):
        a, b = int(r.post0), int(r.postn)
        hi, lo, A = r.w_hi, r.w_lo, r.atr
        up = np.flatnonzero(h[a:b + 1] > hi)
        dn = np.flatnonzero(l[a:b + 1] < lo)
        iu = up[0] if len(up) else 10 ** 9
        idn = dn[0] if len(dn) else 10 ** 9
        if iu == idn == 10 ** 9:
            brk[i] = 0
            continue
        side = 1 if iu < idn else -1
        brk[i] = side
        j = a + min(iu, idn)
        edge = hi if side > 0 else lo
        seg = slice(j, b + 1)
        # extension beyond the broken edge, in ATR, over the rest of the session
        ext[i] = (h[seg].max() - edge) / A if side > 0 else (edge - l[seg].min()) / A
        # reversion: did price come back INSIDE the range after breaking
        back[i] = 1.0 if (l[seg].min() < hi if side > 0 else h[seg].max() > lo) else 0.0
        # the break trade: fill at the next bar's open, 2N stop, flat at the session end
        e = j + 1
        if e > b:
            continue
        px = o[e]
        st = px - side * STOP_MULT * A
        out = None
        for k in range(e, b + 1):
            if (l[k] <= st) if side > 0 else (h[k] >= st):
                out = st; held[i] = k - e; break
        if out is None:
            out = c[b]; held[i] = b - e
        R[i] = side * (out - px) / (STOP_MULT * A)
    T = T.copy()
    T["brk"], T["ext"], T["back"], T["R"], T["held"] = brk, ext, back, R, held
    return T


# ------------------------------------------------------------------------------------------------
# the control: the SAME LENGTH window at a RANDOM time in the SAME session
# ------------------------------------------------------------------------------------------------
def control_table(d, length, seed=11, draws=1):
    """A window of identical length starting at a random eligible minute of the same session, with
    the same minimum tail remaining. Holds range width, volatility, drift and time-remaining fixed
    and asks whether THIS window's range predicts better than ANY window's range."""
    rng = np.random.default_rng(seed)
    starts = np.arange(RTH_OPEN, RTH_CLOSE - length - MIN_TAIL + 1, TF)
    out = []
    for _ in range(draws):
        s = int(rng.choice(starts))
        T = window_table(d, s, length)
        if T is not None:
            out.append(outcomes(d, T).assign(_ctrl_start=s))
    return pd.concat(out, ignore_index=True) if out else None
