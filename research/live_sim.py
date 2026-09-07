"""What the book does under a realistic fill model, and everything that follows from it.

The research engines charge a flat cost: 1 tick of spread plus 1 tick of slippage on each side,
one extra tick when a stop fills, $1.00 commission per round turn. That is a fair RTH assumption
for MNQ and an OPTIMISTIC one everywhere else, which matters here because one leg takes half its
trades overnight.

The overlay below charges what a live account would actually pay on top:

  overnight (16:00-09:30)      +1 tick per side   MNQ quotes 2 ticks wide off-hours routinely
  first / last 10 min of RTH   +1 tick per side   the fastest tape of the day
  ATR above its 80th pct       +1 tick per side   wide markets slip more
  commission                   configurable       $1.00 base, swept to $2.00

Nothing here is a free parameter chosen to make a result look good -- every charge makes every
result worse. The question is which legs survive being charged honestly.
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
from bos_choch import prep
from book import all_legs, PV, TICK


def overlay(leg, comm_extra=0.0, mult=1.0, vol_pct=None):
    """Extra dollars charged per trade by the realistic model."""
    mod = leg["mod"]; atr = leg["atr"]
    extra_ticks = np.zeros(len(mod))
    overnight = (mod < 570) | (mod >= 960)
    extra_ticks += 2.0 * overnight                      # 1 tick each side
    edge = ((mod >= 570) & (mod < 580)) | ((mod >= 950) & (mod < 960))
    extra_ticks += 2.0 * edge
    if vol_pct is None:
        vol_pct = np.nanpercentile(atr[~np.isnan(atr)], 80)
    extra_ticks += 2.0 * (atr > vol_pct)
    return mult * (extra_ticks * TICK * PV) + comm_extra


def priced(legs, comm_extra=0.0, mult=1.0):
    out = {}
    for k, v in legs.items():
        w = dict(v)
        w["pnl"] = v["pnl"] - overlay(v, comm_extra, mult)
        out[k] = w
    return out


def daily(legs, us, IX):
    D = {}
    for k, v in legs.items():
        x = np.zeros(len(us))
        for p, s in zip(v["pnl"], v["sess"]):
            if s in IX:
                x[IX[s]] += p
        D[k] = x
    return D


def stats(x, ann=252):
    eq = np.cumsum(x)
    dd = (np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()
    sh = x.mean() / x.std(ddof=1) * np.sqrt(ann) if x.std() > 0 else 0.0
    return x.sum(), dd, sh


W = 108
US = np.unique(prep(30)["sess"])
IX = {s: i for i, s in enumerate(US)}
CUT = US[int(0.65 * len(US))]
RES = US < CUT


def hdr(t):
    print("=" * W); print(t); print("=" * W)


if __name__ == "__main__":
    raw = all_legs()

    hdr("1. THE COST OF BEING CHARGED HONESTLY")
    print("   Every leg under the flat research cost, then under the realistic overlay, then with")
    print("   the overlay doubled and commission raised to $2.00 per round turn.\n")
    print(f"   {'leg':<10}{'trades':>8}{'flat $':>10}{'realistic $':>13}{'lost':>9}"
          f"{'2x + $2 comm':>14}{'lost':>9}{'% overnight':>13}")
    scen = {}
    for nm, ce, mu in [("flat", 0.0, 0.0), ("real", 0.0, 1.0), ("harsh", 1.0, 2.0)]:
        scen[nm] = priced(raw, ce, mu)
    for k in raw:
        a = scen["flat"][k]["pnl"].sum()
        b = scen["real"][k]["pnl"].sum()
        c = scen["harsh"][k]["pnl"].sum()
        on = 100 * ((raw[k]["mod"] < 570) | (raw[k]["mod"] >= 960)).mean()
        print(f"   {k:<10}{len(raw[k]['pnl']):>8}{a:>10,.0f}{b:>13,.0f}{b-a:>9,.0f}"
              f"{c:>14,.0f}{c-a:>9,.0f}{on:>12.0f}%")
    for nm in ("flat", "real", "harsh"):
        tot = sum(v["pnl"].sum() for v in scen[nm].values())
        print(f"   {'BOOK ' + nm:<10}{'':>8}{tot:>10,.0f}")

    print()
    hdr("2. OUT OF SAMPLE — research and locked, under the realistic model")
    L = scen["real"]
    D = daily(L, US, IX)
    print(f"   {'leg':<12}{'research $':>12}{'DD':>9}{'Sharpe':>8}   "
          f"{'LOCKED $':>11}{'DD':>9}{'Sharpe':>8}")
    for k, x in D.items():
        r = stats(x[RES]); q = stats(x[~RES])
        print(f"   {k:<12}{r[0]:>12,.0f}{r[1]:>9,.0f}{r[2]:>8.2f}   "
              f"{q[0]:>11,.0f}{q[1]:>9,.0f}{q[2]:>8.2f}")
    bk = sum(D.values())
    r = stats(bk[RES]); q = stats(bk[~RES])
    print(f"   {'BOOK':<12}{r[0]:>12,.0f}{r[1]:>9,.0f}{r[2]:>8.2f}   "
          f"{q[0]:>11,.0f}{q[1]:>9,.0f}{q[2]:>8.2f}")

    print()
    hdr("3. WALK-FORWARD — anchored and rolling, nothing refitted inside a fold")
    print("   These configurations were chosen once, on the research block. Walk-forward here is")
    print("   asking whether the SAME fixed rules keep working forward, not whether re-optimising")
    print("   works -- that question was answered on this branch already, and the answer was no.\n")
    folds = np.array_split(np.arange(len(US)), 8)
    print(f"   {'fold':<8}{'window':<26}" + "".join(f"{k:>11}" for k in D) + f"{'BOOK':>11}")
    neg = {k: 0 for k in D}; negb = 0
    for f in range(1, 8):
        sl = folds[f]
        lab = f"{US[sl[0]]}..{US[sl[-1]]}"
        row = f"   {f:<8}{str(prep(30)['df'].index[0].date())[:0]:<0}"
        row = f"   {f:<8}{'sessions ' + str(sl[0]) + '-' + str(sl[-1]):<26}"
        for k, x in D.items():
            v = x[sl].sum()
            neg[k] += v < 0
            row += f"{v:>11,.0f}"
        bv = bk[sl].sum(); negb += bv < 0
        row += f"{bv:>11,.0f}"
        print(row)
    print(f"   {'negative folds of 7':<34}" + "".join(f"{neg[k]:>11}" for k in D)
          + f"{negb:>11}")

    print()
    hdr("4. MONTE CARLO — three different nulls, on the LOCKED block only")
    rng = np.random.default_rng(20260823)
    z = bk[~RES]
    nz = len(z)

    sims = np.empty(10000)
    for s in range(10000):
        o = np.empty(nz); f = 0
        while f < nz:
            st = rng.integers(0, nz); ln = min(rng.geometric(1.0 / 20), nz - f)
            for q2 in range(ln):
                o[f + q2] = z[(st + q2) % nz]
            f += ln
        sims[s] = o.sum()
    print(f"   a) stationary block bootstrap of DAILY P&L, 10,000 paths, mean block 20 days")
    print(f"      p5 ${np.percentile(sims,5):,.0f}   median ${np.median(sims):,.0f}   "
          f"p95 ${np.percentile(sims,95):,.0f}   P(net<0) = {100*(sims<0).mean():.1f}%")

    tr = np.concatenate([v["pnl"][np.isin(v["sess"], US[~RES])] for v in L.values()])
    dds = np.empty(10000); ends = np.empty(10000)
    for s in range(10000):
        o = rng.permutation(tr)
        eq = np.cumsum(o)
        dds[s] = (np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()
        ends[s] = eq[-1]
    print(f"   b) TRADE-ORDER shuffle, {len(tr)} locked trades, 10,000 orderings")
    print(f"      the sequence actually realised drew down "
          f"${stats(bk[~RES])[1]:,.0f}; shuffled median ${np.median(dds):,.0f}, "
          f"p95 ${np.percentile(dds,95):,.0f}")
    print(f"      -> a worse ORDER of the same trades costs up to "
          f"${np.percentile(dds,95)-stats(bk[~RES])[1]:,.0f} more drawdown")

    exn = np.empty(5000)
    for s in range(5000):
        tot = 0.0
        for v in L.values():
            m = np.isin(v["sess"], US[~RES])
            n = int(m.sum())
            # each trade pays 0-3 extra ticks per side, drawn at random
            extra = rng.integers(0, 4, n) * 2.0 * TICK * PV
            tot += v["pnl"][m].sum() - extra.sum()
        exn[s] = tot
    print(f"   c) EXECUTION NOISE: 0-3 extra ticks per side per trade, drawn at random, 5,000 draws")
    print(f"      p5 ${np.percentile(exn,5):,.0f}   median ${np.median(exn):,.0f}   "
          f"p95 ${np.percentile(exn,95):,.0f}   P(net<0) = {100*(exn<0).mean():.1f}%")

    print()
    hdr("5. PORTFOLIO CONSTRUCTION — how many contracts of each")
    print("   Weights are fitted on the RESEARCH block only and then applied, unchanged, to the")
    print("   locked block. Contracts are integers because a fifth of an MNQ does not exist.\n")
    keys = list(D)
    Xr = np.array([D[k][RES] for k in keys])
    vol = Xr.std(axis=1)
    C = np.corrcoef(Xr)

    schemes = {}
    schemes["equal weight"] = np.ones(len(keys))
    schemes["inverse volatility"] = 1.0 / np.maximum(vol, 1e-9)
    iv = 1.0 / np.maximum(vol, 1e-9)
    schemes["risk parity (corr-aware)"] = iv / np.maximum(C.dot(iv), 1e-9)
    mu = Xr.mean(axis=1)
    schemes["return / variance"] = np.maximum(mu, 0) / np.maximum(vol ** 2, 1e-12)

    print(f"   {'scheme':<26}" + "".join(f"{k:>10}" for k in keys)
          + f"{'res $':>10}{'DD':>8}{'Sh':>6}{'LOCK $':>10}{'DD':>8}{'Sh':>6}")
    for nm, w in schemes.items():
        w = np.asarray(w, float)
        w = w / w.max()                       # the biggest leg trades 1 contract
        n = np.maximum(np.round(w * 3), 1)    # scale so the largest is 3, floor at 1
        x = sum(n[i] * D[k] for i, k in enumerate(keys))
        r = stats(x[RES]); q = stats(x[~RES])
        print(f"   {nm:<26}" + "".join(f"{int(n[i]):>10}" for i in range(len(keys)))
              + f"{r[0]:>10,.0f}{r[1]:>8,.0f}{r[2]:>6.2f}{q[0]:>10,.0f}{q[1]:>8,.0f}{q[2]:>6.2f}")
    x1 = sum(D[k] for k in keys)
    r = stats(x1[RES]); q = stats(x1[~RES])
    print(f"   {'1 contract each':<26}" + "".join(f"{1:>10}" for _ in keys)
          + f"{r[0]:>10,.0f}{r[1]:>8,.0f}{r[2]:>6.2f}{q[0]:>10,.0f}{q[1]:>8,.0f}{q[2]:>6.2f}")
