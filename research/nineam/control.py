"""The matched control: random entries with the same side, geometry and minute-of-day mix.

This is the base rate that counts. It prices in drift, costs, barrier width and session timing at
once, so whatever is left over is the rule rather than the session. CLAUDE.md records what
happened both times this branch ran it as a final check instead of as a gate, so it runs FIRST
here and every headline number is quoted against it.
"""
from __future__ import annotations
import numpy as np
import sim as S


def matched(b, t, stopD, tgtD, flat=960, draws=400, seed=7, block=None):
    """Percentile of the real rule's net P&L within its own matched-random null.

    `block` is a boolean mask over the real trades (research or locked); the control is scored on
    the same sessions so the comparison is within-block.
    """
    mod = b["mod"]; si = b["si"]
    rng = np.random.default_rng(seed)
    if block is None:
        block = np.ones(t["n"], bool)
    sess_ok = np.unique(si[t["eb"][block]])
    in_blk = np.isin(si, sess_ok)

    # pool of eligible bars per (minute of day), restricted to the block's sessions
    want = {}
    for i, s in zip(t["eb"][block], t["side"][block]):
        want[(int(mod[i]), int(s))] = want.get((int(mod[i]), int(s)), 0) + 1
    pools = {}
    for m in {k[0] for k in want}:
        pools[m] = np.flatnonzero(in_blk & (mod == m) & np.isfinite(stopD) & (stopD > 0))

    real = float(t["pnl"][block].sum())
    real_pf = _pf(t["pnl"][block])
    sims = np.empty(draws); simpf = np.empty(draws)
    for dq in range(draws):
        ent = []; sd = []
        for (m, s), k in want.items():
            pool = pools.get(m)
            if pool is None or len(pool) == 0:
                continue
            take = rng.choice(pool, size=min(k, len(pool)), replace=False)
            ent.append(take); sd.append(np.full(len(take), s))
        if not ent:
            sims[dq] = np.nan; simpf[dq] = np.nan; continue
        r = S.run_fixed(b, np.concatenate(ent), np.concatenate(sd), stopD, tgtD, flat=flat)
        sims[dq] = r["pnl"].sum(); simpf[dq] = _pf(r["pnl"])
    good = np.isfinite(sims)
    pct = float(100.0 * (sims[good] < real).mean()) if good.any() else np.nan
    return dict(real=real, real_pf=real_pf, pct=pct,
                p=float((1.0 + (sims[good] >= real).sum()) / (1.0 + good.sum())),
                ctrl_mean=float(np.nanmean(sims)), ctrl_sd=float(np.nanstd(sims)),
                ctrl_pf=float(np.nanmedian(simpf)), draws=int(good.sum()))


def _pf(p):
    w = p[p > 0].sum(); l = -p[p < 0].sum()
    return float(w / l) if l > 0 else np.inf


def mde(p, alpha=0.05, power=0.80):
    """Minimum detectable effect, in $/trade, for this sample size and dispersion.

    An effect smaller than this cannot be resolved by the sample no matter what it reads, which is
    the number that stops a positive point estimate from being read as a finding.
    """
    n = len(p)
    if n < 5:
        return np.nan
    from scipy import stats
    z = stats.norm.ppf(1 - alpha) + stats.norm.ppf(power)
    return float(z * p.std(ddof=1) / np.sqrt(n))
