"""The shipped Pine's own logic, in Python, diffed against `cmma_core`.

`CLAUDE.md`: a Pine port cannot be asserted by reading it. This module re-implements what the
script actually does -- accumulate daily bars from intraday bars on New York calendar boundaries,
Wilder ATR by recurrence, SMA and the efficiency ratio from a rolling array, an EMA by recurrence,
finalise at the midnight rollover, round the continuous target to whole contracts and hold it
through the session -- with no pandas resampling and no shared code path. Then it diffs.

WHERE THE TWO ARE EXPECTED TO DIFFER, declared in advance:

  * INTEGER CONTRACTS. The engine holds a fractional target; Pine cannot. This is the only
    approved difference and its cost is measured across base sizes rather than assumed.
  * WARM-UP. The engine's pandas windows produce NaN until they fill; the script's array fills
    from the first bar on the chart, so the first ~26 daily bars can differ if the chart begins
    mid-history.

Everything else must agree: the same daily closes, the same signal to floating point, the same
trading dates.

Usage: python3 research/cmma/cmma_parity.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmma_core as C            # noqa: E402


def pine_logic(f, ma_len=5, atr_len=5, ker_len=21, com=2.0, use_tanh=True, use_ker=True):
    """Exactly what the script does, bar by bar. `time` in Pine is the bar's OPEN, and this feed
    is close-stamped, so the day id is taken from the stamp shifted back one bar-width -- which is
    what makes the script's midnight boundary identical to the notebook's `closed='right'` bin."""
    step = pd.Series(f.index).diff().median()
    open_time = f.index - step
    day_id = pd.DatetimeIndex(open_time).normalize()

    o = f["open"].to_numpy()
    h = f["high"].to_numpy()
    l = f["low"].to_numpy()
    c = f["close"].to_numpy()
    d_id = day_id.to_numpy()

    closes = []
    atr = np.nan
    prev_c = np.nan
    sig_ema = np.nan
    live = {}                                    # trading date -> signal traded that day
    cur = None
    dH = dL = dC = np.nan
    for i in range(len(c)):
        if cur is not None and d_id[i] != cur:
            tr = (dH - dL if np.isnan(prev_c)
                  else max(dH - dL, abs(dH - prev_c), abs(dL - prev_c)))
            atr = tr if np.isnan(atr) else atr + (tr - atr) / atr_len
            closes.append(dC)
            if len(closes) > ker_len + 8:
                closes.pop(0)
            n = len(closes)
            if n >= ma_len and n >= ker_len + 1 and np.isfinite(atr) and atr > 0:
                ma = float(np.mean(closes[-ma_len:]))
                cmma = (dC - ma) / atr
                bounded = np.tanh(cmma) if use_tanh else cmma
                den = float(np.sum(np.abs(np.diff(closes[-(ker_len + 1):]))))
                ker = abs(dC - closes[-(ker_len + 1)]) / den if den > 0 else 0.0
                raw = (ker if use_ker else 1.0) * (-bounded)
                a = 1.0 / (1.0 + com)
                sig_ema = raw if np.isnan(sig_ema) else sig_ema + a * (raw - sig_ema)
                live[pd.Timestamp(d_id[i]).date()] = sig_ema
            prev_c = dC
            cur = d_id[i]
            dH, dL, dC = h[i], l[i], c[i]
        elif cur is None:
            cur = d_id[i]
            dH, dL, dC = h[i], l[i], c[i]
        else:
            dH = max(dH, h[i])
            dL = min(dL, l[i])
            dC = c[i]
    return pd.Series(live).sort_index()


def main(market="NQ", contracts=50, use_tanh=False, smooth=0.0):
    """Defaults are the SHIPPED configuration (candidate C: no tanh, no EMA smoothing). Pass
    use_tanh=True, smooth=2.0 to check the notebook's original."""
    print("=" * 100)
    print("CMMA PINE PARITY -- the script's own logic against the research engine")
    print(f"  configuration: tanh {'on' if use_tanh else 'OFF'}, EMA com {smooth}")
    print("=" * 100)
    f = C.load_intraday(market)
    d = C.daily_from_intraday(f)
    eng = C.signal(d, use_tanh=use_tanh, smooth=smooth)
    pin = pine_logic(f, com=smooth, use_tanh=use_tanh)
    pin.index = pd.DatetimeIndex(pin.index)
    eng.index = pd.DatetimeIndex(eng.index)
    both = eng.index.intersection(pin.index)
    a, b = eng.reindex(both), pin.reindex(both)
    ok = np.isfinite(a) & np.isfinite(b)
    diff = (a[ok] - b[ok]).abs()
    print(f"  {market}: engine {len(eng)} signal days, script {len(pin)}, shared {int(ok.sum())}")
    print(f"  signal agreement: max |diff| {diff.max():.3e}, mean {diff.mean():.3e}, "
          f"correlation {np.corrcoef(a[ok], b[ok])[0, 1]:.10f}")
    print(f"  within 1e-9 on {(diff < 1e-9).mean() * 100:.2f}% of shared days")

    # `session_pnl` matches on plain dates, so hand it the same index type it builds internally
    eng_d = pd.Series(eng.to_numpy(), index=[t.date() for t in eng.index])
    pin_d = pd.Series(pin.to_numpy(), index=[t.date() for t in pin.index])
    pe = C.session_pnl(f, eng_d, mode="endpoints")
    pp = C.session_pnl(f, pin_d, mode="endpoints")
    j = pe.index.intersection(pp.index)
    print(f"\n  daily P&L, fractional target: engine {pe['net'].loc[j].sum():+.1f} pts, "
          f"script {pp['net'].loc[j].sum():+.1f} pts over {len(j)} shared days")

    px0 = float(d["close"].iloc[0])

    def sh(x):
        r = x / px0
        return r.mean() / r.std() * np.sqrt(252)
    q = np.round(pp["sig"].loc[j] * contracts) / contracts
    turn = q.diff().abs().fillna(q.abs())
    net = q * pp["move"].loc[j] - turn * C.COST_PER_ROUND_TURN_PTS
    print(f"  script AS SHIPPED (rounded to {contracts} contracts at full signal, per contract-"
          f"equivalent): {net.mean():+.3f} pts/day, Sharpe {sh(net):+.2f}, "
          f"{int((q != 0).sum())} days with a position")
    print(f"  engine, fractional:                                              "
          f"{pe['net'].loc[j].mean():+.3f} pts/day, Sharpe {sh(pe['net'].loc[j]):+.2f}, "
          f"{len(j)} days")
    print("\n  The signal series must agree to floating point; the P&L may differ only by the")
    print("  integer-contract rounding, which is the one difference the port is allowed.")


if __name__ == "__main__":
    mk = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    main(mk)                                   # as shipped
    main(mk, use_tanh=True, smooth=2.0)        # the notebook's original
