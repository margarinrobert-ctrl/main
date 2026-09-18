"""V60 part five: the SHIPPED PINE's own order model, in Python, diffed against the engine.

`CLAUDE.md`: a Pine port cannot be asserted by reading it. `STUDY_PINE_PARITY.md` found three wrong
rules in a script that was transcribed line by line, read back twice and shipped lint-clean;
`STUDY_V56` found an exit-bar marker updating BELOW the entry block, worth 95 extra trades, that
reading could not see. So the shipped script's order model is written out here as its own walk and
run against `v38grid`'s tensor on identical bars.

WHERE THE TWO ARE EXPECTED TO DIFFER, declared in advance so a surprise is a finding and not a
rediscovery:

  1. THE CHANNEL EXIT'S FILL. The engine sells at the CLOSE of the bar whose close breaks the
     channel. A script cannot: `strategy.close()` submits at that close and fills at the NEXT
     bar's open. This is the same `flat_open` correction this branch already made for the
     fixed-time flatten, and `v60_vbt.py` measures it independently at 1.9-10.3 points a trade.
  2. RE-ENTRY AFTER A CHANNEL EXIT. The engine frees the position lock ON the exit bar, so a signal
     at that bar is eligible. The script is still in the position at that bar's close, so its
     earliest re-entry is one bar later.
  3. TICK ROUNDING. The bracket is placed as an integer number of ticks from the fill.

Everything else must agree: the same signal bars, the same fill bar, a stop live on the entry bar,
and the ATR read at the SIGNAL bar rather than the fill bar.

Usage: python3 research/v60/v60_parity.py
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
import v38grid as G             # noqa: E402
import v39mc as MC              # noqa: E402
from run_v60 import MARKETS      # noqa: E402


def available():
    """Only the markets whose bars are on disk. A container recycle wipes the uploaded feeds, so
    this is checked rather than assumed -- a parity harness that dies on a missing CSV tells you
    nothing about the markets you DO have."""
    out = []
    for mk in MARKETS:
        try:
            V.load_market(mk, 60)
            out.append(mk)
        except Exception:
            pass
    return out

BASE_A = dict(mode="cross", ema_f=21, ema_s=62, win=40, don_e=10, don_x=10,
              stop=3.0, tp=0.0, gate="adx>=20", aroon="off", aroon_n=25)
BASE_B = dict(mode="cross", ema_f=21, ema_s=62, win=40, don_e=55, don_x=20,
              stop=3.0, tp=0.0, gate="chop<=45", aroon="off", aroon_n=25)

# The two shipped presets, plus the three OPTIONAL features, each turned on alone so a parity
# failure names one feature rather than a combination.
PRESETS = {
    "A - research top cell": BASE_A,
    "B - marginal consensus": BASE_B,
    "A + aroon up>=70 at the PRIOR bar": dict(BASE_A, aroon="up>=70", aroon_at="prior"),
    "A + entry window 09:30-16:00 NY": dict(BASE_A, sess=(570, 960)),
    "A + hard flatten at 16:00 NY": dict(BASE_A, flat=960),
    "A + MACD 12/26/9 macd>0 at the PRIOR bar": dict(BASE_A, macd="macd > 0", macd_at="prior"),
    "B + MACD 12/26/9 macd>0 at the SIGNAL bar (inert)": dict(BASE_B, macd="macd > 0"),
}
TICK = {"NQ": 0.25, "US100L": 0.1, "US30L": 1.0}


def script_walk(P, cfg, tick, blk, tf=60):
    """The shipped Pine's order model, bar by bar, with nothing shared with the engine.

    One live position. Signal on a confirmed close; market entry at the next open; a fill-relative
    bracket in whole ticks placed WITH the entry, so the entry bar is protected; the channel exit
    tested only from the bar after the fill and filling at the NEXT open.
    """
    o, h, l, c, atr = P["o"], P["h"], P["l"], P["c"], P["atr"]
    n = P["n"]
    ex_lo = I.shift(I.rmin(l, cfg["don_x"]), 1)
    sig = V.signal_mask(P, (cfg["mode"], cfg["ema_f"], cfg["ema_s"], cfg["win"], cfg["don_e"],
                            cfg["gate"], 0, "off"))
    if cfg["aroon"] != "off":
        a = P["aroon"][cfg["aroon_n"]][cfg["aroon"]]
        if cfg.get("aroon_at") == "prior":
            a = np.r_[False, a[:-1]]         # the identity-breaking reading
        sig = sig & a
    if cfg.get("macd"):
        from v60macd import conditions
        cm = conditions(c, 12, 26, 9)[cfg["macd"]]
        if cfg.get("macd_at") == "prior":
            cm = np.r_[False, cm[:-1]]
        sig = sig & cm
    lo_m, hi_m = cfg.get("sess", (0, 1440))
    if lo_m > 0 or hi_m < 1440:
        sig = sig & (P["mod"] >= lo_m) & (P["mod"] < hi_m)
    flat_m = cfg.get("flat", 0)
    if flat_m:
        sig = sig & (P["mod"] + tf < flat_m)   # `not flatDue` guards the ENTRY too
    lo, hi = blk
    out = []
    i = lo
    while i < min(hi, n - 2):
        if not sig[i]:
            i += 1
            continue
        f = i + 1                                    # market order fills at the next open
        px = o[f]
        a = atr[i]                                   # ATR at the SIGNAL bar, as the script stores
        if not np.isfinite(a) or a <= 0:
            i += 1
            continue
        st_ticks = max(round(cfg["stop"] * a / tick), 1)
        st = px - st_ticks * tick
        tg = (px + max(round(cfg["tp"] * cfg["stop"] * a / tick), 1) * tick
              if cfg["tp"] > 0 else 1e18)
        j = f
        why = 0
        xp = np.nan
        while j <= min(f + G.MAX_HOLD, n - 1):
            if l[j] <= st:                           # the bracket is live on the fill bar
                xp = o[j] if o[j] < st else st
                why = 1
                break
            if h[j] >= tg:
                xp = o[j] if o[j] > tg else tg
                why = 2
                break
            if flat_m and P["mod"][j] + tf >= flat_m:
                if j + 1 >= n:
                    break
                xp = o[j + 1]                        # flat AT the cutoff bar's open
                why = 3
                j = j + 1
                break
            if j > f and np.isfinite(ex_lo[j]) and c[j] < ex_lo[j]:
                if j + 1 >= n:
                    break
                xp = o[j + 1]                        # strategy.close fills at the NEXT open
                why = 4
                j = j + 1
                break
            j += 1
        if why == 0:
            j = min(f + G.MAX_HOLD, n - 1)
            xp = c[j]
            why = 5
        out.append((i, f, j, why, px, xp))
        i = j + 1                                    # earliest re-entry is the bar AFTER the exit
    return out


def engine_walk(P, cfg, blk, tf=60):
    keep = (G.COMM, G.EC, G.SE)
    G.COMM, G.EC, G.SE = 0.0, 0.0, 0.0
    try:
        xb, pnl, why = G.tensor_stop(P, cfg["don_x"], cfg["stop"], cfg["tp"], cfg.get("flat", 0))
    finally:
        G.COMM, G.EC, G.SE = keep
    m = V.signal_mask(P, (cfg["mode"], cfg["ema_f"], cfg["ema_s"], cfg["win"], cfg["don_e"],
                          cfg["gate"], 0, "off"))
    if cfg["aroon"] != "off":
        a = P["aroon"][cfg["aroon_n"]][cfg["aroon"]]
        if cfg.get("aroon_at") == "prior":
            a = np.r_[False, a[:-1]]
        m = m & a
    if cfg.get("macd"):
        from v60macd import conditions
        cm = conditions(P["c"], 12, 26, 9)[cfg["macd"]]
        if cfg.get("macd_at") == "prior":
            cm = np.r_[False, cm[:-1]]
        m = m & cm
    lo_m, hi_m = cfg.get("sess", (0, 1440))
    if lo_m > 0 or hi_m < 1440:
        m = m & (P["mod"] >= lo_m) & (P["mod"] < hi_m)
    if cfg.get("flat", 0):
        m = m & (P["mod"] + tf < cfg["flat"])
    s = np.flatnonzero(m)
    s = s[(s >= blk[0]) & (s < blk[1])].astype(np.int64)
    p_, s_ = MC.gather(P, xb, pnl, s)
    return [(int(i), int(i) + 1, int(xb[i]), int(why[i]), float(P["o"][i + 1]),
             float(P["o"][i + 1] + p_[k] / P["pv"])) for k, i in enumerate(s_)]


def compare(a, b):
    """Match on the SIGNAL bar, which is the only field both models agree on by construction."""
    bm = {t[0]: t for t in b}
    both, only_a = [], 0
    for t in a:
        u = bm.pop(t[0], None)
        if u is None:
            only_a += 1
        else:
            both.append((t, u))
    return both, only_a, len(bm)


def main():
    print("=" * 108)
    print("11. PINE PARITY -- the shipped script's order model against the engine, GROSS")
    print("=" * 108)
    mks = available()
    print(f"  markets with bars on disk: {', '.join(mks) if mks else 'NONE'}")
    if not mks:
        return
    for name, cfg in PRESETS.items():
        print(f"\n  {name}: EMA {cfg['ema_f']}/{cfg['ema_s']} cross w{cfg['win']}, "
              f"don {cfg['don_e']}/{cfg['don_x']}, {cfg['stop']}N, "
              f"tp {'none' if cfg['tp'] == 0 else cfg['tp']}, {cfg['gate']}, aroon {cfg['aroon']}")
        print(f"  {'market':<8}{'block':<10}{'script':>8}{'engine':>8}{'count':>8}{'matched':>9}"
              f"{'same exit bar':>15}{'script pts':>12}{'engine pts':>12}{'gap':>9}")
        for mk in mks:
            P = V.prep(60, mk)
            cut = int(P["n"] * V.SPLIT)
            for bn, blk in (("research", (0, cut)), ("locked", (cut, P["n"]))):
                s = script_walk(P, cfg, TICK[mk], blk)
                e = engine_walk(P, cfg, blk)
                both, oa, ob = compare(s, e)
                if not both:
                    print(f"  {mk:<8}{bn:<10}{len(s):>8d}{len(e):>8d}   -- no matched trades --")
                    continue
                same = sum(1 for t, u in both if t[2] == u[2])
                sp = float(np.mean([t[5] - t[4] for t in s])) if s else np.nan
                ep = float(np.mean([u[5] - u[4] for u in e])) if e else np.nan
                agree = 100.0 * min(len(s), len(e)) / max(len(s), len(e), 1)
                print(f"  {mk:<8}{bn:<10}{len(s):>8d}{len(e):>8d}{agree:>7.1f}%{len(both):>9d}"
                      f"{100.0 * same / len(both):>14.1f}%{sp:>+12.2f}{ep:>+12.2f}"
                      f"{100.0 * (sp - ep) / abs(ep) if ep else np.nan:>+8.1f}%")
    print("\n  A NEGATIVE gap is the correct direction: the script gives back the channel exit's")
    print("  fill convention, which the engine takes for free. A POSITIVE gap would mean the")
    print("  script reads BETTER than the research, which is the shape STUDY_V56 had to fix.")


if __name__ == "__main__":
    main()
