"""GATE 1 -- the Donchian + EMA trend primary on US30, before any mathematical state is attached.

The user's frame: Donchian trend following with an EMA, US30 only. Under the mechanism-first
architecture that is the PRIMARY, and it has to clear its own control before a meta layer is built
on it -- otherwise the six estimators are being asked to rescue a dead base, which
`STUDY_EMA48_VWAP_DL` and `STUDY_VWANOM` both measured as impossible.

54 declared cells: entry channel 20/30/55 x EMA filter off/50/200 (as a STATE, close above/below)
x stop 2.0/2.5 ATR x timeframe 15/30/60. Exit = the opposite 20-bar channel or the stop, NO TARGET.
Both sides. Percent of entry price, US30's 2.29-point round turn.
"""
from __future__ import annotations

import itertools
import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mathmodels import mmcore as M  # noqa: E402

RNG = np.random.default_rng(2718)
ND = 300
COST = 2.29


@njit(cache=True)
def walk(o, h, l, c, at, ehi, elo, xhi, xlo, ok_up, ok_dn, stop_mult, cost):
    n = len(c)
    eb = np.full(n, -1, np.int64); out = np.empty(n)
    sd = np.empty(n, np.int64); hl = np.empty(n, np.int64)
    cnt = 0; last = -1
    for i in range(1, n - 1):
        if i <= last or at[i] <= 0 or not np.isfinite(at[i]):
            continue
        if np.isnan(ehi[i]) or np.isnan(elo[i]):
            continue
        s = 0
        if c[i] > ehi[i] and ok_up[i] == 1:
            s = 1
        elif c[i] < elo[i] and ok_dn[i] == 1:
            s = -1
        if s == 0:
            continue
        j = i + 1
        ent = o[j]; risk = stop_mult * at[i]
        stop = ent - s * risk
        x = -1; px = 0.0
        for t in range(j, n):
            if (l[t] <= stop) if s > 0 else (h[t] >= stop):
                x = t; px = stop
                break
            if t > j and not np.isnan(xlo[t]):
                if (s > 0 and c[t] < xlo[t]) or (s < 0 and c[t] > xhi[t]):
                    x = t; px = c[t]
                    break
        if x < 0:
            x = n - 1; px = c[n - 1]
        eb[cnt] = j; out[cnt] = 100.0 * (s * (px - ent) - cost) / ent
        sd[cnt] = s; hl[cnt] = x - j
        cnt += 1
        last = x
    return eb[:cnt], out[:cnt], sd[:cnt], hl[:cnt]


@njit(cache=True)
def walk_at(o, h, l, c, at, xhi, xlo, sig, side, stop_mult, cost):
    n = len(c); m = len(sig)
    out = np.full(m, np.nan)
    last = -1
    for q in range(m):
        i = sig[q]
        if i <= last or i + 1 >= n or at[i] <= 0 or not np.isfinite(at[i]):
            continue
        s = side[q]; j = i + 1
        ent = o[j]; risk = stop_mult * at[i]
        stop = ent - s * risk
        x = -1; px = 0.0
        for t in range(j, n):
            if (l[t] <= stop) if s > 0 else (h[t] >= stop):
                x = t; px = stop
                break
            if t > j and not np.isnan(xlo[t]):
                if (s > 0 and c[t] < xlo[t]) or (s < 0 and c[t] > xhi[t]):
                    x = t; px = c[t]
                    break
        if x < 0:
            x = n - 1; px = c[n - 1]
        out[q] = 100.0 * (s * (px - ent) - cost) / ent
        last = x
    return out


def chan(h, l, n):
    return (pd.Series(h).rolling(n).max().shift(1).to_numpy(),
            pd.Series(l).rolling(n).min().shift(1).to_numpy())


