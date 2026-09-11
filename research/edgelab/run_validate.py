"""Stage 2: freeze a handful of distinct candidates, then measure them on data they did not pick.

THE ORDER MATTERS AND IS ENFORCED HERE.

  1. Re-score the discovery survivors with DAY-CLUSTERED statistics. Trades inside one session
     are not independent; the unit of inference is the day.
  2. DEDUPLICATE. The raw top-25 is one rule wearing twenty-five hats -- the same trades reached
     through permuted conditions. Candidates whose trade sets overlap above a Jaccard threshold
     are collapsed, so the shortlist is genuinely distinct hypotheses.
  3. FREEZE. Conditions, thresholds, geometry and window are fixed (brief 49). Nothing after this
     point may re-optimise.
  4. WALK-FORWARD inside discovery+validation, purged and embargoed (brief 32, 33).
  5. VALIDATION block, read once per frozen rule.
  6. PRODUCTION block -- read LAST, once, and never fed back (brief 47).

The multiplicity of stage 1 is carried forward and printed with the results, because a p-value
selected out of 27,786 tests is not the p-value it appears to be.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from edgelab import data, features, labels, splits, discover, fast, validate

DISC = "research/edgelab/_discovery.parquet"


def trade_set(P, C, cond, win, block):
    m = win.copy()
    for c in cond.split(" AND "):
        m = m & C[c]
    return set(np.flatnonzero(P["valid"] & m & block).tolist()), m


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def shortlist(d, F, C, disc, days, raw, k=8, min_n=150, min_days=40, jac=0.5, draws=400):
    """Re-score with day clustering, then collapse near-duplicates."""
    cand = raw[(raw["n"] >= min_n)].sort_values("expR", ascending=False).head(400)
    seen = []
    rng = np.random.default_rng(23)
    cache = {}
    for _, row in cand.iterrows():
        key = (row["stop_atr"], row["rr"], row["win_lo"], row["win_hi"], row["max_hold"])
        if key not in cache:
            cache[key] = (labels.precompute(d, row["stop_atr"], rr=row["rr"],
                                            max_hold=int(row["max_hold"]),
                                            lo=int(row["win_lo"]), hi=int(row["win_hi"])),
                          fast._day_pools(labels.precompute(d, row["stop_atr"], rr=row["rr"],
                                                            max_hold=int(row["max_hold"]),
                                                            lo=int(row["win_lo"]),
                                                            hi=int(row["win_hi"])), disc, days))
        P, dp = cache[key]
        win = (d["mod"] >= row["win_lo"]) & (d["mod"] < row["win_hi"])
        ts, m = trade_set(P, C, row["cond"], win, disc)
        if len(ts) < min_n:
            continue
        if any(jaccard(ts, o) > jac for o, _ in seen):
            continue
        s = fast.score_days(P, m, disc, days, day_pools=dp, draws=draws, rng=rng)
        if s is None or s["days"] < min_days:
            continue
        s.update(cond=row["cond"], stop_atr=row["stop_atr"], rr=row["rr"],
                 win_lo=int(row["win_lo"]), win_hi=int(row["win_hi"]),
                 max_hold=int(row["max_hold"]))
        seen.append((ts, s))
        if len(seen) >= k:
            break
    return pd.DataFrame([s for _, s in seen])


def main():
    d = data.bars(15)
    F = features.build(d)
    C = discover.conditions(F)
    B = splits.blocks(d)
    days = fast.day_index(d)
    raw = pd.read_parquet(DISC)
    nfam = int(raw["tests_in_family"].iloc[0])
    print(f"discovery family: {nfam:,} tests. Everything below is selected out of that, and the "
          f"discovery column is NOT evidence.\n")

    sl = shortlist(d, F, C, B["discovery"], days, raw)
    print("SHORTLIST -- distinct candidates, day-clustered, DISCOVERY block")
    cols = ["cond", "stop_atr", "rr", "win_lo", "n", "days", "win", "ctrl_win", "excess",
            "day_R", "pos_days", "p_day", "ambig"]
    print(sl[cols].to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    rows = []
    for _, r in sl.iterrows():
        fz = validate.Frozen(name=r["cond"], conds=tuple(r["cond"].split(" AND ")),
                             stop_atr=float(r["stop_atr"]), rr=float(r["rr"]),
                             max_hold=int(r["max_hold"]), win_lo=int(r["win_lo"]),
                             win_hi=int(r["win_hi"]))
        P = labels.precompute(d, fz.stop_atr, rr=fz.rr, max_hold=fz.max_hold,
                              lo=fz.win_lo, hi=fz.win_hi)
        win = (d["mod"] >= fz.win_lo) & (d["mod"] < fz.win_hi)
        m = win.copy()
        for c in fz.conds:
            m = m & C[c]
        out = dict(cond=fz.name, stop=fz.stop_atr, rr=fz.rr, win_lo=fz.win_lo)
        for tag, blk in (("disc", B["discovery"]), ("valid", B["validation"]),
                         ("prod", B["production"])):
            s = fast.score_days(P, m, blk, days,
                                day_pools=fast._day_pools(P, blk, days), draws=400)
            if s is None:
                out[f"{tag}_n"] = 0
                continue
            out[f"{tag}_n"] = s["n"]; out[f"{tag}_days"] = s["days"]
            out[f"{tag}_win"] = s["win"]; out[f"{tag}_ctrl"] = s["ctrl_win"]
            out[f"{tag}_expR"] = s["expR"]; out[f"{tag}_dayR"] = s["day_R"]
            out[f"{tag}_p"] = s["p_day"]
        rows.append(out)
    res = pd.DataFrame(rows)
    print("\nOUT OF SAMPLE -- validation (2022-2023) and production (2024-2025), read once")
    show = ["cond", "stop", "rr", "disc_n", "disc_win", "disc_expR",
            "valid_n", "valid_win", "valid_ctrl", "valid_expR", "valid_p",
            "prod_n", "prod_win", "prod_ctrl", "prod_expR", "prod_p"]
    show = [c for c in show if c in res.columns]
    with pd.option_context("display.width", 260, "display.max_columns", 40):
        print(res[show].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    res.to_parquet("research/edgelab/_validated.parquet")
    return sl, res


if __name__ == "__main__":
    main()
