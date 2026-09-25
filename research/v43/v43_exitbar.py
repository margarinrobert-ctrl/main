"""How concentrated MAE is on the EXIT BAR -- a CENSORING diagnostic, not a better estimator.

MAE is the maximum adverse excursion from entry over the whole trade, and that IS the measure of
entry heat. Nothing here disputes that. What this module measures is how much of the recorded
number is contributed by the bar the trade left on, because that share is a direct read on how
badly a stop is CENSORING the excursion: on a stopped-out trade the exit bar is where the worst
excursion happened, by construction, so a large share means the stop is truncating the observation
rather than the market being calm.

Removing the exit bar is NOT a repair and the figures below are not "true" MAE -- they discard real
adverse excursion and are biased low. The repair is to stop censoring, which is
`v43_uncensored.py`: widen the stop until it cannot bind, or drop exits entirely and read a fixed
horizon. Same protocol STUDY_M4_ANATOMY used on the barrier system.

There is a second, much smaller effect in the same place: `core.run` updates hi_since/lo_since at
the top of the bar loop and only then tests the exit, so the closing bar's full high and low are
counted although the position left partway through. Every bar strictly inside the trade is exact,
since a bar's high is the true intrabar maximum.

Entry price is o[t_in]: core.run sets entry_bar = i+1 and fills at o[i+1].
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle")
sys.path.insert(0, "research/v43")
import v43_maemfe as V       # noqa: E402


def excursion(h, l, a, b, px):
    """MFE/MAE in points over bars [a, b] inclusive, off the fill price."""
    return h[a:b + 1].max() - px, px - l[a:b + 1].min()


def main():
    rows = []
    for cfg in V.CONFIGS:
        P = V.prep(cfg["tf"])
        T = V.run_one(P, cfg, V.gate_of(P, cfg["gate"]))
        h, l, o, atr = P["h"], P["l"], P["o"], P["atr"]
        full_f, full_a, cut_f, cut_a = [], [], [], []
        for a, b, r in zip(T["tin"], T["tout"], T["risk"]):
            if r <= 0 or b <= a:
                continue
            px = o[a]
            f1, a1 = excursion(h, l, a, b, px)
            f2, a2 = excursion(h, l, a, b - 1, px)      # exit bar removed
            full_f.append(f1 / r); full_a.append(a1 / r)
            cut_f.append(f2 / r); cut_a.append(a2 / r)
        if len(full_f) < 20:
            continue
        rows.append(dict(name=cfg["name"], n=len(full_f),
                         mfe_full=np.mean(full_f), mfe_excl=np.mean(cut_f),
                         mae_full=np.mean(full_a), mae_excl=np.mean(cut_a)))
    d = pd.DataFrame(rows)
    d["mfe_share"] = 100 * (d.mfe_full - d.mfe_excl) / d.mfe_full
    d["mae_share"] = 100 * (d.mae_full - d.mae_excl) / d.mae_full
    d.to_csv("results/v43/v43_exitbar.csv", index=False)
    print(d.round(3).to_string(index=False))
    print(f"\n  exit bar contributes {d.mfe_share.mean():.1f}% of MFE and "
          f"{d.mae_share.mean():.1f}% of MAE on average across the eight configurations")


if __name__ == "__main__":
    main()


def by_reason():
    """MAE with and without the exit bar, split by HOW the trade ended.

    For a stopped-out trade the exit bar is where the worst excursion happened by construction, so
    full-trade MAE on that subset is close to the stop distance whatever the entry did. Splitting
    is what separates "how much heat did the entry take" from "how often did it get stopped"."""
    rows = []
    for cfg in V.CONFIGS:
        P = V.prep(cfg["tf"])
        T = V.run_one(P, cfg, V.gate_of(P, cfg["gate"]))
        h, l, o = P["h"], P["l"], P["o"]
        acc = {}
        for a, b, r, w in zip(T["tin"], T["tout"], T["risk"], T["why"]):
            if r <= 0 or b <= a:
                continue
            px = o[a]
            k = "stop" if w == core.STOP_EXIT else "channel"
            acc.setdefault(k, []).append(((px - l[a:b + 1].min()) / r,
                                          (px - l[a:b].min()) / r))
        row = dict(name=cfg["name"])
        tot = sum(len(v) for v in acc.values())
        for k in ("stop", "channel"):
            v = acc.get(k, [])
            row[f"{k}_share"] = 100.0 * len(v) / tot if tot else np.nan
            row[f"{k}_mae_full"] = float(np.mean([x[0] for x in v])) if v else np.nan
            row[f"{k}_mae_excl"] = float(np.mean([x[1] for x in v])) if v else np.nan
        rows.append(row)
    d = pd.DataFrame(rows)
    d.to_csv("results/v43/v43_exitreason.csv", index=False)
    print(d.round(3).to_string(index=False))
    return d
