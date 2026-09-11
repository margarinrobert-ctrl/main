"""ORB v1 as specified: the causality audit, then the three-block report."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import orb_core as C   # noqa: E402
import orb_run as R    # noqa: E402

pd.set_option("display.width", 220)


def line(t):
    print("\n" + "=" * 118)
    print(t)
    print("=" * 118)


if __name__ == "__main__":
    D = C.build("NQ")
    blk, cuts = R.blocks_of(D)

    line("THE SPEC, AS IMPLEMENTED")
    print(f"  market NQ   trading bars {D['trade_tf']}m   higher timeframe {D['htf']}m   "
          f"execution path 1m")
    print(f"  session 09:30-16:00 New York, liquidation {C.LIQUIDATE//60:02d}:{C.LIQUIDATE%60:02d} "
          f"filled at the NEXT 1m bar's open")
    print(f"  opening range = the first {C.RANGE_MIN} completed minutes (09:30-09:45); breakouts are")
    print(f"    not evaluated until 09:45 and the range bars themselves can never signal")
    print(f"  EMA({C.EMA_FAST})/EMA({C.EMA_SLOW}) on the last CLOSED {D['htf']}m bar; ATR({C.ATR_N}) Wilder; "
          f"volume SMA({C.VOL_N}) shifted one bar")
    print(f"  range/ATR gate [{C.RATIO_LO}, {C.RATIO_HI}]   buffer max({C.BUF_ATR}xATR, {C.TICK})   "
          f"volume > {C.VOL_MULT}x its own prior SMA")
    print(f"  risk {C.RISK_PCT*100:.2f}% of CURRENT equity, stop {C.STOP_ATR:.1f}xATR frozen at the signal, "
          f"start ${C.EQUITY0:,.0f}")
    print(f"  50% out at +1R (rounded DOWN to a whole lot), stop to breakeven, rest at +2R")
    print(f"  cost per side: spread {C.SPREAD} + slippage {C.SLIP} as a price adjustment, "
          f"+ {C.FEE_PTS} pts of fees = {C.SPREAD+C.SLIP+C.FEE_PTS} pts; point value {C.POINT_VALUE}")
    us = np.unique(D["sess"])
    print(f"  {len(us):,} RTH sessions, {us[0]} to {us[-1]}; blocks cut at {cuts[0]} and {cuts[1]}")

    # ---------------------------------------------------------------- causality audit
    line("A. TRUNCATION AUDIT -- recompute every input on history that ENDS at the bar")
    rng = np.random.default_rng(0)
    probe = rng.choice(np.arange(5000, len(D["c"])), 40, replace=False)
    bad = 0
    for i in sorted(probe):
        Dt = dict(D)
        cut_t = i + 1
        # rebuild the trading-bar indicators on a truncated series
        h, l, c, v = D["h"][:cut_t], D["l"][:cut_t], D["c"][:cut_t], D["v"][:cut_t]
        pc = np.roll(c, 1); pc[0] = c[0]
        tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
        atr_t = C._wilder(tr, C.ATR_N)[-1]
        vs_t = pd.Series(v).rolling(C.VOL_N).mean().shift(1).to_numpy()[-1]
        s = D["sess"][:cut_t]
        m = s == s[-1]
        tp = (h[m] + l[m] + c[m]) / 3.0
        vw_t = (tp * v[m]).sum() / v[m].sum() if v[m].sum() > 0 else np.nan
        for name, full, trunc in (("atr", D["atr"][i], atr_t), ("vol_sma", D["vsma"][i], vs_t),
                                  ("vwap", D["vwap"][i], vw_t)):
            a, b = full, trunc
            if not (np.isnan(a) and np.isnan(b)) and not np.isclose(a, b, rtol=1e-9, atol=1e-9):
                print(f"    LEAK {name} at {i}: full {a} truncated {b}")
                bad += 1
    print(f"  40 probe bars x 3 series: {bad} mismatches. "
          f"{'CLEAN' if bad == 0 else 'FAILED'}")
    fwd = D["ts"][np.flatnonzero(D["in_range"])]
    print(f"  opening-range bars are {C.RANGE_MIN//D['trade_tf']} per session "
          f"({len(fwd)/len(us):.2f} measured) and none of them is evaluable")

    # ---------------------------------------------------------------- the run
    t, side = R.run(D)
    line("B. WHAT THE FILTER CHAIN COSTS -- sessions surviving each condition")
    sess_all = len(us)
    ratio = (D["rh"] - D["rl"]) / D["ra"]
    okr = pd.Series(np.isfinite(ratio) & (ratio >= C.RATIO_LO) & (ratio <= C.RATIO_HI),
                    index=D["sess"]).groupby(level=0).max()
    print(f"  sessions                                   {sess_all:6,d}")
    print(f"  ... with a range/ATR ratio in [0.3, 1.5]   {int(okr.sum()):6,d}  "
          f"({100*okr.mean():.1f}%)")
    raw, _ = C.signals(D)
    sess_sig = len(np.unique(D["sess"][raw != 0]))
    print(f"  ... producing at least one full signal      {sess_sig:6,d}  "
          f"({100*sess_sig/sess_all:.1f}%)")
    print(f"  ... and actually traded (first signal only) {len(t):6,d}  "
          f"({100*len(t)/sess_all:.1f}%)")
    print(f"  signals discarded because a trade was already taken this session: "
          f"{int((raw != 0).sum()) - sess_sig:,}")
    print(f"  trades skipped because quantity < 1 lot: {t.attrs['skipped_for_size']:,}")

    line("C. THE THREE BLOCKS")
    rows, names = [], []
    for name, mask in blk.items():
        sess_b = np.unique(D["sess"][mask])
        tt = t[t["sess"].isin(sess_b)]
        days = pd.to_datetime(pd.Series(sess_b).astype(str), format="%Y%m%d")
        rows.append(R.stats(tt, days)); names.append(name)
    sess_all_d = pd.to_datetime(pd.Series(us).astype(str), format="%Y%m%d")
    rows.append(R.stats(t, sess_all_d)); names.append("ALL (reference)")
    R.table(rows, names)
    print("\n  'ALL' is a research-block statistic wearing a whole-sample name and is printed only")
    print("  for reference -- the out-of-sample column is the one that was never selected on.")

    line("D. EXIT MIX AND THE INTRABAR ASSUMPTION")
    for name, mask in blk.items():
        tt = t[t["sess"].isin(np.unique(D["sess"][mask]))]
        if not len(tt):
            continue
        mix = tt["exit_reason"].value_counts(normalize=True).mul(100).round(1).to_dict()
        pnl = tt.groupby("exit_reason", observed=True)["net"].sum().round(0).to_dict()
        print(f"  {name:16s} " + "  ".join(f"{k} {mix.get(k,0):.1f}% (${pnl.get(k,0):,.0f})"
                                           for k in ("stop", "target", "breakeven", "liquidation")))
    print(f"\n  exits are walked on the 1-MINUTE path, so the bar-level tie-break is mostly gone.")
    print(f"  residual 1-minute bars where a stop and a target were both touched: "
          f"{100*(t['ambiguous']>0).mean():.2f}% of trades -- resolved as a STOP (conservative).")
    opt, _ = R.run(D, conservative=False)
    print(f"  the OPPOSITE assumption (target first) would give ${opt['net'].sum():,.0f} against "
          f"${t['net'].sum():,.0f} -- a difference of ${opt['net'].sum()-t['net'].sum():,.0f}, "
          f"which is the size of the assumption.")

    line("E. SIZING REALITY")
    print(f"  quantity: median {t['qty'].median():.0f}, min {t['qty'].min():.0f}, "
          f"max {t['qty'].max():.0f}   |   trades where the 50% scale rounds to ZERO lots: "
          f"{100*(t['scale_qty']==0).mean():.1f}%")
    print(f"  final equity ${t['equity'].iloc[-1]:,.0f} from ${C.EQUITY0:,.0f}")

    t.to_parquet("results/orb/trades_v1.parquet")
    print("\n  trades written to results/orb/trades_v1.parquet")
