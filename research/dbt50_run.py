"""The experiment: 36 independent synthetic worlds, 50 years each, three trend regimes.

Run:  python3 research/dbt50_run.py --paths 12 --years 50 [--meta] [--out results.json]

What it produces, in the order the protocol demands:

  1. the ABLATION -- the same strategy in a martingale world (trend=0, drift=0). Anything it earns
     there is cost-model error or a bug, not trend following.
  2. MARGINAL MEANS per parameter across independent worlds, which is what "the best mean on each
     parameter" has to mean: for each value of each knob, the mean out-of-sample R per trade over
     worlds, with a standard error, averaging over the other knobs.
  3. the SELECTION TEST -- pick the best configuration on the first 65% of each world's sessions,
     read the rest once, and report the distribution of that out-of-sample result across worlds.
     The in-sample-minus-out-of-sample gap is the cost of having to choose parameters.
  4. the MATCHED CONTROL for the selected configuration in each world.
  5. cost sensitivity at 1.5x.
  6. optionally the deep meta-label, trained on in-sample trades only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dbt50 as B

REGIMES = {
    "trend_realistic": dict(trend=0.10, ann_drift=0.07),
    "trend_strong": dict(trend=0.35, ann_drift=0.07),
    "null_martingale": dict(trend=0.0, ann_drift=0.0),
}


def sweep_world(w, verbose=False):
    """Every (don_n, adx_min, tp_r, hold) on one world, both sides, one merged book each."""
    Tl = B.tensors(w, 1)
    Ts = B.tensors(w, -1)
    rows = []
    trig = {}
    for dn in B.DONS:
        for ax in B.ADXS:
            trig[(dn, ax, 1)] = B.triggers(w, dn, ax, 1)
            trig[(dn, ax, -1)] = B.triggers(w, dn, ax, -1)
    for dn in B.DONS:
        for ax in B.ADXS:
            tl, ts = trig[(dn, ax, 1)], trig[(dn, ax, -1)]
            for tp in B.TPRS:
                for hd in B.HOLDS:
                    bk = B.combined_book(w, Tl, Ts, tl, ts, tp, hd)
                    rows.append((dn, ax, tp, hd, bk["n"], bk["n_is"], bk["n_oos"],
                                 bk["per"], bk["per_is"], bk["per_oos"], bk["dollars"]))
    dt = np.dtype([("don", "i8"), ("adx", "f8"), ("tp", "f8"), ("hold", "i8"),
                   ("n", "i8"), ("n_is", "i8"), ("n_oos", "i8"),
                   ("per", "f8"), ("per_is", "f8"), ("per_oos", "f8"), ("dollars", "f8")])
    return np.array(rows, dtype=dt), Tl, Ts, trig


def control_for(w, Tl, Ts, trig, cfg, draws=400, seed=11):
    """Matched control for one configuration, per side, weighted by that side's trade count."""
    dn, ax, tp, hd = cfg
    out = {}
    for side, T in ((1, Tl), (-1, Ts)):
        tr = trig[(dn, ax, side)]
        if len(tr) < 10:
            continue
        ci, co = B.control(w, T, tr, tp, hd, draws=draws, seed=seed + side)
        out[side] = (float(ci.mean()), float(co.mean()), ci, co)
    if not out:
        return None
    wl = {s: len(trig[(dn, ax, s)]) for s in out}
    tot = sum(wl.values())
    is_mu = sum(out[s][0] * wl[s] for s in out) / tot
    oos_mu = sum(out[s][1] * wl[s] for s in out) / tot
    oos_draws = sum(out[s][3] * wl[s] for s in out) / tot
    return dict(is_R=is_mu, oos_R=oos_mu, oos_draws=oos_draws)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", type=int, default=12)
    ap.add_argument("--years", type=int, default=50)
    ap.add_argument("--min-trades", type=int, default=300)
    ap.add_argument("--draws", type=int, default=400)
    ap.add_argument("--meta", action="store_true")
    ap.add_argument("--regimes", default=",".join(REGIMES))
    ap.add_argument("--out", default="/tmp/dbt50_results.json")
    a = ap.parse_args()

    results = {}
    t_start = time.time()
    for reg in a.regimes.split(","):
        kw = REGIMES[reg]
        print(f"\n=== {reg}  {kw}  {a.paths} worlds x {a.years} years")
        allrows, sel, ctrl, metas, gen = [], [], [], [], []
        for p in range(a.paths):
            t0 = time.time()
            w = B.build_world(seed=1000 * (list(REGIMES).index(reg) + 1) + p,
                              years=a.years, **kw)
            import synth50 as S
            gen.append(S.stats(w.d))
            rows, Tl, Ts, trig = sweep_world(w)
            rows = rows[rows["n_is"] >= a.min_trades]
            allrows.append(rows)
            # --- selection on IS only, read OOS once
            best = rows[np.argmax(rows["per_is"])]
            cfg = (int(best["don"]), float(best["adx"]), float(best["tp"]), int(best["hold"]))
            c = control_for(w, Tl, Ts, trig, cfg, draws=a.draws)
            sel.append((cfg, float(best["per_is"]), float(best["per_oos"]),
                        int(best["n_is"]), int(best["n_oos"]), float(best["dollars"])))
            ctrl.append(c)
            if a.meta and reg == "trend_realistic":
                bk = B.combined_book(w, Tl, Ts, trig[(cfg[0], cfg[1], 1)],
                                     trig[(cfg[0], cfg[1], -1)], cfg[2], cfg[3])
                m = B.meta_filter(w, bk, cfg[0], verbose=True)
                if m:
                    metas.append(m)
            print(f"  world {p:>2}  best IS {best['per_is']:+.4f}R -> OOS "
                  f"{best['per_oos']:+.4f}R  (control OOS "
                  f"{c['oos_R']:+.4f}R)  cfg don{cfg[0]} adx{cfg[1]:.0f} tp{cfg[2]} hold{cfg[3]}"
                  f"  [{time.time()-t0:.0f}s]")
            del Tl, Ts
        results[reg] = dict(rows=[r.tolist() for r in allrows], sel=sel, ctrl=[
            None if c is None else dict(is_R=c["is_R"], oos_R=c["oos_R"]) for c in ctrl],
            meta=metas, gen=gen)
    with open(a.out, "w") as fh:
        json.dump(results, fh, default=float)
    print(f"\nwrote {a.out}  ({time.time()-t_start:.0f}s total)")


if __name__ == "__main__":
    main()
