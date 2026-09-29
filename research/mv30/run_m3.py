"""THE DECISION TEST -- because a forecast that changes nothing is not a result.

`run_m1` reproduced V67's split on US30: movement targets score 2.4-3.4x their exact circular-shift
null while DIRECTION scores 1.02x. `run_m2` reproduced VWANOM's anomaly direction and strengthened
it -- rho(detector, trade return) is NEGATIVE in **12 of 12** cells across three blocks and two
providers. Neither is an edge yet, and `STUDY_V67` is the warning: a volatility forecast reading
locked IC 0.7065 bought exactly ZERO when it was put into a stop, and lost to its own shuffled twin
out of sample, because an ATR stop already contains that information.

So three questions, in the order that can kill the idea fastest:

  A. IS THE ANOMALY SCORE JUST VOLATILITY? If the detectors correlate with a plain ATR reading at
     0.9 then "anomaly detection" is a rename and this branch has caught its own pool duplicating
     seven times already. Measured on the trigger's own bars, which is where a filter acts.

  B. THE ANOMALY AS A VETO, re-simulated. A filter is a VETO, not a subset -- refusing a signal
     releases the position lock and admits a later breakout the unfiltered run never saw
     (`STUDY_AUCTION`), and `STUDY_XAU_CVD_FEATURES` measured that the two framings disagree.
     Scored against a RANDOM GATE of the same selectivity, also re-simulated, on all three blocks.
     `run_m2` already flagged the tension this has to resolve: on the forward block the rank
     correlation is negative while the TOP-QUARTILE MEAN is higher, so a veto that removes the top
     quartile may be removing the good trades.

  C. THE ADAPTIVE HOLD CAP. Every hold cap on this branch is a constant, and time-to-touch is the
     one predictable thing an ATR stop says nothing about. A ridge fitted on research forecasts
     `ttb`; the cap becomes a multiple of that forecast instead of a fixed 96 bars. Run against a
     fixed cap AND against the SAME forecast SHUFFLED -- the test V67 says is mandatory, because a
     forecast must beat its own noise twin and not merely beat the baseline.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mv30 import mv30core as C  # noqa: E402
from mr30 import mr30core as M  # noqa: E402
from v67 import v67core as V67  # noqa: E402
from mv30.run_m2 import detectors, donchian_long, clean  # noqa: E402

KEEPS = (0.90, 0.75, 0.60, 0.50)


def resim(f, sig, side, hold=96, stop=2.0):
    return M.walk(f, sig, side, stop_a=stop, tgt_a=100.0, hold=hold)


def rand_gate_p(f, sig, side, keep, obs, n=300, seed=11, hold=96):
    """Random gate keeping the SAME fraction of signals, re-simulated end to end."""
    rng = np.random.default_rng(seed)
    k = max(10, int(round(keep * len(sig))))
    out = np.empty(n)
    for i in range(n):
        pick = np.sort(rng.choice(len(sig), size=k, replace=False))
        t = resim(f, np.asarray(sig)[pick], np.asarray(side)[pick], hold=hold)
        out[i] = t.pct.mean() if len(t) >= 10 else np.nan
    out = out[np.isfinite(out)]
    return float(np.median(out)), float(np.mean(out >= obs))


def main():
    fL = C.frame("US30L"); XL = C.features(fL); bL = M.blocks(fL)
    fI = C.frame("US30I"); XI = C.features(fI); bI = M.blocks(fI, "US30I")
    det = detectors(XL, bL["A_research"])
    dI = detectors(pd.concat([XL, XI]), np.r_[bL["A_research"], np.zeros(len(XI), bool)])
    dI = {k: v[len(XL):] for k, v in dI.items()}

    sigL, sdL = donchian_long(fL)
    sigI, sdI = donchian_long(fI)

    print("A. IS THE ANOMALY SCORE JUST VOLATILITY? |rho| on the trigger's own bars")
    at = fL["atr"].to_numpy(); c = fL["close"].to_numpy()
    volr = pd.Series(at / c).rolling(250).rank(pct=True).shift(1).to_numpy()
    for k in det:
        a = det[k][sigL]; b = volr[sigL]
        m = np.isfinite(a) & np.isfinite(b)
        r = float(np.corrcoef(pd.Series(a[m]).rank(), pd.Series(b[m]).rank())[0, 1])
        print(f"   {k:<9} vs ATR percentile: rho {r:+.4f}"
              f"   {'-- A RENAME OF VOLATILITY' if abs(r) > 0.85 else ''}")

    print("\nB. THE ANOMALY AS A VETO, re-simulated, vs a random gate of the same selectivity")
    print(f"   {'block':<14}{'det':<9}{'keep':>6}{'n':>6}{'mean %':>9}{'base %':>9}"
          f"{'uplift':>9}{'rand %':>9}{'p':>7}")
    rows = []
    for feed, fr, bb, dd, sg, sd_ in (("US30L", fL, bL, det, sigL, sdL),
                                      ("US30I", fI, bI, dI, sigI, sdI)):
        for bn, mask in bb.items():
            sel = np.array([bool(mask[i]) for i in sg])
            s0, d0 = np.asarray(sg)[sel], np.asarray(sd_)[sel]
            if len(s0) < 150:
                continue
            base = resim(fr, s0, d0)
            bm = base.pct.mean()
            for k in ("ae", "iforest"):
                a = dd[k][s0]
                for keep in KEEPS:
                    thr = np.nanquantile(a, keep)
                    ok = np.isfinite(a) & (a <= thr)
                    if ok.sum() < 60:
                        continue
                    t = resim(fr, s0[ok], d0[ok])
                    mu = t.pct.mean()
                    rmed, p = rand_gate_p(fr, s0, d0, keep, mu)
                    print(f"   {feed + ' ' + bn[0]:<14}{k:<9}{keep:>6.2f}{len(t):>6}"
                          f"{mu:>9.4f}{bm:>9.4f}{mu - bm:>9.4f}{rmed:>9.4f}{p:>7.3f}")
                    rows.append(dict(feed=feed, blk=bn, det=k, keep=keep,
                                     mu=mu, base=bm, p=p))
            print()

    print("C. THE ADAPTIVE HOLD CAP from a time-to-touch forecast, against a fixed cap")
    print("   and against the SAME FORECAST SHUFFLED (`STUDY_V67`'s mandatory twin)\n")
    from sklearn.linear_model import Ridge
    D = C.D_of(fL)
    T = V67.build_targets(D, 48)
    y = T["ttb"]
    A, med = clean(XL)
    res = bL["A_research"]
    tr = res & np.isfinite(y)
    tr[:800] = False
    mu_, sd_x = A[tr].mean(0), A[tr].std(0); sd_x[sd_x <= 0] = 1
    Zs = np.clip((A - mu_) / sd_x, -8, 8)
    rg = Ridge(alpha=50.0).fit(Zs[tr], y[tr])
    yhat = rg.predict(Zs)
    ok = np.isfinite(y) & res
    print(f"   ridge ttb forecast: research IC {V67.ic(yhat[ok], y[ok]):+.4f}", end="")
    okb = np.isfinite(y) & bL["B_holdout"]
    print(f"   holdout IC {V67.ic(yhat[okb], y[okb]):+.4f}")
    rngs = np.random.default_rng(3)
    yshuf = yhat.copy()
    blkn = 500
    nb = len(yshuf) // blkn
    yshuf[:nb * blkn] = np.roll(yshuf[:nb * blkn].reshape(nb, blkn),
                                int(rngs.integers(1, nb)), axis=0).ravel()
    print(f"\n   {'block':<14}{'policy':<26}{'n':>6}{'mean %':>9}{'PF':>8}{'total %':>10}")
    for bn, mask in bL.items():
        sel = np.array([bool(mask[i]) for i in sigL])
        s0, d0 = sigL[sel], sdL[sel]
        for nm, hv in (("fixed 96", None), ("adaptive 2x ttb_hat", yhat),
                       ("adaptive, SHUFFLED fc", yshuf)):
            if hv is None:
                t = resim(fL, s0, d0, hold=96)
            else:
                caps = np.clip(np.round(2.0 * hv[s0]), 8, 240).astype(int)
                parts = []
                for cap in np.unique(caps):
                    q = caps == cap
                    parts.append(resim(fL, s0[q], d0[q], hold=int(cap)))
                t = pd.concat(parts)
            print(f"   {bn:<14}{nm:<26}{len(t):>6}{t.pct.mean():>9.4f}"
                  f"{M.pf(t.pct):>8.3f}{t.pct.sum():>10.2f}")
        print()


if __name__ == "__main__":
    main()
