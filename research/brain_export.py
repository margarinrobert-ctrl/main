"""Run the Quant Brain over a diverse slice of the explorer and ship the results with the page.

The Edge Finder is a static page: no server, no Python, no 1-minute bars in the browser. So the
brain runs HERE, once, and the page shows what it found. The alternative -- a button that
pretends to think -- would be worse than no button.

Selection is deliberately not "the top 40 by P&L". Forty variations of one rule would produce a
correlation matrix of forty 0.95s and a portfolio that is one strategy. Candidates are taken in
descending research P&L and kept only when they share at most one condition with everything
already chosen, which is what makes the matrix worth looking at.
"""
from __future__ import annotations

import json
import re
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
import metrics as MT
import quant_brain as QB
import regimes as RG
from test_suite import _daily

ART = ("results/brain/claude-0/-home-user-main/e473d7de-e277-515e-b24b-75724aaa9da5/"
       "scratchpad/edge-finder.html")
N_KEEP = 40


def pick(D, n=N_KEEP, max_shared=1):
    rows, rules, ex = D["rows"], D["rules"], D["exits"]
    order = sorted(range(len(rows)), key=lambda i: -rows[i][4])
    chosen, sets = [], []
    for i in order:
        cs = set(rules[rows[i][0]])
        if any(len(cs & s) > max_shared for s in sets):
            continue
        if rows[i][3] < 80:
            continue
        chosen.append(i); sets.append(cs)
        if len(chosen) >= n:
            break
    return chosen


def main():
    t0 = time.time()
    html = open(ART).read()
    m = re.search(r'<script id="DATA" type="application/json">(.*?)</script>', html, re.S)
    D = json.loads(m.group(1))
    names, rules, exits, rows = D["names"], D["rules"], D["exits"], D["rows"]
    idx = pick(D)
    print(f"{len(idx)} strategies selected from {len(rows):,}, "
          f"sharing at most one condition with each other", flush=True)

    R = RG.classify(30)
    cons = MT.Constraints(max_drawdown=8000, min_profit_factor=1.2, min_sortino=1.0,
                          min_expectancy=25, min_oos=0, max_exposure=80, min_trades=60)
    out, series = [], []
    for k, i in enumerate(idx):
        r = rows[i]
        conds = [names[j] for j in rules[r[0]]]
        am, tp, fl = exits[r[2]]
        side = 1 if r[1] == 1 else -1
        A = QB.analyse(conds, side, am, tp, int(fl), 30, constraints=cons, R=R, fast=True)
        if A is None:
            continue
        s = A["s"]; M = A["M"]
        imp = QB.improve(s, tries=25)
        best_res = max(imp["all"], key=lambda x: x["d_res"]) if imp["all"] else None
        surv = imp["survivors"][0] if imp["survivors"] else None

        def pack(rr):
            if rr is None:
                return None
            mm = rr["m"]
            return dict(label=rr["label"], d_res=round(rr["d_res"]), d_lok=round(rr["d_lok"]),
                        net=round(mm["net profit"]), pf=round(mm["profit factor"], 2),
                        sortino=round(mm["Sortino"], 2), dd=round(mm["max drawdown $"]),
                        expect=round(mm["expectancy $"]), trades=mm["trades"],
                        win=round(mm["win rate %"], 1))

        out.append(dict(
            row=i, name=" + ".join(conds), conds=conds, side=r[1], geo=[am, tp, fl],
            score=round(A["score"], 1), dims=A["dims"],
            research=round(A["research"]), locked=round(A["locked"]),
            metrics={k2: (None if not np.isfinite(v) else round(float(v), 3))
                     for k2, v in M.items() if isinstance(v, (int, float))},
            extras={k2: (None if not np.isfinite(v) else round(float(v), 4))
                    for k2, v in A["extras"].items()},
            constraints=[[c[0], round(c[1], 2), c[2], round(c[3], 2), c[4]]
                         for c in A["constraints"]],
            works=[[w[0], w[1], w[2], round(w[3]), round(w[4]), round(w[5], 1)] for w in A["works"]],
            avoid=[[w[0], w[1], w[2], round(w[3]), round(w[4]), round(w[5], 1)] for w in A["avoid"]],
            improve=dict(tried=imp["tried"],
                         improved_research=sum(1 for x in imp["all"] if x["d_res"] > 0),
                         survivors=len(imp["survivors"]),
                         best_research=pack(best_res), best_surviving=pack(surv),
                         table=[pack(x) for x in imp["all"][:8]]),
        ))
        series.append(np.round(_daily(s)).astype(np.int32))
        if k % 5 == 0:
            print(f"   {k+1}/{len(idx)}  {time.time()-t0:.0f}s", flush=True)

    Dm = np.column_stack(series)
    df = pd.DataFrame(Dm)
    pear = df.corr().to_numpy()
    rank = df.corr(method="spearman").to_numpy()
    C = np.cov(Dm.T); P = np.linalg.pinv(C)
    dp = np.sqrt(np.outer(np.diag(P), np.diag(P)))
    part = -P / np.where(dp == 0, 1, dp); np.fill_diagonal(part, 1.0)

    reg = {}
    for ax, kk, nm in (("volatility", 2, "high vol"), ("volatility", 0, "low vol"),
                       ("trend", 2, "trending"), ("trend", 0, "mean-reverting"),
                       ("direction", 0, "down"), ("direction", 2, "up")):
        mm = R["labels"][ax][:len(Dm)] == kk
        if mm.sum() > 60:
            reg[nm] = np.nan_to_num(df[mm].corr().to_numpy()).round(3).tolist()

    D["brain"] = dict(
        strategies=out,
        daily=[s.tolist() for s in series],
        pearson=np.nan_to_num(pear).round(3).tolist(),
        rank=np.nan_to_num(rank).round(3).tolist(),
        partial=np.nan_to_num(part).round(3).tolist(),
        regime=reg,
        n_sess=int(Dm.shape[0]),
        note=("Computed by research/quant_brain.py and shipped with this page. "
              "The browser has no Python, no 1-minute bars and no engine; these are results, "
              "not a live calculation."),
    )
    # JSON.parse rejects Infinity and NaN; Python's json.dumps emits them happily. Sanitise
    # the whole structure and then dump with allow_nan=False so a survivor is an error, not a
    # page that fails to boot.
    def _clean(x):
        import math as _m
        if isinstance(x, float):
            return None if not _m.isfinite(x) else x
        if isinstance(x, dict):
            return {k: _clean(v) for k, v in x.items()}
        if isinstance(x, list):
            return [_clean(v) for v in x]
        return x

    blob = json.dumps(_clean(D), separators=(",", ":"), allow_nan=False)
    open(ART, "w").write(html[:m.start(1)] + blob + html[m.end(1):])
    print(f"\n{len(out)} strategies exported, {len(blob)/1e6:.1f} MB blob, {time.time()-t0:.0f}s")
    surv = sum(s["improve"]["survivors"] > 0 for s in out)
    print(f"improvement engine: {surv} of {len(out)} strategies had a variant that improved the "
          f"locked block without a worse drawdown or Sortino")


if __name__ == "__main__":
    main()
