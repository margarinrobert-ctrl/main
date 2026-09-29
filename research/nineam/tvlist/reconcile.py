"""Trade-by-trade transcription check: the user's TradingView export against our walker.

Run over the sessions BOTH sides can see (our pre-open coverage: 2026-04-30 .. 2026-09-16). Every
session is classified -- SAME (session, side and fill minute agree), SAME SIDE but shifted,
OPPOSITE SIDE, TV ONLY, OURS ONLY -- and every disagreement is printed, because the SHAPE of the
disagreement says whether it is the rule, the order model, or the data.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)
import tv_trades as TV  # noqa: E402
import na_30s as T      # noqa: E402
import na_s30 as S      # noqa: E402
import na_live as L     # noqa: E402


def run(path, cfg=None):
    cfg = dict(L.TV if cfg is None else cfg)
    tv = TV.load(path)
    f = T.frame(tf=0.5, atr_n=14)
    c = S.Ctx30(name="US30L", tf=0.5, fix=1, frame=f, block_name="ALL")
    ours = c.trades(cfg)
    ours = ours.assign(et=f.index[ours["eb"].to_numpy()])
    have = set(pd.to_datetime(np.unique(c.day[(c.mod >= 540) & (c.mod < 545)]), unit="D").date)
    tvw = tv[tv.entry_time.dt.date.isin(have)].copy()
    tvw["d"] = tvw.entry_time.dt.date
    ours["d"] = ours.et.dt.date

    rows = []
    for d in sorted(set(tvw.d) | set(ours.d)):
        a = tvw[tvw.d == d].reset_index(drop=True)
        b = ours[ours.d == d].reset_index(drop=True)
        for i in range(max(len(a), len(b))):
            ta = a.iloc[i] if i < len(a) else None
            tb = b.iloc[i] if i < len(b) else None
            r = dict(day=d, tv_t=None, tv_side=None, tv_pts=None, tv_why=None,
                     our_t=None, our_side=None, our_pts=None, our_why=None)
            if ta is not None:
                r.update(tv_t=ta.entry_time, tv_side=int(ta.side),
                         tv_pts=round(ta.pts_gross - 2.29, 1), tv_why=ta.signal)
            if tb is not None:
                r.update(our_t=tb.et, our_side=int(tb.side), our_pts=round(tb.pts, 1),
                         our_why={1: "stop", 2: "target", 3: "flat", 6: "opp cross"}.get(int(tb.why)))
            if ta is None:
                r["match"] = "OURS ONLY"
            elif tb is None:
                r["match"] = "TV ONLY"
            elif r["tv_side"] != r["our_side"]:
                r["match"] = "OPPOSITE SIDE"
            else:
                dt = abs((r["tv_t"] - r["our_t"]).total_seconds()) / 60.0
                r["match"] = "SAME" if dt <= 1.0 else "SAME SIDE, SHIFTED"
                r["dt_min"] = dt
            rows.append(r)
    m = pd.DataFrame(rows)
    return tv, ours, m, have


def main(path):
    tv, ours, m, have = run(path)
    print("=" * 96)
    print(f"TRANSCRIPTION CHECK -- {len(have)} sessions both sides can see")
    print("=" * 96)
    n_tv = int(m.tv_t.notna().sum()); n_us = int(m.our_t.notna().sum())
    print(f"  TradingView trades {n_tv}    ours {n_us}\n")
    vc = m["match"].value_counts()
    print(vc.to_string())
    same = m[m.match == "SAME"]
    ok = (same.tv_pts - same.our_pts).abs() <= 1.0
    print(f"\n  SAME entries with the same OUTCOME (net pts within 1.0): {int(ok.sum())} of {len(same)}")
    print(f"  entries agreeing on session, side and minute: {len(same)} of {max(n_tv, n_us)} "
          f"({len(same)/max(n_tv, n_us):.1%})")
    show = m[m.match != "SAME"].copy()
    for k in ("tv_t", "our_t"):
        show[k] = show[k].apply(lambda v: "" if pd.isna(v) else v.strftime("%H:%M:%S"))
    print("\n  every disagreement:")
    print(show.drop(columns=[c for c in ["dt_min"] if c in show]).to_string(index=False))
    m.to_csv(os.path.join(HERE, "reconcile_2026-09-23.csv"), index=False)
    return m


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "tv_export_2026-09-23.csv"))
