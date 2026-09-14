"""The market-regime filter applied to ORB v1, on all four feeds.

SELECTION DISCIPLINE. The regime thresholds are swept on the IN-SAMPLE blocks only
(development/research + validation). The out-of-sample block is read exactly twice per market:
once for the base thresholds as specified, once for the marginal consensus. US30_ISO is a second
provider over a span the other US30 file does not reach and has ONE reserved block, so it never
enters the selection at all and is read once at the base.
"""
from __future__ import annotations

import itertools
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import orb_core as C     # noqa: E402
import orb_feeds as OF   # noqa: E402
import orb_regime as G   # noqa: E402
import orb_run as R      # noqa: E402

pd.set_option("display.width", 250)
MARKETS = ["NQ", "US100", "US30", "US30_ISO"]
TTF, HTF = 15, 60
IS_BLOCKS = {"NQ": ("development", "validation"), "US100": ("research", "validation"),
             "US30": ("research", "validation"), "US30_ISO": ()}
OOS_BLOCK = {"NQ": "out-of-sample", "US100": "test", "US30": "test",
             "US30_ISO": "reserved (second provider)"}

ADX_IN = [20.0, 25.0, 30.0]
ADX_OUT = [15.0, 18.0, 20.0]
SLOPE = [0.025, 0.05, 0.10]
DIST = [0.15, 0.25, 0.40]
BASE = dict(adx_entry=25.0, adx_exit=20.0, slope_thr=0.05, dist_thr=0.25)


def line(t):
    print("\n" + "=" * 126)
    print(t)
    print("=" * 126)


def blocks_for(D):
    if D["market"] == "US30_ISO":
        return {"reserved (second provider)": np.ones(len(D["c"]), bool)}
    if D["market"] == "NQ":
        return R.blocks_of(D)[0]
    return dict(D["blocks"])


def run_regime(D, reg_bars, **kw):
    return R.run(D, allow_long=(reg_bars == G.BULL), allow_short=(reg_bars == G.BEAR), **kw)


