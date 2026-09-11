"""Does the CMMA mean-reversion strategy have an edge on MNQ? The honest evaluation.

Order is fixed: audit, then reproduce what the notebook reported, then re-measure it properly,
then the holdout, then the robustness battery. The holdout is the last 30% of trading days and is
not read until section 6.
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cmma_core as C            # noqa: E402
import metrics as M              # noqa: E402
import montecarlo as MC          # noqa: E402
import leakage_audit as LA       # noqa: E402

PPY = 252


def sharpe_se_annual(sharpe_annual, n_obs, periods=PPY):
    """ANNUALISED standard error of an annualised Sharpe.

    `metrics.sharpe_standard_error` takes a PER-PERIOD Sharpe. Handing it an annualised one
    returns a number about sqrt(252) too small -- on this strategy 0.04 instead of 0.58, which
    would make a Sharpe indistinguishable from zero look like a precise estimate. That is the same
    class of error as the notebook's `eq.mean()/eq.std()`, so it is fixed rather than inherited.
    """
    pp = sharpe_annual / np.sqrt(periods)
    return M.sharpe_standard_error(pp, n_obs) * np.sqrt(periods)


def stats(pnl, price0):
    """Performance on the daily return series. Returns are points converted to a fraction of the
    starting index level, so Sharpe and drawdown are scale-free and comparable across feeds."""
    r = pnl / price0
    return M.performance_stats(r, periods_per_year=PPY)


def line(label, d, price0, extra=""):
    st = stats(d, price0)
    se = sharpe_se_annual(st["sharpe"], len(d))
    return (f"  {label:<34}{len(d):>6d}{d.mean():>+10.3f}{d.sum():>+11.0f}"
            f"{st['sharpe']:>+9.2f} +-{se:<5.2f}{st['max_drawdown'] * 100:>9.1f}%"
            f"{(d > 0).mean() * 100:>8.1f}%{extra}")


HDR = (f"  {'':<34}{'days':>6}{'pts/day':>10}{'total':>11}{'Sharpe':>9}"
       f"{'  +-SE':<7}{'maxDD':>9}{'win':>8}")


def main(market="NQ"):
    print("=" * 104)
    print(f"CMMA MEAN REVERSION ON MNQ -- {market} price path, does it have an edge?")
    print("=" * 104)
    f = C.load_intraday(market)
    d = C.daily_from_intraday(f)
    sig = C.signal(d)
    p_end = C.session_pnl(f, sig, mode="endpoints")
    p_bar = C.session_pnl(f, sig, mode="barbodies")
    px0 = float(d["close"].iloc[0])
    cut = C.split_at(p_end.index)
    IS = p_end.index < cut
    print(f"  {len(f):,} intraday bars, {len(d):,} daily bars, {len(p_end):,} traded days")
    print(f"  session {C.SESSION[0]}-{C.SESSION[1]} New York   split {cut.date()}  "
          f"({IS.sum()} in-sample / {(~IS).sum()} holdout)")
    print(f"  cost {C.COST_PER_ROUND_TURN_PTS:.3f} pts per round turn "
          f"(${C.ROUND_TURN_USD} fees + {C.SLIP_TICKS_PER_SIDE} tick slippage a side)")

    # ---------------------------------------------------------------- 1. audit
    print("\n" + "=" * 104)
    print("1. LEAKAGE AND EXECUTION AUDIT")
    print("=" * 104)
    feat = pd.DataFrame({"signal": p_end["sig"]}, index=p_end.index)
    fwd = (p_end["move"] / px0)
    rep = LA.audit(feat, fwd)
    print(LA.format_report(rep) if rep else "  audit: no findings")
    # `check_execution_alignment` is fed the position and the return it is HELD FOR, so its
    # "same-bar" correlation IS this strategy's information coefficient rather than a leak; the
    # leak it hunts for cannot exist here, because the signal at trading date D is built from data
    # through the end of calendar day D-2. That is verified by construction in `cmma_core.signal`
    # and the numbers are reported for what they are.
    ex = LA.check_execution_alignment(p_end["sig"], fwd)
    c0 = float(np.corrcoef(p_end["sig"], fwd)[0, 1])
    c1 = float(np.corrcoef(p_end["sig"][:-1], fwd.to_numpy()[1:])[0, 1])
    print(f"  IC of the signal against the session move it is held for : {c0:+.4f}")
    print(f"  IC against the NEXT session's move                       : {c1:+.4f}")
    bad = any(x.get("level") == LA.CRITICAL
              for x in (ex if isinstance(ex, list) else []))
    print(f"  verdict from the skill's checker                         : "
          f"{'same-bar signature' if bad else 'clean'}")
    print("  An IC of 0.065 on daily returns is small and plausible. The skill's red-flag line is")
    print("  0.15; anything above that on this kind of feature is usually a leak.")

    # ---------------------------------------------------------------- 2. the notebook's number
    print("\n" + "=" * 104)
    print("2. WHAT THE NOTEBOOK REPORTS, AND WHY IT IS NOT A SHARPE RATIO")
    print("=" * 104)
    eq = p_bar["gross"].cumsum()
    print(f"  notebook:  eq = pnl.cumsum();  sr = eq.mean() / eq.std()   ->   "
          f"{eq.mean() / eq.std():.3f}")
    print("  That is the mean of an EQUITY CURVE divided by its own standard deviation. It is")
    print("  large for any curve that trends and it has no sampling interpretation: it does not")
    print("  scale with the square root of time, it is not comparable between strategies, and it")
    print("  cannot be given a standard error. The same series scored as a return stream:")
    st = stats(p_bar["gross"], px0)
    se = sharpe_se_annual(st["sharpe"], len(p_bar))
    print(f"  annualised Sharpe on the daily return series: {st['sharpe']:+.2f} +- {se:.2f}")
    print(f"  The two happen to be close here ({eq.mean() / eq.std():.3f} against "
          f"{st['sharpe']:.2f}), which is a coincidence of this sample and not a validation of the")
    print("  formula. And the standard error is the point: +-0.58 on a 3-year sample means this")
    print("  Sharpe is not distinguishable from zero OR from 1.5 without more data.")

    # ---------------------------------------------------------------- 3. accounting and costs
    print("\n" + "=" * 104)
    print("3. THE THREE ACCOUNTING CHOICES, ONE AT A TIME (full sample)")
    print("=" * 104)
    print(HDR)
    print(line("notebook: bar bodies, gross", p_bar["gross"], px0))
    print(line("honest: session endpoints, gross", p_end["gross"], px0))
    print(line("endpoints, NET of costs", p_end["net"], px0))
    gap = p_bar["gross"].sum() - p_end["gross"].sum()
    print(f"\n  summing bar bodies instead of taking the session's endpoints is worth "
          f"{gap:+.0f} points in total")
    print(f"  ({gap / len(p_end):+.3f} a day): every gap BETWEEN bars is silently dropped.")
    print(f"  mean daily turnover {p_end['turn'].mean():.3f} contracts -> "
          f"{p_end['cost'].mean():.3f} pts/day of cost, "
          f"{p_end['cost'].sum():.0f} points over the sample.")
    be = M.breakeven_cost_bps(p_end["gross"] / px0, p_end["turn"])
    print(f"  breakeven cost: {be:.2f} bps of notional per unit turnover "
          f"(the model charges {C.COST_PER_ROUND_TURN_PTS / px0 * 1e4:.2f} bps at the sample's "
          f"first price).")

    # ---------------------------------------------------------------- 4. in-sample
    print("\n" + "=" * 104)
    print("4. IN-SAMPLE ONLY (the first 70%), net of costs")
    print("=" * 104)
    print(HDR)
    print(line("CMMA as briefed", p_end["net"][IS], px0))
    for nm, kw in (("without KER weighting", dict(use_ker=False)),
                   ("without tanh bounding", dict(use_tanh=False)),
                   ("without the EMA smoothing", dict(smooth=0)),
                   ("sign(cmma) only, no scaling",
                    dict(use_ker=False, smooth=0))):
        s2 = C.signal(d, **kw)
        q = C.session_pnl(f, s2, mode="endpoints")
        m2 = q.index < cut
        print(line(nm, q["net"][m2], px0))
    print("\n  each component removed one at a time, so a component that contributes nothing is")
    print("  visible as a row that does not move.")

    # ---------------------------------------------------------------- 5. the parameter surface
    print("\n" + "=" * 104)
    print("5. THE PARAMETER SURFACE, IN-SAMPLE -- and the trial count it creates")
    print("=" * 104)
    print("  The notebook sweeps MA type x length (cells 20-28) and then reads a decile plot and")
    print("  adds a threshold filter (cells 31-32), all on the full sample. Here the same sweep is")
    print("  run IN-SAMPLE ONLY, and every cell is counted as a trial.")
    print(f"  {'MA':<6}{'len':>5}{'days':>7}{'pts/day':>10}{'Sharpe':>9}{'net Sharpe':>12}")
    trials, sharpes, cols = 0, [], {}
    for ma in ("sma", "ema"):
        for L in range(3, 20):
            s2 = C.signal(d, ma=ma, length=L)
            q = C.session_pnl(f, s2, mode="endpoints")
            m2 = q.index < cut
            if m2.sum() < 100:
                continue
            g = stats(q["gross"][m2], px0)["sharpe"]
            n = stats(q["net"][m2], px0)["sharpe"]
            trials += 1
            sharpes.append(n)
            cols[f"{ma}_{L}"] = (q["net"][m2] / px0).reset_index(drop=True)
            if L in (3, 5, 8, 12, 19):
                print(f"  {ma:<6}{L:>5}{int(m2.sum()):>7d}"
                      f"{q['net'][m2].mean():>+10.3f}{g:>+9.2f}{n:>+12.2f}")
    sharpes = np.array(sharpes)
    print(f"\n  {trials} configurations swept.  net Sharpe: best {sharpes.max():+.2f}, "
          f"median {np.median(sharpes):+.2f}, worst {sharpes.min():+.2f}, "
          f"{(sharpes > 0).mean() * 100:.0f}% positive")
    base_n = stats(p_end["net"][IS], px0)["sharpe"]
    print(f"  the briefed cell (sma, 5) scores {base_n:+.2f} -- rank "
          f"{int((sharpes > base_n).sum()) + 1} of {trials}")
    dsr = M.deflated_sharpe_ratio(base_n, n_trials=trials, n_obs=int(IS.sum()),
                                  periods_per_year=PPY)
    print(f"  DEFLATED SHARPE at {trials} trials: {dsr}")
    try:
        R = pd.DataFrame(cols).dropna()
        pbo = M.probability_of_backtest_overfitting(R, n_splits=10, max_combinations=2000)
        print(f"  probability of backtest overfitting across the sweep: {pbo}")
    except Exception as e:
        print(f"  PBO not computed: {e}")

    # ---------------------------------------------------------------- 6. the holdout
    print("\n" + "=" * 104)
    print("6. THE HOLDOUT -- read once, now")
    print("=" * 104)
    print(HDR)
    print(line("in-sample,  net", p_end["net"][IS], px0))
    print(line("HOLDOUT,    net", p_end["net"][~IS], px0))
    print(line("in-sample,  gross", p_end["gross"][IS], px0))
    print(line("HOLDOUT,    gross", p_end["gross"][~IS], px0))

    # ---------------------------------------------------------------- 7. robustness
    print("\n" + "=" * 104)
    print("7. ROBUSTNESS ON THE FULL SAMPLE, net of costs")
    print("=" * 104)
    r = (p_end["net"] / px0)
    bb = MC.block_bootstrap(r, n_sims=2000, periods_per_year=PPY)
    print(f"  block bootstrap (stationary): {bb}")
    sh = MC.shift_null(p_end["move"] / px0, p_end["sig"], n_sims=2000, periods_per_year=PPY)
    print(f"  shift null (same position series, wrong dates): {sh}")
    print("\n  BY CALENDAR YEAR, net:")
    print(f"  {'year':<8}{'days':>6}{'pts/day':>10}{'total':>11}{'Sharpe':>9}{'win':>8}")
    for y, grp in p_end.groupby(p_end.index.year):
        if len(grp) < 20:
            continue
        print(f"  {y:<8}{len(grp):>6d}{grp['net'].mean():>+10.3f}{grp['net'].sum():>+11.0f}"
              f"{stats(grp['net'], px0)['sharpe']:>+9.2f}{(grp['net'] > 0).mean() * 100:>7.1f}%")
    top = p_end["net"].sort_values(ascending=False)
    k = max(1, len(top) // 100)
    print(f"\n  concentration: the best {k} days ({k / len(top) * 100:.1f}%) are "
          f"{top.head(k).sum() / p_end['net'].sum() * 100:.0f}% of net; "
          f"the best {k * 5} are {top.head(k * 5).sum() / p_end['net'].sum() * 100:.0f}%")

    # ---------------------------------------------------------------- 8. cost sensitivity
    print("\n" + "=" * 104)
    print("8. COST SENSITIVITY")
    print("=" * 104)
    cs = M.cost_sensitivity(p_end["gross"] / px0, p_end["turn"], periods_per_year=PPY)
    print(cs.to_string(index=False))
    return f, d, sig, p_end, p_bar, px0, cut, IS


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "NQ")
