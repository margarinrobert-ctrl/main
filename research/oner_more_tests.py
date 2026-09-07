"""Live-market tests on the four re-set versions. Everything read on the locked block.

The one test that has killed more candidates on this branch than all the others put together is
first: each condition against a RANDOM FILTER OF THE SAME SELECTIVITY. Total dollars fails every
restrictive condition and per-trade edge passes every one; only the matched comparison says
anything, and it is read on the block the rule was not selected on.

After that: the true 1-minute execution path, entry-timing dispersion, cost sensitivity, a
stationary block bootstrap, and a rolling walk-forward. A version that only survives the first is
not shippable and a version that survives all of them still might not be.

Usage: python3 research/oner_more_tests.py
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
import indicators as I
from dropone import filter_null
from oner_anom import _parts
from oner_more import select
from oner_union import FAMILIES
from test_suite import _daily, _dd, _sharpe, build

_S = {}


def strat(key, S=None, drop=None):
    """A fully instrumented Strategy for one version, optionally with condition `drop` removed."""
    S = S or select(key, verbose=False)
    F = FAMILIES[key]
    names, masks = _parts(F, S["d"], S["p"])
    use = [i for i in range(len(masks)) if i != drop]
    m = np.ones(len(S["d"]["c"]), bool)
    for i in use:
        m &= masks[i]
    m[:300] = False
    return build([names[i] for i in use], side=S["side"], atr_mult=S["am"], tp_r=1.0,
                 flat_min=S["flat"], tf=S["tf"], trig=np.flatnonzero(m).astype(np.int64),
                 name=f"{key} {S['p']}" + (f" without {names[drop]}" if drop is not None else ""))


def dropone(keys, draws=2000):
    print("1. EACH CONDITION AGAINST A RANDOM FILTER OF THE SAME SIZE   (locked block)")
    print(f"   {'':<5}{'condition dropped':<26}{'n full':>8}{'n sub':>8}{'full $/tr':>11}"
          f"{'random $/tr':>13}{'p':>8}")
    out = {}
    for k in keys:
        S = select(k, verbose=False)
        full = strat(k, S)
        names, _m = _parts(FAMILIES[k], S["d"], S["p"])
        rows = []
        for j, nm in enumerate(names):
            sub = strat(k, S, drop=j)
            nul = filter_null(full, sub, draws=draws)
            obs, rnd, p = nul["lok"]
            rows.append((nm, p))
            lm = full.ent_sess >= full.cut; sm = sub.ent_sess >= sub.cut
            print(f"   {k:<5}{nm[:24]:<26}{int(lm.sum()):>8}{int(sm.sum()):>8}"
                  f"{obs:>11,.0f}{rnd:>13,.0f}{p:>8.3f}"
                  + ("  <- real filter" if np.isfinite(p) and p < 0.10 else ""))
        out[k] = rows
        _S[k] = full
    print("   a condition is 'real' only if the rule's own selection beats random selections of "
          "the same\n   size on the block it was not chosen on. p is one-sided.")
    return out


def execution(keys):
    from intrabar import compare
    print("\n2. TRUE 1-MINUTE EXECUTION PATH")
    print(f"   {'':<5}{'model':<30}{'trades':>8}{'net $':>10}{'PF':>7}{'win %':>8}")
    for k in keys:
        S = select(k, verbose=False)
        F = FAMILIES[k]
        names, masks = _parts(F, S["d"], S["p"])
        m = np.ones(len(S["d"]["c"]), bool)
        for x in masks:
            m &= x
        m[:300] = False
        s, out, (offs, tim) = compare(names, side=S["side"], atr_mult=S["am"], tp_r=1.0,
                                      flat_min=S["flat"], tf=S["tf"],
                                      trig=np.flatnonzero(m).astype(np.int64))
        for lab, (pnl, why, amb) in out.items():
            w = pnl > 0
            print(f"   {k:<5}{lab:<30}{len(pnl):>8}{pnl.sum():>10,.0f}"
                  f"{pnl[w].sum()/max(-pnl[~w].sum(),1e-9):>7.2f}{100*w.mean():>8.1f}")
        print(f"   {'':<5}{'entry delayed 0/1/2/5/10/20/29m':<30}"
              + "  ".join(f"{x:,.0f}" for x in tim))


def costs(keys):
    print("\n3. COST SENSITIVITY   (locked block, dollars per trade)")
    print(f"   {'':<5}{'1x (as measured)':>18}{'1.5x':>10}{'2x':>10}{'3x':>10}{'+1 tick':>10}"
          f"{'breakeven':>12}")
    for k in keys:
        S = select(k, verbose=False)
        F = FAMILIES[k]
        names, _m = _parts(F, S["d"], S["p"])
        base = _S.get(k) or strat(k, S)
        vals = []
        for cm, xs in ((1.0, 0.0), (1.5, 0.0), (2.0, 0.0), (3.0, 0.0), (1.0, 1.0)):
            s = base.sim(cost_mult=cm, extra_slip_t=xs)
            m = s.ent_sess >= s.cut
            vals.append(s.pnl[m].mean() if m.sum() else np.nan)
        # how many multiples of the measured cost it takes to reach zero
        lo, hi = 1.0, 40.0
        for _ in range(22):
            mid = 0.5 * (lo + hi)
            s = base.sim(cost_mult=mid)
            m = s.ent_sess >= s.cut
            (lo, hi) = (mid, hi) if (m.sum() and s.pnl[m].mean() > 0) else (lo, mid)
        print(f"   {k:<5}" + "".join(f"{v:>{w},.0f}" for v, w in
                                     zip(vals, (18, 10, 10, 10, 10)))
              + f"{0.5*(lo+hi):>11.1f}x")


def bootstrap(keys, draws=3000, seed=3):
    print("\n4. STATIONARY BLOCK BOOTSTRAP   (locked block, 20-trade blocks)")
    rng = np.random.default_rng(seed)
    print(f"   {'':<5}{'n':>5}{'net $':>10}{'5th pct':>10}{'median':>10}{'95th':>10}"
          f"{'P(net<0)':>10}{'P(DD>2x)':>10}")
    for k in keys:
        s = _S.get(k) or strat(k, select(k, verbose=False))
        p = s.pnl[s.ent_sess >= s.cut]
        if len(p) < 25:
            print(f"   {k:<5}{len(p):>5}   (too few locked trades to bootstrap)"); continue
        L, nets, dds = 20, [], []
        obs_dd = _dd(p)
        for _ in range(draws):
            out = []
            while len(out) < len(p):
                i = rng.integers(0, len(p))
                out.extend(p[i:i + L] if i + L <= len(p) else np.r_[p[i:], p[:L - (len(p) - i)]])
            q = np.array(out[:len(p)])
            nets.append(q.sum()); dds.append(_dd(q))
        nets = np.array(nets); dds = np.array(dds)
        print(f"   {k:<5}{len(p):>5}{p.sum():>10,.0f}{np.percentile(nets,5):>10,.0f}"
              f"{np.median(nets):>10,.0f}{np.percentile(nets,95):>10,.0f}"
              f"{(nets<0).mean():>10.2f}{(dds>2*obs_dd).mean():>10.2f}")


def walkforward(keys, folds=6):
    print(f"\n5. ROLLING WALK-FORWARD   {folds} equal folds over the whole sample, no refitting")
    print(f"   {'':<5}" + "".join(f"{'f'+str(i+1):>9}" for i in range(folds))
          + f"{'positive':>10}")
    for k in keys:
        s = _S.get(k) or strat(k, select(k, verbose=False))
        edges = np.linspace(0, s.n_sess, folds + 1).astype(int)
        vals = []
        for a, b in zip(edges[:-1], edges[1:]):
            m = (s.ent_sess >= a) & (s.ent_sess < b)
            vals.append(float(s.pnl[m].sum()) if m.sum() else 0.0)
        print(f"   {k:<5}" + "".join(f"{v:>9,.0f}" for v in vals)
              + f"{sum(1 for v in vals if v > 0):>7}/{folds}")


if __name__ == "__main__":
    keys = [a for a in sys.argv[1:] if a in FAMILIES] or list(FAMILIES)
    print("LIVE-MARKET TESTS ON THE RE-SET VERSIONS\n")
    dropone(keys)
    execution(keys)
    costs(keys)
    bootstrap(keys)
    walkforward(keys)