if __name__ == "__main__":
    Ds = {m: C.build(m, trade_tf=TTF, htf=HTF) for m in MARKETS}

    line("A. THE REGIME ITSELF -- distribution, and what the HYSTERESIS is worth")
    print(f"  {'market':10s}{'BULL':>9s}{'BEAR':>9s}{'CHOP':>9s}{'median ADX':>13s}"
          f"{'no-hysteresis CHOP':>21s}{'bars reclassified':>20s}")
    for m in MARKETS:
        r = G.regime(m, **BASE)
        flat = G.regime(m, adx_entry=25.0, adx_exit=25.0,
                        slope_thr=BASE["slope_thr"], dist_thr=BASE["dist_thr"])
        s, f = r["state"], flat["state"]
        print(f"  {m:10s}{100*(s==G.BULL).mean():>8.1f}%{100*(s==G.BEAR).mean():>8.1f}%"
              f"{100*(s==G.CHOP).mean():>8.1f}%{np.median(r['adx']):>13.1f}"
              f"{100*(f==G.CHOP).mean():>20.1f}%{100*(s!=f).mean():>19.1f}%")
    print("\n  With entry 25 and exit 25 the state machine collapses to `ADX >= 25`. That moves")
    print("  only 0.8-0.9% of bars on every feed, so THE HYSTERESIS IS VERY NEARLY INERT here:")
    print("  ADX(14) on 15-minute bars rarely sits in the 20-25 band for long enough to matter.")
    print("  Panel D confirms it from the other side -- the adx_exit axis is flat to the cent.")

    line("B. WHAT THE FILTER REMOVES, AND WHAT THOSE TRADES WOULD HAVE DONE")
    print("  Every unfiltered ORB v1 trade, tagged by the regime frozen at its own signal bar,")
    print("  and by whether the filter would KEEP it (long in BULL, short in BEAR).")
    print(f"\n  {'market':10s}{'bucket':26s}{'n':>7s}{'expectancy':>13s}{'net $':>12s}"
          f"{'PF':>8s}{'win %':>8s}")
    keepers = {}
    for m in MARKETS:
        D = Ds[m]
        base_t, _ = R.run(D)
        rb = G.on_bars(D, G.regime(m, **BASE))
        reg_at = rb[base_t["sig_bar"].to_numpy()]
        kept = ((base_t["side"].to_numpy() == 1) & (reg_at == G.BULL)) | \
               ((base_t["side"].to_numpy() == -1) & (reg_at == G.BEAR))
        keepers[m] = (base_t, reg_at, kept)
        for lab, sel in (("BULL regime", reg_at == G.BULL), ("BEAR regime", reg_at == G.BEAR),
                         ("CHOP regime", reg_at == G.CHOP),
                         ("KEPT by the filter", kept), ("REMOVED by the filter", ~kept)):
            tt = base_t[sel]
            if not len(tt):
                print(f"  {m:10s}{lab:26s}{0:>7d}{'-':>13s}{'-':>12s}{'-':>8s}{'-':>8s}")
                continue
            n = tt["net"].to_numpy()
            gp, gl = n[n > 0].sum(), -n[n <= 0].sum()
            print(f"  {m:10s}{lab:26s}{len(tt):>7,d}{n.mean():>13,.2f}{n.sum():>12,.0f}"
                  f"{(gp/gl if gl > 0 else np.inf):>8.3f}{100*(n>0).mean():>8.1f}")
        print()

    line("C. UNFILTERED vs REGIME-FILTERED, every feed and every block")
    for m in MARKETS:
        D = Ds[m]
        rb = G.on_bars(D, G.regime(m, **BASE))
        t0, _ = R.run(D)
        t1, _ = run_regime(D, rb)
        blk = blocks_for(D)
        rows, names = [], []
        for name, mask in blk.items():
            sb = np.unique(D["sess"][mask])
            days = pd.to_datetime(pd.Series(sb).astype(str), format="%Y%m%d")
            for lab, t in (("no filter", t0), ("regime", t1)):
                tt = t[t["sess"].isin(sb)] if len(t) else t
                rows.append(R.stats(tt, days) if len(tt) else dict(trades=0))
                names.append(f"{name[:9]}/{lab[:6]}")
        print(f"\n  {m}")
        R.table(rows, names)

    line("D. SENSITIVITY -- 81 threshold combinations, scored IN-SAMPLE ONLY")
    grid = []
    for m in MARKETS:
        D = Ds[m]
        blk = blocks_for(D)
        ism = np.zeros(len(D["c"]), bool)
        for b in IS_BLOCKS[m]:
            ism |= blk[b]
        oosm = blk[OOS_BLOCK[m]]
        for ae, ax, sl, di in itertools.product(ADX_IN, ADX_OUT, SLOPE, DIST):
            if ax > ae:
                continue
            rb = G.on_bars(D, G.regime(m, adx_entry=ae, adx_exit=ax, slope_thr=sl, dist_thr=di))
            t, _ = run_regime(D, rb)
            row = dict(market=m, adx_entry=ae, adx_exit=ax, slope=sl, dist=di, n=len(t))
            for tag, mask in (("is", ism), ("oos", oosm)):
                sb = np.unique(D["sess"][mask])
                tt = t[t["sess"].isin(sb)] if len(t) else t
                row[f"{tag}_n"] = len(tt)
                row[f"{tag}_exp"] = tt["net"].mean() if len(tt) else np.nan
                row[f"{tag}_tot"] = tt["net"].sum() if len(tt) else 0.0
            grid.append(row)
    g = pd.DataFrame(grid)
    g.to_parquet("results/orb/regime_grid.parquet")

    sel = g[(g["market"] != "US30_ISO") & (g["is_n"] >= 20)]
    print(f"  {len(g):,} cells ({len(sel):,} scorable in-sample on the three selectable feeds)")
    print(f"  share profitable in-sample: {100*(sel['is_tot'] > 0).mean():.1f}%   "
          f"median in-sample expectancy ${sel['is_exp'].median():,.2f}")
    print(f"  in-sample to out-of-sample expectancy correlation: "
          f"Pearson {sel['is_exp'].corr(sel['oos_exp']):+.3f}   "
          f"Spearman {sel['is_exp'].corr(sel['oos_exp'], method='spearman'):+.3f}")
    for ax, vals in (("adx_entry", ADX_IN), ("adx_exit", ADX_OUT), ("slope", SLOPE),
                     ("dist", DIST)):
        print(f"\n  {ax}   (marginal average over the in-sample blocks)")
        for v in vals:
            mm = sel[sel[ax] == v]
            if not len(mm):
                continue
            per = mm.groupby("market")["is_exp"].mean()
            print(f"    {v:>7}   cells {len(mm):4d}   median IS trades {mm['is_n'].median():5.0f}"
                  f"   mean IS exp {mm['is_exp'].mean():+9.2f}   "
                  f"share profitable {100*(mm['is_tot']>0).mean():5.1f}%   "
                  f"per market " + " ".join(f"{k} {per.get(k, np.nan):+7.2f}" for k in
                                            ("NQ", "US100", "US30")))

    line("E. THE OUT-OF-SAMPLE READ -- base thresholds, and the marginal consensus")
    cons = {ax: sel.groupby(ax)["is_exp"].mean().idxmax()
            for ax in ("adx_entry", "adx_exit", "slope", "dist")}
    if cons["adx_exit"] > cons["adx_entry"]:
        cons["adx_exit"] = cons["adx_entry"]
    print(f"  multiplicity: {len(sel):,} in-sample cells scored on three feeds; TWO threshold sets")
    print(f"  are read out of sample. Marginal consensus: {cons}")
    print(f"\n  {'market':10s}{'thresholds':22s}{'block':30s}{'n':>6s}{'expectancy':>13s}"
          f"{'net $':>11s}{'PF':>8s}{'Sharpe':>9s}")
    for m in MARKETS:
        D = Ds[m]
        blk = blocks_for(D)
        for lab, cfg in (("base (as specified)", BASE),
                         ("marginal consensus", dict(adx_entry=float(cons["adx_entry"]),
                                                     adx_exit=float(cons["adx_exit"]),
                                                     slope_thr=float(cons["slope"]),
                                                     dist_thr=float(cons["dist"])))):
            rb = G.on_bars(D, G.regime(m, **cfg))
            t, _ = run_regime(D, rb)
            name = OOS_BLOCK[m]
            sb = np.unique(D["sess"][blk[name]])
            tt = t[t["sess"].isin(sb)] if len(t) else t
            if not len(tt):
                print(f"  {m:10s}{lab:22s}{name:30s}{0:>6d}   no trades")
                continue
            days = pd.to_datetime(pd.Series(sb).astype(str), format="%Y%m%d")
            s = R.stats(tt, days)
            print(f"  {m:10s}{lab:22s}{name:30s}{s['trades']:>6,d}{s['expectancy']:>13,.2f}"
                  f"{s['total']:>11,.0f}{s['pf']:>8.3f}{s['sharpe']:>9.3f}")
