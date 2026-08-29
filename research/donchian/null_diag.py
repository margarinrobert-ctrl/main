"""Diagnose the negative null: conservative bias, or a genuine engine bug?

Decisive test: strip the geometry. With NO stop and NO target the trade exits
only on time, there is no same-bar ambiguity and no stop-fill rule to apply.
On a driftless series that MUST give t ~ 0. If it does, the bias lives in the
geometry rules (priced pessimism). If it does not, the engine is broken.
"""
import numpy as np, pandas as pd
from engine import build_walk, stats, simulate, atr
from strategy import run, signals
from null_test import synth
import data as D

real = D.load("NAS")
print("="*100)
print("DIAGNOSTIC A - geometry stripped: no stop, no target, pure time exit")
print("  A driftless series MUST give t ~ 0 here. Non-zero => real look-ahead bug.")
print("="*100)
for rep in range(4):
    d = synth(real, phi=0.0, seed=1000+rep)
    w = build_walk(d)
    idx, side, a = signals(d, 20)
    s2 = d.sess.values[idx]; keep = np.concatenate([[True], s2[1:] != s2[:-1]])
    idx, side = idx[keep], side[keep]
    entry = w["opens"][idx, 0]
    inf_t = np.where(side > 0, np.inf, -np.inf)
    inf_s = np.where(side > 0, -np.inf, np.inf)
    tr = simulate(w, idx, side.astype(float), entry, inf_s, inf_t,
                  max_hold=16, flat_tod=660, cost_pts=0.0)
    st = stats(tr)
    print(f"  seed {1000+rep}: n={st['n']:>5,}  exp={st['exp']:>+8.4f}  t={st['t']:>+6.2f}"
          f"  ambig={st['ambig']:.1%}")

print("\n"+"="*100)
print("DIAGNOSTIC B - ambiguity rate and its cost, by geometry (driftless)")
print("  The same-bar rule books a LOSS when one bar holds both stop and target.")
print("="*100)
d = synth(real, phi=0.0, seed=1000); w = build_walk(d)
print(f"  {'stop':>5} {'targ':>5} {'n':>7} {'ambig':>8} {'exp':>9} {'t':>7}   {'exp if ambig=win':>18}")
for sm in (1.0, 1.5, 2.5):
    for tm in (1.5, 2.0, 3.0):
        tr = run(d, w, n_entry=20, stop_mult=sm, targ_mult=tm, cost_pts=0.0, slip_pts=0.0)
        st = stats(tr)
        alt = tr.copy()
        am = alt.ambig.values
        alt.loc[am, "net"] = (alt.side[am]*(alt.targ[am]-alt.entry[am]))
        print(f"  {sm:>5.1f} {tm:>5.1f} {st['n']:>7,} {st['ambig']:>8.1%} {st['exp']:>+9.3f}"
              f" {st['t']:>+7.2f}   {alt.net.mean():>+18.3f}")

print("\n"+"="*100)
print("DIAGNOSTIC C - is the synthetic bar geometry realistic?")
print("  If synthetic bars are far wider than real ones, ambiguity is inflated and")
print("  the null is harsher than reality rather than wrong.")
print("="*100)
for nm, dd in (("REAL NAS", real), ("SYNTHETIC", d)):
    rng_ = (dd.high.values - dd.low.values)
    a = atr(dd, 14)
    ok = ~np.isnan(a) & (a > 0)
    body = np.abs(dd.close.values - dd.open.values)
    print(f"  {nm:<10} median range/ATR = {np.median(rng_[ok]/a[ok]):.3f}"
          f"   median body/range = {np.median((body[ok]+1e-9)/(rng_[ok]+1e-9)):.3f}"
          f"   median range = {np.median(rng_):.2f} pts")
