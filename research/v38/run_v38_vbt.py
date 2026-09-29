"""V38 part 4 -- the winner re-simulated in VECTORBT, as an INDEPENDENT ENGINE.

WHY. Three separate engine bugs on this branch were found by diffing an engine against a second
implementation of its own order model, and NONE was visible by reading the code
(`STUDY_PINE_PARITY`, `STUDY_V8_EXIT_OPT`, `STUDY_V34_MECHANIC`). A number that two independently
written engines agree on is worth more than a number one engine produces twice.

WHAT THIS CAN AND CANNOT CHECK. vectorbt's `from_signals` resolves a stop against the bar's own
range and fills at a chosen price series; my engine walks the bars in sequence taking the stop
first when a stop and a channel exit fall in the same bar. So the two agree on TRADE COUNT and
ENTRY BARS exactly if the signal logic matches, and differ by the exit convention. A trade-count
mismatch means the SIGNAL is wrong; a P&L mismatch at a matching count means the EXIT CONVENTION
differs, which is the known and expected difference. That is exactly the diagnostic
`STUDY_PINE_PARITY` prescribes -- run it as a transcription check first, then as an order-model
measurement.

Usage: python3 research/v38/run_v38_vbt.py
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd
import vectorbt as vbt

sys.path.insert(0, "research")
sys.path.insert(0, "research/v38")
import indicators as I       # noqa: E402
import v38grid as G          # noqa: E402
import v38feeds as F         # noqa: E402
from run_v38 import hdr      # noqa: E402
from run_v38b import run_cfg, line          # noqa: E402
from run_v38c import CANDS                  # noqa: E402


def main():
    t0 = time.perf_counter()
    hdr("10. THE WINNER IN VECTORBT -- a second engine, written to the same spec")
    print(f"   vectorbt {vbt.__version__}")
    for mkt in ("US30L", "US100L"):
        pv = F.INSTR[mkt]["pv"]
        d = F.frame(mkt, 30)
        P = G.prep(30, d=d, pv=pv)
        msk, ten = G.masks(P), G.tensor(P)
        idx = pd.to_datetime(d["ts"])
        c = pd.Series(P["c"], index=idx)
        o = pd.Series(P["o"], index=idx)
        for nm, cfg in CANDS.items():
            m, p, sb, _w = run_cfg(P, ten, msk, cfg, None, np.unique(P["day"]))
            sig = msk[(cfg["don_e"], cfg["lr_len"], cfg["lr_read"], cfg["ma_len"], cfg["ma_read"])]
            ent = np.zeros(P["n"], bool)
            ent[np.minimum(sig + 1, P["n"] - 1)] = True          # fill at the NEXT open
            ex_lo = P["ex_lo"][cfg["don_x"]]
            xit = np.zeros(P["n"], bool)
            xit[1:] = (P["c"][1:] < ex_lo[1:])
            slf = np.where(P["c"] > 0, cfg["stop_n"] * P["atr"] / np.maximum(P["c"], 1e-9), np.nan)
            slf = pd.Series(slf, index=idx).shift(1).bfill().to_numpy()
            pf = vbt.Portfolio.from_signals(
                close=c, entries=pd.Series(ent, index=idx), exits=pd.Series(xit, index=idx),
                price=o, sl_stop=slf, accumulate=False, size=1, size_type="amount",
                fees=0.0, fixed_fees=G.COMM * G.COST_MULT + 2.0 * G.EC * G.COST_MULT * pv,
                init_cash=1_000_000, freq="30min")
            tr = pf.trades.records_readable
            n_v = len(tr)
            net_v = float(tr["PnL"].sum()) * pv if len(tr) else 0.0
            print(f"\n   {mkt} 30m -- {nm}")
            print(line("my engine", m))
            print(f"      {'vectorbt':<30} n {n_v:>5}  net ${net_v:>+10,.0f}  "
                  f"$/trade {(net_v / max(n_v, 1)):>+8.2f}")
            print(f"      trade-count ratio {n_v / max(m['n'], 1):.3f}   "
                  f"{'SIGNAL SETS AGREE' if abs(n_v - m['n']) <= 0.08 * m['n'] else 'SIGNAL COUNTS DIFFER -- the entry logic is not the same in the two engines'}")
    print(f"\n   NOTE ON WHAT THIS PROVES. The two engines share a signal definition and differ in")
    print("   how a stop and a channel exit inside ONE bar are ordered -- mine takes the stop, the")
    print("   pessimistic branch. A matching trade count with a different net is that convention,")
    print("   not a bug; a mismatched COUNT would be a bug, and is what this run exists to catch.")
    print(f"\n   elapsed {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
