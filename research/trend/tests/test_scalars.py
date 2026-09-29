"""E[|F_k|] should be near 10 on the sample with the HARD-CODED scalars. Not refit; reported."""
import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np, pandas as pd, data as D, volatility as V, forecast as F


def test_scalars():
    pan = D.panel(); cfg = pan["cfg"]; close = pan["close"]; train = close.index < pan["split"]
    r = close.pct_change(); sig = V.estimate(r, cfg["vol"]["span_short"], cfg["vol"]["long_window"], cfg["vol"]["blend_short"])
    bad = 0
    for n in close.columns:
        for s in cfg["sleeves"]:
            f = F.sleeve_forecast(close[n], sig[n], s["n"], s["scalar"], cfg["forecast_cap"])
            m = float(f[train].abs().mean())
            flag = "" if 7.0 <= m <= 13.0 else "  <-- outside 7-13"
            print(f"  {n:6s} sleeve {s['n']:>3d}/{4*s['n']:<4d} E|F| = {m:5.2f}{flag}")
            bad += flag != ""
    print(f"  {bad} sleeve-instrument cells outside [7, 13]. The scalars are properties of the filter and")
    print("  are NOT refit; a persistent miss is diagnostic of the data (few, correlated, trending), not a knob.")


if __name__ == "__main__":
    test_scalars()
