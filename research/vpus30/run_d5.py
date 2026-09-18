"""The overfitting diagnostic and a DESCRIPTIVE holdout read of the two screen leaders.

The one pre-declared holdout read was spent in run_d4. Everything here is descriptive by
construction and is labelled so; it exists to say WHY the meta layer did not transfer, not to
rescue it.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vpus30 import vpdon as D  # noqa: E402
from vpus30.run_d2 import build_all, EX_N, SL  # noqa: E402

RNG = np.random.default_rng(5150)


def main():
    f, g, cut, X, t, best_d = build_all()
    pool = list(np.load("research/vpus30/don_pool_final.npy", allow_pickle=True))
    ts = pd.DatetimeIndex(t.ts)
    res = np.asarray(ts < cut)
    sig, sd, y = t.sig.to_numpy(), t.side.to_numpy(), t.pct.to_numpy()
    E = X.iloc[sig][pool].reset_index(drop=True)

    rows = []
    for c in pool:
        v = E[c].to_numpy(float)
        a = pd.Series(v[res]).corr(pd.Series(y[res]), method="spearman")
        b = pd.Series(v[~res]).corr(pd.Series(y[~res]), method="spearman")
        rows.append(dict(feat=c, ic_r=a, ic_h=b))
    R = pd.DataFrame(rows).dropna()
    pe = R.ic_r.corr(R.ic_h)
    sp = R.ic_r.corr(R.ic_h, method="spearman")
    sign = float((np.sign(R.ic_r) == np.sign(R.ic_h)).mean())
    print(f"univariate IC across {len(R)} features")
    print(f"  corr(research IC, holdout IC)  Pearson {pe:+.4f}  Spearman {sp:+.4f}")
    print(f"  sign kept {sign:.3f}   (0.50 is a coin flip)")
    print(f"  |IC| research mean {R.ic_r.abs().mean():.4f}  holdout {R.ic_h.abs().mean():.4f}")
    print("\ntop 8 by |research IC|")
    print(R.reindex(R.ic_r.abs().sort_values(ascending=False).index).head(8)
          .to_string(index=False, float_format=lambda x: f"{x:+.4f}"))

    print("\nDESCRIPTIVE (the one pre-declared read is spent): the two screen leaders as vetoes")
    sh, dh = sig[~res], sd[~res]
    base_h, _ = D.walk_at(g, sh, dh, ex_n=EX_N, sl=SL)
    print(f"  base holdout  n {np.isfinite(base_h).sum()}  net% {np.nanmean(base_h):.4f}"
          f"  PF {D.pf(base_h):.3f}")
    for c in ("p_bull", "stack5", "inside_va", "stack20"):
        v = E[c].to_numpy(float)
        thr = np.nanmedian(v[res])
        m = np.isfinite(v[~res]) & (v[~res] > thr)
        if m.sum() < 30:
            print(f"  {c:<11} too few holdout events ({int(m.sum())})"); continue
        r, _ = D.walk_at(g, sh[m], dh[m], ex_n=EX_N, sl=SL)
        ctl = np.empty(300)
        for i in range(300):
            pick = RNG.choice(len(sh), size=int(m.sum()), replace=False)
            q, _ = D.walk_at(g, sh[pick], dh[pick], ex_n=EX_N, sl=SL)
            ctl[i] = np.nanmean(q) if np.isfinite(q).sum() >= 5 else np.nan
        mu = float(np.nanmean(r))
        print(f"  {c:<11} kept {m.mean():.2f}  n {int(np.isfinite(r).sum()):>3}  net% {mu:+.4f}"
              f"  PF {D.pf(r):.3f}  ctl {np.nanmedian(ctl):+.4f}"
              f"  p {float(np.nanmean(ctl >= mu)):.3f}")


if __name__ == "__main__":
    main()
