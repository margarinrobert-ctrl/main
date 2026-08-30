"""Deep uncertainty for the breakout filter: a heteroscedastic deep ensemble with MC dropout.

WHAT THIS IS FOR, AND WHAT IT IS NOT FOR
----------------------------------------
`docs/ib/STUDY_FEATURES.md` measured 1,072 IC tests on this instrument and found ONE feature
surviving FDR, worth 0.28 ticks against a 6.0-tick round turn. So a network asked to predict the
NEXT MOVE here will not find one, and this module does not ask it to. It is asked for the SECOND
moment: how dispersed is the outcome, and how much of that dispersion is the model admitting it
has never seen this state before.

That is a much easier target -- volatility is the most forecastable thing in a price series -- and
it is directly tradeable through geometry rather than through direction:

    aleatoric   irreducible spread of the outcome given the state.  Sets the STOP and the TARGET.
    epistemic   disagreement between models that fit the same data.  Sets the VETO and the SIZE.

The regression head still emits a mean, and the classification head still emits P(target before
stop). Both are used, but neither is allowed to carry the strategy on its own: the gates in
`dbu.py` require the Donchian trigger AND the BVAR density AND the uncertainty state, and the
sizing formula is driven by the variance, not by the mean.

THE DECOMPOSITION
-----------------
For an ensemble of M members, each evaluated with K MC-dropout passes, on a Gaussian head:

    mu_bar    = mean_{m,k} mu_{m,k}
    aleatoric = mean_{m,k} sigma^2_{m,k}          (what each model says is irreducible)
    epistemic = var_{m,k}  mu_{m,k}               (how much the models disagree about the mean)

This is the standard law-of-total-variance split (Kendall & Gal 2017; Lakshminarayanan 2017). Two
practical cautions that matter more than the architecture:

  * a deep ensemble's epistemic term is a LOWER bound and it is only meaningful if the members
    differ in initialisation AND in data order AND in bootstrap resample. All three are on here.
  * epistemic uncertainty on a walk-forward fold measures distance from the TRAINING window, which
    is exactly the regime-shift detector you want, and exactly why the model must be refit on a
    schedule (see `dbu.py: WF`) rather than once.

LEAKAGE
-------
Features are read at the SIGNAL bar; labels resolve over the following h bars. Neighbouring
samples therefore share up to h bars of outcome, so folds are PURGED by h bars and EMBARGOED by
another h. Without that, validation loss is optimistic by a wide margin and the calibration step
below would be calibrating on its own training set. `selftest()` asserts the purge is applied.
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import torch
    import torch.nn as nn
    HAVE_TORCH = True
except Exception:                                     # pragma: no cover
    HAVE_TORCH = False
    torch = None
    nn = object


# ===================================================================== the network
if HAVE_TORCH:

    class HeteroMLP(nn.Module):
        """Two heads on a shared trunk: Gaussian (mu, log var) and a barrier probability.

        Dropout is applied at every hidden layer and is left ON at inference -- that is the MC
        dropout part. `nn.GELU` rather than ReLU because the variance head benefits from a smooth
        activation; the difference is small and this is not where the edge is.
        """

        def __init__(self, n_in, width=64, depth=2, p_drop=0.15):
            super().__init__()
            layers, d = [], n_in
            for _ in range(depth):
                layers += [nn.Linear(d, width), nn.GELU(), nn.Dropout(p_drop)]
                d = width
            self.trunk = nn.Sequential(*layers)
            self.mu = nn.Linear(d, 1)
            self.logvar = nn.Linear(d, 1)
            self.logit = nn.Linear(d, 1)
            nn.init.zeros_(self.logvar.bias)

        def forward(self, x):
            z = self.trunk(x)
            # clamp keeps the NLL finite when a member collapses on a small fold
            return self.mu(z).squeeze(-1), self.logvar(z).squeeze(-1).clamp(-8.0, 8.0), \
                self.logit(z).squeeze(-1)

    def gaussian_nll(mu, logvar, y):
        """Beta-free Gaussian NLL. The variance term is what teaches the model to say 'unsure'."""
        return 0.5 * (logvar + (y - mu) ** 2 * torch.exp(-logvar)).mean()


@dataclass
class UQCfg:
    members: int = 5             # ensemble size. 5 is the knee; 10 buys ~nothing here
    mc: int = 20                 # MC-dropout passes per member at inference
    width: int = 64
    depth: int = 2
    p_drop: float = 0.15
    epochs: int = 60
    batch: int = 256
    lr: float = 1e-3
    wd: float = 1e-4             # weight decay is the prior; do not set it to 0
    bootstrap: float = 0.8       # per-member resample fraction, for genuine member diversity
    lam_cls: float = 0.5         # weight on the barrier-classification loss
    patience: int = 8
    seed: int = 17


# ===================================================================== fitting
def _standardise(Xtr, X):
    mu = np.nanmean(Xtr, 0); sd = np.nanstd(Xtr, 0)
    sd = np.where(sd > 1e-9, sd, 1.0)
    return (np.nan_to_num(X - mu) / sd).astype(np.float32)


def fit_ensemble(X, y, lab, cfg: UQCfg = UQCfg(), val_frac=0.15, verbose=False):
    """Train `cfg.members` heteroscedastic nets on (X -> y, lab).

    y    continuous outcome, in R units or ticks. Use the SAME quantity the strategy is paid in.
    lab  1 if the trade would have hit its target before its stop, else 0. Take it from the
         simulator, not from a hand-rolled forward return -- the barrier order is the label.

    The last `val_frac` of the (already time-ordered) rows is held out for early stopping and for
    the temperature calibration. It is contiguous and at the END, never random: a random split
    leaks the future through overlapping labels.
    """
    if not HAVE_TORCH:
        raise RuntimeError("uq_net needs pytorch: pip install torch")
    X = np.asarray(X, float); y = np.asarray(y, float); lab = np.asarray(lab, float)
    n = len(X); nv = max(int(val_frac * n), 64)
    tr, va = slice(0, n - nv), slice(n - nv, n)
    Xtr = X[tr]
    Xs = _standardise(Xtr, X)
    ysd = max(float(np.std(y[tr])), 1e-6); ymu = float(np.mean(y[tr]))
    yn = ((y - ymu) / ysd).astype(np.float32)
    models, hist = [], []
    for m in range(cfg.members):
        g = torch.Generator().manual_seed(cfg.seed + 1000 * m)
        torch.manual_seed(cfg.seed + 1000 * m)
        rng = np.random.default_rng(cfg.seed + 1000 * m)
        idx = rng.choice(np.arange(n - nv), size=int(cfg.bootstrap * (n - nv)), replace=True)
        net = HeteroMLP(X.shape[1], cfg.width, cfg.depth, cfg.p_drop)
        opt = torch.optim.AdamW(net.parameters(), lr=cfg.lr, weight_decay=cfg.wd)
        xb_all = torch.tensor(Xs[idx]); yb_all = torch.tensor(yn[idx])
        lb_all = torch.tensor(lab[idx].astype(np.float32))
        xv = torch.tensor(Xs[va]); yv = torch.tensor(yn[va])
        lv = torch.tensor(lab[va].astype(np.float32))
        bce = nn.BCEWithLogitsLoss()
        best, best_state, bad = math.inf, None, 0
        for ep in range(cfg.epochs):
            net.train()
            perm = torch.randperm(len(xb_all), generator=g)
            for i in range(0, len(perm), cfg.batch):
                j = perm[i:i + cfg.batch]
                mu, lv_, lg = net(xb_all[j])
                loss = gaussian_nll(mu, lv_, yb_all[j]) + cfg.lam_cls * bce(lg, lb_all[j])
                opt.zero_grad(); loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), 5.0)
                opt.step()
            net.eval()
            with torch.no_grad():
                mu, lvv, lg = net(xv)
                v = float(gaussian_nll(mu, lvv, yv) + cfg.lam_cls * bce(lg, lv))
            if v < best - 1e-4:
                best, bad = v, 0
                best_state = {k: t.detach().clone() for k, t in net.state_dict().items()}
            else:
                bad += 1
                if bad >= cfg.patience:
                    break
        if best_state is not None:
            net.load_state_dict(best_state)
        models.append(net); hist.append(best)
        if verbose:
            print(f"    member {m}: val {best:.4f} after {ep + 1} epochs")
    scaler = dict(mu=np.nanmean(Xtr, 0), sd=np.where(np.nanstd(Xtr, 0) > 1e-9,
                                                     np.nanstd(Xtr, 0), 1.0),
                  ymu=ymu, ysd=ysd)
    ens = dict(models=models, scaler=scaler, cfg=cfg, val_nll=hist, temp=1.0)
    ens["temp"] = calibrate(ens, X[va], lab[va])
    return ens


def calibrate(ens, Xva, lab_va, grid=None):
    """Temperature scaling on the held-out tail. An uncalibrated P(win) is not a probability, and
    the sizing formula divides by it -- so this is not optional."""
    p = predict(ens, Xva, temp=1.0)["p_up"]
    p = np.clip(p, 1e-6, 1 - 1e-6)
    lg = np.log(p / (1 - p))
    best, bt = math.inf, 1.0
    for t in (grid if grid is not None else np.linspace(0.4, 3.0, 27)):
        q = 1.0 / (1.0 + np.exp(-lg / t))
        nll = -np.mean(lab_va * np.log(q) + (1 - lab_va) * np.log(1 - q))
        if nll < best:
            best, bt = nll, float(t)
    return bt


# ===================================================================== inference
def predict(ens, X, temp=None, batch=8192):
    """Per-row mu, aleatoric sd, epistemic sd, P(win) and its ensemble spread.

    All returned in the units of the training target `y` (ticks or R), not in standardised units.
    """
    if not HAVE_TORCH:
        raise RuntimeError("uq_net needs pytorch: pip install torch")
    cfg = ens["cfg"]; sc = ens["scaler"]
    t = ens.get("temp", 1.0) if temp is None else temp
    Xs = ((np.nan_to_num(np.asarray(X, float) - sc["mu"])) / sc["sd"]).astype(np.float32)
    n = len(Xs)
    MU = np.empty((cfg.members * cfg.mc, n), np.float32)
    VA = np.empty_like(MU)
    PR = np.empty_like(MU)
    r = 0
    for net in ens["models"]:
        net.train()                       # dropout ON: this is the MC part, not a bug
        for _ in range(cfg.mc):
            outs = []
            with torch.no_grad():
                for i in range(0, n, batch):
                    mu, lv, lg = net(torch.tensor(Xs[i:i + batch]))
                    outs.append((mu.numpy(), lv.numpy(), lg.numpy()))
            MU[r] = np.concatenate([o[0] for o in outs])
            VA[r] = np.exp(np.concatenate([o[1] for o in outs]))
            PR[r] = 1.0 / (1.0 + np.exp(-np.concatenate([o[2] for o in outs]) / t))
            r += 1
    ysd = sc["ysd"]; ymu = sc["ymu"]
    mu = MU.mean(0) * ysd + ymu
    alea = np.sqrt(VA.mean(0)) * ysd
    epi = MU.std(0) * ysd
    p_up = PR.mean(0)
    p_epi = PR.std(0)
    return dict(mu=mu, sd_alea=alea, sd_epi=epi, sd=np.sqrt(alea ** 2 + epi ** 2),
                p_up=p_up, p_epi=p_epi)


def ece(p, lab, bins=10):
    """Expected calibration error -- report it beside every P(win) or do not quote the P(win)."""
    p = np.asarray(p, float); lab = np.asarray(lab, float)
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    edges[0] -= 1e-9; edges[-1] += 1e-9
    e, tot = 0.0, len(p)
    for i in range(bins):
        m = (p > edges[i]) & (p <= edges[i + 1])
        if m.sum() > 0:
            e += m.sum() / tot * abs(p[m].mean() - lab[m].mean())
    return float(e)


# ===================================================================== purged walk-forward
def purged_folds(n, folds=6, h=6, embargo=None):
    """Contiguous expanding-window folds with a purge and an embargo of h bars each.

    Yields (train_idx, test_idx). The purge removes the h rows before the test block, whose labels
    overlap it; the embargo removes the h rows after, which matters when the window is rolling
    rather than expanding.
    """
    emb = h if embargo is None else embargo
    edges = np.linspace(0, n, folds + 2).astype(int)
    for f in range(1, folds + 1):
        te0, te1 = edges[f], edges[f + 1]
        tr = np.arange(0, max(te0 - h, 0))
        te = np.arange(te0, te1)
        yield tr, te, emb


def walk_forward(X, y, lab, cfg: UQCfg = UQCfg(), folds=6, h=6, min_train=2000, verbose=False):
    """Out-of-sample uncertainty estimates for every row a fold can reach.

    Returns the same dict as `predict`, with NaN wherever no fold had enough history. These arrays
    are the ONLY ones that may be used to make a trading decision -- the in-sample fit of a model
    with this many parameters says nothing.
    """
    n = len(X)
    out = {k: np.full(n, np.nan) for k in
           ("mu", "sd_alea", "sd_epi", "sd", "p_up", "p_epi")}
    for tr, te, _ in purged_folds(n, folds, h):
        if len(tr) < min_train:
            continue
        ens = fit_ensemble(X[tr], y[tr], lab[tr], cfg, verbose=verbose)
        pr = predict(ens, X[te])
        for k in out:
            out[k][te] = pr[k]
        if verbose:
            m = np.isfinite(lab[te])
            print(f"  fold train {len(tr):>6,} test {len(te):>6,}  "
                  f"ECE {ece(pr['p_up'][m], lab[te][m]):.3f}")
    return out


# ===================================================================== self-test
def selftest(n=6000, seed=4, quick=True):
    """A synthetic world where the true uncertainty is known, so the split can be checked.

    x1 drives the mean, x2 drives the NOISE, and the last quarter of the sample is drawn from a
    region of x-space the training window never saw. A working decomposition must (a) have its
    aleatoric term track x2, and (b) have its epistemic term rise in the unseen region.
    """
    if not HAVE_TORCH:
        return {"skipped": "pytorch not installed"}
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n); x2 = rng.uniform(-1, 1, n); x3 = rng.normal(size=n)
    shift = np.zeros(n); shift[int(0.75 * n):] = 4.0            # the regime the model never saw
    x1 = x1 + shift
    noise = 0.3 + 1.7 * (x2 > 0.3)                              # heteroscedastic by construction
    y = 0.8 * np.tanh(x1 - shift) + noise * rng.normal(size=n)
    lab = (y > 0).astype(float)
    X = np.column_stack([x1, x2, x3])
    cfg = UQCfg(members=3, mc=8, epochs=25 if quick else 80, seed=seed)
    k = int(0.6 * n)
    ens = fit_ensemble(X[:k], y[:k], lab[:k], cfg)
    pr = predict(ens, X)

    seen = slice(k, int(0.75 * n))                              # in-distribution, out-of-sample
    unseen = slice(int(0.75 * n), n)                            # covariate shift
    a_lo = np.nanmean(pr["sd_alea"][:k][x2[:k] <= 0.3])
    a_hi = np.nanmean(pr["sd_alea"][:k][x2[:k] > 0.3])
    e_seen = np.nanmean(pr["sd_epi"][seen])
    e_unseen = np.nanmean(pr["sd_epi"][unseen])
    assert a_hi > 1.6 * a_lo, f"aleatoric did not track the noise: {a_lo:.2f} vs {a_hi:.2f}"
    assert e_unseen > 1.5 * e_seen, \
        f"epistemic did not rise off-distribution: {e_seen:.3f} vs {e_unseen:.3f}"

    # the purge must actually remove the overlapping rows
    for tr, te, emb in purged_folds(1000, 4, h=10):
        if len(tr):
            assert te[0] - tr[-1] > 10, "purge gap missing"
    cal = ece(pr["p_up"][seen], lab[seen])
    return dict(alea_low=float(a_lo), alea_high=float(a_hi), epi_seen=float(e_seen),
                epi_unseen=float(e_unseen), ece_oos=float(cal), temp=ens["temp"])


if __name__ == "__main__":
    print("uq_net selftest:", selftest())
