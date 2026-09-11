"""After the one-time calibration, realised training vol must be within 10% of tau."""
import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np, backtest as B


def test_vol_target():
    c = B.calibrate(); o = B.run(c=c)
    tr = o["net"][o["net"].index < o["split"]]
    v = float(tr.std() * np.sqrt(256)); tau = o["cfg"]["tau"]
    print(f"  c = {c:.4f}   realised training vol {v:.4f} vs tau {tau}   ratio {v/tau:.3f}")
    assert abs(v / tau - 1) < 0.10


if __name__ == "__main__":
    test_vol_target(); print("vol target OK")
