"""US30 mean reversion as a PRIMARY, built mechanism-first. Phase 0 is written here, before code.

WHY THIS AND NOT ANOTHER BREAKOUT. Every US30 primary this branch has tested is a trend or
breakout object -- Donchian (eight separate failures against a random entry), the Initial Balance,
the VWAP-EMA spec, the Strat, the opening range, the volume-profile setups -- while the same branch
has now reached MEAN REVERSION by twelve independent routes: `STUDY_V47`'s momentum premium is
reversal on both blocks and monotone in horizon; `STUDY_V13`'s every price-vs-MA feature is
mean-reverting at h=1; ridge's largest coefficient is RSI14 NEGATIVE in three separate ML studies;
`research/atme/`'s entry-mechanic response is a monotone mirror image with buying dips improving and
chasing degrading; `STUDY_V43`'s breakout takes MORE adverse excursion than a random bar. The gap in
the record is therefore not another filter on a breakout -- it is the primary those twelve readings
imply, tested head-on on this market with a control in front.

PHASE 0 -- THE COUNTERPARTY.
  Family: RISK TRANSFER, not constrained flow. When price travels several ATR away from where it was
  a few bars ago, the participants on the wrong side of that move are leveraged intraday accounts
  whose stops are being run and hedgers who must re-hedge NOW. They are not choosing the moment; the
  move chooses it for them. Whoever takes the other side is paid to hold inventory across the
  reversal, and is paid precisely because that inventory can keep going against them -- which is the
  signature of a risk premium rather than an arbitrage, and predicts NEGATIVE SKEW: many small wins,
  occasional large losses. If this primary works and its skew is positive, the mechanism story is
  wrong even if the p-value is not.
  Why it cannot be arbitraged away: absorbing a fast displacement requires capital and the
  willingness to be wrong for a while. That is a capacity limit, not an information edge.
  What would end it: a market where that inventory risk is cheaper to hold, i.e. tighter spreads and
  deeper books -- so the effect should be SMALLER in the later block, not larger.

THE PRIMARY. Displacement d = (close - close[n]) / ATR(14), read at the SIGNAL bar and known there.
  Event: |d| >= k.  Side: -sign(d), FORCED by the mechanism -- no fitted direction, and the sign
  flip is run as the arm that must fail. Entry at the next open. One live position (`STUDY_V34`).

THE MECHANISM'S OWN PREDICTION, which is the decisive test and not the p-value. Flow is proportional
to the size of the displacement, so the reversal must be LARGER where |d| is larger. If the quintile
gradient runs the other way -- as the levered-ETF primary's did in `STUDY_LEV_ETF_REBALANCE` -- the
conditioning variable is contradicting the mechanism and the family is dead however it scores.

DECLARED GRID for Gate 1, research block only, counted as trials:
  n in {2, 4, 8, 16} x k in {1.5, 2.5} x two geometries = 16 cells.
  Geometries are chosen by the mechanism rather than searched: SYM (1.5 ATR stop, 1.5 ATR target)
  and REV (3.0 ATR stop, 1.0 ATR target), the shape a reversion trade actually has. Both have their
  driftless break-even printed beside their win rate, because on this branch a win rate has meant
  nothing without it four separate times.

BLOCKS. A = first 70% of US30L sessions, B = the rest, C = US30_ISO after US30L ends -- a DIFFERENT
PROVIDER over a span no search here has touched.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from numba import njit

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research"))
from v38 import v38feeds as F  # noqa: E402

COST = 2.29          # US30 round turn in index points (broker + exchange + slippage)
PV = 5.0             # $ per point, US30 CFD / YM
CUT_A = "2023-01-01"  # ~70% of the US30L sessions
ISO_FROM = "2025-07-16"


def load(name="US30L", tf=15):
    # `v38feeds.load` reads the ISO file expecting a capitalised `Volume`; the column on disk is
    # lowercase, so that path raises. Read it here rather than patching a module three published
    # studies import.
    if name == "US30I":
        d = pd.read_csv(os.path.join(ROOT, "data/US30_ISO_15m.csv"), parse_dates=["ny"])
        f = pd.DataFrame({c: d[c].to_numpy(float) for c in
                          ("open", "high", "low", "close", "volume")}, index=d["ny"])
        f = f.sort_index()
        f = f[~f.index.duplicated(keep="first")]
    else:
        f = F.load(name)[["open", "high", "low", "close", "volume"]]
    if tf != 15:
        f = f.resample(f"{tf}min").agg(dict(open="first", high="max", low="min",
                                            close="last", volume="sum")).dropna()
    f = f.copy()
    h, l, c = f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy()
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    f["atr"] = pd.Series(tr).ewm(span=14, adjust=False).mean().to_numpy()
    f["mod"] = f.index.hour * 60 + f.index.minute
    return f


def blocks(f, name="US30L"):
    if name == "US30I":
        return {"C_forward": np.asarray(f.index >= ISO_FROM)}
    ix = np.asarray(f.index < CUT_A)
    return {"A_research": ix, "B_holdout": ~ix}


def displacement(f, n):
    """d = (close - close[n]) / ATR(14), causal at the signal bar."""
    c = f["close"].to_numpy()
    at = f["atr"].to_numpy()
    prev = np.r_[np.full(n, np.nan), c[:-n]]
    with np.errstate(invalid="ignore", divide="ignore"):
        return (c - prev) / np.where(at > 0, at, np.nan)


def events(f, n, k, fade=True):
    """Signal bars and the side the mechanism forces. Returns sorted bar indices."""
    d = displacement(f, n)
    ok = np.isfinite(d) & (np.abs(d) >= k)
    ok[:max(n, 20) + 1] = False
    ok[-2:] = False
    sig = np.flatnonzero(ok)
    side = -np.sign(d[sig]).astype(np.int64)
    if not fade:
        side = -side
    keep = side != 0
    return sig[keep], side[keep], d[sig[keep]]


@njit(cache=True)
def _walk(o, h, l, c, at, sig, side, stop_a, tgt_a, hold, cost, m0, m1, mod):
    """One live position. Stop and target are ATR MULTIPLES at the signal bar. A bar touching both
    is resolved as the STOP and the ambiguous share is returned so the reader can price the
    convention (`STUDY_VOLBO_BREAKOUT`: it has been worth twice an edge)."""
    n = len(c)
    m = len(sig)
    eb = np.full(m, -1, np.int64); xb = np.full(m, -1, np.int64)
    pts = np.zeros(m); rr = np.zeros(m); risk = np.zeros(m)
    why = np.zeros(m, np.int64); amb = np.zeros(m, np.int64); sd = np.zeros(m, np.int64)
    cnt = 0; last = -1
    for q in range(m):
        i = sig[q]
        if i <= last or i + 1 >= n:
            continue
        if at[i] <= 0 or not np.isfinite(at[i]):
            continue
        if m0 >= 0 and (mod[i] < m0 or mod[i] >= m1):
            continue
        s = side[q]
        j = i + 1
        ent = o[j]
        rk = stop_a * at[i]
        stop = ent - s * rk
        targ = ent + s * tgt_a * at[i]
        x = -1; px = 0.0; w = 2; a = 0
        for t in range(j, n):
            hs = (l[t] <= stop) if s > 0 else (h[t] >= stop)
            ht = (h[t] >= targ) if s > 0 else (l[t] <= targ)
            if hs and ht:
                a = 1
            if hs:
                x = t; px = stop; w = 0
                break
            if ht:
                x = t; px = targ; w = 1
                break
            if hold > 0 and t - j >= hold:
                x = t; px = c[t]; w = 2
                break
        if x < 0:
            x = n - 1; px = c[n - 1]; w = 2
        eb[cnt] = j; xb[cnt] = x
        pts[cnt] = s * (px - ent) - cost
        rr[cnt] = pts[cnt] / rk
        risk[cnt] = rk; why[cnt] = w; amb[cnt] = a; sd[cnt] = s
        cnt += 1
        last = x
    return (eb[:cnt], xb[:cnt], pts[:cnt], rr[:cnt], risk[:cnt], why[:cnt], amb[:cnt], sd[:cnt])


def walk(f, sig, side, stop_a=1.5, tgt_a=1.5, hold=16, cost=COST, m0=-1, m1=-1):
    order = np.argsort(sig)
    s_, d_ = np.asarray(sig)[order].astype(np.int64), np.asarray(side)[order].astype(np.int64)
    eb, xb, pts, rr, rk, why, amb, sd = _walk(
        f["open"].to_numpy(), f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy(),
        f["atr"].to_numpy(), s_, d_, float(stop_a), float(tgt_a), int(hold), float(cost),
        int(m0), int(m1), f["mod"].to_numpy().astype(np.int64))
    t = pd.DataFrame(dict(e_bar=eb, x_bar=xb, pts=pts, R=rr, risk=rk, why=why, amb=amb, side=sd))
    t["ts"] = f.index[eb]
    t["pct"] = 100.0 * t.pts / f["open"].to_numpy()[eb]
    t["hold"] = t.x_bar - t.e_bar
    return t


def pf(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(x[x > 0].sum() / max(-x[x < 0].sum(), 1e-12)) if len(x) >= 5 else np.nan


def breakeven(stop_a, tgt_a, cost, atr):
    """Driftless break-even win rate for the two-outcome barrier pair, cost in ATR units."""
    c = cost / max(atr, 1e-9)
    return (stop_a + c) / (stop_a + tgt_a)


def control(f, sig, side, mask, n_draw=400, seed=0, **kw):
    """Matched random entry: same block, same COUNT, same side distribution, SORTED bars so the
    position lock rejects the same share (`STUDY_V59`). Returns the control means."""
    rng = np.random.default_rng(seed)
    elig = np.flatnonzero(mask & np.isfinite(f["atr"].to_numpy()) & (f["atr"].to_numpy() > 0))
    elig = elig[(elig > 300) & (elig < len(f) - 2)]
    want = int(len(sig))
    sides = np.asarray(side)
    out = []
    for _ in range(n_draw):
        pick = np.sort(rng.choice(elig, size=min(want, len(elig)), replace=False))
        sd = rng.permutation(sides)[:len(pick)]
        t = walk(f, pick, sd, **kw)
        if len(t) >= 10:
            out.append(t.pct.mean())
    return np.array(out)
