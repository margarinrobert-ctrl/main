"""PHASE 3 -- is the grid's maximum a region or a corner? Neighbourhood on TRAIN, then ONE read of
VALIDATION.

PHASE 2 SAID THE GRID IS NULL: 1.4% of cells clear PF 1, median PF 0.717, and all 24 marginal
averages are negative. The top cell therefore has to be treated as the maximum of a search until
shown otherwise, and there are two ways to show otherwise -- a neighbourhood that also works, and a
validation block that agrees.

THE GRID IS SMALLER THAN IT LOOKS. `stop="sweep"` ignores `stop_k` entirely, so its 1,800 cells are
360 distinct configurations and the top 15 rows of phase 2 are 3 distinct rows. Effective size is
3,960, not 5,400, and that is the number the multiplicity applies at.
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v36")
import indicators as I        # noqa: E402
import levels as LV           # noqa: E402
import setup as S             # noqa: E402
import engine as E            # noqa: E402
from run_base import splits, metrics, line   # noqa: E402


def hdr(t):
    print("\n" + "=" * 124)
    print(t)
    print("=" * 124, flush=True)


def build(d, atr1, pools, ifv, defn, tf):
    sl = S.find_sweeps(d, pools, +1, defn=defn, atr=atr1)
    ss = S.find_sweeps(d, pools, -1, defn=defn, atr=atr1)
    r, iv = ifv[tf]
    return pd.concat([S.setups(d, +1, sl, iv, r, tf), S.setups(d, -1, ss, iv, r, tf)],
                     ignore_index=True).sort_values("inv_bar_1m").reset_index(drop=True)


if __name__ == "__main__":
    t0 = time.perf_counter()
    d = LV.load()
    atrs = {p: I.ema(I.true_range(d["h"], d["l"], d["c"]), p) for p in (14, 20, 30)}
    pools = S.build_pools(d)
    ifv = {}
    for tf in (5, 15):
        r = S.htf_frame(d, tf)
        at = I.ema(I.true_range(r["h"], r["l"], r["c"]), 14)
        ifv[tf] = (r, S.find_ifvgs(r, S.find_fvgs(r, at)))

    df = pd.read_csv("research/v36/v36_phase2.csv")
    # collapse the inert stop_k axis so a configuration is counted once
    df["k_eff"] = np.where(df["stop"] == "sweep", 0.0, df.stop_k)
    dist = df.drop_duplicates(subset=["defn", "tf", "entry", "stop", "atr_p", "k_eff", "tp_r"])
    hdr(f"PHASE 3 -- {len(dist):,} DISTINCT configurations (of {len(df):,} grid rows)")
    print(f"   share with PF > 1: {float((dist.pf > 1).mean()):.3f}   median PF "
          f"{dist.pf.median():.3f}   median R/trade {dist.R.median():+.4f}")

    top = dist.nlargest(5, "R").reset_index(drop=True)
    hdr("THE TOP 5 DISTINCT CONFIGURATIONS ON TRAIN, and their parameter NEIGHBOURHOOD")
    for t in top.itertuples():
        nb = dist[(dist.defn == t.defn) & (dist.tf == t.tf) & (dist.entry == t.entry) &
                  (dist.stop == t.stop)]
        print(f"   {t.defn} {t.tf}m {t.entry}/{t.stop} atr{t.atr_p} k{t.k_eff} tp{t.tp_r}   "
              f"train R {t.R:+.4f}  PF {t.pf:.3f}  n {int(t.n)}  Sharpe {t.sharpe:+.2f}  "
              f"DD {t.dd:.1f}")
        print(f"      same family, all other atr/k/tp: {len(nb)} cells, "
              f"{float((nb.pf > 1).mean()):.0%} with PF>1, mean R {nb.R.mean():+.4f}, "
              f"worst {nb.R.min():+.4f}")
        # one-axis-at-a-time perturbation
        for ax in ("defn", "tf", "entry", "stop"):
            alt = dist[(dist.atr_p == t.atr_p) & (dist.k_eff == t.k_eff) & (dist.tp_r == t.tp_r)]
            for c in ("defn", "tf", "entry", "stop"):
                if c != ax:
                    alt = alt[alt[c] == getattr(t, c)]
            vals = alt.set_index(ax).R.to_dict()
            print(f"      vary {ax:<6} " + "  ".join(f"{k}:{v:+.3f}" for k, v in vals.items()))

    hdr("THE ONE READ OF VALIDATION -- top 5 distinct configurations, nothing changed after this")
    print(f"   {'configuration':<42}{'TRAIN':>26}{'  |':>3}{'VALIDATION':>26}")
    print(f"   {'':<42}{'n':>6}{'R':>9}{'PF':>7}{'Sh':>6}{'  |':>3}{'n':>6}{'R':>9}{'PF':>7}"
          f"{'Sh':>6}")
    rows = []
    for t in top.itertuples():
        su = build(d, atrs[14], pools, ifv, t.defn, int(t.tf))
        sb = su.inv_bar_1m.to_numpy(np.int64)
        tr, info = E.run(d, su, atrs[int(t.atr_p)][sb], entry=t.entry, stop=t.stop,
                         stop_k=(t.stop_k if t.stop != "sweep" else 1.0), stop_buf=0.25,
                         tp="R", tp_r=t.tp_r, retest_bars=60)
        blk = splits(d["tday"], tr.fill_bar.to_numpy())
        got = {}
        for b in ("train", "valid"):
            m = blk[b]
            got[b] = metrics(tr.R.to_numpy()[m], tr.pnl.to_numpy()[m],
                             d["tday"][tr.fill_bar.to_numpy()[m]])
        tag = f"{t.defn} {t.tf}m {t.entry}/{t.stop} a{t.atr_p} tp{t.tp_r}"
        a, b_ = got["train"], got["valid"]
        print(f"   {tag:<42}{a['n']:>6}{a['R']:>+9.4f}{a['pf']:>7.3f}{a['sharpe']:>+6.2f}{'  |':>3}"
              + (f"{b_['n']:>6}{b_['R']:>+9.4f}{b_['pf']:>7.3f}{b_['sharpe']:>+6.2f}"
                 if b_ else f"{'--':>6}"))
        rows.append(dict(tag=tag, tr_R=a["R"], tr_pf=a["pf"],
                         va_R=b_["R"] if b_ else np.nan, va_pf=b_["pf"] if b_ else np.nan))
    v = pd.DataFrame(rows)
    ok = v.dropna(subset=["va_R"])
    if len(ok):
        print(f"\n   configurations still profitable on validation: "
              f"{int((ok.va_R > 0).sum())} of {len(ok)}   "
              f"mean train R {ok.tr_R.mean():+.4f} -> mean validation R {ok.va_R.mean():+.4f}")
    v.to_csv("research/v36/v36_phase3.csv", index=False)
    print(f"\n   elapsed {time.perf_counter() - t0:.0f}s")
