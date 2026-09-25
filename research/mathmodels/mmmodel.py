"""THE MODEL, frozen: an 8-state LightGBM veto on a 60m Donchian 30/20 + EMA200 trend primary.

This is the best object `docs/ib/STUDY_MATH_MODELS.md` produced, and it SHIPS NOTHING -- read the
verdict before using it. Holdout: PF 1.065 -> 1.334 and total return 4.70 -> 9.35 on 41% of the
trades, p90 of R rising so the tail survives, decaying the right way across the split -- and
p 0.158 against a random gate of the same size, calibration drifting to 0.410 against the 0.30 it
was set for, and a deflated Sharpe of 0.471 at 80 counted looks, which is BELOW the expected
best-of-noise of its own search (0.0929 against 0.0996). Gate 1 was never cleared either: the
primary alone reads p 0.167 against a risk-matched random entry.

THERE IS NO PINE VERSION AND THAT IS NOT AN OVERSIGHT. A gradient booster cannot be written into
Pine, and the portable RIDGE form -- which beat the forest in STUDY_V66 -- is strictly worse here:
holdout IC -0.0122, PF 1.054, p 0.453. The lean 3-state models the drop-one pointed at are worse
still (lgbm-3 holdout PF 0.894). So the only form worth handing over is this one, in Python.

USAGE
    m = MathVetoModel().fit()            # fits on the research block only
    m.report()                           # reproduces the published table
    take = m.should_take(state_row)      # True if this event survives the veto
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mathmodels import mmcore as M
from mathmodels.run_m2 import walk, walk_at, chan, COST

# ---- the frozen configuration. Every number was fixed before the holdout was opened.
MARKET, TF = "US30L", 60
ENTRY_CH, EXIT_CH, EMA_LEN, STOP_N = 30, 20, 200, 2.0
STATE_WINDOW = 500
KEEP = 0.30
FEATURES = ["ou.kappa", "ou.halflife", "ou.z", "dfa.H", "vr.ratio", "bns.share", "pe.h", "kf.t"]
# `vr.z` and `bns.z` are EXCLUDED: they are near-duplicates of vr.ratio and bns.share on the signal
# bars (rho 0.958 / 0.959), the eighth pool-duplication catch on this branch.

PARAMS = dict(n_estimators=250, num_leaves=7, learning_rate=0.03, min_child_samples=30,
              subsample=0.8, colsample_bytree=0.7, verbose=-1, n_jobs=4)


def purged_folds(n, k=5, embargo=30):
    """Trades occupy [signal, exit] and those windows overlap, so a plain K-fold trains on the
    answer. Rows adjacent to each test fold are removed from training."""
    edges = np.linspace(0, n, k + 1).astype(int)
    for i in range(k):
        te = np.arange(edges[i], edges[i + 1])
        tr = np.setdiff1d(np.arange(n),
                          np.arange(max(0, te[0] - embargo), min(n, te[-1] + embargo + 1)))
        yield tr, te


class MathVetoModel:
    def __init__(self, market=MARKET, tf=TF):
        self.market, self.tf = market, tf
        self.model = self.scaler = self.threshold = None

    # ------------------------------------------------------------------ data
    def build(self):
        """Bars -> primary events -> the eight mathematical states at each SIGNAL bar."""
        f = M.load(self.market, self.tf)
        sess = np.unique(f.index.normalize())
        cut = pd.Timestamp(sess[int(0.75 * len(sess))])
        o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
        atr = f["atr"].to_numpy()
        ehi, elo = chan(h, l, ENTRY_CH)
        xhi, xlo = chan(h, l, EXIT_CH)
        ema = pd.Series(c).ewm(span=EMA_LEN, adjust=False).mean().to_numpy()
        ok_up = (c > ema).astype(np.int64)
        ok_dn = (c < ema).astype(np.int64)

        ent_bar, ret, side, hold = walk(o, h, l, c, atr, ehi, elo, xhi, xlo,
                                        ok_up, ok_dn, STOP_N, COST)
        sig_bar = ent_bar - 1                      # the SIGNAL bar. Never read state at the fill.
        states = M.states(f, STATE_WINDOW)
        X = states.iloc[sig_bar][FEATURES].to_numpy(float)

        self.f, self.cut = f, cut
        self.px = (o, h, l, c, atr, xhi, xlo)
        self.sig, self.side, self.ret = sig_bar, side, ret
        self.ts = f.index[ent_bar]
        self.res = np.asarray(self.ts < cut)
        self.median = np.nanmedian(X[self.res], axis=0)      # research-only imputation
        self.X = np.where(np.isfinite(X), X, self.median)
        return self

    # ------------------------------------------------------------------ fit
    def fit(self):
        if self.model is None and not hasattr(self, "X"):
            self.build()
        Xr, yr = self.X[self.res], self.ret[self.res]

        # out-of-fold predictions set the threshold; the fitted model is trained on all of research
        oof = np.full(len(yr), np.nan)
        sc = StandardScaler()
        for tr, te in purged_folds(len(yr)):
            m = lgb.LGBMRegressor(**PARAMS)
            m.fit(sc.fit_transform(Xr[tr]), yr[tr])
            oof[te] = m.predict(sc.transform(Xr[te]))
        self.oof = oof
        self.threshold = float(np.nanquantile(oof, 1.0 - KEEP))

        self.scaler = StandardScaler().fit(Xr)
        self.model = lgb.LGBMRegressor(**PARAMS).fit(self.scaler.transform(Xr), yr)
        return self

    # ------------------------------------------------------------------ use
    def score(self, X):
        X = np.atleast_2d(np.asarray(X, float))
        X = np.where(np.isfinite(X), X, self.median)
        return self.model.predict(self.scaler.transform(X))

    def should_take(self, X):
        """True where the event survives the veto. A filter is a VETO, not a subset: refusing a
        signal releases the position lock and admits a later one, so anything scored this way must
        be RE-SIMULATED, never split out of an existing trade list."""
        return self.score(X) >= self.threshold

    # ------------------------------------------------------------------ verify
    def _sim(self, mask, block):
        o, h, l, c, atr, xhi, xlo = self.px
        sel = self.res if block == "research" else ~self.res
        s, d = self.sig[sel], self.side[sel]
        if mask is not None:
            s, d = s[mask], d[mask]
        return walk_at(o, h, l, c, atr, xhi, xlo, s.astype(np.int64), d.astype(np.int64),
                       STOP_N, COST)

    def report(self, seed=4242, draws=400):
        rng = np.random.default_rng(seed)
        m_res = self.oof >= self.threshold
        m_hol = self.score(self.X[~self.res]) >= self.threshold
        print(f"{self.tf}m Donchian {ENTRY_CH}/{EXIT_CH} + EMA{EMA_LEN} state + {STOP_N}N, "
              f"{self.market}, keep {KEEP:.0%}")
        print(f"{'':22}{'n':>6}{'%/trade':>9}{'PF':>7}{'total':>9}{'p90':>7}{'ctl':>9}{'p':>7}")
        for tag, mask, blk in (("research base", None, "research"),
                               ("research kept", m_res, "research"),
                               ("HOLDOUT base", None, "holdout"),
                               ("HOLDOUT kept", m_hol, "holdout")):
            r = self._sim(mask, blk)
            ctl = np.nan; p = np.nan
            if mask is not None:
                sel = self.res if blk == "research" else ~self.res
                n = int(np.isfinite(r).sum())
                draws_ = np.empty(draws)
                for i in range(draws):
                    pick = np.sort(rng.choice(int(sel.sum()), size=n, replace=False))
                    mm = np.zeros(int(sel.sum()), bool); mm[pick] = True
                    draws_[i] = np.nanmean(self._sim(mm, blk))
                ctl = float(np.nanmedian(draws_))
                p = float(np.mean(draws_ >= np.nanmean(r)))
            print(f"{tag:<22}{int(np.isfinite(r).sum()):>6}{np.nanmean(r):>9.4f}"
                  f"{M.pf(r):>7.3f}{np.nansum(r):>9.2f}"
                  f"{np.nanpercentile(r[np.isfinite(r)], 90):>7.3f}{ctl:>9.4f}{p:>7.3f}")
        print(f"  calibration: holdout kept {m_hol.mean():.3f} against the {KEEP:.2f} it was set for")
        print("  VERDICT: does not clear. Gate 1 p 0.167, holdout gate p ~0.16, "
              "deflated Sharpe 0.471 at 80 looks -- below its own noise floor.")


if __name__ == "__main__":
    MathVetoModel().fit().report()
