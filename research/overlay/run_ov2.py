"""The overlay, and the validation battery in the order the skill specifies."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ov_core as O           # noqa: E402
import overlay_eval as E      # noqa: E402

KS = (5, 10, 15, 30, 60, 120)
K_MAIN = 30


def main():
    print(__doc__)
    D = O.build("NQ", 1)
    base, bst = O.trades(D, gate=0)
    n_sig = len(D["sig_bar"])

    print("=" * 112)
    print("A. THE URGENCY SWEEP -- every gate needs a timeout, and if it only works at one K it is")
    print("   not a result")
    print("=" * 112)
    print(f"  {'K (min)':>8s} {'trades':>7s} {'skipped':>8s} {'med delay':>10s} "
          f"{'pts/trade':>10s} {'Δ vs base':>10s} {'total Δ':>10s} {'med hold':>9s}")
    print(f"  {'baseline':>8s} {len(base):7d} {0:8d} {0:10d} {base['net'].mean():+10.3f} "
          f"{0.0:+10.3f} {0.0:+10.0f} {base['hold_min'].median():9.0f}")
    keep = {}
    for K in KS:
        ov, st = O.trades(D, gate=1, K=K)
        keep[K] = ov
        d = ov["net"].sum() - base["net"].sum()
        print(f"  {K:8d} {len(ov):7d} {int((st == 1).sum()):8d} "
              f"{int(ov['delay'].median()):10d} {ov['net'].mean():+10.3f} "
              f"{ov['net'].mean()-base['net'].mean():+10.3f} {d:+10.0f} "
              f"{ov['hold_min'].median():9.0f}")
    ov = keep[K_MAIN]
    print(f"\n  Carried forward: K = {K_MAIN} minutes.")

    print("\n" + "=" * 112)
    print("B. BASELINE vs OVERLAY")
    print("=" * 112)
    bd, od = O.daily(base, D), O.daily(ov, D)
    bt, ot = E.tail_stats(bd), E.tail_stats(od)
    rows = [("trades", len(base), len(ov)),
            ("points / trade", base["net"].mean(), ov["net"].mean()),
            ("% of entry price / trade", base["pct"].mean(), ov["pct"].mean()),
            ("win rate %", 100 * (base["net"] > 0).mean(), 100 * (ov["net"] > 0).mean()),
            ("total points", base["net"].sum(), ov["net"].sum()),
            ("median hold (min)", base["hold_min"].median(), ov["hold_min"].median()),
            ("Sharpe (daily, ann.)", bt["sharpe"], ot["sharpe"]),
            ("max drawdown (pts)", bt["max_drawdown"], ot["max_drawdown"]),
            ("worst day (pts)", bt["worst_day"], ot["worst_day"]),
            ("CVaR 5% (pts)", bt["cvar_05"], ot["cvar_05"])]
    print(f"  {'metric':26s} {'baseline':>12s} {'overlay':>12s} {'Δ':>12s}")
    for k, a, b in rows:
        print(f"  {k:26s} {a:12.3f} {b:12.3f} {b-a:+12.3f}")

    print("\n" + "=" * 112)
    print("C. ATTRIBUTION -- where the PnL difference actually comes from")
    print("=" * 112)
    dec = E.decompose(base[["signal_id", "side", "qty", "entry_px", "exit_px"]],
                      ov[["signal_id", "side", "qty", "entry_px", "exit_px"]])
    print(f"  total difference {dec['total_difference']:+,.1f} points   "
          f"matched {dec['n_matched']}   dropped by overlay {dec['n_dropped_by_overlay']}   "
          f"added {dec['n_added_by_overlay']}")
    for k, v in dec["components"].items():
        print(f"    {k:22s} {v:+12,.1f} pts   {dec['pct_of_total'][k]:+7.1f}% of Δ")
    if dec["warning"]:
        print(f"  WARNING: {dec['warning']}")

    print("\n" + "=" * 112)
    print("D. THE RANDOM-DELAY PLACEBO -- the headline test")
    print("=" * 112)
    obs_delays = ov["delay"].to_numpy()
    base_total = base["net"].sum()
    observed = ov["net"].sum() - base_total

    def run_fn(sample_delays):
        d = np.zeros(n_sig, np.int64)
        d[:] = np.round(sample_delays(n_sig)).astype(np.int64)
        t, _ = O.trades(D, gate=2, K=K_MAIN, rand_delay=d)
        return float(t["net"].sum() - base_total)

    pl = E.placebo_test(run_fn, obs_delays, n_sims=200, seed=7,
                        observed_improvement=observed)
    print(f"  observed improvement      {observed:+,.1f} points "
          f"({observed/len(ov):+.3f} per overlay trade)")
    print(f"  placebo mean              {pl['placebo_mean']:+,.1f} points")
    print(f"  placebo 5-95%            [{pl['placebo_q05']:+,.1f}, {pl['placebo_q95']:+,.1f}]")
    print(f"  percentile vs placebo     {pl['percentile_vs_placebo']:.1f}")
    print(f"  p (one-sided)             {pl['p_value_one_sided']:.4f}")
    print(f"  verdict                   {pl['verdict']}")
    share = pl["placebo_mean"] / observed if observed != 0 else np.nan
    print(f"  the placebo reproduces {100*share:.0f}% of the observed gain with NO information in")
    print(f"  the gate -- only the same distribution of waiting.")

    print("\n" + "=" * 112)
    print("E. PAIRED BLOCK BOOTSTRAP on the daily difference")
    print("=" * 112)
    pb = E.paired_bootstrap(bd, od, n_boot=5000, block=10, seed=3)
    for k, v in pb.items():
        if isinstance(v, (int, float, np.floating)):
            print(f"  {k:28s} {v:+.4f}")
        elif isinstance(v, (list, tuple)):
            print(f"  {k:28s} [{v[0]:+.4f}, {v[1]:+.4f}]")

    print("\n" + "=" * 112)
    print("F. COST SWEEP AND FILL HAIRCUT")
    print("=" * 112)
    cs = E.cost_sweep(base[["signal_id", "side", "qty", "entry_px", "exit_px"]],
                      ov[["signal_id", "side", "qty", "entry_px", "exit_px"]],
                      commission_per_share=(0.0, 0.86),
                      slippage_bps_per_side=(0.0, 0.19, 0.37, 0.75, 1.5))
    print(cs.to_string(index=False))
    be = E.improvement_breakeven(base[["signal_id", "side", "qty", "entry_px", "exit_px"]],
                                 ov[["signal_id", "side", "qty", "entry_px", "exit_px"]])
    print(f"\n  gain before haircut {be['gain_before_haircut']:+,.1f} points")
    print(f"  breakeven haircut   {be['breakeven_haircut_bps_per_side']:.4f} bps per side")
    print(f"  half the Roll implied effective spread on this series: 0.1871 bps")
    print(f"  ratio {be['breakeven_haircut_bps_per_side']/0.1871:.2f} -- below 1.0 means the "
          "overlay is claiming")
    print("  more price improvement than the spread it would be trying to earn.")

    print("\n" + "=" * 112)
    print("G. TIMEOUT AND MISSED-TRADE CENSUS")
    print("=" * 112)
    for K in KS:
        o2, st2 = O.trades(D, gate=1, K=K)
        skipped = np.flatnonzero(st2 == 1)
        cf = base[base["signal_id"].isin(skipped)]
        print(f"  K {K:4d} min: skipped {len(skipped):4d} signals "
              f"({100*len(skipped)/n_sig:4.1f}% of all)   their baseline PnL "
              f"{cf['net'].sum():+9,.0f} pts   mean {cf['net'].mean() if len(cf) else np.nan:+8.2f} "
              f"vs the kept trades' {base[~base['signal_id'].isin(skipped)]['net'].mean():+7.2f}")
    print("\n  A skipped signal is one where the stop level was breached while the overlay waited.")
    print("  If those were on average large winners, the overlay buys its Sharpe with foregone")
    print("  return; if large losers, the gain is a FILTER result and needs its own trial count.")


if __name__ == "__main__":
    main()
