"""Run the true 1-minute path simulation + perturbation Monte Carlo for the NQ ATME config.

Also computes the SEQUENTIAL (one-position-at-a-time) version of the same rule, which is what a
Pine strategy with pyramiding=0 actually trades. The sweep evaluates every trigger independently
and therefore allows overlapping trades; that is fine as an estimator of per-trade expectancy but
it is NOT an achievable equity curve on one contract, and the difference has to be measured rather
than assumed.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from edgelab import feeds
from scalp import core
from hypo.metrics import suite
from atme.livesim import run_live, perturb

WINDOW = (540, 780)
INST = "NQ"
ENTRY_K, WAIT_BARS, STOP_K, TP_R, HOLD_BARS, STRIDE = 1.0, 3, 1.0, 1.0, 24, 4
FLAT_MOD = 780


def build():
    d5 = feeds.bars(INST, 5)
    d1 = feeds.bars(INST, 1)
    ck = core.COSTS[INST]
    pos1 = pd.Series(np.arange(len(d1["idx"])), index=d1["idx"])
    B = core.blocks(INST, d5)
    return d5, d1, ck, pos1, B


def triggers(d5, block_mask):
    m = core.window(d5, *WINDOW) & block_mask
    m[:300] = False
    t = np.flatnonzero(m & np.isfinite(d5["atr"]) & (d5["atr"] > 0)).astype(np.int64)
    return t[::STRIDE]


def live(d5, d1, ck, pos1, trig):
    """Map each 5-minute signal onto the first minute of the NEXT 5-minute bar and walk it."""
    want_t = d5["idx"][trig] + pd.Timedelta(minutes=5)
    sig = pos1.reindex(want_t).to_numpy()
    ok = np.isfinite(sig)
    trig, sig = trig[ok], sig[ok].astype(np.int64)
    atr = d5["atr"][trig]
    want_px = d5["c"][trig] - ENTRY_K * atr
    hs = ck.spread_at(d1["mod"])
    R, filled, why, amb, wait, held = run_live(
        d1["o"], d1["h"], d1["l"], d1["c"], d1["mod"].astype(np.int64), sig,
        want_px, STOP_K * atr, TP_R, WAIT_BARS * 5, HOLD_BARS * 5, FLAT_MOD,
        hs, ck.slip_stop, ck.commission)
    f = filled.astype(bool)
    day = ((d1["idx"][sig] + pd.Timedelta(hours=6)).normalize().view("int64")
           // 86_400_000_000_000)
    return dict(trig=trig[f], sig=sig[f], R=R[f], why=why[f], amb=amb[f],
                wait=wait[f], held=held[f], day=np.asarray(day)[f], n_signals=len(trig))


def sequential(res):
    """Keep only trades that could be taken with ONE position open at a time."""
    entry = res["sig"] + res["wait"]
    exit_ = entry + res["held"]
    keep = np.zeros(len(entry), bool)
    free = -1
    for i in range(len(entry)):
        if res["sig"][i] >= free:          # signal itself must arrive with the book flat
            keep[i] = True
            free = exit_[i]
    return keep


def report(tag, R, days):
    s = suite(np.asarray(R), days)
    print(f"  {tag:<24} n={len(R):<6} win={s['win']:6.2f}%  E[R]={s['expR']:+.4f}  "
          f"PF={s['pf']:.3f}  Sharpe={s['sharpe']:.2f}  maxdd_R={s['maxdd_R']:.1f}  "
          f"top5%={s['top5pct_share']:.3f}")
    return s


if __name__ == "__main__":
    d5, d1, ck, pos1, B = build()
    out = {}
    for block in ("research", "validation"):
        trig = triggers(d5, B[block])
        r = live(d5, d1, ck, pos1, trig)
        out[block] = r
        print(f"\n{block.upper()}  signals={r['n_signals']}  fills={len(r['R'])} "
              f"({100*len(r['R'])/r['n_signals']:.1f}%)  ambiguous={100*r['amb'].mean():.2f}%")
        report("all fills", r["R"], r["day"])
        k = sequential(r)
        report("sequential (1 position)", r["R"][k], r["day"][k])
        for code, name in ((1, "stop"), (2, "target"), (3, "flat 13:00"), (4, "max hold")):
            m = r["why"] == code
            if m.sum():
                print(f"      {name:<12} {100*m.mean():5.1f}%  meanR {r['R'][m].mean():+.4f}")

    for tag, kw in (("mild", dict(price_sd=0.05, cost_scale=(0.75, 1.5), drop_frac=0.05)),
                    ("harsh", dict(price_sd=0.10, cost_scale=(0.5, 2.5), drop_frac=0.10))):
        for block in ("validation",):
            r = out[block]
            for label, sel in (("all", np.ones(len(r["R"]), bool)), ("seq", sequential(r))):
                p = perturb(r["R"][sel], **kw)
                print(f"\nMC {tag}/{label}/{block}: paths={p['paths']} "
                      f"p05={p['mean_p05']:+.4f} p50={p['mean_p50']:+.4f} p95={p['mean_p95']:+.4f} "
                      f"P(neg)={p['p_negative']:.4f} dd50={p['dd_p50']:.1f} dd95={p['dd_p95']:.1f} "
                      f"ddworst={p['dd_worst']:.1f}")
