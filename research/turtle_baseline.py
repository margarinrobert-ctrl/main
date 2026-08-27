"""Phase 0: what the supplied script does on this data, before anything is changed.

Run on the RESEARCH block only.  The locked block is read once, at the end of the study, next to
the candidate -- a baseline peek is still a peek, and a baseline that looked bad on the holdout
would change what gets shipped just as surely as a candidate that looked good.

Three things are established here:

  * the four supplied presets on their design timeframes, with no session restriction -- the
    strategy as it stands;
  * the same presets with entries confined to 07:00-11:00 New York and a hard flatten at 11:00 --
    the request, applied naively, which is the thing to beat;
  * the matched control for each, which says how much of either number is the instrument rather
    than the rule.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import turtle_bars as B
import turtle_metrics as M
import turtle_sim as T
import turtle_tensor as X
from turtle_sim import P

WIN_LO, WIN_HI = 420, 720          # 07:00 .. 12:00 New York; the flatten grace needs the tail
SESS = dict(sess_start=420, sess_end=660, flatten_min=660, flat_grace=60)

PRESETS = {
    "T1  240m  ADX<22 + not extended": dict(tf=240, adx_max=22.0, ext_max=3.964),
    "T2  240m  ADX<22": dict(tf=240, adx_max=22.0, ext_max=0.0),
    "T3  120m  ADX<22": dict(tf=120, adx_max=22.0, ext_max=0.0),
    "T4   60m  ADX<22 + not extended": dict(tf=60, adx_max=22.0, ext_max=3.193),
    "Spec defaults (no gate)": dict(tf=60, adx_max=0.0, ext_max=0.0),
}


def base_params(spec: dict, **kw) -> P:
    return T.replace(P(entry1=20, entry2=55, exit1=10, exit2=20, atr_len=20, atr_mult=2.0,
                       pyr_step=0.5, max_units=4, skip_win=True,
                       cost_abs=spec["cost_abs"], cost_bp=spec["cost_bp"],
                       stop_slip=spec["stop_slip"]), **kw)


def run_one(name: str, tf: int, p: P, windowed: bool, draws: int = 200) -> tuple[dict, dict]:
    spec = B.INSTRUMENTS[name]
    s = B.load(name, tf)
    if windowed:
        s = s.window(WIN_LO, WIN_HI)
    cut = B.split_session(B.load(name, tf))
    ex = X.build(s, p)
    trig = T.signal_bars(s, p)
    sc = X.scan(s, ex, trig, p)
    st = M.summarise(s, sc, spec, 0, cut, name)
    block = (s.sess >= cut).astype(np.int64)
    ctrl = X.Control(s, np.where(block == 0, trig, 0), block=block, seed=20250822)
    bank = M.control_bank(s, ex, ctrl, p, spec, 0, cut, name, draws=draws)
    return st, M.excess(st, bank)


def main() -> None:
    print("=" * 108)
    print("PHASE 0 -- the supplied strategy, RESEARCH BLOCK ONLY")
    print("=" * 108)
    for name in ("US30", "XAU", "BTC"):
        spec = B.INSTRUMENTS[name]
        print(f"\n### {name}   point value ${spec['point_value']}   round turn "
              f"{spec['cost_abs']} abs / {spec['cost_bp']} bp + slip {spec['stop_slip']}")
        print(f"{'preset':<36} {'mode':<10} {'n':>6} {'net $':>12} {'/trade':>9} {'Sharpe':>7} "
              f"{'PF':>6} {'win':>6} {'ctrl /trade':>12} {'excess':>9} {'p':>6}")
        for label, cfg in PRESETS.items():
            tf = cfg["tf"]
            if tf % spec["native"]:
                continue
            for mode in ("as shipped", "07-11 NY"):
                kw = dict(adx_max=cfg["adx_max"], ext_max=cfg["ext_max"])
                if mode == "07-11 NY":
                    kw.update(SESS)
                p = base_params(spec, **kw)
                try:
                    st, ex = run_one(name, tf, p, windowed=(mode == "07-11 NY"))
                except Exception as e:                      # pragma: no cover - diagnostics
                    print(f"{label:<36} {mode:<10} ERROR {e}")
                    continue
                print(f"{label:<36} {mode:<10} {st['n']:>6,d} {st['net']:>12,.0f} "
                      f"{st['per_trade']:>9.2f} {st['sharpe']:>7.2f} {st['pf']:>6.2f} "
                      f"{st['win_rate']:>6.1%} {ex.get('ctrl_per_trade', 0):>12.2f} "
                      f"{ex.get('ex_per_trade', 0):>9.2f} {ex.get('p_per_trade', 1):>6.3f}")


if __name__ == "__main__":
    main()
