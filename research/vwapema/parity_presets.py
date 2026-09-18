"""Every shipped preset diffed against the engine, under the script's own order model."""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.vwapema import vecore as V
from research.vwapema.ve_parity import run_pine

DS = {s: V.build(sess=s) for s in ("ny", "utc")}
SW = json.load(open("results/vwapema/sweep_cells.json"))
OP = json.load(open("results/vwapema/optuna_finalists.json"))
PRESETS = {
    "As published":            dict(sess="ny", p=dict(V.PARAMS), tgt_R=3.0),
    "Optuna: total R":         dict(sess=OP["totR"]["cfg"]["sess"], p=OP["totR"]["cfg"]["p"], tgt_R=OP["totR"]["cfg"]["tgt_R"]),
    "Optuna: profit factor":   dict(sess=OP["pf"]["cfg"]["sess"], p=OP["pf"]["cfg"]["p"], tgt_R=OP["pf"]["cfg"]["tgt_R"]),
    "Optuna: return/drawdown": dict(sess=OP["retdd"]["cfg"]["sess"], p=OP["retdd"]["cfg"]["p"], tgt_R=OP["retdd"]["cfg"]["tgt_R"]),
    "Sweep: top row":          dict(sess=SW["top"]["sess"], p=SW["top"]["p"], tgt_R=SW["top"]["tgt_R"]),
    "Sweep: neighbourhood":    dict(sess=SW["robust"]["sess"], p=SW["robust"]["p"], tgt_R=SW["robust"]["tgt_R"]),
}
print(__doc__)
print(f"{'preset':26s} {'engine':>7s} {'script':>7s} {'ratio':>7s} {'same exit bar':>14s} {'R corr':>8s} {'gap res':>9s} {'gap lock':>9s}")
rows = []
for nm, c in PRESETS.items():
    D = DS[c["sess"]]
    sig, _ = V.triggers(D, side=1, p=c["p"])
    e = V.run(D, sig, side=1, tgt_R=c["tgt_R"], atr_stop=c["p"]["atr_stop"], p=c["p"])
    p = run_pine(D, sig, 1, trail_next_open=1, p=c["p"], tgt_R=c["tgt_R"])
    m = e.merge(p, on="sig", suffixes=("_e", "_p"))
    same = 100 * float((m.exit_bar_e == m.exit_bar_p).mean()) if len(m) else np.nan
    cr = float(np.corrcoef(m.R_e, m.R_p)[0, 1]) if len(m) > 2 else np.nan
    g = []
    for blk in (0, 1):
        ee, pp = e[e.blk == blk], p[p.blk == blk]
        g.append(100 * (pp.R.mean() - ee.R.mean()) / max(abs(ee.R.mean()), 1e-9) if len(ee) and len(pp) else np.nan)
    print(f"{nm:26s} {len(e):7d} {len(p):7d} {len(p)/max(len(e),1):7.4f} {same:13.1f}% {cr:8.4f} {g[0]:+8.1f}% {g[1]:+8.1f}%")
    rows.append(dict(preset=nm, engine=len(e), script=len(p), ratio=len(p)/max(len(e),1),
                     same_exit_bar=same, r_corr=cr, gap_research=g[0], gap_locked=g[1]))
pd.DataFrame(rows).to_csv("results/vwapema/parity_presets.csv", index=False)
print("\n  The script's trail exits at the NEXT bar's open where the engine exits at the breaching")
print("  close, which is why the exit bar differs on most trades while R correlation stays ~0.98.")
