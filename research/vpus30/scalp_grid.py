"""What the BEST Donchian scalp on US30 actually is, and what scalping costs on this feed.

Nothing here is a fresh discovery: US30's blocks have been read repeatedly on this branch
(STUDY_VP_US30, STUDY_VP_DONCHIAN_US30), so EVERY number below is DESCRIPTIVE. The point is to
rank what exists and to price the scalp constraint, not to select a cell.

Declared axes (4,320 configs = the stated multiplicity):
  timeframe 15 / 30 / 60m (resampled from the same 15m series)
  entry channel 10 / 15 / 20 / 30 / 55      exit channel 5 / 10 / 20
  stop 0.75 / 1.0 / 1.5 / 2.5 ATR           target none / 1.5 / 2.0 / 3.0 ATR
  hold cap 8 / 16 / 26 bars                 session RTH+flatten / all hours no flatten
Scored in PERCENT OF ENTRY PRICE with the 2.29-point round turn charged, long and short.
"""
from __future__ import annotations

import itertools
import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vpus30 import vpcore as V  # noqa: E402

RT = 2.29
RTH0, RTH1 = 570, 960

ENT = (10, 15, 20, 30, 55)
EXI = (5, 10, 20)
STP = (0.75, 1.0, 1.5, 2.5)
TGT = (0.0, 1.5, 2.0, 3.0)
HLD = (8, 16, 26)
TFS = (15, 30, 60)
SES = (1, 0)                      # 1 = RTH entries + 16:00 flatten, 0 = all hours, no flatten


@njit(cache=True)
def _walk(o, h, l, c, at, mod, ehi, elo, xhi, xlo, sl, tp, hold, sess, flat_mod, cost):
    n = len(c)
    out = np.empty(n); sd = np.empty(n, np.int64); hl = np.empty(n, np.int64)
    cf = np.empty(n); eb = np.empty(n, np.int64)
    cnt = 0; last = -1
    for i in range(1, n - 1):
        if i <= last or at[i] <= 0 or not np.isfinite(at[i]):
            continue
        if sess == 1 and (mod[i] < RTH0 or mod[i] >= RTH1):
            continue
        if np.isnan(ehi[i]) or np.isnan(elo[i]):
            continue
        s = 1 if c[i] > ehi[i] else (-1 if c[i] < elo[i] else 0)
        if s == 0:
            continue
        j = i + 1
        if sess == 1 and mod[j] >= flat_mod:
            continue
        ent = o[j]
        risk = sl * at[i]
        stop = ent - s * risk
        targ = ent + s * tp * at[i] if tp > 0 else 0.0
        x = -1; px = 0.0
        for t in range(j, n):
            if (l[t] <= stop) if s > 0 else (h[t] >= stop):
                x = t; px = stop
                break
            if tp > 0 and (((h[t] >= targ) if s > 0 else (l[t] <= targ))):
                x = t; px = targ
                break
            if t > j and not np.isnan(xlo[t]):
                if (s > 0 and c[t] < xlo[t]) or (s < 0 and c[t] > xhi[t]):
                    x = t; px = c[t]
                    break
            if t - j >= hold:
                x = t; px = c[t]
                break
            if sess == 1 and t + 1 < n and mod[t + 1] >= flat_mod and mod[t] < flat_mod:
                x = t + 1; px = o[t + 1]
                break
        if x < 0:
            x = n - 1; px = c[n - 1]
        out[cnt] = 100.0 * (s * (px - ent) - cost) / ent
        sd[cnt] = s; hl[cnt] = x - j; cf[cnt] = cost / risk; eb[cnt] = j
        cnt += 1
        last = x
    return out[:cnt], sd[:cnt], hl[:cnt], cf[:cnt], eb[:cnt]


def build(tf):
    f = V.load()
    if tf != 15:
        r = f.resample(f"{tf}min", label="left", closed="left").agg(
            dict(open="first", high="max", low="min", close="last", tv="sum")).dropna()
    else:
        r = f[["open", "high", "low", "close", "tv"]].copy()
    r["atr"] = V.atr(r, 14)
    r["mod"] = r.index.hour * 60 + r.index.minute
    return r


def main():
    sess_all = np.unique(V.load().index.normalize())
    cut = pd.Timestamp(sess_all[int(0.75 * len(sess_all))])
    rows = []
    for tf in TFS:
        g = build(tf)
        o, h, l, c = (g[k].to_numpy() for k in ("open", "high", "low", "close"))
        at = g["atr"].to_numpy(); mod = g["mod"].to_numpy().astype(np.int64)
        ch = {}
        for n in set(ENT) | set(EXI):
            ch[n] = (pd.Series(h).rolling(n).max().shift(1).to_numpy(),
                     pd.Series(l).rolling(n).min().shift(1).to_numpy())
        idx = g.index
        for en, ex, sl, tp, hd, se in itertools.product(ENT, EXI, STP, TGT, HLD, SES):
            r, sd, hl, cf, eb = _walk(o, h, l, c, at, mod, ch[en][0], ch[en][1], ch[ex][0], ch[ex][1],
                                  sl, tp, hd, se, RTH1, RT)
            if len(r) < 60:
                continue
            # a trade's block is its signal block; approximate by position in the series
            rows.append(dict(tf=tf, ent=en, exi=ex, stop=sl, tgt=tp, hold=hd, sess=se,
                             n=len(r), tot=float(r.sum()), mu=float(r.mean()),
                             pf=float(r[r > 0].sum() / max(-r[r < 0].sum(), 1e-12)),
                             med_hold=float(np.median(hl)) * tf,
                             cost_risk=float(np.median(cf))))
        print(f"  tf {tf}m done, {len(rows)} cells so far", flush=True)
    d = pd.DataFrame(rows)
    d.to_csv("research/vpus30/scalp_grid.csv", index=False)
    print(f"\n{len(d)} scorable cells of {len(ENT)*len(EXI)*len(STP)*len(TGT)*len(HLD)*len(TFS)*len(SES)} declared")
    print(f"profitable {float((d.tot > 0).mean()):.3f}")
    print("\nMARGINAL AVERAGE of total % by axis (read this, not the top row)")
    for ax in ("tf", "ent", "exi", "stop", "tgt", "hold", "sess"):
        m = d.groupby(ax).tot.mean().round(2).to_dict()
        print(f"  {ax:<6} {m}")
    print("\nTOP 10 by total %, with the median hold in MINUTES")
    print(d.sort_values("tot", ascending=False).head(10).to_string(
        index=False, float_format=lambda x: f"{x:.4f}"))
    print("\nBEST CELL AT EACH MEDIAN-HOLD CEILING (what a scalp actually costs)")
    for cap in (30, 60, 120, 240, 10**9):
        s = d[d.med_hold <= cap]
        if len(s) == 0:
            print(f"  <= {cap:>4} min : no cell"); continue
        b = s.loc[s.tot.idxmax()]
        print(f"  <= {cap:>4} min : tf {int(b.tf):>2}m ent {int(b.ent):>2} exi {int(b.exi):>2} "
              f"stop {b.stop} tgt {b.tgt} hold {int(b.hold)} sess {int(b.sess)} | "
              f"n {int(b.n):>5} tot {b.tot:+7.2f}% mu {b.mu:+.4f} PF {b.pf:.3f} "
              f"hold {b.med_hold:.0f}min cost/risk {b.cost_risk:.3f}")


if __name__ == "__main__":
    main()