def main():
    rows = []
    cache = {}
    for tf in (15, 30, 60):
        f = M.load("US30L", tf)
        s = np.unique(f.index.normalize())
        cut = pd.Timestamp(s[int(0.75 * len(s))])
        cache[tf] = (f, cut)
        o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
        at = f["atr"].to_numpy()
        xh, xl = chan(h, l, 20)
        ones = np.ones(len(c), np.int64)
        for en, ema, sm in itertools.product((20, 30, 55), (0, 50, 200), (2.0, 2.5)):
            eh, el = chan(h, l, en)
            if ema == 0:
                ou, od = ones, ones
            else:
                e = pd.Series(c).ewm(span=ema, adjust=False).mean().to_numpy()
                ou = (c > e).astype(np.int64)
                od = (c < e).astype(np.int64)
            eb, r, sd, hlv = walk(o, h, l, c, at, eh, el, xh, xl, ou, od, sm, COST)
            ts = f.index[eb]
            m = np.asarray(ts < cut)
            if m.sum() < 60:
                continue
            rr = r[m]
            rows.append(dict(tf=tf, ent=en, ema=ema, stop=sm, n=len(rr), mu=float(rr.mean()),
                             tot=float(rr.sum()), pf=M.pf(rr),
                             hold=float(np.median(hlv[m])) * tf,
                             long_share=float((sd[m] > 0).mean())))
    d = pd.DataFrame(rows)
    d.to_csv("research/mathmodels/gate1.csv", index=False)
    print(f"{len(d)} scorable cells of 54 declared   profitable {float((d.tot>0).mean()):.3f}\n")
    print("MARGINAL AVERAGE of %/trade")
    for ax in ("tf", "ent", "ema", "stop"):
        print(f"  {ax:<5} " + str(d.groupby(ax).mu.mean().round(4).to_dict()))

    print("\nTOP 6 research cells")
    print(d.sort_values("mu", ascending=False).head(6).to_string(
        index=False, float_format=lambda x: f"{x:.4f}"))

    print("\nMATCHED RANDOM ENTRY on the leaders (same side mix, same stop, same exit)")
    print(f"{'cell':<28}{'blk':<10}{'n':>6}{'%/trade':>9}{'PF':>7}{'ctl':>9}{'p':>7}")
    lead = d.sort_values("mu", ascending=False).head(3)
    for b in lead.itertuples():
        f, cut = cache[b.tf]
        o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
        at = f["atr"].to_numpy()
        xh, xl = chan(h, l, 20)
        eh, el = chan(h, l, b.ent)
        ones = np.ones(len(c), np.int64)
        if b.ema == 0:
            ou, od = ones, ones
        else:
            e = pd.Series(c).ewm(span=b.ema, adjust=False).mean().to_numpy()
            ou = (c > e).astype(np.int64); od = (c < e).astype(np.int64)
        eb, r, sd, hlv = walk(o, h, l, c, at, eh, el, xh, xl, ou, od, b.stop, COST)
        ts = f.index[eb]
        elig = np.flatnonzero(np.isfinite(at) & (at > 0))
        elig = elig[(elig > 300) & (elig < len(c) - 60)]
        nm = f"{b.tf}m d{b.ent} ema{b.ema} {b.stop}N"
        for bl, sel, gm in (("research", np.asarray(ts < cut), f.index < cut),
                            ("HOLDOUT", np.asarray(ts >= cut), f.index >= cut)):
            rr = r[sel]
            if len(rr) < 40:
                continue
            e2 = elig[np.isin(elig, np.flatnonzero(gm))]
            share = float((sd[sel] > 0).mean())
            ctl = np.empty(ND)
            for q in range(ND):
                pick = np.sort(RNG.choice(e2, size=min(len(rr), len(e2)), replace=False))
                sr = np.where(RNG.random(len(pick)) < share, 1, -1)
                ctl[q] = np.nanmean(walk_at(o, h, l, c, at, xh, xl, pick.astype(np.int64),
                                            sr.astype(np.int64), b.stop, COST))
            mu = float(rr.mean())
            print(f"{nm:<28}{bl:<10}{len(rr):>6}{mu:>9.4f}{M.pf(rr):>7.3f}"
                  f"{np.nanmedian(ctl):>9.4f}{float(np.mean(ctl >= mu)):>7.3f}")


if __name__ == "__main__":
    main()
