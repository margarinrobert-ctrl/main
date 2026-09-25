"""Is the volatility state actionable for STOP PLACEMENT, or has the ATR already done the job?

Part B of `v22trade.py` found the one non-flat column in the whole study: on BOTH timeframes,
median MAE measured IN ATR UNITS falls from ~2.2 to ~1.2 as short-horizon realised volatility rises
through its own 250-bar percentile, and the stop-out rate falls with it. The mechanism is ATR
MEAN REVERSION -- when vol sits low in its own distribution, ATR(14) has already contracted, so a
2.0N stop is SMALL relative to the excursion the trade is about to make. That is the OPPOSITE of the
naive reading ("widen stops when volatility is high"): the ATR overcorrects, and the correction
available is in the low-percentile bucket.

This file does not search. It declares five stop policies before looking, scores them on research,
and reads the locked block once. One of them is the flat stop and one is the naive INVERSE, which is
the sign check -- if the inverse also improves, the improvement is not the state.
"""
from __future__ import annotations

import sys
import numpy as np

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v22")
import v16core as C           # noqa: E402
import v22vol as V            # noqa: E402

STATE = "pct_cc20_250"
# (label, stop when state <= 0.5, stop when state > 0.5)
POLICIES = (
    ("flat 2.0N                     ", 2.0, 2.0),
    ("wide in LOW  vol pct  2.5/1.5 ", 2.5, 1.5),
    ("wide in LOW  vol pct  2.5/2.0 ", 2.5, 2.0),
    ("wide in LOW  vol pct  3.0/1.5 ", 3.0, 1.5),
    ("INVERSE (naive)       1.5/2.5 ", 1.5, 2.5),
)


def blocks(sess, frac=0.65):
    u = np.unique(sess)
    return sess < u[int(len(u) * frac)], sess >= u[int(len(u) * frac)]


def merged(P, sig, lo_stop, hi_stop, low):
    """Outcomes where each signal uses the stop its own state selects, then the position lock."""
    A = C.outcomes(P, 1, sig, stop_mult=lo_stop, tp_r=0.0)
    B = C.outcomes(P, 1, sig, stop_mult=hi_stop, tp_r=0.0)
    xb = np.where(low, A["xb"], B["xb"])
    R = np.where(low, A["R"], B["R"])
    why = np.where(low, A["why"], B["why"])
    return dict(xb=xb, R=R, why=why, sig=sig)


def bootstrap(R, sess_of_trade, n=4000, seed=7):
    """Resample whole DAYS with their trades attached; trade-weighted mean each draw."""
    rng = np.random.default_rng(seed)
    days, inv = np.unique(sess_of_trade, return_inverse=True)
    by = [np.flatnonzero(inv == i) for i in range(len(days))]
    out = np.empty(n)
    for k in range(n):
        pick = rng.integers(0, len(days), len(days))
        out[k] = np.concatenate([by[i] for i in pick]).size and \
            R[np.concatenate([by[i] for i in pick])].mean()
    return float((out <= 0).mean()), float(np.quantile(out, .05)), float(np.quantile(out, .95))


def hdr(t):
    print("\n" + "=" * 112)
    print(t)
    print("=" * 112)


if __name__ == "__main__":
    for tf in (15, 30):
        P = C.prep(tf, entry_n=30, exit_n=20, cost_mult=1.44)
        sig = C.signals(P, 1)
        F = V.build(P["o"], P["h"], P["l"], P["c"])
        s = F[STATE][sig]
        res, lock = blocks(P["sess"])
        res, lock = res[sig], lock[sig]
        good = np.isfinite(s)
        low = np.where(good, s <= 0.5, False)

        hdr(f"NQ {tf}m   Donchian 30/20 long, no target, real MNQ costs   "
            f"state = {STATE} at the SIGNAL bar")
        print(f"   {'policy':<32}{'RESEARCH':>26}{'|':>4}{'LOCKED':>26}")
        print(f"   {'':<32}{'n':>7}{'R/trade':>10}{'PF':>9}{'|':>4}{'n':>7}{'R/trade':>10}{'PF':>9}"
              f"{'P(<=0)':>9}")
        for lab, a, b in POLICIES:
            O = merged(P, sig, a, b, low)
            line = f"   {lab:<32}"
            for blk, tag in ((res, "r"), (lock, "l")):
                idx = C.take(O, blk & good & (O["xb"] >= 0))
                r = O["R"][idx]
                pf = r[r > 0].sum() / abs(r[r < 0].sum()) if (r < 0).any() else np.nan
                line += f"{len(idx):>7}{r.mean():>+10.4f}{pf:>9.3f}"
                if tag == "r":
                    line += f"{'|':>4}"
                else:
                    p0 = bootstrap(r, P["sess"][O["sig"][idx]])[0]
                    line += f"{p0:>9.3f}"
            print(line)

        hdr(f"NQ {tf}m   THE HEAT SLOPE ITSELF, read on BOTH blocks -- is it a research artefact?")
        O = C.outcomes(P, 1, sig, stop_mult=2.0, tp_r=0.0)
        print(f"   {'quintile of ' + STATE:<28}{'RESEARCH':>34}{'|':>4}{'LOCKED':>30}")
        print(f"   {'':<28}{'n':>7}{'MAE p50':>10}{'MAE p90':>9}{'stop-out':>10}{'|':>4}"
              f"{'n':>7}{'MAE p50':>10}{'MAE p90':>9}{'stop-out':>10}")
        mae = np.empty(len(sig))
        mfe = np.empty(len(sig))
        from v22trade import _heat
        _heat(P["o"], P["h"], P["l"], sig, O["xb"], P["atr"], 1, mae, mfe)
        for q in range(5):
            lo_, hi_ = q / 5, (q + 1) / 5
            m = good & (s > lo_ - 1e-9) & (s <= hi_ + (1e-9 if q == 4 else 0)) & (s <= hi_)
            line = f"   {f'{lo_:.1f} - {hi_:.1f}':<28}"
            for blk in (res, lock):
                mm = m & blk & np.isfinite(mae)
                idx = C.take(O, mm)
                line += (f"{int(mm.sum()):>7}{np.nanquantile(mae[mm],.5):>10.2f}"
                         f"{np.nanquantile(mae[mm],.9):>9.2f}"
                         f"{(O['why'][idx]==C.STOP).mean():>10.1%}")
                if blk is res:
                    line += f"{'|':>4}"
            print(line)
