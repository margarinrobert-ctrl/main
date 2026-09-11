"""THE ANOMALY LAYER: does an UNUSUAL bar move further, and is it a worse bar to trade?

`STUDY_VWANOM` found the one thing that replicated across nine of ten feed x cell x block cells --
an event on an unusual bar is a WORSE event, by autoencoder reconstruction error, Mahalanobis
distance and isolation forest alike, mean rho -0.093, including both reads on a reserved forward
block. It was never tested on US30 and never against a MOVEMENT target. Both are asked here.

FOUR DETECTORS, ALL UNSUPERVISED AND ALL FITTED ON THE RESEARCH BLOCK ONLY -- none of them ever
sees a label, so there is nothing to overfit to an outcome:
    pca      reconstruction error from the research-fitted principal subspace
    maha     Mahalanobis distance to the research-fitted mean and covariance
    iforest  isolation forest, research-fitted
    ae       a small autoencoder (torch), research-fitted, early-stopped on a research split

TWO QUESTIONS, KEPT SEPARATE BECAUSE THEY HAVE DIFFERENT ANSWERS:
  1. MOVEMENT. Does anomaly predict how far and how fast price then travels? Scored with the same
     exact circular-shift null as `run_m1`, on all three blocks.
  2. OUTCOME. Does a trade opened on an anomalous bar do worse? Scored as VWANOM scored it -- a
     rank correlation between the detector and the trade's return, on a Donchian-20 long base with
     a 2 ATR stop, on all three blocks including the different-provider forward feed.

A detector that predicts movement and NOT outcome is a sizing input. One that predicts outcome is a
veto. They are reported separately because conflating them is how a movement forecast gets sold as
an edge.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mv30 import mv30core as C  # noqa: E402
from mr30 import mr30core as M  # noqa: E402
from v67 import v67core as V67  # noqa: E402
from mv30.run_m1 import zrank, ic_all_shifts, EXCL  # noqa: E402


def clean(X, med=None):
    A = X.to_numpy(float).copy()
    if med is None:
        med = np.nanmedian(A, axis=0)
    ix = np.where(~np.isfinite(A))
    A[ix] = np.take(med, ix[1])
    return A, med


def detectors(X, fitmask, seed=0):
    """All four, fitted on `fitmask` rows only, scored everywhere. Higher = more unusual."""
    from sklearn.decomposition import PCA
    from sklearn.ensemble import IsolationForest
    A, med = clean(X)
    mu = A[fitmask].mean(0); sd = A[fitmask].std(0); sd[sd <= 0] = 1.0
    Z = (A - mu) / sd
    Z = np.clip(Z, -8, 8)
    F = Z[fitmask]
    out = {}
    p = PCA(n_components=12, random_state=seed).fit(F)
    out["pca"] = np.sqrt(((Z - p.inverse_transform(p.transform(Z))) ** 2).sum(1))
    cov = np.cov(F.T) + 1e-6 * np.eye(F.shape[1])
    ic_ = np.linalg.pinv(cov)
    d = Z - F.mean(0)
    out["maha"] = np.sqrt(np.einsum("ij,jk,ik->i", d, ic_, d))
    sub = np.flatnonzero(fitmask)
    rng = np.random.default_rng(seed)
    sub = rng.choice(sub, size=min(40000, len(sub)), replace=False)
    iso = IsolationForest(n_estimators=200, random_state=seed, n_jobs=2).fit(Z[sub])
    out["iforest"] = -iso.score_samples(Z)
    out["ae"] = _autoenc(Z, fitmask, seed)
    return out


def _autoenc(Z, fitmask, seed):
    import torch
    torch.manual_seed(seed); torch.set_num_threads(4)
    F = torch.tensor(Z[fitmask], dtype=torch.float32)
    n_in = F.shape[1]
    net = torch.nn.Sequential(torch.nn.Linear(n_in, 32), torch.nn.ReLU(),
                              torch.nn.Linear(32, 8), torch.nn.ReLU(),
                              torch.nn.Linear(8, 32), torch.nn.ReLU(),
                              torch.nn.Linear(32, n_in))
    opt = torch.optim.Adam(net.parameters(), lr=1e-3)
    cut = int(len(F) * 0.85)
    tr, va = F[:cut], F[cut:]
    best, bad, bw = 1e18, 0, None
    for ep in range(40):
        perm = torch.randperm(len(tr))
        for i in range(0, len(tr), 4096):
            b = tr[perm[i:i + 4096]]
            opt.zero_grad()
            loss = ((net(b) - b) ** 2).mean()
            loss.backward(); opt.step()
        with torch.no_grad():
            v = float(((net(va) - va) ** 2).mean())
        if v < best - 1e-5:
            best, bad = v, 0
            bw = {k: p.detach().clone() for k, p in net.state_dict().items()}
        else:
            bad += 1
            if bad >= 5:
                break
    if bw is not None:
        net.load_state_dict(bw)
    with torch.no_grad():
        Zt = torch.tensor(Z, dtype=torch.float32)
        return ((net(Zt) - Zt) ** 2).sum(1).numpy()


def donchian_long(f, n=20):
    h, c = f["high"].to_numpy(), f["close"].to_numpy()
    ch = pd.Series(h).rolling(n).max().shift(1).to_numpy()
    sig = np.flatnonzero(np.isfinite(ch) & (c > ch))
    sig = sig[(sig > 800) & (sig < len(c) - 2)]
    return sig, np.ones(len(sig), np.int64)


def main():
    print("Fitting four unsupervised detectors on the US30L RESEARCH block only.\n")
    fL = C.frame("US30L"); XL = C.features(fL); bL = M.blocks(fL)
    det = detectors(XL, bL["A_research"])
    fI = C.frame("US30I"); XI = C.features(fI); bI = M.blocks(fI, "US30I")
    _, medL = clean(XL)
    detI = detectors(pd.concat([XL, XI]), np.r_[bL["A_research"],
                                                np.zeros(len(XI), bool)])
    detI = {k: v[len(XL):] for k, v in detI.items()}

    print("1. DOES ANOMALY PREDICT MOVEMENT? (Spearman IC, exact circular-shift null)")
    D = C.D_of(fL)
    print(f"  {'detector':<10}{'target':<7}{'h':>4}{'block':<12}{'IC':>9}{'p95':>9}{'p':>8}")
    for h in (16, 48):
        T = V67.build_targets(D, h)
        for t in ("rng", "rv", "ttb", "mae"):
            for k in ("pca", "ae"):
                for bn, mask in bL.items():
                    y = T[t]
                    m = mask & np.isfinite(y) & np.isfinite(det[k])
                    idx = np.flatnonzero(m)
                    idx = idx[idx >= 800]
                    if len(idx) < 5000:
                        continue
                    xz = zrank(det[k][idx]); yz = zrank(y[idx])
                    obs = abs(float((xz @ yz) / len(yz)))
                    null = ic_all_shifts(xz[:, None], yz)
                    ok = np.ones(len(null), bool); ok[:EXCL] = False; ok[-EXCL:] = False
                    print(f"  {k:<10}{t:<7}{h:>4}{bn:<12}{obs:>9.4f}"
                          f"{np.percentile(null[ok], 95):>9.4f}"
                          f"{float(np.mean(null[ok] >= obs)):>8.4f}")
        print()

    print("2. DOES AN ANOMALOUS BAR MAKE A WORSE TRADE? (VWANOM's question, US30)")
    print("   Donchian-20 long, 2 ATR stop, no target, 96-bar cap. rho(detector, trade %) --")
    print("   VWANOM found NEGATIVE in 9 of 10 cells, mean -0.093.")
    print(f"\n  {'detector':<10}{'block':<12}{'n':>7}{'rho':>9}{'p (shift)':>11}"
          f"{'top-25% mean':>14}{'bot-75% mean':>14}")
    neg = tot = 0
    for feed, fr, bb, dd in (("US30L", fL, bL, det), ("US30I", fI, bI, detI)):
        sig, side = donchian_long(fr)
        tr = M.walk(fr, sig, side, stop_a=2.0, tgt_a=100.0, hold=96)
        sb = tr.e_bar.to_numpy() - 1
        for bn, mask in bb.items():
            sel = np.array([bool(mask[i]) for i in sb])
            if sel.sum() < 80:
                continue
            for k in dd:
                a = dd[k][sb][sel]
                r = tr.pct.to_numpy()[sel]
                m = np.isfinite(a) & np.isfinite(r)
                if m.sum() < 80:
                    continue
                rho = float(np.corrcoef(pd.Series(a[m]).rank(), pd.Series(r[m]).rank())[0, 1])
                q = np.quantile(a[m], 0.75)
                hi_ = r[m][a[m] >= q].mean(); lo_ = r[m][a[m] < q].mean()
                rng_ = np.random.default_rng(7)
                nul = np.array([float(np.corrcoef(pd.Series(np.roll(a[m], int(rng_.integers(
                    20, len(a[m]) - 20)))).rank(), pd.Series(r[m]).rank())[0, 1])
                    for _ in range(400)])
                p = float(np.mean(nul <= rho))
                neg += int(rho < 0); tot += 1
                print(f"  {k:<10}{feed + ' ' + bn[0]:<12}{int(m.sum()):>7}{rho:>9.4f}"
                      f"{p:>11.3f}{hi_:>14.4f}{lo_:>14.4f}")
        print()
    print(f"  NEGATIVE in {neg} of {tot} cells (VWANOM: 9 of 10)")


if __name__ == "__main__":
    main()
