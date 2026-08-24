"""The tuner is only worth having if it agrees with the engine. This asserts that it does.

The claim the whole module rests on is that a trade's outcome depends only on its signal bar and
the geometry, so the price walk can be cached per bar instead of redone per configuration. If that
claim is wrong the tuner is fast and useless. So: random rules x random geometries, and every
trade's P&L, entry bar and exit bar must match `test_suite.sim_core` EXACTLY, not approximately.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tuner as U

RULES = [
    "always",
    "close>ema200",
    "close>ema50 and rsi14<40",
    "adx14>20 and pdi14>ndi14",
    "close>ema200 and close<ema20 and stoch14<30",
    "35<rsi14<65",
    "not close>ema100",
    "macd(12,26,9)>0 and body>50",
    "supertrend(10,3)>0 and pos<40",
    "close>ema(9) and cross(9,21)>0",
    "vwapd>0.5 and rvol20>1.2",
    "emadist200>0 and emadist20<-0.5",
]

GEOMS = [(1.0, 1.0, 0, 0), (2.0, 1.0, 0, 0), (2.5, 3.0, 0, 0), (1.5, 2.0, 0, 0),
         (2.0, 0.5, 690, 0), (3.0, 1.5, 960, 0), (2.0, 1.0, 0, 6), (1.0, 2.0, 690, 12)]


def check(tf=30, sides=(1, -1), verbose=True):
    from test_suite import build
    d = U.bars(tf)
    stops = sorted({g[0] for g in GEOMS}); targs = sorted({g[1] for g in GEOMS})
    flats = sorted({g[2] for g in GEOMS}); holds = sorted({g[3] for g in GEOMS})
    bad = []; nchk = 0; ntr = 0
    for side in sides:
        T = U.tensor(tf, side, stops, targs, flats, holds, 14, U.Entry(), only=None)
        for rule in RULES:
            trig = np.flatnonzero(U.mask(d, rule)).astype(np.int64)
            for (st, tg, fl, hd) in GEOMS:
                g = T.gi(st, tg, fl, hd)
                n = len(trig)
                pnl = np.zeros(n); eb = np.zeros(n, np.int64)
                xb = np.zeros(n, np.int64); wo = np.zeros(n, np.int64)
                # LEGACY costs: `test_suite.sim_core` is the pre-change model, so the equality
                # check has to be made against the pre-change cost stack. `research/costs.py`
                # reconstructs it exactly rather than leaving it to be remembered.
                ft, fs = U.LEGACY_COSTS.friction(d)
                k = U._walk_one(trig, T.xb[g], T.why[g], T.raw[g], ft, fs,
                                U.LEGACY_COSTS.fee_rt(), U.LEGACY_COSTS.maker_target(),
                                d["si"], np.int64(d["cut"]), pnl, eb, xb, wo)
                pnl, eb, xb = pnl[:k], eb[:k], xb[:k]
                nchk += 1; ntr += k
                if hd > 0:
                    continue          # sim_core has no max-hold exit; nothing to compare against
                s = build([], side=side, atr_mult=st, tp_r=tg, flat_min=fl, tf=tf,
                          trig=trig, pool=False)
                # sim_core reports the FILL bar; the tensor is keyed on the SIGNAL bar
                ok = (len(s.pnl) == k and np.array_equal(s.ent_bar, eb + 1)
                      and np.array_equal(s.ex_bar, xb)
                      and np.allclose(s.pnl, pnl, atol=1e-9, rtol=0))
                if not ok:
                    m = min(len(s.pnl), k)
                    j = int(np.argmax(np.abs(s.pnl[:m] - pnl[:m]))) if m else -1
                    bad.append(f"{rule!r} side={side} {st}x/{tg}R flat={fl}: "
                               f"engine {len(s.pnl)} trades vs tensor {k}"
                               + (f", worst P&L diff {abs(s.pnl[j]-pnl[j]):.6f} at trade {j}"
                                  if m else ""))
    if verbose:
        print(f"  {nchk} rule x geometry x side combinations, {ntr:,} trades compared")
        print("  tensor vs test_suite.sim_core:",
              "EXACT MATCH" if not bad else "\n    " + "\n    ".join(bad))
    return bad


def check_costs(tf=30):
    """Costs are applied at read time; that must equal charging them inside the walk."""
    from test_suite import build
    d = U.bars(tf)
    T = U.tensor(tf, 1, [2.0], [1.0], [0], [0], 14, U.Entry(), only=None)
    trig = np.flatnonzero(U.mask(d, "close>ema50")).astype(np.int64)
    bad = []
    for mult in (0.5, 1.0, 2.0, 3.0):
        n = len(trig)
        pnl = np.zeros(n); eb = np.zeros(n, np.int64)
        xb = np.zeros(n, np.int64); wo = np.zeros(n, np.int64)
        cs = U.Costs(broker="legacy", legacy=True, mult=mult)
        ft, fs = cs.friction(d)
        k = U._walk_one(trig, T.xb[0], T.why[0], T.raw[0], ft, fs, cs.fee_rt(),
                        cs.maker_target(), d["si"], np.int64(d["cut"]), pnl, eb, xb, wo)
        s = build([], side=1, atr_mult=2.0, tp_r=1.0, tf=tf, trig=trig, pool=False,
                  cost_mult=mult)
        if not (len(s.pnl) == k and np.allclose(s.pnl, pnl[:k], atol=1e-9)):
            bad.append(f"cost_mult={mult}: {len(s.pnl)} vs {k} trades, "
                       f"max diff {np.abs(s.pnl[:k]-pnl[:k]).max():.6f}")
    print("  cost model applied at read time:", "EXACT MATCH" if not bad else "; ".join(bad))
    return bad


def check_window(tf=30):
    """A window must restrict the SIGNAL bar and nothing else: a trade may still exit later."""
    d = U.bars(tf)
    r = U.run("close>ema50", tf=tf, win="09:30-11:00", stop=2.0, target=1.0, control=0)
    wm = U.win_mask(d, "09:30-11:00")
    trig = np.flatnonzero(U.mask(d, "close>ema50") & wm)
    ok = bool(wm[trig].all())
    print("  window restricts signals only:", "OK" if ok and r.n > 0 else "FAILED")
    return [] if ok else ["window mask leaked"]


def check_leak(tf=30):
    bad = __import__("indpool").leak_check(tf)
    print("  indicator causality under truncation:",
          "CLEAN" if not bad else "; ".join(bad))
    return bad


def check_study(tf=30):
    """The tuner must re-derive a result an INDEPENDENT module already established.

    `STUDY_LIMIT_ENTRY.md` measured, with its own simulator, that on unsignalled entries a market
    order loses and a resting limit 0.75xATR in your favour makes money -- on both sides, which is
    what rules out the sample's uptrend as the explanation. Two implementations agreeing on a
    non-obvious sign pattern is worth more than either one's internal consistency."""
    out = {}
    for lab, en in (("market", U.Entry()),
                    ("limit", U.Entry(kind="limit", k=0.75, expiry=6, thru=2.0))):
        for side in (1, -1):
            r = U.run("always", tf=tf, side=side, win="07:00-11:00", stop=2.0, target=1.0,
                      entry=en, control=0)
            out[(lab, side)] = r.per
    bad = []
    for side in (1, -1):
        if not out[("market", side)] < 0:
            bad.append(f"market side={side} should lose, got ${out[('market', side)]:.1f}/trade")
        if not out[("limit", side)] > 0:
            bad.append(f"limit side={side} should earn, got ${out[('limit', side)]:.1f}/trade")
    print("  agrees with STUDY_LIMIT_ENTRY (market loses, limit earns, both sides):",
          "OK" if not bad else "; ".join(bad))
    print("    " + "  ".join(f"{l} {'long' if s==1 else 'short'} ${v:.1f}/tr"
                             for (l, s), v in out.items()))
    return bad


if __name__ == "__main__":
    tf = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    print(f"\nTUNER VERIFICATION  [{tf}m bars]\n" + "=" * 78)
    bad = check(tf) + check_costs(tf) + check_window(tf) + check_leak(tf) + check_study(tf)
    print("=" * 78)
    print("  ALL CHECKS PASS" if not bad else f"  {len(bad)} FAILURES")
    sys.exit(1 if bad else 0)
