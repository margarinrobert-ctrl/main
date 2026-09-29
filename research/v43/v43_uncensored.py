"""MAE as UNCENSORED entry heat.

MAE is the maximum adverse excursion from the entry price over the life of the trade, and that is
exactly the right statistic for how much heat an entry takes. The problem with comparing it across
these eight configurations is not the statistic, it is CENSORING: a stop truncates the excursion it
was going to record. A trade heading for -3.0 ATR that is stopped at -2.0 ATR reports -2.0, so a
mean MAE is a mixture of real heat on the survivors and the stop distance on the stopped -- and the
mixing weight is the stop-out rate, which is why mean MAE tracks stop-out share at rho +0.978
across configurations whose stops run 1.5N to 2.5N and whose stop-out rates run 19% to 62%.

The fix is the one this branch already wrote down for barrier systems in STUDY_M4_ANATOMY: widen
the stop until the barrier stops binding, then read the distribution. Two uncensored measurements:

  A. NO STOP. The configuration's own entry and channel exit, stop set to 1000N so it can never
     bind. MAE is then the true adverse excursion over the trade's natural life.
  B. FIXED HORIZON. From each real entry bar, walk H bars forward with NO exit of any kind. This
     removes the last asymmetry -- a longer exit channel gives a trade more time to draw down --
     and makes the eight entries comparable on identical terms. This is the decisive one for
     "which entry takes the least heat".

Reported in ATR AT ENTRY, never in R: R divides by atr_mult * ATR, which puts the stop back in the
denominator and re-introduces exactly the artifact being removed.

Usage: python research/v43/v43_uncensored.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle")
sys.path.insert(0, "research/v43")
import v43_maemfe as V       # noqa: E402

HORIZONS = (10, 20, 40)


def horizon_heat(P, tin, H):
    """MAE and MFE in ATR at entry, over exactly H bars from the fill, with no exit at all."""
    h, l, o, atr = P["h"], P["l"], P["o"], P["atr"]
    n = len(o)
    mae, mfe = [], []
    for a in tin:
        b = min(a + H, n - 1)
        if b <= a:
            continue
        # ATR at the SIGNAL bar (a-1) is what the strategy sized on; guard the edge
        an = atr[a - 1] if a >= 1 and np.isfinite(atr[a - 1]) and atr[a - 1] > 0 else np.nan
        if not np.isfinite(an) or an <= 0:
            continue
        px = o[a]
        mae.append((px - l[a:b + 1].min()) / an)
        mfe.append((h[a:b + 1].max() - px) / an)
    if len(mae) < 15:
        return None
    return float(np.mean(mae)), float(np.mean(mfe)), float(np.median(mae)), len(mae)


def main():
    rows = []
    for cfg in V.CONFIGS:
        P = V.prep(cfg["tf"])
        gate = V.gate_of(P, cfg["gate"])

        # A -- the configuration as declared, and the same thing with the stop unable to bind
        T = V.run_one(P, cfg, gate)
        wide = dict(cfg); wide["mult"] = 1000.0
        W = V.run_one(P, wide, gate)

        def heat(T_, mult):
            r = T_["risk"]; ok = r > 0
            if ok.sum() < 15:
                return None
            # risk = mult * ATR, so mae/risk*mult recovers ATR units
            return float(np.mean(T_["mae"][ok] / r[ok]) * mult), \
                   float(np.mean(T_["mfe"][ok] / r[ok]) * mult), int(ok.sum())

        a_dec = heat(T, cfg["mult"])
        a_wid = heat(W, 1000.0)
        row = dict(name=cfg["name"], tf=cfg["tf"], stop=cfg["mult"])
        if a_dec:
            row.update(mae_declared=a_dec[0], mfe_declared=a_dec[1], n_declared=a_dec[2])
        if a_wid:
            row.update(mae_nostop=a_wid[0], mfe_nostop=a_wid[1], n_nostop=a_wid[2])

        # B -- fixed horizon from the real entries, no exit
        for H in HORIZONS:
            hh = horizon_heat(P, T["tin"], H)
            if hh:
                row[f"mae_h{H}"], row[f"mfe_h{H}"], row[f"maemed_h{H}"], row[f"n_h{H}"] = hh
        rows.append(row)

    d = pd.DataFrame(rows)
    d.to_csv("results/v43/v43_uncensored.csv", index=False)
    pd.set_option("display.width", 240)
    print("  ALL FIGURES IN ATR AT ENTRY. 'declared' is censored by that config's own stop.\n")
    print(d[["name", "tf", "stop", "mae_declared", "mae_nostop", "mae_h10", "mae_h20", "mae_h40",
             "maemed_h20", "n_h20"]].round(3).to_string(index=False))
    print()
    print(d[["name", "mfe_declared", "mfe_nostop", "mfe_h10", "mfe_h20", "mfe_h40"]]
          .round(3).to_string(index=False))
    for col in ("mae_declared", "mae_nostop", "mae_h20"):
        s = d[col]
        print(f"\n  {col:<14} spread {s.max() - s.min():.3f} ATR   "
              f"lowest {d.loc[s.idxmin(), 'name']} ({s.min():.3f})   "
              f"highest {d.loc[s.idxmax(), 'name']} ({s.max():.3f})")
    return d


if __name__ == "__main__":
    main()


def control_heat(P, gate, n_target, H, draws=200, seed=11):
    """The same fixed-horizon heat from RANDOM bars inside the same regime.

    This is the test the censored version could not run: with no stop and a fixed horizon there is
    nothing left that differs between the breakout entry and a random one except WHEN it enters.
    Random bars are drawn from the gated set, matched on count -- no position lock is needed
    because nothing is being held."""
    h, l, o, atr = P["h"], P["l"], P["o"], P["atr"]
    n = len(o)
    elig = np.flatnonzero(gate[:n - H - 1])
    elig = elig[elig > 1]
    if len(elig) < n_target * 3:
        return None
    rng = np.random.default_rng(seed)
    ma, mf = [], []
    for _ in range(draws):
        pick = rng.choice(elig, size=min(n_target, len(elig)), replace=False)
        a1, f1 = [], []
        for a in pick:
            an = atr[a - 1]
            if not np.isfinite(an) or an <= 0:
                continue
            px = o[a]; b = a + H
            a1.append((px - l[a:b + 1].min()) / an)
            f1.append((h[a:b + 1].max() - px) / an)
        if len(a1) >= 15:
            ma.append(np.mean(a1)); mf.append(np.mean(f1))
    if not ma:
        return None
    return float(np.mean(ma)), float(np.mean(mf)), np.asarray(ma)


def with_control(H=20):
    rows = []
    for cfg in V.CONFIGS:
        P = V.prep(cfg["tf"]); gate = V.gate_of(P, cfg["gate"])
        T = V.run_one(P, cfg, gate)
        hh = horizon_heat(P, T["tin"], H)
        if not hh:
            continue
        mae, mfe, _med, nn = hh
        ctl = control_heat(P, gate, nn, H)
        if not ctl:
            continue
        c_mae, c_mfe, dist = ctl
        rows.append(dict(name=cfg["name"], n=nn, mae=mae, c_mae=c_mae, d_mae=mae - c_mae,
                         p_mae=float(np.mean(dist <= mae)),
                         mfe=mfe, c_mfe=c_mfe, d_mfe=mfe - c_mfe,
                         ratio=mfe / mae, c_ratio=c_mfe / c_mae))
    d = pd.DataFrame(rows)
    d.to_csv(f"results/v43/v43_uncensored_control_h{H}.csv", index=False)
    print(f"\n  FIXED {H}-BAR HORIZON, NO EXIT, vs random bars in the same regime (ATR units)")
    print("  p_mae = share of random draws whose MAE was at or below the strategy's; low = the")
    print("  breakout takes LESS heat than a random bar, high = MORE.\n")
    print(d.round(3).to_string(index=False))
    return d
