"""T2  FEATURES: build, TRUNCATION AUDIT, base rates on the trigger's own bars, correlation collapse
on the SIGNAL bars. Writes feats_all.pkl (events + features) for T3..T5.
"""
from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tfcore as C  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

pd.set_option("display.width", 220)
t0 = time.time()


def hd(t):
    print("\n" + "=" * 100); print(t); print("=" * 100, flush=True)


E = pd.read_pickle(os.path.join(HERE, "events_all.pkl"))
b = C.base()
bs = C.base_series(b)
print(f"  base series built ({time.time()-t0:.0f}s)", flush=True)

hd("2a  VOLUME IS REAL ON EVERY TRADEABLE SESSION?")
vb = b[b.index >= C.VOL_FROM]
dz = b.groupby("day")["volume"].sum()
tdays = np.unique(E["day"])
print(f"  tradeable sessions {len(tdays)}; with ZERO total volume: {int((dz.reindex(tdays) <= 0).sum())}; "
      f"first tradeable {C.DK.from_day(tdays.min()).date()} vs volume from {C.VOL_FROM.date()}")
print(f"  corr(volume, high-low) on the volume era {np.corrcoef(vb['volume'], vb['high']-vb['low'])[0,1]:+.4f}")

F = []
for tf in C.TFS:
    c = C.ctx(tf)
    ev = E[E.tf == tf].reset_index(drop=True)
    X = C.features(b, c.f0, ev["sig"].to_numpy(), ev["side"].to_numpy(), tf, bs=bs)
    F.append(pd.concat([ev, X], axis=1))
    print(f"  tf {tf:>4}: {len(ev)} events featurised ({time.time()-t0:.0f}s)", flush=True)
F = pd.concat(F, ignore_index=True)
cols = C.feat_cols(F)
print(f"  {len(cols)} features: {', '.join(cols)}")

hd("2b  TRUNCATION AUDIT -- every feature recomputed from frames CUT at the signal bar's end")
g = np.random.default_rng(5)
bad = tot = 0; worst = []
for tf in C.TFS:
    ev = E[E.tf == tf]
    pr = ev.iloc[np.sort(g.choice(len(ev), 6, replace=False))]
    bb, tt, ww = C.audit(tf, pr)
    bad += bb; tot += tt; worst += ww
    print(f"  tf {tf:>4}: {bb} mismatches of {tt}  ({time.time()-t0:.0f}s)", flush=True)
print(f"  TOTAL {bad} mismatches of {tot}")
for w in worst[:10]:
    print("   ", w)
pd.DataFrame([dict(mismatches=bad, probes=tot)]).to_csv(os.path.join(HERE, "t2_audit.csv"), index=False)

hd("2c  BASE RATES ON THE TRIGGER'S OWN BARS (flag > 0.95)")
DIRN = {"rng.brk", "rng.brk_pct", "mom.gap", "mom.slope", "mom.gate", "mom.ret30", "pre.gap",
        "pre.h8dir", "flow.cpos", "flow.cvd10", "flow.cvd30", "flow.cvd_bar", "flow.up10"}
print("  Directional (side-oriented) features are flagged on the share > 0; magnitudes (positive by")
print("  construction) only on the modal share, since a width being > 0 is not information.")
rows = []
for col in cols:
    for lab, m in (("gated", F.gated == 1), ("ungated", F.gated >= 0)):
        x = F.loc[m, col].to_numpy(float)
        fin = np.isfinite(x)
        xf = x[fin]
        pos = float((xf > 0).mean()) if len(xf) else np.nan
        vc = pd.Series(xf).round(9).value_counts(normalize=True)
        modal = float(vc.iloc[0]) if len(vc) else np.nan
        rows.append(dict(feature=col, set=lab, n=int(m.sum()), finite=float(fin.mean()),
                         share_pos=pos, modal_share=modal, median=float(np.median(xf)) if len(xf) else np.nan,
                         kind="dir" if col in DIRN else "mag",
                         flag=bool((max(pos, 1 - pos) > 0.95 if col in DIRN else False)
                                   or modal > 0.95) if len(xf) else True))
BR = pd.DataFrame(rows)
BR.to_csv(os.path.join(HERE, "t2_baserates.csv"), index=False)
piv = BR.pivot(index="feature", columns="set", values=["finite", "share_pos", "modal_share", "flag"])
print(piv.to_string(float_format=lambda v: f"{v:.3f}"))
fl = sorted(set(BR.loc[BR.flag, "feature"]))
print(f"\n  FLAGGED (>95% one way on some set): {fl}")

hd("2d  CORRELATION COLLAPSE ON THE SIGNAL BARS (Spearman, all events pooled)")
R = F[cols].rank().corr()
pairs = []
for i, a in enumerate(cols):
    for bcol in cols[i + 1:]:
        if abs(R.loc[a, bcol]) >= 0.80:
            pairs.append((a, bcol, R.loc[a, bcol]))
for a, bcol, r in sorted(pairs, key=lambda z: -abs(z[2])):
    print(f"  {a:18s} {bcol:18s} {r:+.4f}")
dup = [bcol for a, bcol, r in pairs if abs(r) >= 0.999]
# degenerate on the universe (modal share > 0.95 on the UNGATED set) -> dropped, not modelled
degen = sorted(set(BR.loc[(BR.set == "ungated") & (BR.modal_share > 0.95), "feature"]))
print(f"  degenerate on the whole universe, dropped: {degen}")
dup = dup + degen
print(f"  exact duplicates (|rho| >= 0.999), dropped: {dup}")
# inert on the gated set is kept in the universe but printed
keep = [k for k in cols if k not in dup]
F.to_pickle(os.path.join(HERE, "feats_all.pkl"))
pd.Series(keep).to_csv(os.path.join(HERE, "t2_keep.csv"), index=False)
R.to_csv(os.path.join(HERE, "t2_corr.csv"))
print(f"\n  kept {len(keep)} features. done in {time.time()-t0:.0f}s")
