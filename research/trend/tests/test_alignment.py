"""No same-bar execution: the held position at t must be a function of closes up to t-1 only."""
import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np, backtest as B


def test_positions_are_shifted():
    o = B.run(c=1.0)
    # the held series equals pos shifted by exactly one bar
    assert (o["held"].iloc[1:].to_numpy() == o["pos"].shift(1).iloc[1:].to_numpy()).all()
    # r_exec at t is open_{t+1}/open_t - 1: it must not correlate with a position decided at t
    # more than it does with the position decided at t-1 (which is the one that actually earned it)
    for n in o["names"]:
        same = np.corrcoef(o["pos"][n].iloc[:-1], o["r_exec"][n].iloc[:-1])[0, 1]
        prev = np.corrcoef(o["held"][n].iloc[1:], o["r_exec"][n].iloc[1:])[0, 1]
        print(f"{n}: corr(pos_t, r_exec_t) {same:+.4f}   corr(pos_t-1, r_exec_t) {prev:+.4f}")
        assert abs(same) < 0.15, "a same-bar correlation this size means the signal is trading its own bar"


if __name__ == "__main__":
    test_positions_are_shifted(); print("alignment OK")
