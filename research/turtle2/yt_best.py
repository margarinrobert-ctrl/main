"""ONE Turtle with everything on it: MACD, Aroon, an entry window, a hard flatten and an ADX floor.

WHAT "BEST-MEASURED VALUES" MEANS HERE, because it is the only defensible reading. The defaults are
chosen on the IN-SAMPLE block ONLY and the out-of-sample block is read once, afterwards, for the
chosen cell. Selecting on the out-of-sample column would guarantee a good-looking table and mean
nothing -- and on this family it would be especially misleading, because every gate measured so far
moves in-sample DOWN and out-of-sample UP, which is the shape a selection artifact has.

The gates are ON at those values by explicit instruction, over a stated objection. The objection is
recorded once, in the script header and in `docs/ib/STUDY_V60_AROON.md` section 8e, and is not
repeated at every switch.

The frozen `ytturtle.run` kernel is never parameterised -- `yt_gates.run_gated` is a copy with a
parity assertion. This module only builds the eligibility masks it consumes.

Usage: python3 research/turtle2/yt_best.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle2")
sys.path.insert(0, "research/v60")
sys.path.insert(0, "research/v38")

import yt_gates as Y            # noqa: E402
import run_yt as RY             # noqa: E402
import indicators as I          # noqa: E402

MARKET, CHART, MODE = "NQ", 60, 2
MIN_IS = 40                     # a cell with fewer in-sample trades is not a candidate

WINDOWS = [("all hours", None), ("09:30-16:00", (570, 960)), ("09:30-12:00", (570, 720)),
           ("08:00-12:00", (480, 720))]
FLATS = [("none", 0), ("12:00", 720), ("16:00", 960)]
ADXES = [("off", 0.0), (">=20", 20.0), (">=25", 25.0), (">=30", 30.0)]
MACDS = ["off", "hist > 0", "macd > 0", "hist > 0 and rising", "fresh cross <= 10"]
AROONS = [("off", None), ("osc>=0", "osc>=0"), ("osc>=50", "osc>=50"), ("up>=70", "up>=70")]
AROON_LEN = 25                  # > the Turtle's 20-bar entry channel, so it is not an identity


def build(b):
    """Every series the grid can ask for, once."""
    from v60macd import conditions
    from v60core import aroon
    c, h, l = b["c"], b["h"], b["l"]
    mod = Y.ny_minutes(b["idx"])
    up, dn = aroon(h, l, AROON_LEN)
    osc = up - dn
    ar = {"osc>=0": osc >= 0.0, "osc>=50": osc >= 50.0, "up>=70": up >= 70.0}
    return dict(mod=mod, adx=Y.adx(h, l, c, 14), macd=conditions(c, 12, 26, 9), aroon=ar)


def masks(b, S, win, flat_min, adx_min, macd, aroon, tf=CHART):
    n = b["n"]
    ok = np.ones(n, bool)
    if win is not None:
        ok &= (S["mod"] >= win[0]) & (S["mod"] < win[1])
    if adx_min > 0:
        ok &= np.isfinite(S["adx"]) & (S["adx"] >= adx_min)
    if macd != "off":
        ok &= S["macd"][macd]
    if aroon is not None:
        ok &= S["aroon"][aroon]
    fl = np.zeros(n, bool)
    if flat_min > 0:
        prev = np.r_[S["mod"][0] - tf, S["mod"][:-1]]
        fl = (S["mod"] >= flat_min) & (prev < flat_min)
        ok &= (S["mod"] + tf < flat_min)
    return ok, fl


def score(ok, fl, block):
    R = Y.go(MARKET, CHART, MODE, block, ok, fl)[0]
    return Y.stats(R)


def main():
    print("=" * 104)
    print("ONE TURTLE, EVERY GATE ON -- defaults chosen on the IN-SAMPLE block, OOS read once after")
    print("=" * 104)
    if not Y.parity(MARKET, CHART, MODE):
        print("  PARITY FAILED -- stopping.")
        return
    b = RY.prep(MARKET, CHART)
    S = build(b)
    print(f"\n  {MARKET} {CHART}m, mode {MODE} (thirds). Aroon length {AROON_LEN} against a "
          f"20-bar channel, so it is NOT the Donchian identity.")
    print(f"  grid: {len(WINDOWS)} windows x {len(FLATS)} flattens x {len(ADXES)} ADX x "
          f"{len(MACDS)} MACD x {len(AROONS)} Aroon = "
          f"{len(WINDOWS) * len(FLATS) * len(ADXES) * len(MACDS) * len(AROONS)} cells, "
          f"minimum {MIN_IS} in-sample trades to be a candidate.\n")

    rows = []
    for wn, win in WINDOWS:
        for fn, fm in FLATS:
            if fm and win is not None and fm < win[1]:
                continue
            for an, am in ADXES:
                for mn in MACDS:
                    for arn, ar in AROONS:
                        ok, fl = masks(b, S, win, fm, am, mn, ar)
                        a = score(ok, fl, "is")
                        if a is None or a["n"] < MIN_IS:
                            continue
                        rows.append(dict(win=wn, flat=fn, adx=an, macd=mn, aroon=arn,
                                         n=a["n"], expR=a["expR"], pf=a["pf"],
                                         totalR=a["totalR"], win_pct=a["win"],
                                         _w=win, _f=fm, _a=am, _m=mn, _ar=ar))
    df = pd.DataFrame(rows)
    print(f"  scorable cells: {len(df)}   profitable in-sample: "
          f"{(df.expR > 0).mean() * 100:.1f}%   median R/trade {df.expR.median():+.3f}")

    base_ok, base_fl = masks(b, S, None, 0, 0.0, "off", None)
    base_is, base_oos = score(base_ok, base_fl, "is"), score(base_ok, base_fl, "oos")
    print(f"\n  FROZEN BASELINE (no gates):  IS n {base_is['n']:>4d} R {base_is['expR']:+.3f} "
          f"PF {base_is['pf']:.2f}   |   OOS n {base_oos['n']:>4d} R {base_oos['expR']:+.3f} "
          f"PF {base_oos['pf']:.2f}")

    print("\n  TOP 10 BY IN-SAMPLE R/TRADE -- read the CONSENSUS, not row 1: the top of any ranking")
    print("  is the maximum of its draws, and this one has hundreds.")
    top = df.sort_values("expR", ascending=False).head(10)
    print(f"  {'#':>2} {'window':<12}{'flat':<7}{'adx':<6}{'macd':<20}{'aroon':<9}"
          f"{'IS n':>6}{'IS R':>8}{'IS PF':>7}")
    for i, (_, r) in enumerate(top.iterrows(), 1):
        print(f"  {i:>2} {r['win']:<12}{r['flat']:<7}{r['adx']:<6}{r['macd']:<20}{r['aroon']:<9}"
              f"{r['n']:>6d}{r['expR']:>+8.3f}{r['pf']:>7.2f}")

    print("\n  CONSENSUS OF THE TOP 25 IN-SAMPLE CELLS (what the ranking actually agrees on):")
    t25 = df.sort_values("expR", ascending=False).head(25)
    for col in ("win", "flat", "adx", "macd", "aroon"):
        vc = t25[col].value_counts()
        print(f"    {col:<8}" + "   ".join(f"{k} {v * 4}%" for k, v in vc.items()))

    print("\n  MARGINAL AVERAGE PER AXIS over every scorable cell (in-sample R/trade):")
    for col in ("win", "flat", "adx", "macd", "aroon"):
        g = df.groupby(col).expR.mean().sort_values(ascending=False)
        print(f"    {col:<8}" + "   ".join(f"{k} {v:+.3f}" for k, v in g.items()))

    best = top.iloc[0]
    print("\n" + "=" * 104)
    print("  THE CHOSEN DEFAULTS, and the SINGLE out-of-sample read on them")
    print("=" * 104)
    ok, fl = masks(b, S, best["_w"], best["_f"], best["_a"], best["_m"], best["_ar"])
    a, o = score(ok, fl, "is"), score(ok, fl, "oos")
    print(f"  window {best['win']}   flatten {best['flat']}   ADX {best['adx']}   "
          f"MACD {best['macd']}   Aroon {best['aroon']}({AROON_LEN})")
    print(f"  IN-SAMPLE   n {a['n']:>4d}  R/trade {a['expR']:+.3f}  PF {a['pf']:.2f}  "
          f"win {a['win']:.1f}%")
    print(f"  OUT-SAMPLE  n {o['n']:>4d}  R/trade {o['expR']:+.3f}  PF {o['pf']:.2f}  "
          f"win {o['win']:.1f}%" if o else "  OUT-SAMPLE  too few trades")
    print(f"  against the ungated frozen rules: IS {base_is['expR']:+.3f} -> {a['expR']:+.3f}, "
          f"OOS {base_oos['expR']:+.3f} -> {o['expR']:+.3f}")

    print("\n  THE NEIGHBOURHOOD OF THE CHOSEN CELL -- one axis moved at a time, IS then OOS.")
    print("  A real setting decays smoothly; a spike with negative neighbours is an artifact.")
    print(f"    {'axis':<8}{'setting':<20}{'IS n':>6}{'IS R':>8}{'OOS n':>7}{'OOS R':>8}")
    axes = [("win", WINDOWS, "_w"), ("flat", FLATS, "_f"), ("adx", ADXES, "_a"),
            ("macd", [(m, m) for m in MACDS], "_m"), ("aroon", AROONS, "_ar")]
    for name, opts, key in axes:
        for label, val in opts:
            args = dict(win=best["_w"], flat_min=best["_f"], adx_min=best["_a"],
                        macd=best["_m"], aroon=best["_ar"])
            args[{"_w": "win", "_f": "flat_min", "_a": "adx_min",
                  "_m": "macd", "_ar": "aroon"}[key]] = val
            ok2, fl2 = masks(b, S, args["win"], args["flat_min"], args["adx_min"],
                             args["macd"], args["aroon"])
            a2, o2 = score(ok2, fl2, "is"), score(ok2, fl2, "oos")
            if a2 is None:
                continue
            mark = "  <-- chosen" if val == best[key] else ""
            print(f"    {name:<8}{str(label):<20}{a2['n']:>6d}{a2['expR']:>+8.3f}"
                  + (f"{o2['n']:>7d}{o2['expR']:>+8.3f}" if o2 else f"{'--':>7}{'--':>8}") + mark)


if __name__ == "__main__":
    main()
