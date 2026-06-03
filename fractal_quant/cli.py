"""Command-line entry point.

Examples
--------
    python -m fractal_quant.cli --symbol QQQ
    python -m fractal_quant.cli --symbol SPY --shorts --cost-bps 1.5
    python -m fractal_quant.cli --symbol QQQ --walk-forward
    python -m fractal_quant.cli --symbol SPY --msm --msm-k 5
    python -m fractal_quant.cli --csv mydata.csv

Built for a non-coder: sensible defaults, clear printed output, charts saved
to ./charts/<symbol>/.
"""
from __future__ import annotations

import argparse
import os

import numpy as np

from . import __version__
from . import data as datamod
from . import report
from .backtest import backtest
from .strategy import StrategyParams, generate_signals
from .validation import sweep, walk_forward


def build_parser() -> argparse.ArgumentParser:
    pa = argparse.ArgumentParser(
        prog="fractal_quant",
        description="Fractal regime engine (Hurst/FRAMA) + honest backtest "
                    f"+ MSM vol model.  v{__version__}")
    pa.add_argument("--symbol", default="QQQ",
                    help="ticker: SPY ^GSPC ES=F QQQ ^NDX NQ=F (default QQQ)")
    pa.add_argument("--csv", help="load a CSV (Date,Close[,OHLC]) instead of yfinance")
    pa.add_argument("--start", help="start date YYYY-MM-DD (else --period)")
    pa.add_argument("--period", default="5y", help="yfinance period (default 5y)")
    pa.add_argument("--no-cache", action="store_true", help="ignore local cache")

    pa.add_argument("--hwin", type=int, default=120, help="Hurst window")
    pa.add_argument("--framaN", type=int, default=16, help="FRAMA period")
    pa.add_argument("--zlook", type=int, default=20, help="z-score lookback")
    pa.add_argument("--shorts", action="store_true", help="allow short positions")
    pa.add_argument("--hurst", choices=["rs", "dfa"], default="rs",
                    help="Hurst estimator (default rs; dfa less biased)")
    pa.add_argument("--cost-bps", type=float, default=1.0,
                    help="transaction cost per side in bps (default 1.0)")

    pa.add_argument("--walk-forward", action="store_true",
                    help="run walk-forward OOS validation + param sweep")
    pa.add_argument("--msm", action="store_true",
                    help="fit the MSM volatility model + GARCH benchmark")
    pa.add_argument("--msm-k", type=int, default=4, help="MSM components k")
    pa.add_argument("--out", default="charts", help="output dir (default charts)")
    pa.add_argument("--no-charts", action="store_true", help="skip saving charts")
    return pa


def _load(args) -> dict:
    if args.csv:
        print(f"[data] loading CSV {args.csv}")
        return datamod.load_csv(args.csv)
    return datamod.load(args.symbol, start=args.start, period=args.period,
                        use_cache=not args.no_cache)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    name = args.symbol if not args.csv else os.path.basename(args.csv)
    out_dir = os.path.join(args.out, name.replace("^", "_").replace("=", "_"))

    data = _load(args)
    p = StrategyParams(hwin=args.hwin, framaN=args.framaN, zlook=args.zlook,
                       allow_short=args.shorts, hurst_method=args.hurst)

    sig = generate_signals(data, p)
    res = backtest(sig["ret"], sig["pos"], cost_bps=args.cost_bps)

    period = (f"{data['date'][0]} -> {data['date'][-1]}  ·  "
              f"{len(data['date'])} bars")
    label = "Fractal " + ("(L/S)" if args.shorts else "(long-only)")
    print()
    print("=" * 64)
    print(f"  FRACTAL REGIME ENGINE — {name}  (H={args.hurst.upper()})")
    print("=" * 64)
    _print_live(sig)
    print()
    print(report.stats_table(res, period=period, label=label))

    if not args.no_charts:
        paths = report.save_charts(data, sig, res, out_dir, symbol=name)
        print("\n[charts] saved:")
        for pth in paths:
            print(f"  {pth}")

    if args.walk_forward:
        _run_walk_forward(data, p, args, out_dir)

    if args.msm:
        _run_msm(data, sig, args, out_dir)

    print("\n" + report.caveats_text())
    return 0


