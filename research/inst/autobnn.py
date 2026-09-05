"""AutoBNN, re-implemented.

Google's AutoBNN (Bayesian neural networks that mirror the Automatic Statistician's compositional
Gaussian-process kernels; TensorFlow Probability, 2024) is not importable here without the full
TensorFlow stack, so its architecture is rebuilt in torch and stated as such:

  LEAF components, each a small Bayesian layer whose features play the role of a GP kernel:
    Linear        f(t) = w . t                       (trend)
    Periodic(p)   f(t) = w . [sin(2 pi k t / p), cos(...)]_k   (seasonality at period p)
    Smooth (RBF)  f(t) = w . exp(-(t - c_j)^2 / 2 l^2)  (random Fourier / basis-function BNN)
    Matern-ish    f(t) = w . exp(-|t - c_j| / l)
  OPERATORS: Sum(f, g), Product(f, g), Changepoint(f, g, tau, slope) = sig((t-tau)/s) g + (1-sig) f.
  A fixed compositional structure is the paper's 'sum of products' default; a small structure
  search is done by picking, on the TRAINING window only, the structure with the best ELBO.
  INFERENCE: mean-field Gaussian variational posterior over every weight (Bayes by backprop),
  Gaussian likelihood with a learned noise scale, the ELBO optimised with Adam. The posterior
  predictive is sampled, so every forecast comes with a standard deviation.

Everything below is causal by construction: a model is fitted on a window that ENDS before the
bar it is asked about, and the target is a forward quantity from that bar."""
from __future__ import annotations
import math, numpy as np, torch, torch.nn as nn, torch.nn.functional as F
torch.set_num_threads(2)


class BayesLinear(nn.Module):
    def __init__(self, d_in, d_out, prior_sd=1.0):
        super().__init__()
        self.mu = nn.Parameter(torch.randn(d_out, d_in) * 0.05)
        self.rho = nn.Parameter(torch.full((d_out, d_in), -4.0))
        self.bmu = nn.Parameter(torch.zeros(d_out)); self.brho = nn.Parameter(torch.full((d_out,), -4.0))
        self.prior_sd = prior_sd
    def sd(self): return F.softplus(self.rho)
    def bsd(self): return F.softplus(self.brho)
    def forward(self, x, sample=True):
        if sample:
            w = self.mu + self.sd() * torch.randn_like(self.mu); b = self.bmu + self.bsd() * torch.randn_like(self.bmu)
        else:
            w, b = self.mu, self.bmu
        return x @ w.T + b
    def kl(self):
        def _kl(mu, sd):
            p = self.prior_sd
            return (torch.log(p / sd) + (sd ** 2 + mu ** 2) / (2 * p ** 2) - 0.5).sum()
        return _kl(self.mu, self.sd()) + _kl(self.bmu, self.bsd())


class Leaf(nn.Module):
    """One kernel-like component of t (normalised to [0,1] over the window) and, optionally, of
    exogenous features x. `kind` in {linear, periodic, rbf, matern}."""
    def __init__(self, kind, period=None, n_basis=16, d_x=0):
        super().__init__(); self.kind = kind; self.period = period; self.n_basis = n_basis; self.d_x = d_x
        if kind == "linear": d = 1
        elif kind == "periodic": d = 2 * n_basis
        else:
            d = n_basis
            self.register_buffer("centres", torch.linspace(0, 1, n_basis))
            self.log_l = nn.Parameter(torch.tensor(math.log(0.15)))
        self.head = BayesLinear(d + d_x, 1)
    def feats(self, t):
        if self.kind == "linear": return t[:, None]
        if self.kind == "periodic":
            k = torch.arange(1, self.n_basis + 1, device=t.device, dtype=t.dtype)
            a = 2 * math.pi * t[:, None] * k[None, :] / self.period
            return torch.cat([torch.sin(a), torch.cos(a)], 1) / math.sqrt(self.n_basis)
        l = torch.exp(self.log_l); d = t[:, None] - self.centres[None, :]
        return torch.exp(-(d ** 2) / (2 * l ** 2)) if self.kind == "rbf" else torch.exp(-d.abs() / l)
    def forward(self, t, x=None, sample=True):
        f = self.feats(t)
        if self.d_x: f = torch.cat([f, x], 1)
        return self.head(f, sample).squeeze(-1)
    def kl(self): return self.head.kl()


