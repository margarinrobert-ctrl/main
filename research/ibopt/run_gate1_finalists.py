"""Gate 1 on the Optuna finalists, RESEARCH ONLY -- with the arm the search's marginals demand.

The search chose long-only, a 30-minute IB, no target and a hold to 15:55, on large-IB days. In a
sample where the index rose, that is what an exposure to the opening drive plus drift looks like,
so each finalist is scored against TWO nulls: the risk-matched random entry (same day, same side,
same risk and reward, random bar) and ALWAYS-LONG entered at the IB close on the SAME DAYS with the
same stop distance and flatten -- a rule that only beats the second one has a filter, not an entry.
"""
import os, sys, json
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
from research.ibopt import ibcore as C   # noqa: E402
import gates                              # noqa: E402

pd.set_option("display.width", 200)
print(__doc__)
F = C.build("US30L")
fin = json.load(open("results/ibopt/finalists.json"))
fin["published"] = dict(kw=dict(ib_min=60, retr=0.25, stopf=0.60, tgt=0.50, flat_min=955, side="both",
                                ib_atr_min=0.0, ib_atr_max=0.0))


def always_side(F, t, kw):
    """Enter at the CLOSE of the first bar after the IB, same side the rule took that day, stop the
    same distance in points as the rule's, same target rule, same flatten."""
    out = []
    for _, r in t.iterrows():
        d = int(r.day); a, b = F["starts"][d], F["ends"][d]; m = F["mod"][a:b]
        first_after = a + np.flatnonzero(m >= C.IB_OPEN + kw["ib_min"])[0]
        last_before = a + np.flatnonzero(m < kw["flat_min"])[-1]
        s = 1 if r.side == 0 else -1
        ent = F["c"][first_after]; risk = r.risk
        rew = risk * (kw["tgt"] + kw["retr"]) / (kw["stopf"] - kw["retr"]) if kw["tgt"] < 90 else 1e18
        stp = ent - s * risk; tp = ent + s * rew
        pts = None
        for i in range(first_after + 1, last_before + 1):
            if s > 0:
                if F["l"][i] <= stp: pts = (stp if F["o"][i] > stp else F["o"][i]) - ent; break
                if F["h"][i] >= tp: pts = (tp if F["o"][i] < tp else F["o"][i]) - ent; break
            else:
                if F["h"][i] >= stp: pts = ent - (stp if F["o"][i] < stp else F["o"][i]); break
                if F["l"][i] <= tp: pts = ent - (tp if F["o"][i] > tp else F["o"][i]); break
        if pts is None:
            pts = (F["c"][last_before] - ent) * s
        out.append(100 * (pts - F["cost"]) / ent)
    return np.array(out)


rows = []
for nm, spec in fin.items():
    kw = spec["kw"]
    t = C.run(F, **kw); t = t[t.blk == 0].reset_index(drop=True)
    st = C.stats(t)
    g1 = gates.primary_gate(t.pct.to_numpy() / 100.0)
    ctl = C.control(F, t.day.to_numpy(), draws=1000, **kw)
    al = always_side(F, t, kw)
    rows.append(dict(primary=nm, n=st["n"], pct=st["pct"], tot=st["tot"], pf=st["pf"], win=st["win"],
                     boot_p=g1["bootstrap_p_one_sided"],
                     ctl_med=float(np.median(ctl)), p_entry=float((ctl >= st["pct"]).mean()),
                     always_pct=float(al.mean()), always_pf=float(al[al > 0].sum() / max(-al[al < 0].sum(), 1e-9)),
                     gate1=g1["verdict"].split(" --")[0]))
R = pd.DataFrame(rows)
print(R.to_string(index=False, float_format=lambda v: f"{v:9.4f}"))
print("\n  `p_entry` is against the risk-matched random entry; `always_*` is the same days and sides")
print("  entered at the IB close with the same risk -- what the finalist earns OVER that is the entry.")
R.to_csv("results/ibopt/gate1_finalists.csv", index=False)
