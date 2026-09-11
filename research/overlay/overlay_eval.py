"""
overlay_eval.py — falsification tools for fast-alpha execution overlays.

The premise: adding an entry/exit delay rule to a backtest is one of the easiest
ways to manufacture an improvement that does not exist. These functions exist to
kill such results cheaply, before capital meets them.

Dependencies: numpy, pandas. scipy is optional (used only for a normal-approx
p-value when the bootstrap is degenerate).

Trade-log convention used by decompose() and cost_sweep():

    signal_id   identifier of the slow-strategy signal that generated the trade.
                Must match across the baseline and overlay logs so trades can be
                paired. This is the join key; without it there is no attribution.
    side        +1 long, -1 short
    qty         shares/contracts (must be equal across arms for a valid
                comparison — if the overlay changed size, the comparison is
                contaminated by leverage)
    entry_px    fill price on entry
    exit_px     fill price on exit
    entry_time  optional, used for holding-period stats
    exit_time   optional

Run `python overlay_eval.py` for a self-test on synthetic data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "roll_spread",
    "decompose",
    "placebo_test",
    "paired_bootstrap",
    "cost_sweep",
    "improvement_breakeven",
    "tail_stats",
]


# --------------------------------------------------------------------------
# 1. Bounce floor
# --------------------------------------------------------------------------

def roll_spread(prices, return_bps: bool = True) -> dict:
    """Roll (1984) implied effective spread from serial covariance of returns.

    In a market where the only source of negative autocorrelation is trades
    alternating between bid and ask, the effective spread satisfies

        spread = 2 * sqrt(-cov(r_t, r_{t-1}))

    Interpretation: any short-horizon "mean reversion" edge smaller than about
    half this number is plausibly bid-ask bounce in the print series rather than
    a forecastable price path. Bounce cannot be harvested — you cannot buy at the
    bid by wanting to — so an overlay whose claimed edge sits below this floor
    needs the placebo test before any of its results are believable.

    A non-negative covariance means Roll's assumption fails (momentum dominates
    at this frequency); the estimator returns NaN and the diagnostic is simply
    unavailable, which is not itself evidence either way.

    Parameters
    ----------
    prices : array-like of trade/close prices, evenly spaced
    return_bps : express the spread in basis points of mean price as well

    Returns
    -------
    dict with 'cov', 'spread_abs', 'spread_bps', 'half_spread_bps'
    """
    p = np.asarray(pd.Series(prices).dropna(), dtype=float)
    if p.size < 3:
        raise ValueError("need at least 3 prices")
    r = np.diff(p)
    cov = float(np.cov(r[1:], r[:-1], ddof=1)[0, 1])

    if cov >= 0:
        spread_abs = np.nan
    else:
        spread_abs = 2.0 * np.sqrt(-cov)

    mean_px = float(np.mean(p))
    spread_bps = np.nan if np.isnan(spread_abs) else spread_abs / mean_px * 1e4

    return {
        "cov": cov,
        "spread_abs": spread_abs,
        "spread_bps": spread_bps if return_bps else np.nan,
        "half_spread_bps": spread_bps / 2 if not np.isnan(spread_bps) else np.nan,
        "note": (
            "cov >= 0: Roll's assumption violated, floor unavailable"
            if cov >= 0 else
            "compare per-trade edge (bps) to half_spread_bps"
        ),
    }


# --------------------------------------------------------------------------
# 2. Attribution
# --------------------------------------------------------------------------

def _pnl(df: pd.DataFrame) -> pd.Series:
    return df["side"] * df["qty"] * (df["exit_px"] - df["entry_px"])


def decompose(base_trades: pd.DataFrame, overlay_trades: pd.DataFrame) -> dict:
    """Attribute the total PnL difference between two arms to its sources.

    The headline "overlay improved the strategy" hides at least three different
    claims. This separates them:

      entry_improvement  better fill prices on trades BOTH arms took
      exit_improvement   better exit prices on trades BOTH arms took
      dropped_trades     PnL of baseline trades the overlay never took
                         (negative of their PnL: the overlay forwent them)
      added_trades       PnL of trades only the overlay took
      residual           anything unexplained (should be ~0 by construction;
                         non-zero indicates qty mismatch between arms)

    A gain concentrated in `dropped_trades` is a *filter* result, not an
    execution result, and must be re-validated as a filter with its own trial
    count. A gain concentrated in `entry_improvement` is the claim usually being
    made — and is the one roll_spread() and placebo_test() are built to falsify.

    Trades are matched on `signal_id`.
    """
    for name, df in (("base", base_trades), ("overlay", overlay_trades)):
        missing = {"signal_id", "side", "qty", "entry_px", "exit_px"} - set(df.columns)
        if missing:
            raise ValueError(f"{name}_trades missing columns: {sorted(missing)}")

    b = base_trades.set_index("signal_id")
    o = overlay_trades.set_index("signal_id")

    common = b.index.intersection(o.index)
    only_b = b.index.difference(o.index)
    only_o = o.index.difference(b.index)

    bc, oc = b.loc[common], o.loc[common]

    if not np.allclose(bc["qty"].to_numpy(), oc["qty"].to_numpy()):
        qty_warning = (
            "qty differs between arms on matched trades — the comparison mixes "
            "an execution change with a leverage change and the decomposition "
            "below is not clean"
        )
    else:
        qty_warning = None

    # For a long, paying less on entry is a gain; for a short, receiving more is.
    entry_improvement = float(
        (-bc["side"] * bc["qty"] * (oc["entry_px"] - bc["entry_px"])).sum()
    )
    exit_improvement = float(
        (bc["side"] * bc["qty"] * (oc["exit_px"] - bc["exit_px"])).sum()
    )
    dropped = float(-_pnl(b.loc[only_b]).sum()) if len(only_b) else 0.0
    added = float(_pnl(o.loc[only_o]).sum()) if len(only_o) else 0.0

    total = float(_pnl(o).sum() - _pnl(b).sum())
    explained = entry_improvement + exit_improvement + dropped + added

    parts = {
        "entry_improvement": entry_improvement,
        "exit_improvement": exit_improvement,
        "dropped_trades": dropped,
        "added_trades": added,
        "residual": total - explained,
    }
    denom = abs(total) if abs(total) > 1e-12 else np.nan

    return {
        "total_difference": total,
        "components": parts,
        "pct_of_total": {k: (v / denom * 100 if denom == denom else np.nan)
                         for k, v in parts.items()},
        "n_matched": int(len(common)),
        "n_dropped_by_overlay": int(len(only_b)),
        "n_added_by_overlay": int(len(only_o)),
        "warning": qty_warning,
    }


# --------------------------------------------------------------------------
# 3. Random-delay placebo
# --------------------------------------------------------------------------

def placebo_test(run_fn, observed_delays, n_sims: int = 200, seed: int = 0,
                 observed_improvement: float | None = None) -> dict:
    """Null distribution for an overlay improvement under uninformative delays.

    The question this answers: how much of the improvement survives when the
    delay is preserved but the *information* is removed? If a random gate with
    the same delay profile reproduces the gain, the fast signal is not doing the
    work — mechanical delay is, and the mechanism is usually bid-ask bounce or a
    change in which trades get taken.

    Parameters
    ----------
    run_fn : callable(sample_delays) -> float
        Re-runs the strategy using `sample_delays(n) -> array of n delays in
        bars` in place of the real gate, and returns the improvement over
        baseline in the same units as `observed_improvement` (total PnL, CAGR
        difference, Sharpe difference — pick one and be consistent).
    observed_delays : array-like
        Delays in bars that the *real* overlay produced. Resampled with
        replacement so the placebo matches the real delay distribution rather
        than an invented one — matching the mean alone is not enough, since the
        tail of long waits is where population change happens.
    n_sims : number of placebo runs (200+ recommended)
    observed_improvement : the real overlay's improvement, for percentile scoring

    Returns
    -------
    dict with the placebo distribution, and if `observed_improvement` is given,
    the percentile and a one-sided empirical p-value.
    """
    delays = np.asarray(observed_delays, dtype=float)
    delays = delays[~np.isnan(delays)]
    if delays.size == 0:
        raise ValueError("observed_delays is empty")

    rng = np.random.default_rng(seed)

    def sample_delays(n):
        return rng.choice(delays, size=int(n), replace=True)

    results = np.array([float(run_fn(sample_delays)) for _ in range(int(n_sims))])

    out = {
        "placebo_mean": float(np.mean(results)),
        "placebo_std": float(np.std(results, ddof=1)) if results.size > 1 else np.nan,
        "placebo_q05": float(np.quantile(results, 0.05)),
        "placebo_q95": float(np.quantile(results, 0.95)),
        "n_sims": int(n_sims),
        "distribution": results,
    }

    if observed_improvement is not None:
        obs = float(observed_improvement)
        pct = float((results < obs).mean() * 100)
        p = float((results >= obs).mean())
        out.update({
            "observed": obs,
            "percentile_vs_placebo": pct,
            "p_value_one_sided": p,
            "verdict": (
                "improvement is within the placebo distribution — the fast signal "
                "is not the source of the gain"
                if p > 0.10 else
                "improvement exceeds mechanical delay; the signal is doing work"
            ),
        })
    return out


# --------------------------------------------------------------------------
# 4. Paired significance
# --------------------------------------------------------------------------

def paired_bootstrap(base_daily, overlay_daily, n_boot: int = 5000,
                     block: int = 10, seed: int = 0,
                     periods_per_year: int = 252) -> dict:
    """Block bootstrap on the DIFFERENCE of two daily PnL/return series.

    The two arms share nearly all of their risk, so comparing standalone Sharpes
    with independent standard errors is badly over-conservative, while eyeballing
    "0.87 vs 0.99" is over-permissive. The paired difference series is the right
    object, and a moving-block bootstrap preserves the autocorrelation that an
    iid bootstrap would destroy.

    Series must be aligned and equal length (index alignment is applied if both
    are pandas Series).

    Returns mean daily difference, Sharpe difference, bootstrap CIs, and
    two-sided p-values for both.
    """
    if isinstance(base_daily, pd.Series) and isinstance(overlay_daily, pd.Series):
        joined = pd.concat([base_daily.rename("b"), overlay_daily.rename("o")],
                           axis=1).dropna()
        b, o = joined["b"].to_numpy(float), joined["o"].to_numpy(float)
    else:
        b = np.asarray(base_daily, dtype=float)
        o = np.asarray(overlay_daily, dtype=float)
        if b.shape != o.shape:
            raise ValueError("series must be the same length")

    d = o - b
    n = d.size
    if n < block * 3:
        raise ValueError(f"series too short ({n}) for block size {block}")

    def sharpe(x):
        s = np.std(x, ddof=1)
        return float(np.mean(x) / s * np.sqrt(periods_per_year)) if s > 0 else np.nan

    obs_mean = float(np.mean(d))
    obs_sharpe_diff = sharpe(o) - sharpe(b)

    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    starts_max = n - block

    means = np.empty(n_boot)
    sdiffs = np.empty(n_boot)
    for i in range(int(n_boot)):
        starts = rng.integers(0, starts_max + 1, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        means[i] = np.mean(d[idx])
        sdiffs[i] = sharpe(o[idx]) - sharpe(b[idx])

    # Two-sided p: proportion of resampled means on the other side of zero,
    # centred on the observed statistic (basic bootstrap null).
    centred = means - obs_mean
    p_mean = float(np.mean(np.abs(centred) >= abs(obs_mean)))
    centred_s = sdiffs - obs_sharpe_diff
    p_sharpe = float(np.mean(np.abs(centred_s) >= abs(obs_sharpe_diff)))

    return {
        "n_obs": int(n),
        "mean_daily_difference": obs_mean,
        "mean_ci95": (float(np.quantile(means, 0.025)),
                      float(np.quantile(means, 0.975))),
        "p_value_mean": p_mean,
        "sharpe_base": sharpe(b),
        "sharpe_overlay": sharpe(o),
        "sharpe_difference": obs_sharpe_diff,
        "sharpe_diff_ci95": (float(np.quantile(sdiffs, 0.025)),
                             float(np.quantile(sdiffs, 0.975))),
        "p_value_sharpe": p_sharpe,
        "block": int(block),
        "n_boot": int(n_boot),
    }


# --------------------------------------------------------------------------
# 5. Cost / slippage sweep
# --------------------------------------------------------------------------

def cost_sweep(base_trades: pd.DataFrame, overlay_trades: pd.DataFrame,
               commission_per_share=(0.0, 0.0035),
               slippage_bps_per_side=(0.0, 0.25, 0.5, 1.0, 2.0)) -> pd.DataFrame:
    """Net PnL for both arms across a grid of commission and slippage.

    The number that matters is not any single cell but the slippage level at
    which the overlay's advantage disappears. An overlay claiming better fills
    while assuming zero slippage is claiming a better price and paying the same
    taker cost — the assumption does not cancel between arms, it favours the
    overlay. If the advantage dies at a quarter of a tick, it was a rounding
    artifact.

    Slippage is charged per side, in bps of the fill price, on both entry and
    exit. Commission is per share on both sides.
    """
    rows = []
    for comm in commission_per_share:
        for slip in slippage_bps_per_side:
            vals = {}
            for name, df in (("base", base_trades), ("overlay", overlay_trades)):
                gross = _pnl(df).sum()
                shares = (df["qty"].abs() * 2).sum()          # entry + exit
                comm_cost = shares * comm
                slip_cost = (df["qty"].abs() *
                             (df["entry_px"] + df["exit_px"]) * slip / 1e4).sum()
                vals[name] = float(gross - comm_cost - slip_cost)
            rows.append({
                "commission_per_share": comm,
                "slippage_bps_per_side": slip,
                "base_net": vals["base"],
                "overlay_net": vals["overlay"],
                "improvement": vals["overlay"] - vals["base"],
            })
    out = pd.DataFrame(rows)
    out["improvement_positive"] = out["improvement"] > 0
    out.attrs["n_trades_base"] = int(len(base_trades))
    out.attrs["n_trades_overlay"] = int(len(overlay_trades))
    if len(base_trades) != len(overlay_trades):
        out.attrs["warning"] = (
            "arms have different trade counts, so cost level and trade "
            "selection move together in this table — read it alongside "
            "decompose(), not on its own"
        )
    return out


def improvement_breakeven(base_trades: pd.DataFrame,
                          overlay_trades: pd.DataFrame) -> dict:
    """How much of the overlay's claimed fill improvement can be given back
    before the advantage disappears?

    The realistic failure mode is not that the overlay's logic is wrong but that
    it captures only a fraction of the price improvement the backtest books —
    because the better print required resting an order that often did not fill,
    or crossing anyway. This charges the overlay arm a per-side haircut in bps
    and finds the level at which the improvement hits zero.

    Read the result against the instrument's spread. If the improvement dies at
    a haircut well below half the spread, the overlay never had room to be real.
    """
    base_pnl = float(_pnl(base_trades).sum())
    ov_pnl = float(_pnl(overlay_trades).sum())
    gain = ov_pnl - base_pnl

    notional_per_bps = float(
        (overlay_trades["qty"].abs() *
         (overlay_trades["entry_px"] + overlay_trades["exit_px"])).sum() / 1e4
    )
    if notional_per_bps <= 0:
        raise ValueError("overlay notional is zero")

    breakeven = gain / notional_per_bps
    return {
        "gain_before_haircut": gain,
        "breakeven_haircut_bps_per_side": float(breakeven),
        "note": (
            "improvement survives only if realised fill quality is within "
            f"{breakeven:.3f} bps/side of what the backtest assumed"
        ),
    }


# --------------------------------------------------------------------------
# 6. Tail statistics
# --------------------------------------------------------------------------

def tail_stats(daily, periods_per_year: int = 252) -> dict:
    """Drawdown and left-tail statistics.

    Required whenever exits are gated. Waiting for a favourable counter-move
    before honouring a stop improves the average exit and fattens the left tail,
    because the counter-move is exactly what fails to arrive on the days that
    matter. That trade-off is invisible in Sharpe and obvious here.
    """
    x = np.asarray(pd.Series(daily).dropna(), dtype=float)
    if x.size == 0:
        raise ValueError("empty series")
    equity = np.cumsum(x)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    sd = np.std(x, ddof=1)
    q05 = np.quantile(x, 0.05)
    return {
        "total": float(equity[-1]),
        "sharpe": float(np.mean(x) / sd * np.sqrt(periods_per_year)) if sd > 0 else np.nan,
        "max_drawdown": float(dd.min()),
        "worst_day": float(x.min()),
        "cvar_05": float(x[x <= q05].mean()),
        "pct_days_negative": float((x < 0).mean() * 100),
        "skew": float(pd.Series(x).skew()),
    }


# --------------------------------------------------------------------------
# Demo / self-test
# --------------------------------------------------------------------------

def _demo():
    """Synthetic case where the 'improvement' is pure bid-ask bounce.

    A random walk is observed through a one-cent spread, so prints alternate
    around the true price. The overlay 'waits for a down bar' before buying and
    books that print as its fill — the classic illusion. The battery should
    catch it, and the placebo should reproduce almost the whole gain.
    """
    rng = np.random.default_rng(7)
    n = 20_000
    half_spread = 0.005                                  # one cent wide
    true_px = 400 + np.cumsum(rng.normal(0, 0.02, n))    # ~5-min SPY-ish vol
    prints = true_px + rng.choice([-1, 1], n) * half_spread

    print("=" * 70)
    print("1. BOUNCE FLOOR — Roll implied spread")
    print("=" * 70)
    roll = roll_spread(prints)
    print(f"  implied spread   {roll['spread_abs']:.4f}  "
          f"({roll['spread_bps']:.3f} bps)     true {2 * half_spread:.4f}")
    print(f"  half-spread floor {roll['half_spread_bps']:.3f} bps")
    print("  -> a claimed per-trade edge below this is presumed bounce\n")

    # Both arms see the same 300 signals. The overlay's only change is booking
    # a fill one full spread better, i.e. it books the bounce and nothing else.
    n_sig = 300
    idx = rng.integers(10, n - 10, n_sig)
    base = pd.DataFrame({
        "signal_id": np.arange(n_sig),
        "side": 1,
        "qty": 100.0,
        "entry_px": prints[idx] + half_spread,
        "exit_px": prints[idx] + rng.normal(0.10, 0.5, n_sig),
    })
    overlay = base.copy()
    overlay["entry_px"] = base["entry_px"] - 2 * half_spread
    skipped = rng.choice(n_sig, 20, replace=False)
    overlay = overlay[~overlay["signal_id"].isin(skipped)]

    print("=" * 70)
    print("2. ATTRIBUTION")
    print("=" * 70)
    dec = decompose(base, overlay)
    print(f"  total difference  ${dec['total_difference']:,.2f}")
    for k, v in dec["components"].items():
        print(f"    {k:<22} ${v:>10,.2f}   {dec['pct_of_total'][k]:>6.1f}%")
    print(f"  matched {dec['n_matched']}, dropped by overlay "
          f"{dec['n_dropped_by_overlay']}")
    print("  -> components offset: a large booked 'entry improvement' partly "
          "cancelled\n     by forgone trades. Neither number is visible in a "
          "headline Sharpe.\n")

    print("=" * 70)
    print("3. PLACEBO — random delays, same distribution, no information")
    print("=" * 70)
    observed_delays = rng.integers(1, 4, len(overlay))

    def run_fn(sample_delays):
        d = sample_delays(len(overlay))
        # A delay of any length lands on a random side of the book, so a
        # mechanical wait books the same half-spread the real gate did.
        booked = (d > 0) * 2 * half_spread * 100.0
        return float(booked.sum() + rng.normal(0, 15))

    pl = placebo_test(run_fn, observed_delays, n_sims=300,
                      observed_improvement=dec["total_difference"])
    print(f"  observed      ${pl['observed']:,.2f}")
    print(f"  placebo mean  ${pl['placebo_mean']:,.2f}   "
          f"[{pl['placebo_q05']:,.2f}, {pl['placebo_q95']:,.2f}]")
    print(f"  percentile {pl['percentile_vs_placebo']:.1f}   "
          f"p = {pl['p_value_one_sided']:.3f}")
    print(f"  -> {pl['verdict']}\n")

    print("=" * 70)
    print("4. HOW MUCH FILL QUALITY CAN BE GIVEN BACK?")
    print("=" * 70)
    be = improvement_breakeven(base, overlay)
    print(f"  gain before haircut  ${be['gain_before_haircut']:,.2f}")
    print(f"  breakeven haircut    "
          f"{be['breakeven_haircut_bps_per_side']:.3f} bps/side")
    print(f"  vs half-spread       {roll['half_spread_bps']:.3f} bps")
    print("  -> if realised fills miss the assumed price by more than the "
          "haircut,\n     the improvement is gone\n")

    print("=" * 70)
    print("5. COST SWEEP (same cost model applied to both arms)")
    print("=" * 70)
    sweep = cost_sweep(base, overlay)
    disp = sweep.copy()
    disp["commission_per_share"] = disp["commission_per_share"].map("{:.4f}".format)
    print(disp.to_string(index=False,
                         float_format=lambda v: f"{v:,.2f}"))
    if "warning" in sweep.attrs:
        print(f"\n  note: {sweep.attrs['warning']}")

    print("\n" + "=" * 70)
    print("6. PAIRED BOOTSTRAP + TAIL COMPARISON")
    print("=" * 70)
    days = 1200
    b_daily = rng.normal(0.0006, 0.01, days)
    o_daily = b_daily + rng.normal(0.00003, 0.0009, days)
    pb = paired_bootstrap(b_daily, o_daily, n_boot=800, block=10)
    print(f"  Sharpe {pb['sharpe_base']:.3f} -> {pb['sharpe_overlay']:.3f}  "
          f"(delta {pb['sharpe_difference']:+.3f}, "
          f"95% CI [{pb['sharpe_diff_ci95'][0]:+.3f}, "
          f"{pb['sharpe_diff_ci95'][1]:+.3f}])")
    print(f"  mean daily difference {pb['mean_daily_difference']:+.6f}   "
          f"p = {pb['p_value_mean']:.3f}")
    for label, s in (("base", b_daily), ("overlay", o_daily)):
        t = tail_stats(s)
        print(f"  {label:<8} maxDD {t['max_drawdown']:.4f}   "
              f"worst {t['worst_day']:.4f}   CVaR5 {t['cvar_05']:.4f}")

    print("\nAll functions executed.")


if __name__ == "__main__":
    _demo()
