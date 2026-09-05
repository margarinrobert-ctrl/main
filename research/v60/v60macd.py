"""V60 part seven: does the MACD do anything to this breakout, and which reading?

THE QUESTION IS NOT "IS MACD ANY GOOD". It is the one `STUDY_V16_MOMENTUM.md` and
`STUDY_V60_AROON.md` both answer the same way: A MOMENTUM FILTER CANNOT IMPROVE A BREAKOUT,
BECAUSE A BREAKOUT IS A MOMENTUM EVENT. RSI(14) >= 55 already passes 94.7% of breakout bars;
`aroon osc >= 0` passes 100.0% of them by construction. So the FIRST number for any proposed
confirmation is its BASE RATE ON THE TRIGGER'S OWN BARS -- a filter that passes 95% of signals
cannot change a strategy no matter what its P&L column says.

Eight readings of the MACD are tested, because "add the MACD" is not one condition:

  hist > 0              the classic: MACD above its signal line
  macd > 0              the oscillator above zero, i.e. fast MA above slow
  hist > 0 and macd > 0 both at once
  hist rising           hist > hist[1], the histogram's own slope
  hist > 0 and rising   the two-bar version people actually trade
  hist cross up <= N    a FRESH bullish cross within N bars -- a recency condition, not a state
  macd > 0 at prior bar the zero-line state one bar BEFORE the signal
  hist > 0 at prior bar  the same for the histogram

THE PRIOR-BAR READINGS ARE HERE FOR THE REASON `STUDY_V60_AROON.md` established: a condition read
on the breakout bar can be partly determined BY the breakout. The MACD is not an identity the way
Aroon is -- it is a difference of two exponential averages, not a channel position -- but the same
diagnostic applies and costs nothing to run.

The MA TYPE axis (EMA vs SMA at the same lengths) is included as a control, not as a hope.
`STUDY_MA_LAG.md`: MA type is not a degree of freedom, MA LAG is. If the EMA and SMA columns differ
much at matched lengths, something is wrong with one of them.

Usage: python3 research/v60/v60macd.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "v38"))
sys.path.insert(0, os.path.join(HERE, "..", "v39"))

import indicators as I          # noqa: E402
import v60core as V             # noqa: E402
from v60_parity import PRESETS, available     # noqa: E402
from v60session import score                  # noqa: E402

FASTS = (12,)
SLOWS = (26,)
SIGS = (9,)
GRID = [(12, 26, 9), (8, 21, 5), (19, 39, 9)]     # the brief's, and one rung either side
CROSS_WIN = 10


def macd_series(c, fast, slow, sig, ma_type="EMA"):
    """MACD line, signal and histogram, matching the reference indicator exactly.

    `ma()` in the source switches between ta.ema and ta.sma for BOTH the oscillator and the signal,
    and both switches are independent -- so both are parameters here.
    """
    f = I.ema(c, fast) if ma_type == "EMA" else I.sma(c, fast)
    s = I.ema(c, slow) if ma_type == "EMA" else I.sma(c, slow)
    line = f - s
    sg = I.ema(line, sig) if ma_type == "EMA" else I.sma(line, sig)
    return line, sg, line - sg


def _since(flag):
    out = np.full(len(flag), -1, np.int64)
    last = -1
    for i in range(len(flag)):
        if flag[i]:
            last = i
        out[i] = i - last if last >= 0 else -1
    return out


def conditions(c, fast, slow, sig, ma_type="EMA"):
    line, sg, hist = macd_series(c, fast, slow, sig, ma_type)
    prev = np.r_[np.nan, hist[:-1]]
    rising = hist > prev
    crossup = np.r_[False, (hist[1:] > 0) & (hist[:-1] <= 0)]
    since = _since(crossup)
    def lag(x):
        return np.r_[False, x[:-1]]
    return {
        "hist > 0": hist > 0,
        "macd > 0": line > 0,
        "hist > 0 and macd > 0": (hist > 0) & (line > 0),
        "hist rising": rising,
        "hist > 0 and rising": (hist > 0) & rising,
        f"fresh cross <= {CROSS_WIN}": (since >= 0) & (since <= CROSS_WIN),
        "macd > 0 @ prior bar": lag(line > 0),
        "hist > 0 @ prior bar": lag(hist > 0),
    }


def main():
    mks = available()
    print("=" * 104)
    print("13. THE MACD ON A DONCHIAN BREAKOUT -- base rate first, P&L second")
    print("=" * 104)
    print(f"  markets with bars on disk: {', '.join(mks) if mks else 'NONE'}")
    if not mks:
        return

    for mk in mks:
        P = V.prep(60, mk)
        c = P["c"]
        print(f"\n{'=' * 104}\n  {mk} 60m")
        for name, cfg in PRESETS.items():
            if name not in ("A - research top cell", "B - marginal consensus"):
                continue
            base = V.signal_mask(P, (cfg["mode"], cfg["ema_f"], cfg["ema_s"], cfg["win"],
                                     cfg["don_e"], cfg["gate"], 0, "off"))
            brk = P["brk"][cfg["don_e"]] & np.isfinite(P["atr"]) & (P["atr"] > 0)
            print(f"\n  --- {name}  (donchian {cfg['don_e']}/{cfg['don_x']}, "
                  f"{cfg['stop']}N, {cfg['gate']})")
            print(f"  {'condition':<26}{'all bars':>10}{'on brk':>9}{'on sig':>9}"
                  f"{'res n':>7}{'res pts':>10}{'res PF':>8}"
                  f"{'lock n':>8}{'lock pts':>10}{'lock PF':>9}")
            (rn, rp, rf), (ln, lp, lf) = score(P, cfg, base)
            print(f"  {'(no MACD condition)':<26}{'--':>10}{'--':>9}{'--':>9}"
                  f"{rn:>7d}{rp:>+10.2f}{rf:>8.2f}{ln:>8d}{lp:>+10.2f}{lf:>9.2f}")
            for f_, s_, g_ in GRID:
                C = conditions(c, f_, s_, g_)
                print(f"  MACD {f_}/{s_}/{g_}")
                for cn, cm in C.items():
                    ok = np.isfinite(cm.astype(float))
                    m = base & cm
                    (rn, rp, rf), (ln, lp, lf) = score(P, cfg, m)
                    print(f"    {cn:<24}{cm.mean() * 100:>9.1f}%"
                          f"{(cm & brk).sum() / max(brk.sum(), 1) * 100:>8.1f}%"
                          f"{(cm & base).sum() / max(base.sum(), 1) * 100:>8.1f}%"
                          f"{rn:>7d}{rp:>+10.2f}{rf:>8.2f}{ln:>8d}{lp:>+10.2f}{lf:>9.2f}")

        # the MA-type control, on the brief's own lengths
        print(f"\n  --- {mk}: EMA vs SMA at 12/26/9 -- the MA-TYPE CONTROL, not a hope")
        cfg = PRESETS["A - research top cell"]
        base = V.signal_mask(P, (cfg["mode"], cfg["ema_f"], cfg["ema_s"], cfg["win"],
                                 cfg["don_e"], cfg["gate"], 0, "off"))
        print(f"  {'condition':<26}{'type':<6}{'on sig':>9}{'res n':>7}{'res pts':>10}"
              f"{'lock n':>8}{'lock pts':>10}{'overlap vs EMA':>16}")
        ce = conditions(c, 12, 26, 9, "EMA")
        cs = conditions(c, 12, 26, 9, "SMA")
        for cn in ("hist > 0", "macd > 0", "hist > 0 and rising"):
            for tn, C in (("EMA", ce), ("SMA", cs)):
                m = base & C[cn]
                (rn, rp, _), (ln, lp, _) = score(P, cfg, m)
                ov = (C[cn] == ce[cn]).mean() * 100
                print(f"  {cn:<26}{tn:<6}{(C[cn] & base).sum() / max(base.sum(), 1) * 100:>8.1f}%"
                      f"{rn:>7d}{rp:>+10.2f}{ln:>8d}{lp:>+10.2f}{ov:>15.1f}%")


if __name__ == "__main__":
    main()
