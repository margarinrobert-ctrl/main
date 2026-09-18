"""What real costs do to the nine shipped strategies.

The research layer charged COMM = $1.00 per round turn with no exchange fee and no NFA line, and
a flat tick of slippage on every fill. Real MNQ fees are nearer $1.44, and slippage is worst
exactly where a stop system meets it. This measures the damage, strategy by strategy, on both
blocks.

READ THE DECOMPOSITION, NOT JUST THE TOTAL. The change is not one-directional on this side of the
codebase, and saying otherwise would be wrong:

  * FEES go UP. $1.00 -> $1.44 on MNQ, because the old number was broker commission with no
    exchange fee and no NFA line.
  * CALM-BAR FRICTION goes DOWN. `sim_core` charged EC = 2 ticks per side flat. The new model
    charges half a 1-tick spread plus 1 tick of slippage = 1.5 ticks per side on a median bar,
    which is a fairer description of a liquid micro in the middle of the session.
  * FAST-BAR FRICTION goes UP a lot -- up to 3x the base, plus the stop premium, plus double
    again outside the session.

So a low-frequency strategy that exits on targets can genuinely come out slightly ahead, and a
high-frequency one that exits on stops in fast markets comes out much worse. That is the point of
the model, and it is why this script prints the fee and friction lines separately instead of one
"cheaper/worse" verdict.

(The TypeScript side is different: its old model already charged 1.5 ticks per side, so there the
new model really is worse everywhere. `scripts/quant-costs.ts` reports that one.)
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import costs as C
import tuner as U


def _legs():
    from allstrats import all_strategies
    return all_strategies()


def run(broker="discount", verbose=True):
    legs = _legs()
    real = U.Costs(symbol="MNQ", broker=broker)
    old = U.LEGACY_COSTS
    rows = []
    for name, s in sorted(legs.items()):
        tf = s["tf"]
        d = U.bars(tf)
        geo = dict(stop=s["am"], target=1.0, flat=s["flat"], hold=0)
        T = U.tensor(tf, s["side"], [geo["stop"]], [geo["target"]], [geo["flat"]], [geo["hold"]],
                     14, U.Entry(), only=None)
        trig = np.asarray(s["trig"], np.int64)
        out = {}
        for label, cs in (("old", old), ("real", real)):
            o = np.zeros((1, U.NCOL))
            ft, fs = cs.friction(d)
            U._walk_many(trig, T.xb[0:1], T.why[0:1], T.raw[0:1], ft, fs, cs.fee_rt(),
                         cs.maker_target(), d["si"], np.int64(d["cut"]), o)
            n = max(o[0, U.C_N], 1)
            out[label] = dict(n=int(o[0, U.C_N]), net=o[0, U.C_NET], per=o[0, U.C_NET] / n,
                              win=100 * o[0, U.C_WIN] / n,
                              res=o[0, U.C_NETR], lok=o[0, U.C_NETL],
                              stops=100 * o[0, U.C_STOP] / n)
        rows.append((name, s["side"], tf, out))
    if verbose:
        _report(rows, broker)
    return rows


def _report(rows, broker):
    print("=" * 100)
    print(f"THE NINE SHIPPED STRATEGIES, OLD COSTS vs REAL COSTS   [MNQ, broker '{broker}']")
    print("=" * 100)
    print(C.model("MNQ", broker).describe())
    new = C.model("MNQ", broker)
    old_rt = C.LEGACY.round_turn_points("taker", "taker")
    new_rt = new.round_turn_points("taker", "taker")
    print(f"\n  old model: ${C.LEGACY.fees.round_turn():.2f} broker-only fees, flat 2t/side "
          f"+ 1t on stops -- no exchange fee, no NFA line, no dependence on the bar")
    print(f"\n  where the change comes from, per round turn:")
    print(f"    fees      ${C.LEGACY.fees.round_turn():>5.2f} -> ${new.fees.round_turn():>5.2f}   "
          f"({new.fees.round_turn() - C.LEGACY.fees.round_turn():+.2f})  the exchange and NFA lines the old number omitted")
    print(f"    friction  {2*C.LEGACY.friction_ticks('taker'):>5.2f}t -> "
          f"{2*new.friction_ticks('taker'):>5.2f}t  "
          f"({2*(new.friction_ticks('taker') - C.LEGACY.friction_ticks('taker')):+.2f}t) on a CALM bar; "
          f"up to {2*new.friction_ticks('taker', vol_ratio=99, in_session=False):.2f}t on a fast one out of session")
    print(f"    calm round turn ${old_rt*new.pv:.2f} -> ${new_rt*new.pv:.2f}   "
          f"-- so the direction depends on a strategy's EXIT MIX, not on its edge")
    print()
    print(f"  {'strategy':<10}{'dir':>6}{'tf':>4}{'n':>6}{'stop%':>7}"
          f"{'old $/tr':>10}{'real $/tr':>11}{'delta':>8}"
          f"{'old net':>10}{'real net':>10}{'real lok':>10}  verdict")
    tot_old = tot_real = 0.0
    flipped = cheaper = 0
    for name, side, tf, o in rows:
        a, b = o["old"], o["real"]
        delta = b["per"] - a["per"]
        tot_old += a["net"]; tot_real += b["net"]
        if delta > 0.01:
            v = "cheaper -- exits on targets in calm bars"; cheaper += 1
        elif a["net"] > 0 >= b["net"]:
            v = "was profitable, now is not"; flipped += 1
        elif b["net"] > 0:
            v = "still positive"
        else:
            v = "negative either way"
        print(f"  {name:<10}{'long' if side == 1 else 'short':>6}{tf:>4}{b['n']:>6}"
              f"{b['stops']:>7.0f}{a['per']:>10.1f}{b['per']:>11.1f}{delta:>8.1f}"
              f"{a['net']:>10,.0f}{b['net']:>10,.0f}{b['lok']:>10,.0f}  {v}")
    print(f"\n  BOOK  old ${tot_old:,.0f}   real ${tot_real:,.0f}   "
          f"give-back ${tot_old - tot_real:,.0f} ({100*(tot_old-tot_real)/max(abs(tot_old),1):.0f}%)")
    print(f"  {flipped} of {len(rows)} crossed from profitable to unprofitable on real costs.")
    if cheaper:
        print(f"  {cheaper} came out CHEAPER -- see the decomposition above: on this side of the")
        print(f"  codebase calm-bar friction fell, so a strategy that exits on targets can gain.")
    print("\n  Fee values are dated assumptions, not quotes. Replace them with your own statement")
    print("  and the current CME schedule before sizing any real risk.")


def brokers(verbose=True):
    """The book's net under every broker preset -- how much of it is the broker's cut."""
    legs = _legs()
    print("\n" + "=" * 100)
    print("THE SAME BOOK UNDER EVERY BROKER PRESET")
    print("=" * 100)
    print(f"  {'broker':<12}{'fees/rt':>9}{'book net':>12}{'vs legacy':>12}")
    base = None
    for b in ("legacy", "ibkr", "discount", "propfirm", "premium"):
        cs = U.Costs(symbol="MNQ", broker=b, legacy=(b == "legacy"))
        tot = 0.0
        for name, s in sorted(legs.items()):
            d = U.bars(s["tf"])
            T = U.tensor(s["tf"], s["side"], [s["am"]], [1.0], [s["flat"]], [0], 14,
                         U.Entry(), only=None)
            o = np.zeros((1, U.NCOL))
            ft, fs = cs.friction(d)
            U._walk_many(np.asarray(s["trig"], np.int64), T.xb[0:1], T.why[0:1], T.raw[0:1],
                         ft, fs, cs.fee_rt(), cs.maker_target(), d["si"],
                         np.int64(d["cut"]), o)
            tot += o[0, U.C_NET]
        if base is None:
            base = tot
        print(f"  {b:<12}${cs.model().fees.round_turn():>7.2f}{tot:>12,.0f}{tot - base:>12,.0f}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "discount")
    brokers()
