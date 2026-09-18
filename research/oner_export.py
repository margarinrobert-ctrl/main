"""Ship the 1R book to the page: legs, correlation matrix, book statistics, and Pine per leg."""
from __future__ import annotations

import json
import math
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
import pine_export as PX
import pine_lint as PL
from oner_book2 import load_all, greedy_book, styles
from test_suite import _daily, _dd, _sharpe

ART = ("results/oner/claude-0/-home-user-main/e473d7de-e277-515e-b24b-75724aaa9da5/"
       "scratchpad/edge-finder.html")


def clean(x):
    if isinstance(x, float):
        return None if not math.isfinite(x) else round(x, 4)
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    return x


def main():
    cands = load_all()
    chosen, _D, _n = greedy_book(cands)
    F = [(cands[i][0], cands[i][1]) for i in chosen]
    n_sess = max(s.n_sess for _, s in F)
    D = np.column_stack([np.r_[_daily(s), np.zeros(n_sess)][:n_sess] for _, s in F])
    C = pd.DataFrame(D).corr().to_numpy()
    port = D.sum(axis=1)
    eq = np.cumsum(port)
    dd = float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max())
    allp = np.concatenate([s.pnl for _, s in F])

    legs = []
    bad = 0
    for i, (r, s) in enumerate(F):
        code = PX.emit_strategy(r["rule"], r["side"], r["am"], 1.0, r["flat"], tf=r["tf"],
                                stats={"trades": f"{len(s.pnl)}",
                                       "net P&L": f"${s.pnl.sum():,.0f}",
                                       "win rate": f"{100*(s.pnl>0).mean():.1f}% "
                                                   f"(geometry base {r['base']:.1f}%)",
                                       "locked block": f"${s.pnl[s.ent_sess>=s.cut].sum():,.0f}"})
        bad += len(PL.lint(code))
        lok = float(s.pnl[s.ent_sess >= s.cut].sum())
        legs.append(dict(
            id=f"B{i+1}", rule=r["rule"], tf=r["tf"], side=r["side"], am=r["am"], flat=r["flat"],
            tags=r["tags"], hold_min=round(r["hold_min"]), per_year=round(r["per_year"], 1),
            trades=len(s.pnl), win=100 * float((s.pnl > 0).mean()), base=r["base"],
            exc_r=r["exc_r"], exc_l=r["exc_l"], net=float(s.pnl.sum()), locked=lok,
            research=float(s.pnl[s.ent_sess < s.cut].sum()),
            pf=float(s.pnl[s.pnl > 0].sum() / max(-s.pnl[s.pnl <= 0].sum(), 1e-9)),
            dd=_dd(s.pnl), sharpe=_sharpe(_daily(s)), pine=code))
    assert bad == 0, f"{bad} structural problems in the emitted Pine"

    book = dict(
        legs=legs, corr=np.nan_to_num(C).round(3).tolist(),
        trades=int(len(allp)), win=100 * float((allp > 0).mean()),
        net=float(sum(x["net"] for x in legs)), locked=float(sum(x["locked"] for x in legs)),
        sharpe=_sharpe(port), best_solo=max(x["sharpe"] for x in legs),
        dd=dd, worst_leg_dd=max(x["dd"] for x in legs),
        n_sess=int(n_sess), daily=[list(map(int, np.round(D[:, i]))) for i in range(D.shape[1])],
        note=("Selected on the research block only: no calendar conditions, every subset of the "
              "rule also beats its own base rate, ranked by research win rate, then greedily "
              "decorrelated below |rho| 0.25. The locked column was read once, afterwards. "
              "Procedure chosen by running five head to head in research/oner_procedures.py."),
    )
    html = open(ART).read()
    m = re.search(r'<script id="DATA" type="application/json">(.*?)</script>', html, re.S)
    D_ = json.loads(m.group(1))
    D_["oner"] = clean(book)
    blob = json.dumps(clean(D_), separators=(",", ":"), allow_nan=False)
    open(ART, "w").write(html[:m.start(1)] + blob + html[m.end(1):])
    print(f"{len(legs)} legs exported, all Pine lints clean, blob {len(blob)/1e6:.1f} MB")
    print(f"book: {book['trades']:,} trades, {book['win']:.1f}% win, ${book['net']:,.0f} net, "
          f"${book['locked']:,.0f} locked, Sharpe {book['sharpe']:.2f}, maxDD ${book['dd']:,.0f}")


if __name__ == "__main__":
    main()