class Compose(nn.Module):
    def __init__(self, op, a, b):
        super().__init__(); self.op = op; self.a = a; self.b = b
        if op == "changepoint":
            self.tau = nn.Parameter(torch.tensor(0.5)); self.log_s = nn.Parameter(torch.tensor(math.log(0.05)))
    def forward(self, t, x=None, sample=True):
        fa, fb = self.a(t, x, sample), self.b(t, x, sample)
        if self.op == "sum": return fa + fb
        if self.op == "product": return fa * fb
        g = torch.sigmoid((t - self.tau) / torch.exp(self.log_s)); return (1 - g) * fa + g * fb
    def kl(self): return self.a.kl() + self.b.kl()


def structures(d_x=0, period=26.0):
    """The candidate structures searched on the training window (the paper's small grammar)."""
    L = lambda: Leaf("linear", d_x=d_x); P = lambda: Leaf("periodic", period=period, d_x=d_x)
    R = lambda: Leaf("rbf", d_x=d_x); M = lambda: Leaf("matern", d_x=d_x)
    return {
        "linear": L(), "rbf": R(), "matern": M(),
        "linear+periodic": Compose("sum", L(), P()),
        "linear+rbf": Compose("sum", L(), R()),
        "rbf+periodic": Compose("sum", R(), P()),
        "linear*periodic+rbf": Compose("sum", Compose("product", L(), P()), R()),
        "changepoint(linear,rbf)": Compose("changepoint", L(), R()),
        "sum-of-products": Compose("sum", Compose("product", L(), R()), Compose("product", P(), M())),
    }


class AutoBNN:
    """Fit-by-ELBO structure search + variational training; posterior predictive with samples."""
    def __init__(self, d_x=0, period=26.0, epochs=300, lr=0.02, n_mc=64, seed=0):
        self.d_x, self.period, self.epochs, self.lr, self.n_mc, self.seed = d_x, period, epochs, lr, n_mc, seed
    def _fit_one(self, model, t, x, y):
        torch.manual_seed(self.seed)
        log_noise = nn.Parameter(torch.tensor(math.log(y.std().item() + 1e-6)))
        opt = torch.optim.Adam(list(model.parameters()) + [log_noise], lr=self.lr)
        n = len(y)
        for _ in range(self.epochs):
            opt.zero_grad()
            pred = model(t, x, sample=True)
            nll = 0.5 * ((y - pred) ** 2 / torch.exp(2 * log_noise)).sum() + n * log_noise
            loss = nll + model.kl() / 1.0
            loss.backward(); opt.step()
        with torch.no_grad():
            pred = model(t, x, sample=False)
            elbo = -(0.5 * ((y - pred) ** 2 / torch.exp(2 * log_noise)).sum() + n * log_noise + model.kl())
        return model, log_noise.detach(), float(elbo)
    def fit(self, t, y, x=None):
        t = torch.as_tensor(t, dtype=torch.float32); y = torch.as_tensor(y, dtype=torch.float32)
        x = None if x is None else torch.as_tensor(x, dtype=torch.float32)
        self.ym, self.ys = y.mean(), y.std() + 1e-8
        yn = (y - self.ym) / self.ys
        best = None
        for name, m in structures(self.d_x, self.period).items():
            m, ln, e = self._fit_one(m, t, x, yn)
            if best is None or e > best[2]: best = (name, m, e, ln)
        self.name, self.model, self.elbo, self.log_noise = best
        return self
    def predict(self, t, x=None):
        t = torch.as_tensor(t, dtype=torch.float32); x = None if x is None else torch.as_tensor(x, dtype=torch.float32)
        with torch.no_grad():
            s = torch.stack([self.model(t, x, sample=True) for _ in range(self.n_mc)])
            noise = torch.exp(self.log_noise)
            mu = s.mean(0) * self.ys + self.ym
            sd = torch.sqrt(s.var(0) + noise ** 2) * self.ys
        return mu.numpy(), sd.numpy()
