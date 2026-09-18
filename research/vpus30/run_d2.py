"""Feature engineering on the Donchian+ATR event stream, US30. Meta layer only.

Order, and none of it is negotiable:
  1. truncation audit on the NEW `don.*` family (VP and quant were audited in run_v1/run_v3)
  2. BASE RATES ON THE TRIGGER'S OWN BARS -- a breakout bar is the N-bar extreme by construction,
     so anything reading channel position is the trigger restated (STUDY_V60 / V62 / V16)
  3. univariate screen of the survivors against a SAME-SELECTIVITY RANDOM VETO, re-simulated end
     to end (a filter is a veto, not a subset -- STUDY_AUCTION)
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vpus30 import vpcore as V, vpquant as Q, vpdon as D  # noqa: E402

RNG = np.random.default_rng(4242)
ENT_N, EX_N, SL, SIDE = 55, 20, 3.0, 0        # chosen at Gate 1: best control p, most events


def build_all():
    f = V.load()
    g = D.frame(f)
    sess = np.unique(g.index.normalize())
    cut = pd.Timestamp(sess[int(0.75 * len(sess))])
    d = V.sessions(f)
    vp = V.features(f, d)                              # RTH-only frame, 22 VP features
    qx, best_d, hp = Q.build(vp, cut)                  # 30 quant features on the same index
    dx = D.don_features(g, ENT_N, EX_N, SL)            # 14 channel/ATR features, full frame
    X = pd.concat([vp[V.FEATS], qx], axis=1).reindex(g.index)
    X = pd.concat([X, dx], axis=1)
    t = D.walk(g, ent_n=ENT_N, ex_n=EX_N, sl=SL, side=SIDE)
    return f, g, cut, X, t, best_d


def main():
    f, g, cut, X, t, best_d = build_all()
    cols = list(X.columns)
    print(f"primary don{ENT_N} {SL}N both  events {len(t)}  features {len(cols)}  ffd d={best_d}")
    print(f"split {str(cut)[:10]}")

    # ---- 1. truncation audit on don.* : rebuild from history ENDING at the bar
    print("\n1. TRUNCATION AUDIT (don.* family)")
    probes = RNG.choice(np.arange(3000, len(g) - 5), size=12, replace=False)
    bad = 0
    for i in sorted(probes):
        sub = D.don_features(g.iloc[: i + 1], ENT_N, EX_N, SL)
        for cnm in D.DON_FEATS:
            a, b = X[cnm].to_numpy()[i], sub[cnm].to_numpy()[-1]
            if not (np.isnan(a) and np.isnan(b)) and abs(np.nan_to_num(a) - np.nan_to_num(b)) > 1e-9:
                bad += 1
    print(f"   mismatches {bad} / {len(probes) * len(D.DON_FEATS)}")

    # ---- 2. base rates on the trigger's own bars
    print("\n2. BASE RATES -- share of SIGNAL bars above the ALL-RTH-bar median")
    rth = g.is_rth.to_numpy().astype(bool)
    sig = t.sig.to_numpy()
    keep, drop = [], []
    for cnm in cols:
        v = X[cnm].to_numpy()
        pop = v[rth & np.isfinite(v)]
        if len(pop) < 1000:
            drop.append((cnm, np.nan, np.nan)); continue
        med = np.nanmedian(pop)
        sv = v[sig]
        sv = sv[np.isfinite(sv)]
        if len(sv) < 200:
            drop.append((cnm, np.nan, np.nan)); continue
        share = float((sv > med).mean())
        lift = share / 0.5
        (drop if (share > 0.95 or share < 0.05) else keep).append((cnm, share, lift))
    print(f"   pool {len(cols)} -> kept {len(keep)}, DEGENERATE on the trigger's bars {len(drop)}")
    for cnm, s, li in sorted(drop, key=lambda r: -(r[1] if np.isfinite(r[1]) else 0))[:12]:
        print(f"     drop {cnm:<16} share {s:.3f} lift {li:.2f}")
    ext = sorted(keep, key=lambda r: -abs(r[1] - 0.5))[:8]
    print("   most selective survivors:")
    for cnm, s, li in ext:
        print(f"     {cnm:<16} share {s:.3f} lift {li:.2f}")
    pool = [k[0] for k in keep]
    pd.Series(pool).to_csv("research/vpus30/don_pool.csv", index=False, header=False)

    # ---- 3. univariate screen, veto framing, same-selectivity random control
    print("\n3. SCREEN on RESEARCH -- each feature cut at its own research median, kept half")
    ts = pd.DatetimeIndex(t.ts)
    res = ts < cut
    base = t[res]
    b_mu = base.pct.mean()
    print(f"   base: n {len(base)}  net% {b_mu:.4f}  PF {D.pf(base.pct):.3f}")
    sig_r = base.sig.to_numpy(); sd_r = base.side.to_numpy()
    nkeep = len(sig_r) // 2

    ctl = np.empty(400)
    for i in range(400):
        pick = RNG.choice(len(sig_r), size=nkeep, replace=False)
        r, _ = D.walk_at(g, sig_r[pick], sd_r[pick], ex_n=EX_N, sl=SL)
        ctl[i] = np.nanmean(r) if np.isfinite(r).sum() >= 5 else np.nan

    rows = []
    for cnm in pool:
        v = X[cnm].to_numpy()[sig_r]
        if not np.isfinite(v).sum() > 200:
            continue
        med = np.nanmedian(v)
        for dr, m in (("hi", v > med), ("lo", v <= med)):
            m = m & np.isfinite(v)
            if m.sum() < 200:
                continue
            r, _ = D.walk_at(g, sig_r[m], sd_r[m], ex_n=EX_N, sl=SL)
            mu = float(np.nanmean(r))
            p = float(np.nanmean(ctl >= mu))
            rows.append(dict(feat=cnm, dir=dr, n=int(np.isfinite(r).sum()), mu=mu,
                             pf=D.pf(r), p=p))
    s = pd.DataFrame(rows).sort_values("p")
    s.to_csv("research/vpus30/don_screen.csv", index=False)
    print(f"   control median {np.nanmedian(ctl):.4f}   cells {len(s)}")
    print(f"   clearing p<=0.05: {int((s.p <= 0.05).sum())}  (expected {0.05*len(s):.1f})")
    print(s.head(14).to_string(index=False,
          float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main()
