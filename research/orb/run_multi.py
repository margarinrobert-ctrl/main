"""ORB v1 on three more feeds. Nothing about the rule changes; four things about the DATA do.

  the opening range is ONE bar on a 15-minute feed, because the range is 15 minutes long. That is
  not a bug and it turns out to be the whole story about the range/ATR gate.
  the exits cannot be walked at 1-minute resolution, so the intrabar tie-break is a real
  assumption on these feeds and is reported BOTH WAYS on every block.
  the volume is TICK volume on the two CFD exports, so the VWAP and the 1.2x volume filter are
  proxies there.
  costs differ, and are reported as a FRACTION OF THE 1 ATR STOP, which is the only unit that
  compares across markets (`STUDY_TURTLE_15M`).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import orb_core as C    # noqa: E402
import orb_feeds as OF  # noqa: E402
import orb_run as R     # noqa: E402

pd.set_option("display.width", 240)
MARKETS = ["NQ", "US100", "US30", "US30_ISO"]
TTF, HTF = 15, 60


def line(t):
    print("\n" + "=" * 124)
    print(t)
    print("=" * 124)


def blocks_for(D):
    if D["market"] == "US30_ISO":
        return {"reserved (second provider)": np.ones(len(D["c"]), bool)}
    if D["market"] == "NQ":
        return R.blocks_of(D)[0]
    return {k: v for k, v in D["blocks"].items()}


def control_random_bar(D, t, n_draw=400, seed=5):
    """Same sessions, same side, same geometry, entered at a random post-range bar."""
    rng = np.random.default_rng(seed)
    elig = (D["mod"] >= C.SESS_OPEN + C.RANGE_MIN) & ~D["in_range"]
    liq = pd.DataFrame({"s": D["m1_sess"], "m": D["m1_mod"], "i": np.arange(len(D["m1_ts"]))})
    liq = liq[liq["m"] >= D["liquidate"]].groupby("s", sort=True)["i"].first()
    pools = {}
    for s in t["sess"].unique():
        pools[s] = np.flatnonzero(elig & (D["sess"] == s))
    sess = t["sess"].to_numpy()
    side = t["side"].to_numpy().astype(np.int64)
    lb = liq.reindex(sess).to_numpy().astype(np.int64)
    keep = np.array([len(pools[s]) > 0 for s in sess])
    tf = D["trade_tf"]
    out = np.zeros(n_draw)
    for d in range(n_draw):
        b = np.array([pools[s][rng.integers(len(pools[s]))] if len(pools[s]) else -1
                      for s in sess], np.int64)
        m = keep & (b >= 0)
        ct = pd.DatetimeIndex(D["ts"][b[m]]) + pd.Timedelta(minutes=tf)
        i0 = np.searchsorted(D["m1_ts"], ct.to_numpy(), side="left").astype(np.int64)
        end = lb[m] - 1
        ok = (i0 <= end) & (i0 < len(D["m1_ts"]))
        if ok.sum() == 0:
            continue
        _, _, q, _, pnl, _, _, _, _ = C._walk(
            i0[ok], side[m][ok], D["atr"][b[m]][ok], end[ok],
            D["m1_o"], D["m1_h"], D["m1_l"], D["m1_c"], D["m1_mod"],
            C.EQUITY0, C.RISK_PCT, D["pv"], D["spread"], D["slip"], D["fee"],
            C.STOP_ATR, D["liquidate"], 1)
        v = pnl[q > 0]
        out[d] = v.mean() if len(v) else 0.0
    return out


if __name__ == "__main__":
    line("A. THE STRUCTURAL FACT A 15-MINUTE FEED EXPOSES: the gate is calibrated to the "
         "trading timeframe")
    print(f"  {'market':10s}{'trading tf':>12s}{'range bars':>12s}{'median range/ATR':>19s}"
          f"{'in [0.3,1.5]':>15s}{'sessions':>11s}")
    Ds = {}
    for m in MARKETS:
        D = C.build(m, trade_tf=TTF, htf=HTF)
        Ds[m] = D
        r = pd.Series((D["rh"] - D["rl"]) / D["ra"], index=D["sess"]).groupby(level=0).first().dropna()
        nb = int(np.round(C.RANGE_MIN / TTF))
        print(f"  {m:10s}{str(TTF)+'m':>12s}{nb:>12d}{r.median():>19.3f}"
              f"{100*((r >= 0.3) & (r <= 1.5)).mean():>14.1f}%{len(np.unique(D['sess'])):>11,d}")
    D5 = C.build("NQ", trade_tf=5, htf=15)
    r5 = pd.Series((D5["rh"] - D5["rl"]) / D5["ra"], index=D5["sess"]).groupby(level=0).first().dropna()
    print(f"  {'NQ':10s}{'5m':>12s}{3:>12d}{r5.median():>19.3f}"
          f"{100*((r5 >= 0.3) & (r5 <= 1.5)).mean():>14.1f}%{len(np.unique(D5['sess'])):>11,d}")
    print("\n  WHEN THE TRADING BAR IS THE OPENING RANGE, range/ATR IS ~1 BY CONSTRUCTION -- the")
    print("  range is one bar and ATR(14) is the average size of one bar. The [0.3, 1.5] band is")
    print("  therefore a band around 1, and it passes most sessions. On 5-minute bars the same")
    print("  band keeps the quietest ninth. The gate was written for a 15-minute chart.")

    line("B. COST AS A FRACTION OF THE 1 ATR STOP -- the only cross-market unit")
    print(f"  {'market':10s}{'cost/side':>11s}{'round turn':>12s}{'median ATR':>12s}"
          f"{'RT / stop':>11s}{'volume series':>52s}")
    for m in MARKETS:
        D = Ds[m]
        sp = OF.SPEC[m]
        rt = 2 * sp["cost_per_side"]
        a = np.nanmedian(D["atr"])
        print(f"  {m:10s}{sp['cost_per_side']:>11.2f}{rt:>12.2f}{a:>12.1f}{100*rt/a:>10.1f}%"
              f"{sp['vol']:>52s}")

    line("C. ORB v1 ON EVERY FEED -- 15-minute trading bars, HTF 60m, everything else as specified")
    allrows = []
    for m in MARKETS:
        D = Ds[m]
        t, _ = R.run(D)
        if len(t) == 0:
            print(f"\n  {m}: no trades")
            continue
        blk = blocks_for(D)
        rows, names = [], []
        for name, mask in blk.items():
            sb = np.unique(D["sess"][mask])
            tt = t[t["sess"].isin(sb)]
            days = pd.to_datetime(pd.Series(sb).astype(str), format="%Y%m%d")
            rows.append(R.stats(tt, days)); names.append(name)
        print(f"\n  {m}  ({OF.SPEC[m]['vol']})")
        R.table(rows, names)
        allrows.append((m, t, D, blk))

    line("D. THE INTRABAR ASSUMPTION, WHICH IS REAL ON A 15-MINUTE FEED")
    print(f"  {'market':10s}{'trades':>8s}{'% with an ambiguous bar':>26s}"
          f"{'stop-first $':>14s}{'target-first $':>16s}{'the assumption is worth':>25s}")
    for m, t, D, _ in allrows:
        opt, _ = R.run(D, conservative=False)
        print(f"  {m:10s}{len(t):>8,d}{100*(t['ambiguous'] > 0).mean():>25.1f}%"
              f"{t['net'].sum():>14,.0f}{opt['net'].sum():>16,.0f}"
              f"{opt['net'].sum() - t['net'].sum():>25,.0f}")
    print("\n  On NQ at 1-minute execution this was 0.00% and worth $0. On a 15-minute feed the")
    print("  same rule cannot be settled by the data, and the number above is the size of a")
    print("  MODELLING CHOICE sitting inside the result.")

    line("E. THE MATCHED CONTROL -- same sessions, same side, same geometry, random entry bar")
    print(f"  {'market':10s}{'block':30s}{'n':>6s}{'observed':>12s}{'control med':>13s}"
          f"{'5-95%':>26s}{'p':>8s}")
    for m, t, D, blk in allrows:
        for name, mask in blk.items():
            sb = np.unique(D["sess"][mask])
            tt = t[t["sess"].isin(sb)]
            if len(tt) < 10:
                print(f"  {m:10s}{name:30s}{len(tt):>6,d}   too few trades to control")
                continue
            c = control_random_bar(D, tt, n_draw=300, seed=5)
            obs = tt["net"].mean()
            print(f"  {m:10s}{name:30s}{len(tt):>6,d}{obs:>12,.2f}{np.median(c):>13,.2f}"
                  f"   [{np.quantile(c, .05):+10,.2f}, {np.quantile(c, .95):+9,.2f}]"
                  f"{(c >= obs).mean():>8.3f}")

    line("F. DOUBLED SLIPPAGE, EVERY FEED AND EVERY BLOCK")
    print(f"  {'market':10s}{'block':30s}{'expectancy':>13s}{'2x slip':>12s}{'Δ':>10s}"
          f"{'PF':>9s}{'PF 2x':>9s}")
    for m, t, D, blk in allrows:
        t2, _ = R.run(D, slip_mult=2.0)
        for name, mask in blk.items():
            sb = np.unique(D["sess"][mask])
            a = t[t["sess"].isin(sb)]; b = t2[t2["sess"].isin(sb)]
            if len(a) < 5:
                continue
            days = pd.to_datetime(pd.Series(sb).astype(str), format="%Y%m%d")
            sa, sbb = R.stats(a, days), R.stats(b, days)
            print(f"  {m:10s}{name:30s}{sa['expectancy']:>13,.2f}{sbb['expectancy']:>12,.2f}"
                  f"{sbb['expectancy']-sa['expectancy']:>+10,.2f}{sa['pf']:>9.3f}{sbb['pf']:>9.3f}")
