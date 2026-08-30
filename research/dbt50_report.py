"""Turn `dbt50_run.py`'s raw output into the tables a decision can be made from.

Three tables, in the order that matters:

  MARGINALS   for each value of each parameter, the mean out-of-sample R per trade ACROSS
              independent worlds, averaging over the other parameters, with a standard error over
              worlds. This is the "best mean on each parameter" answer -- and the standard error
              is what stops it being a lottery winner. A parameter whose marginal profile is flat
              within its error bars has no best value, and reporting one would be noise-mining.
  SELECTION   the in-sample winner in each world and what it then did out of sample, plus its
              matched control. The IS-minus-OOS gap is the cost of choosing.
  ABLATION    the same numbers in the martingale world. This is the row that decides whether the
              strategy follows trends or follows the generator's drift.
"""
from __future__ import annotations

import json
import sys

import numpy as np

FIELDS = ["don", "adx", "tp", "hold", "n", "n_is", "n_oos", "per", "per_is", "per_oos", "dollars"]


def load(path="/tmp/dbt50_results.json"):
    with open(path) as fh:
        return json.load(fh)


def as_array(rows):
    return np.array(rows, float) if len(rows) else np.zeros((0, len(FIELDS)))


def marginals(reg, col="per_oos"):
    """Mean of `col` per parameter value, per world, then across worlds."""
    ci = FIELDS.index(col)
    out = {}
    for pi, pname in ((0, "don"), (1, "adx"), (2, "tp"), (3, "hold")):
        vals = sorted({v for w in reg["rows"] for v in as_array(w)[:, pi]})
        tab = []
        for v in vals:
            per_world = []
            for w in reg["rows"]:
                a = as_array(w)
                m = a[:, pi] == v
                if m.sum():
                    per_world.append(a[m, ci].mean())
            per_world = np.array(per_world)
            tab.append((v, per_world.mean(), per_world.std(ddof=1) / np.sqrt(len(per_world)),
                        len(per_world)))
        out[pname] = tab
    return out


def show(res, path=None):
    lines = []
    P = lines.append
    for reg, d in res.items():
        sel = d["sel"]; ctrl = d["ctrl"]
        is_r = np.array([s[1] for s in sel]); oos_r = np.array([s[2] for s in sel])
        c_oos = np.array([c["oos_R"] if c else np.nan for c in ctrl])
        n_oos = np.array([s[4] for s in sel])
        g = d.get("gen", [])
        P(f"\n{'=' * 78}\n{reg}   {len(sel)} worlds")
        if g:
            P(f"  generator: ann vol {np.mean([x['ann_vol'] for x in g]):.3f}  "
              f"drift {np.mean([x['ann_drift'] for x in g]):+.3f}  "
              f"daily ACF1 {np.mean([x['daily_acf1'] for x in g]):+.4f}  "
              f"VR(5) {np.mean([x['vr5'] for x in g]):.3f}  "
              f"kurt {np.mean([x['daily_kurt'] for x in g]):.1f}")
        px = np.array([x.get("px_end", np.nan) for x in g]) if g else np.array([np.nan])
        deg = int(np.sum((px < 3000) | (px > 750000)))
        if g:
            P(f"  price after 50y: median {np.nanmedian(px):,.0f} from 15,000  "
              f"[{np.nanmin(px):,.0f} .. {np.nanmax(px):,.0f}]"
              + (f"   {deg}/{len(px)} worlds left a plausible band -- in those, a fixed $14 "
                 f"round turn against a collapsed index makes R explode, so read the MEDIAN"
                 if deg else ""))
        P("\n  SELECTION (pick on the first 65% of sessions, read the rest once)")
        P(f"    in-sample winner      {is_r.mean():+.4f}R  per trade  (mean over worlds)")
        P(f"    its out-of-sample     {oos_r.mean():+.4f}R  +- {oos_r.std(ddof=1)/np.sqrt(len(oos_r)):.4f}"
          f"   [{oos_r.min():+.4f} .. {oos_r.max():+.4f}]")
        P(f"    matched control OOS   {np.nanmean(c_oos):+.4f}R")
        exc = oos_r - c_oos
        t = exc.mean() / (exc.std(ddof=1) / np.sqrt(len(exc)))
        P(f"    EXCESS over control   {exc.mean():+.4f}R  t={t:+.2f}  "
          f"({int((exc > 0).sum())}/{len(exc)} worlds positive)")
        P(f"    median world          strategy {np.median(oos_r):+.4f}R  control "
          f"{np.nanmedian(c_oos):+.4f}R  excess {np.median(exc):+.4f}R")
        P(f"    selection cost        {is_r.mean() - oos_r.mean():+.4f}R lost from IS to OOS")
        P(f"    OOS trades per world  {n_oos.mean():,.0f}")
        best = {}
        P("\n  MARGINAL MEAN OOS R PER TRADE, by parameter (mean +- se over worlds)")
        for pname, tab in marginals(d).items():
            s = "  ".join(f"{v:g}: {m:+.4f}+-{se:.4f}" for v, m, se, _ in tab)
            P(f"    {pname:<5} {s}")
            bv, bm, bse, _ = max(tab, key=lambda r: r[1])
            spread = max(t[1] for t in tab) - min(t[1] for t in tab)
            flat = spread < 2 * np.mean([t[2] for t in tab])
            best[pname] = (bv, bm, bse, flat)
            P(f"          best mean: {pname}={bv:g} at {bm:+.4f}R"
              + ("   [FLAT within error bars -- there is no best value here]" if flat else ""))
        if d.get("meta"):
            m = d["meta"]
            b = np.array([x["oos_R"] for x in m]); f = np.array([x["oos_R_filtered"] for x in m])
            kept = np.array([x["n_kept"] / max(x["n_oos"], 1) for x in m])
            P(f"\n  DEEP META-LABEL ({len(m)} worlds, trained on in-sample trades only)")
            P(f"    unfiltered OOS {b.mean():+.4f}R   filtered {f.mean():+.4f}R   "
              f"kept {100*kept.mean():.0f}% of trades")
            dd = f - b
            P(f"    change {dd.mean():+.4f}R  t={dd.mean()/(dd.std(ddof=1)/np.sqrt(len(dd))):+.2f}"
              f"  ({int((dd > 0).sum())}/{len(dd)} worlds improved)")
    txt = "\n".join(lines)
    print(txt)
    if path:
        with open(path, "w") as fh:
            fh.write(txt + "\n")
    return txt


if __name__ == "__main__":
    show(load(sys.argv[1] if len(sys.argv) > 1 else "/tmp/dbt50_results.json"),
         path="/tmp/dbt50_report.txt")
