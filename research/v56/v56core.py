"""V56 -- ADX and an ATR take profit added, and TWO ORDER MODELS so the script can be PROVED to
match the research rather than assumed to.

WHY TWO MODELS. `STUDY_PINE_PARITY` is unambiguous on this branch: a Pine port cannot be asserted by
reading it. `TURTLE_4_FINALISTS` was transcribed line by line, read back twice, shipped lint-clean --
and three rules were wrong, found only by running the script's own order model in Python against the
engine. The gap there was 1.5-2x the engine's points per trade with NO rule differing.

The two models here differ in four places, every one of them a real property of Pine and not a
choice:

  1. NO EXIT ORDER IS LIVE DURING THE ENTRY BAR. `strategy.exit` is called at the close of a bar on
     which a position already exists. The entry fills at the open of bar a, and the first
     `strategy.exit` for it is placed at the CLOSE of bar a -- so it can only trigger from bar a+1.
     The engine checks the barrier from bar a itself.
  2. THE WORKING LEVEL IS ONE BAR STALE. A level computed at the close of bar j is live during bar
     j+1. The engine evaluates the level at bar j and applies it during bar j.
  3. THE RISK IS ANCHORED TO THE FILL BAR'S ATR, not the signal bar's. Pine reads `atrN` at the
     close of the bar on which the position first exists, which is the fill bar. The engine uses the
     signal bar's ATR, which is the only one knowable when the order is sent.
  4. A TIME EXIT FILLS AT THE NEXT BAR'S OPEN. `strategy.close_all()` cannot sell the close of the
     bar that triggers it.

Neither model is "right" in the abstract: the ENGINE model is the one the research measured and the
one whose ATR anchor is causally honest; the PINE model is what the script will actually do on
TradingView. Both are reported, and the difference between them is the number that matters.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit


@njit(cache=True)
def walk(o, h, l, c, atr, sig, exit_lo, stop_mult, tp_atr, cost, slip, max_hold, pine):
    """One walker, two conventions. `pine=1` reproduces the script's order model exactly."""
    n = len(sig)
    m = len(c)
    xb = np.full(n, -1, np.int64)
    R = np.full(n, np.nan)
    reason = np.zeros(n, np.int64)          # 0 stop/channel, 1 target, 2 max hold
    for k in range(n):
        i = sig[k]
        a = i + 1
        if a < 2 or a >= m - 2:
            continue
        anchor = atr[a] if pine == 1 else atr[i]        # pine==2 uses the SIGNAL bar, like the engine
        if not np.isfinite(anchor) or anchor <= 0:
            continue
        px = o[a] + slip
        risk = stop_mult * anchor
        fixed = px - risk
        tgt = px + tp_atr * anchor if tp_atr > 0.0 else 1e18
        end = a + max_hold
        if end > m - 2:
            end = m - 2
        out = np.nan
        rs = 2
        # pine==0 engine: level evaluated at bar j, live at bar j, checked from the entry bar.
        # pine==1 script v1: level one bar stale, and no exit order live during the entry bar.
        # pine==2 script v2: the exit is placed at the SIGNAL bar from the signal close, so it IS
        #                    live during the entry bar; from then on it is still one bar stale,
        #                    which is inherent to Pine and cannot be removed.
        j = a + 1 if pine == 1 else a
        while j <= end:
            if pine == 0:
                ch = exit_lo[j]
                cap = c[j - 1]
            elif j == a:
                # On the entry bar the script has only a FILL-RELATIVE bracket (`strategy.exit`
                # with `loss`/`profit` in ticks, placed at the signal bar). That is the pure ATR
                # stop -- no channel and no prior-close cap, because neither is expressible before
                # the fill price exists.
                ch = -1e18
                cap = 1e18
            else:
                ch = exit_lo[j - 1]
                cap = c[j - 2]
            lvl = fixed
            if np.isfinite(ch) and ch > lvl:
                lvl = ch
            if np.isfinite(cap) and lvl > cap:
                lvl = cap
            if l[j] <= lvl:
                fill = lvl if o[j] > lvl else o[j]
                out = fill - slip
                rs = 0
                break
            if h[j] >= tgt:
                fill = tgt if o[j] < tgt else o[j]
                out = fill - slip
                rs = 1
                break
            j += 1
        if not np.isfinite(out):
            if pine == 1:
                j = end + 1 if end + 1 <= m - 1 else end
                out = o[j] - slip          # a time exit fills at the NEXT bar's open
            else:
                j = end
                out = c[j] - slip
            rs = 2
        xb[k] = j
        R[k] = (out - px - cost) / risk
        reason[k] = rs
    return xb, R, reason


def dmi_adx(h, l, c, n=14):
    """Wilder's ADX. `ta.dmi` returns [+DI, -DI, ADX]; taking the first element substitutes +DI."""
    up = np.diff(h, prepend=h[0])
    dn = -np.diff(l, prepend=l[0])
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))

    def rma(x):
        return pd.Series(x).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()

    a = rma(tr)
    with np.errstate(invalid="ignore", divide="ignore"):
        pdi = 100.0 * rma(plus) / np.where(a > 0, a, np.nan)
        mdi = 100.0 * rma(minus) / np.where(a > 0, a, np.nan)
        dx = 100.0 * np.abs(pdi - mdi) / np.where((pdi + mdi) > 0, pdi + mdi, np.nan)
    return rma(np.nan_to_num(dx))