def _print_live(sig):
    """Print the four live signal cards (regime / Hurst / signal / vol)."""
    def last_valid(a, pred=lambda v: not (isinstance(v, float) and np.isnan(v))):
        for v in reversed(list(a)):
            if pred(v):
                return v
        return None
    reg = last_valid(sig["regime"], lambda v: v not in ("na", None))
    h = last_valid(sig["H"], lambda v: not np.isnan(v))
    pos = sig["pos"][-1]
    vol = last_valid(sig["vol"], lambda v: not np.isnan(v))
    regmap = {"trend": "TRENDING (momentum)", "revert": "MEAN-REVERT (fade)",
              "random": "RANDOM (flat)", None: "—"}
    sigtxt = "LONG" if pos > 0 else "SHORT" if pos < 0 else "FLAT"
    htxt = f"{h:.3f}" if h is not None else "—"
    htag = ("" if h is None else
            "persistent" if h > 0.55 else
            "anti-persistent" if h < 0.45 else "≈ random walk")
    vtxt = f"{vol*100:.1f}%" if vol is not None else "—"
    print(f"  Current regime : {regmap.get(reg, '—')}")
    print(f"  Hurst exponent : {htxt}  ({htag})")
    print(f"  Live signal    : {sigtxt}  (position for next bar)")
    print(f"  Volatility     : {vtxt}  (20d realized, annualized)")


def _run_walk_forward(data, p, args, out_dir):
    print("\n" + "-" * 64)
    print("  WALK-FORWARD (out-of-sample) VALIDATION")
    print("-" * 64)
    try:
        wf = walk_forward(data, p, cost_bps=args.cost_bps)
    except RuntimeError as e:
        print(f"  skipped: {e}")
        return
    print(f"  OOS bars: {wf.n_oos}   (re-selected params each block)")
    print(f"  Strategy OOS  : total {report._pct(wf.s.total)}  "
          f"CAGR {report._pct(wf.s.cagr)}  Sharpe {wf.s.sharpe:.2f}  "
          f"MaxDD {report._pct(wf.s.max_dd)}")
    print(f"  Buy & hold OOS: total {report._pct(wf.b.total)}  "
          f"CAGR {report._pct(wf.b.cagr)}  Sharpe {wf.b.sharpe:.2f}  "
          f"MaxDD {report._pct(wf.b.max_dd)}")
    if not args.no_charts:
        n_oos = wf.n_oos
        dts = data["date"][-n_oos:]
        path = report.save_equity(wf.eq_strat, wf.eq_bh, dts,
                                  os.path.join(out_dir, "walkforward.png"),
                                  "Walk-forward OOS — Growth of $10,000")
        grid, best = sweep(data, (80, 120, 160, 200), (10, 16, 24, 32), p,
                           cost_bps=args.cost_bps)
        sp = report.save_sweep(grid, (80, 120, 160, 200), (10, 16, 24, 32),
                               os.path.join(out_dir, "sweep.png"))
        print(f"  best in-sample params: hwin={best.hwin} framaN={best.framaN} "
              f"(NB: in-sample, shown only to gauge overfitting)")
        print(f"  [charts] {path}\n           {sp}")


def _run_msm(data, sig, args, out_dir):
    from . import msm as msmmod
    print("\n" + "-" * 64)
    print(f"  MSM VOLATILITY MODEL (Calvet-Fisher, k={args.msm_k})")
    print("-" * 64)
    ret = sig["ret"][1:]
    fit = msmmod.fit(ret, k=args.msm_k)
    print(f"  {fit.summary()}")
    fc = msmmod.forecast_vol(fit)
    print("  Volatility forecast (annualized):")
    for H, v in fc.items():
        print(f"    {H:>3d}-day horizon : {v*100:5.1f}%")

    # benchmark vs GARCH(1,1) on RMSE against realized vol
    msm_path = msmmod.conditional_vol_path(fit, ret)
    garch_path, garch_ll = msmmod.garch_benchmark(ret)
    realized = sig["vol"][1:]
    valid = ~np.isnan(realized)
    rmse_msm = float(np.sqrt(np.mean((msm_path[valid] - realized[valid]) ** 2)))
    print(f"  RMSE vs 20d realized: MSM {rmse_msm*100:.2f}%", end="")
    if garch_path is not None:
        m = min(len(garch_path), valid.size)
        gv = valid[:m]
        rmse_g = float(np.sqrt(np.mean(
            (garch_path[:m][gv] - realized[:m][gv]) ** 2)))
        print(f"  |  GARCH(1,1) {rmse_g*100:.2f}%  (LL {garch_ll:.0f})")
        better = "MSM" if rmse_msm <= rmse_g else "GARCH"
        print(f"  -> lower RMSE: {better}")
    else:
        print("  |  GARCH benchmark unavailable (install `arch`)")

    if not args.no_charts:
        path = report.save_vol_forecast(
            realized, msm_path, garch_path, data["date"][1:],
            os.path.join(out_dir, "vol_forecast.png"))
        print(f"  [charts] {path}")
    print("  NB: vol forecasting is descriptive; rich/cheap-vs-implied is "
          "left to the user. Not a trade signal.")


if __name__ == "__main__":
    raise SystemExit(main())
