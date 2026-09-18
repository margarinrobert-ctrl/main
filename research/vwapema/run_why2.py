"""Is the ALWAYS-LONG control fair? It has no stop, so it could simply be taking more risk.

The comparison in `run_why` scores it in the RULE's own R units, which is the right denominator,
but a rule with a stop and a control without one are not automatically comparable. This file adds
the control's own risk profile -- win rate, worst trade, drawdown, downside deviation -- and then
re-runs it in a form that CANNOT be accused of taking more risk: the same entry (session open) with
the SAME ATR stop the rule uses.
"""
import os, sys, json
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.vwapema import vecore as V

pd.set_option("display.width", 235)
print(__doc__)
DS = {s: V.build(sess=s) for s in ("ny", "utc")}
SW = json.load(open("results/vwapema/sweep_cells.json"))
OP = json.load(open("results/vwapema/optuna_finalists.json"))
PRESETS = {
    "As published": dict(sess="ny", p=dict(V.PARAMS), tgt_R=3.0),
    "Optuna totR": {k: OP["totR"]["cfg"][k] for k in ("sess", "p", "tgt_R")},
    "Optuna PF": {k: OP["pf"]["cfg"][k] for k in ("sess", "p", "tgt_R")},
    "Optuna retDD": {k: OP["retdd"]["cfg"][k] for k in ("sess", "p", "tgt_R")},
    "Sweep top row": dict(sess=SW["top"]["sess"], p=SW["top"]["p"], tgt_R=SW["top"]["tgt_R"]),
    "Sweep nbhd": dict(sess=SW["robust"]["sess"], p=SW["robust"]["p"], tgt_R=SW["robust"]["tgt_R"]),
}


def trades(cfg):
    D = DS[cfg["sess"]]
    sig, _ = V.triggers(D, side=1, p=cfg["p"])
    t = V.run(D, sig, side=1, tgt_R=cfg["tgt_R"], atr_stop=cfg["p"]["atr_stop"], p=cfg["p"])
    return t


def control_paths(cfg, t, stopped):
    """Session-open entry, same exit bar as the rule's trade. `stopped` adds the SAME ATR stop the
    rule uses, anchored at the session-open bar, so the control cannot be accused of more risk."""
    D = DS[cfg["sess"]]
    o, h, l, c, atr = D["o"], D["h"], D["l"], D["c"], D["atr"]
    day, rth = D["day"], D["rth"]
    out = []
    for _, r in t.iterrows():
        d = day[int(r.sig)]
        idx = np.flatnonzero((day == d) & rth)
        if len(idx) == 0:
            continue
        a = idx[0]
        ent = o[a] + V.SLIP
        risk = float(r.risk)
        stp = ent - risk
        xb = int(r.exit_bar); px = None
        if stopped:
            for j in range(a, xb + 1):
                if l[j] <= stp:
                    px = (stp if o[j] > stp else o[j]) - V.SLIP
                    break
        if px is None:
            px = c[xb] - V.SLIP
        out.append((px - ent - V.COST_RT) / max(risk, 1e-9))
    return np.array(out)


def prof(x):
    if len(x) == 0:
        return dict(n=0)
    cum = np.cumsum(x)
    dd = float(np.max(np.maximum.accumulate(cum) - cum))
    dn = x[x < 0]
    return dict(n=len(x), R=float(x.mean()), win=100*float((x > 0).mean()), worst=float(x.min()),
                dd=dd, downside_sd=float(dn.std()) if len(dn) else 0.0,
                R_per_dd=float(x.sum()/max(dd, 1e-9)))


print("=" * 128)
print("THE CONTROL'S OWN RISK PROFILE, and the same control WITH the rule's stop attached")
print("=" * 128)
rows = []
for k, cfg in PRESETS.items():
    t = trades(cfg)
    for blk, bn in ((0, "research"), (1, "LOCKED")):
        tt = t[t.blk == blk]
        if len(tt) < 20:
            continue
        rule = prof(tt.R.to_numpy())
        c_no = prof(control_paths(cfg, tt, stopped=False))
        c_st = prof(control_paths(cfg, tt, stopped=True))
        rows.append(dict(preset=k, block=bn, n=rule["n"],
                         rule_R=rule["R"], rule_win=rule["win"], rule_worst=rule["worst"],
                         rule_dd=rule["dd"], rule_RperDD=rule["R_per_dd"],
                         open_R=c_no["R"], open_worst=c_no["worst"], open_dd=c_no["dd"],
                         open_RperDD=c_no["R_per_dd"],
                         open_stopped_R=c_st["R"], open_stopped_worst=c_st["worst"],
                         open_stopped_dd=c_st["dd"], open_stopped_RperDD=c_st["R_per_dd"]))
A = pd.DataFrame(rows)
print(A[["preset", "block", "n", "rule_R", "open_R", "open_stopped_R",
         "rule_worst", "open_worst", "open_stopped_worst"]].to_string(index=False, float_format=lambda v: f"{v:9.3f}"))
print("\n  risk-adjusted (total R over max drawdown, so more risk cannot flatter it):")
print(A[["preset", "block", "rule_dd", "open_dd", "open_stopped_dd",
         "rule_RperDD", "open_RperDD", "open_stopped_RperDD"]].to_string(index=False, float_format=lambda v: f"{v:9.3f}"))
beats = (A.rule_R > A.open_stopped_R).sum()
print(f"\n  presets beating the STOPPED session-open control: {beats} of {len(A)}")
beats_dd = (A.rule_RperDD > A.open_stopped_RperDD).sum()
print(f"  presets beating it on RETURN OVER DRAWDOWN:        {beats_dd} of {len(A)}")
A.to_csv("results/vwapema/why_control_risk.csv", index=False)
