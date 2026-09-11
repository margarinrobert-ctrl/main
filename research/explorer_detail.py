"""Re-simulate every strategy in the Edge Finder explorer and attach its full detail.

Pass 1 of the generator only stored trades and net P&L per block, which is all the selection
needed. The explorer's detail panel needs more: win rate, profit factor, drawdown, exit mix and
the shape of the equity curve. That is a second pass over the 60,000 rows the explorer carries --
cheap, because the exit outcome of entering at bar i under geometry g is already precomputed.

Writes the enriched blob straight back into the artifact HTML, and refuses to do so unless the
re-simulation reproduces the P&L the page already shows.
"""
from __future__ import annotations

import json
import re
import sys
import time

import numpy as np
from numba import njit

sys.path.insert(0, "research")
from alpha_factory2 import EXITS, build_conditions, price_one
from bos_choch import prep
import pine_export as PX

ART = ("results/explorer/claude-0/-home-user-main/e473d7de-e277-515e-b24b-75724aaa9da5/"
       "scratchpad/edge-finder.html")


@njit(cache=True)
def walk(trig, eb, ep, ok, sidx, out_pnl, out_why, out_sess):
    k = 0
    free = -1
    for t in range(len(trig)):
        i = trig[t]
        if i < free or ok[i] == 0:
            continue
        free = eb[i]
        out_pnl[k] = ep[i]; out_why[k] = ok[i]; out_sess[k] = sidx[i]
        k += 1
    return k


def main(tf=30):
    t0 = time.time()
    html = open(ART).read()
    m = re.search(r'<script id="DATA" type="application/json">(.*?)</script>', html, re.S)
    D = json.loads(m.group(1))
    names, rules, exits, rows = D["names"], D["rules"], D["exits"], D["rows"]
    print(f"{len(rows):,} explorer rows, {len(rules):,} rules, {len(exits)} exit geometries")

    d = prep(tf)
    cnames, M = build_conditions(d)
    assert cnames == names, "condition pool has drifted since the explorer was built"
    nb = M.shape[1]
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    atr_, mod = d["atr"], d["mod"].astype(np.int64)
    us = np.unique(d["sess"]); sidx = np.searchsorted(us, d["sess"]).astype(np.int64)
    cut = int(D["stats"]["cut"])
    n_sess = len(us)
    # indexed by SESSION, not by bar -- the trade arrays carry session indices
    sixth = np.minimum((np.arange(n_sess) * 6) // n_sess, 5)

    variants = [(s, gi) for s in (1, -1) for gi in range(len(EXITS))]
    vix = {(s, gi): i for i, (s, gi) in enumerate(variants)}
    EB = np.zeros((len(variants), nb), np.int64)
    EP = np.zeros((len(variants), nb), np.float64)
    OK = np.zeros((len(variants), nb), np.int64)
    for vi, (s, gi) in enumerate(variants):
        am, tp, fl = EXITS[gi]
        price_one(o, h, l, c, atr_, mod, s, am, tp, fl, EB[vi], EP[vi], OK[vi])
    print(f"   exit outcomes precomputed, {time.time()-t0:.0f}s", flush=True)

    buf_p = np.zeros(nb); buf_w = np.zeros(nb, np.int64); buf_s = np.zeros(nb, np.int64)
    det = []
    bad = 0
    for ri, r in enumerate(rows):
        rule_i, side, geo, n_shown, res_shown, lok_shown = r[0], r[1], r[2], r[3], r[4], r[5]
        msk = np.ones(nb, bool)
        for k in rules[rule_i]:
            msk &= M[k]
        trig = np.flatnonzero(msk).astype(np.int64)
        vi = vix[(1 if side == 1 else -1, geo)]   # the page encodes short as 0
        k = walk(trig, EB[vi], EP[vi], OK[vi], sidx, buf_p, buf_w, buf_s)
        p = buf_p[:k]; w = buf_w[:k]; ss = buf_s[:k]
        if k != n_shown or abs(p[ss < cut].sum() - res_shown) > 1.0 \
                or abs(p[ss >= cut].sum() - lok_shown) > 1.0:
            bad += 1
            if bad <= 3:
                print(f"   MISMATCH row {ri}: {k} vs {n_shown} trades")
        wins = p[p > 0]; loss = -p[p <= 0]
        pf = wins.sum() / loss.sum() if loss.sum() > 0 else 999.0
        eq = np.cumsum(p)
        dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
        per = [float(p[sixth[ss] == q].sum()) for q in range(6)]
        det.append([
            int((ss < cut).sum()), int((ss >= cut).sum()),
            round(float(100 * (p > 0).mean()), 1),
            round(min(float(pf), 99.0), 2),
            int(round(dd)),
            int(round(float(p.mean()))),
            int(round(float(p.max()))), int(round(float(p.min()))),
            int(round(100 * float((w == 1).mean()))),
            int(round(100 * float((w == 2).mean()))),
            int(round(100 * float((w == 3).mean()))),
            [int(round(x)) for x in per],
        ])
        if ri % 10000 == 0:
            print(f"   {ri:,} rows, {time.time()-t0:.0f}s", flush=True)

    if bad:
        raise SystemExit(f"{bad} rows did not reproduce -- refusing to write")
    print(f"all {len(rows):,} rows reproduce the page's trades and P&L exactly")

    D["detail"] = det
    # the expression map, prelude and header travel with the page so the browser emits
    # exactly what pine_export.py emits; only the string assembly is duplicated in JS
    D["pine"] = {"P": PX.P, "header": PX._HEADER, "tf": tf,
                 "prims": [[list(a), list(b), c] for a, b, c in PX.PRIMS],
                 "window": PX.WINDOW, "range": PX.RANGE_TABLE}
    blob = json.dumps(D, separators=(",", ":"))
    html = html[:m.start(1)] + blob + html[m.end(1):]
    open(ART, "w").write(html)
    print(f"wrote {len(html)/1e6:.1f} MB, total {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
