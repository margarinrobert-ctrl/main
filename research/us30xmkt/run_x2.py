"""x2 -- the overlap matrix and the effective sample size, BEFORE any market is called independent.

`STUDY_TREND_LONG` measured 68% of NQ's triggers firing on the identical 15-minute US100 bar and
concluded that a second feed of the same index is not a second test. `TEAM_POOLED_WINDOW` measured
85.3% for this exact window with daily leg correlation +0.967. This runs the same measurement over
every pair of the five feeds, on each pair's CONTEMPORANEOUS span, and reads the effective sample
size off a date-clustered standard error.
"""
from __future__ import annotations

import itertools
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xm_core as X  # noqa: E402

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 60)

print("=" * 100)
print("x2  TRIGGER OVERLAP, LEG CORRELATION, EFFECTIVE SAMPLE SIZE")
print("=" * 100)

F = X.load_all()
BL = {m: X.blocks(F[m], m) for m in X.MARKETS}
MASK = {m: X.build_masks(F[m]["high"].to_numpy(), F[m]["low"].to_numpy(),
                         F[m]["close"].to_numpy()) for m in X.MARKETS}

# in-window Donchian-20 long signal bars, as TIMESTAMPS
SIG = {}
for m in X.MARKETS:
    f = F[m]
    s, _ = X.signals(f, [], M=MASK[m])
    mod = f["mod"].to_numpy()[s]
    s = s[(mod >= X.W0) & (mod < X.W1)]
    SIG[m] = pd.DatetimeIndex(f.index[s])
    print(f"    {m:6s} in-window Donchian-20 long signal bars: {len(s):,}")

print("\n--- 1. trigger overlap on each pair's CONTEMPORANEOUS span ------------------------")
rows = []
for a, b in itertools.combinations(X.MARKETS, 2):
    lo = max(F[a].index[0], F[b].index[0])
    hi = min(F[a].index[-1], F[b].index[-1])
    if hi <= lo:
        rows.append(dict(pair=f"{a}/{b}", shared_days=0, n_a=0, n_b=0, same_ab=np.nan,
                         same_ba=np.nan, pm2_ab=np.nan, pm2_ba=np.nan))
        continue
    sa = SIG[a][(SIG[a] >= lo) & (SIG[a] <= hi)]
    sb = SIG[b][(SIG[b] >= lo) & (SIG[b] <= hi)]
    setb = set(sb.values.astype("datetime64[ns]").astype(np.int64))
    seta = set(sa.values.astype("datetime64[ns]").astype(np.int64))
    NS15 = 15 * 60 * 1_000_000_000

    def share(src, dst, k):
        if not len(src):
            return np.nan
        v = src.values.astype("datetime64[ns]").astype(np.int64)
        hit = np.zeros(len(v), bool)
        for off in range(-k, k + 1):
            hit |= np.array([(x + off * NS15) in dst for x in v])
        return float(hit.mean())

    shared_days = len(np.intersect1d(
        np.unique(sa.normalize().values), np.unique(sb.normalize().values)))
    rows.append(dict(pair=f"{a}/{b}", shared_days=shared_days, n_a=len(sa), n_b=len(sb),
                     same_ab=share(sa, setb, 0), same_ba=share(sb, seta, 0),
                     pm2_ab=share(sa, setb, 2), pm2_ba=share(sb, seta, 2)))
ov = pd.DataFrame(rows)
print(ov.round(4).to_string(index=False))

print("\n--- 2. daily leg correlation on the BASE arm, ATR units, over shared dates ---------")
DL = {}
for m in X.MARKETS:
    t = X.trades(F[m], m, [], param="atr", M=MASK[m])
    DL[m] = t.groupby("date")["atr_u"].sum()
    print(f"    {m:6s} base arm: {len(t):,} trades on {len(DL[m]):,} dates")

rows = []
for a, b in itertools.combinations(X.MARKETS, 2):
    j = pd.concat([DL[a].rename("a"), DL[b].rename("b")], axis=1, join="inner")
    rows.append(dict(pair=f"{a}/{b}", shared_dates=len(j),
                     corr=float(j.a.corr(j.b)) if len(j) > 20 else np.nan))
cr = pd.DataFrame(rows)
print(cr.round(4).to_string(index=False))

print("\n--- 3. effective sample size when the five feeds are pooled ------------------------")
print("    A pooled standard error must be clustered on the CALENDAR DATE ACROSS MARKETS, so a")
print("    date on which four feeds fire counts once. n_eff = (sd / SE_clustered)^2.")
rows = []
for arm, conds in X.ARMS:
    for param in ("atr", "pts"):
        parts = []
        for m in X.NEW_MARKETS:
            t = X.trades(F[m], m, conds, param=param, M=MASK[m])
            if len(t):
                parts.append(t[["atr_u", "pct", "date"]].assign(market=m))
        if not parts:
            continue
        P = pd.concat(parts)
        se, n_eff, nd = X.cluster_se(P["atr_u"].to_numpy(), P["date"].to_numpy())
        se_n = P["atr_u"].std(ddof=1) / np.sqrt(len(P))
        rows.append(dict(arm=arm, param=param, n=len(P), dates=nd, n_eff=round(n_eff, 0),
                         retention=round(n_eff / len(P), 3), se_clustered=se, se_naive=se_n,
                         infl=round(se / se_n, 3)))
ef = pd.DataFrame(rows)
print(ef.round(5).to_string(index=False))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cache")
os.makedirs(out, exist_ok=True)
ov.to_csv(f"{out}/x2_overlap.csv", index=False)
cr.to_csv(f"{out}/x2_corr.csv", index=False)
ef.to_csv(f"{out}/x2_neff.csv", index=False)
print(f"\n    wrote {out}/x2_*.csv")
