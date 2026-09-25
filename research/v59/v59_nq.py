"""ONE read on NQ -- a market that had no part in the 243,000-configuration search.

DECLARED BEFORE THE FILE IS OPENED, from the research marginals alone:

  1  THE ATR-FLOOR CANDIDATE. The volatility floor is the ONLY condition of the pool that beats
     `off` in all four market-block columns, and its mirror (ATR <= 0.8x) is the worst setting
     everywhere, so it is a gradient rather than a threshold. Cross, LONG, ADX off,
     ATR >= 1.2x its trailing median, 2.0N stop, NO target, four-hour ceiling, ATR trail,
     09:30-16:00.
  2  THE RESEARCH SURVIVOR (candidate B), which was research-positive on both markets and then
     went NEGATIVE on US30's locked block. NQ decides whether that was noise or a market.
  3  AS BRIEFED (candidate C) -- the plain EMA 16/64 cross with a 2N stop, a 2R target and a
     four-hour ceiling, both sides, all hours, no conditions.

NQ_1m IS STAMPED IN UTC. Every other feed here is already New York, and a loader that forgets to
convert puts an 09:30 window at 04:30 (`STUDY_V58_INITIAL_BALANCE.md`). It is converted here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.v59 import v59core as C                                   # noqa: E402
from research.v59.run_v59 import prep, metrics, keepmask, aggregate     # noqa: E402
from research.v59.v59judge import control, label                        # noqa: E402
from research.v59.v59lock import gi, fi                                 # noqa: E402


def load_nq():
    d = pd.read_csv("data/NQ_1m.csv")
    tc = [c for c in d.columns if "time" in c.lower() or "date" in c.lower()][0]
    ix = pd.DatetimeIndex(pd.to_datetime(d[tc], utc=True)) \
        .tz_convert("America/New_York").tz_localize(None)
    f = pd.DataFrame({k: d[[c for c in d.columns if c.lower().startswith(k)][0]].to_numpy(float)
                      for k in ("open", "high", "low", "close")}, index=ix).sort_index()
    f = f[~f.index.duplicated(keep="first")]
    f = f.resample("15min").agg({"open": "first", "high": "max", "low": "min",
                                 "close": "last"}).dropna()
    f["volume"] = 0.0
    return f


CAND = {
    "1 ATR floor ": (0, "long", fi("off", "atr>=1.2x"),
                     gi(2.0, 99.0, 16, "ATR trail", "09:30-16:00")),
    "2 survivor  ": (0, "long", fi("adx<=20", "off"),
                     gi(1.5, 99.0, 12, "ATR trail", "09:30-16:00")),
    "3 as briefed": (0, "both", fi("off", "off"),
                     gi(2.0, 2.0, 16, "fixed", "all hours")),
}


def boot(x, n=5000, seed=11):
    g = np.random.default_rng(seed)
    return float((g.choice(x, (n, len(x)), replace=True).mean(1) <= 0).mean())


def main():
    f = load_nq()
    print(f"NQ 15m: {len(f):,} bars, {f.index[0]} .. {f.index[-1]}  (New York)")
    F, S, ndays = prep("NQ", frame=f, cost=C.COST_PTS["NQ"])
    sel = np.ones(F["n"], bool)
    ag = aggregate(S, sel, ndays)
    print("\n" + "=" * 92)
    print("NQ, READ ONCE   (ATR units at the signal bar, net of a $1.44 MNQ round turn)")
    print("=" * 92)
    print(f"{'candidate':<13} {'n':>5} {'ATR/tr':>9} {'PF':>6} {'Sharpe':>7} {'win':>6} "
          f"{'ctrl':>8} {'ctrl p':>7}")
    for nm, (m, s, ff, g) in CAND.items():
        mm = metrics(ag[(m, s, ff)], ndays)
        if mm["n"][g] < 10:
            print(f"{nm:<13}  -- too few trades --")
            continue
        ps, meds, per = [], [], []
        for s2 in (["long", "short"] if s == "both" else [s]):
            sd = 0 if s2 == "long" else 1
            st = S[(m, sd)]
            km = keepmask(st, ff)
            if km.sum() < 10:
                continue
            p, med = control(F, st["sig"][km], sd, g, C.COST_PTS["NQ"], mm["atr"][g], sel)
            if np.isfinite(p):
                ps.append(p); meds.append(med)
            per.append(st["pts"][km, g][np.isfinite(st["pts"][km, g])])
        x = np.concatenate(per) if per else np.zeros(0)
        w = x > 0
        print(f"{nm:<13} {int(mm['n'][g]):>5d} {mm['atr'][g]:>+9.4f} {mm['pf'][g]:>6.3f} "
              f"{mm['sharpe'][g]:>7.2f} {w.mean()*100:>5.1f}% "
              f"{(np.mean(meds) if meds else np.nan):>+8.4f} {(max(ps) if ps else np.nan):>7.3f}")
        if len(x):
            print(f"{'':<13} bootstrap P(mean <= 0) on the locked trades: {boot(x):.3f}")


if __name__ == "__main__":
    main()
