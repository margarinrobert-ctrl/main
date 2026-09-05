"""THE ONE REAL DEFECT IN run_ov2: the baseline had no position lock, so all 5,045 signals were
taken independently -- ~6.7 concurrent positions a day. That is fine for isolating an entry
timestamp and it is NOT a tradeable book, so the verdict deserves a re-read on a baseline a
one-contract account could hold.

Each arm locks on its OWN exit bars, which is what a real book does and which lets the overlay
change the population by more than the four trades it dropped without one.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ov_core as O                      # noqa: E402
import overlay_eval as E                 # noqa: E402

K_MAIN = 30

pd.set_option("display.width", 200)


def line(t):
    print("\n" + "=" * 112)
    print(t)
    print("=" * 112)


def summary(t, D):
    d = O.daily(t, D)
    ts = tail(d)
    return dict(trades=len(t), pts=t["net"].mean(), pct=t["pct"].mean(),
                win=100 * (t["net"] > 0).mean(), total=t["net"].sum(),
                hold=t["hold_min"].median(),
                sharpe=np.sqrt(252) * d.mean() / d.std(ddof=1),
                maxdd=ts["max_drawdown"], worst=ts["worst_day"], cvar=ts["cvar_05"])


def tail(d):
    return E.tail_stats(d)


if __name__ == "__main__":
    D = O.build("NQ", 1)
    n_sig = len(D["sig_bar"])

    line("THE POSITION LOCK -- what the baseline looks like when one account has to hold it")
    rows = []
    for lk in (0, 1):
        b, st = O.trades(D, gate=0, lock=lk)
        rows.append(dict(lock=lk, **summary(b, D),
                         blocked=int((st == 3).sum())))
    print(pd.DataFrame(rows).to_string(index=False,
          float_format=lambda v: f"{v:,.3f}"))
    print("\n  concurrency without the lock is what makes the unlocked total large; the locked")
    print("  book is the one an account can actually carry.")

    base, bst = O.trades(D, gate=0, lock=1)
    ov, ost = O.trades(D, gate=1, K=K_MAIN, lock=1)
    bd, od = O.daily(base, D), O.daily(ov, D)

    line("A. BASELINE vs OVERLAY, both with the position lock on")
    sb, so = summary(base, D), summary(ov, D)
    key = [("trades", "trades"), ("points / trade", "pts"), ("% of entry price / trade", "pct"),
           ("win rate %", "win"), ("total points", "total"), ("median hold (min)", "hold"),
           ("Sharpe (daily, ann.)", "sharpe"), ("max drawdown (pts)", "maxdd"),
           ("worst day (pts)", "worst"), ("CVaR 5% (pts)", "cvar")]
    print(f"  {'metric':30s}{'baseline':>13s}{'overlay':>13s}{'Δ':>13s}")
    for lab, k in key:
        print(f"  {lab:30s}{sb[k]:13,.3f}{so[k]:13,.3f}{so[k]-sb[k]:+13,.3f}")
    print(f"\n  blocked by the lock: baseline {int((bst==3).sum()):,}   "
          f"overlay {int((ost==3).sum()):,}   "
          f"stopped while waiting: {int((ost==1).sum()):,}")

    line("B. ATTRIBUTION with the lock on")
    dec = E.decompose(base[["signal_id", "side", "qty", "entry_px", "exit_px"]],
                      ov[["signal_id", "side", "qty", "entry_px", "exit_px"]])
    print(f"  total difference {dec['total_difference']:+,.1f} points   "
          f"matched {dec['n_matched']}   dropped by overlay {dec['n_dropped_by_overlay']}   "
          f"added {dec['n_added_by_overlay']}")
    for k, v in dec["components"].items():
        print(f"    {k:22s} {v:+12,.1f} pts   {dec['pct_of_total'][k]:+7.1f}% of Δ")
    if dec["warning"]:
        print(f"  WARNING: {dec['warning']}")

    line("C. THE RANDOM-DELAY PLACEBO with the lock on")
    obs_delays = ov["delay"].to_numpy()
    base_total = base["net"].sum()
    observed = ov["net"].sum() - base_total

    def run_fn(sample_delays):
        d = np.round(sample_delays(n_sig)).astype(np.int64)
        t, _ = O.trades(D, gate=2, K=K_MAIN, rand_delay=d, lock=1)
        return float(t["net"].sum() - base_total)

    pl = E.placebo_test(run_fn, obs_delays, n_sims=200, seed=7,
                        observed_improvement=observed)
    print(f"  observed improvement      {observed:+,.1f} points")
    print(f"  placebo mean              {pl['placebo_mean']:+,.1f} points")
    print(f"  placebo 5-95%            [{pl['placebo_q05']:+,.1f}, {pl['placebo_q95']:+,.1f}]")
    print(f"  percentile vs placebo     {pl['percentile_vs_placebo']:.1f}")
    print(f"  p (one-sided)             {pl['p_value_one_sided']:.4f}")
    print(f"  verdict                   {pl['verdict']}")

    line("D. PAIRED BLOCK BOOTSTRAP with the lock on")
    pb = E.paired_bootstrap(bd, od, n_boot=5000, block=10, seed=3)
    for k, v in pb.items():
        if isinstance(v, (list, tuple, np.ndarray)):
            print(f"  {k:28s} [{v[0]:+,.4f}, {v[1]:+,.4f}]")
        else:
            print(f"  {k:28s} {v:+,.4f}")

    line("E. FILL HAIRCUT with the lock on")
    bk = E.improvement_breakeven(base, ov)
    for k, v in bk.items():
        print(f"  {k:28s} {v}")

    line("F. URGENCY SWEEP with the lock on")
    print(f"  {'K (min)':>9s}{'trades':>9s}{'blocked':>9s}{'skipped':>9s}"
          f"{'pts/trade':>12s}{'Δ vs base':>12s}{'total Δ':>11s}")
    print(f"  {'baseline':>9s}{len(base):9,d}{int((bst==3).sum()):9,d}{0:9,d}"
          f"{sb['pts']:12,.3f}{0.0:+12.3f}{0.0:+11,.0f}")
    for K in (5, 10, 15, 30, 60, 120):
        t, st = O.trades(D, gate=1, K=K, lock=1)
        print(f"  {K:9d}{len(t):9,d}{int((st==3).sum()):9,d}{int((st==1).sum()):9,d}"
              f"{t['net'].mean():12,.3f}{t['net'].mean()-sb['pts']:+12.3f}"
              f"{t['net'].sum()-base_total:+11,.0f}")
