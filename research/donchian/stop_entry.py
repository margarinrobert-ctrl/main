"""THE AUTHENTIC DONCHIAN ENTRY MECHANIC - a resting stop order at the channel.

The baseline enters at the NEXT bar's open after a bar CLOSES beyond the channel.
That buys after a full 15-minute bar of continuation has already happened, which
for a momentum trade is the worst structural fill available. The classic Turtle /
Donchian mechanic rests a stop order AT the channel level and is filled the
moment price touches it, intrabar.

CLAUDE.md: "The ENTRY MECHANIC was the biggest lever found on this branch."
It has not been tested for this family, because the engine could not express it.

Modelling, deliberately pessimistic:
  * the fill is the channel level plus slippage AGAINST us (a stop order never
    fills better than its trigger, and usually worse)
  * the barrier walk starts at bar i+1, so we claim nothing from the remainder
    of the trigger bar...
  * ...but we DO charge the trigger bar's adverse excursion: if bar i's range
    reaches the stop after the fill, the trade is booked as a stop-out on bar i.
    We take the loss on the trigger bar but never the win.
  * no look-ahead: the channel excludes bar i, so the level is known before the
    bar opens, which is exactly when a resting order must be placed.
"""
import numpy as np, pandas as pd
from engine import build_walk, simulate, atr, donchian, stats, REASONS
import lab

SYM = "NAS"
df, w, res = lab.research(SYM)
h, l, c = df.high.values, df.low.values, df.close.values
sess, tod = df.sess.values, df.tod.values
COST, SLIP = lab.COST[SYM], lab.SLIP[SYM]


def stop_entry_book(n_entry=20, stop_mult=1.5, targ_mult=2.0, max_hold=16,
                    flat_tod=660, win=(420, 660), one_per_session=True,
                    cost_mult=1.0, atr_n=14):
    hi, lo = donchian(df, n_entry)
    a = atr(df, atr_n)
    inwin = (tod >= win[0]) & (tod < win[1])
    ok = inwin & ~np.isnan(hi) & ~np.isnan(a) & (a > 0)
    up = ok & (h > hi)          # price TRADED through the upper channel
    dn = ok & (l < lo)
    both = up & dn              # bar touched both sides: unknowable order -> drop
    up &= ~both; dn &= ~both
    idx = np.where(up | dn)[0]
    if not len(idx): return pd.DataFrame()
    side = np.where(up[idx], 1, -1).astype(np.float64)
    if one_per_session:
        s_ = sess[idx]; keep = np.concatenate([[True], s_[1:] != s_[:-1]])
        idx, side = idx[keep], side[keep]
    lvl = np.where(side > 0, hi[idx], lo[idx])
    entry = lvl + side * SLIP * cost_mult          # slippage always against
    av = a[idx]
    stop = entry - side * stop_mult * av
    targ = (entry + side * targ_mult * av) if targ_mult > 0 else \
        np.where(side > 0, np.inf, -np.inf)
    tr = simulate(w, idx, side, entry, stop, targ, max_hold=max_hold,
                  flat_tod=flat_tod, cost_pts=COST * cost_mult)
    # charge the trigger bar's adverse excursion: if bar i reached the stop
    # after we were filled, book it as a stop-out on bar i.
    sb = tr.sig_bar.values
    sd = tr.side.values
    hit0 = np.where(sd > 0, l[sb] <= tr.stop.values, h[sb] >= tr.stop.values)
    if hit0.any():
        tr.loc[hit0, "exit"] = tr.loc[hit0, "stop"]
        tr.loc[hit0, "gross"] = tr.loc[hit0, "side"] * (tr.loc[hit0, "exit"] - tr.loc[hit0, "entry"])
        tr.loc[hit0, "net"] = tr.loc[hit0, "gross"] - COST * cost_mult
        tr.loc[hit0, "reason"] = 0
        tr.loc[hit0, "bars"] = 0
    return tr


print("="*112)
print("STOP-ORDER ENTRY AT THE CHANNEL vs NEXT-OPEN AFTER A CLOSE BEYOND")
print(f"  {SYM}, 07:00-11:00 New York, RESEARCH BLOCK ONLY, cost {COST} + {SLIP}/side")
print("="*112)
print(f"\n  {'n_entry':>7}  {'mechanic':<22} {'n':>6} {'exp':>8} {'ctrl':>8} {'excess':>8} {'z':>7} {'p':>7} {'pf':>6} {'wr':>6}")
rows = []
for n_e in (10, 20, 40):
    # baseline mechanic
    idx, side, _ = lab.signals(df, n_e)
    g0, _ = lab.sig_gate(SYM, idx, side, stop_mult=1.5, targ_mult=2.0, n_draws=250, quiet=True)
    print(f"  {n_e:>7}  {'next-open (baseline)':<22} {g0['n']:>6,} {g0['exp']:>+8.2f} {g0['ctrl']:>+8.2f}"
          f" {g0['excess']:>+8.2f} {g0['z']:>+7.2f} {g0['p']:>7.4f} {g0['pf']:>6.2f} {g0['wr']:>6.1%}")
    # stop-order mechanic
    tr = stop_entry_book(n_entry=n_e, stop_mult=1.5, targ_mult=2.0)
    g1 = lab.gate(SYM, tr, 1.5, 2.0, n_draws=250, quiet=True)
    print(f"  {n_e:>7}  {'STOP at channel':<22} {g1['n']:>6,} {g1['exp']:>+8.2f} {g1['ctrl']:>+8.2f}"
          f" {g1['excess']:>+8.2f} {g1['z']:>+7.2f} {g1['p']:>7.4f} {g1['pf']:>6.2f} {g1['wr']:>6.1%}")
    rows.append((n_e, g0, g1))
    print()

print("  Note the control is the SAME for both mechanics only if geometry matches;")
print("  it is re-drawn per book, so `excess` is the comparable column.\n")

print("="*112)
print("GEOMETRY SWEEP under the stop-order mechanic (research block)")
print("="*112)
print(f"  {'stop':>5} {'targ':>5} {'n':>6} {'exp':>8} {'ctrl':>8} {'excess':>8} {'z':>7} {'p':>7}")
best = []
for sm in (1.0, 1.5, 2.0, 2.5):
    for tm in (1.0, 1.5, 2.0, 3.0):
        tr = stop_entry_book(n_entry=20, stop_mult=sm, targ_mult=tm)
        if len(tr) < 50: continue
        g = lab.gate(SYM, tr, sm, tm, n_draws=200, quiet=True)
        best.append((sm, tm, g))
        print(f"  {sm:>5.1f} {tm:>5.1f} {g['n']:>6,} {g['exp']:>+8.2f} {g['ctrl']:>+8.2f}"
              f" {g['excess']:>+8.2f} {g['z']:>+7.2f} {g['p']:>7.4f}")
pos = [b for b in best if b[2]["excess"] > 0 and b[2]["p"] < 0.05]
print(f"\n  cells with excess>0 and p<0.05: {len(pos)} / {len(best)}   (chance ~ {0.05*len(best):.1f})")
