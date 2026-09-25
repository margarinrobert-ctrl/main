"""What a volatility state is worth ON REAL TRADES -- heat, and edge, both control-gated.

Part A of this study asked whether a volatility reading FORECASTS chop. This part asks the two
questions that actually spend money.

B. HEAT BY VOLATILITY DECILE. For every trade, the maximum adverse and maximum favourable
   excursion in ATR UNITS. If those quantiles are FLAT across volatility deciles then an ATR-sized
   stop is already volatility-adaptive and a VIX-like overlay adds nothing to stop placement; the
   ATR has done the scaling. If they slope, the slope is the size of the correction available.

D. EDGE BY VOLATILITY CONDITION, against a SELECTIVITY-MATCHED CONTROL. A restrictive filter
   raises profit factor by restrictiveness alone (STUDY_V12), so every condition is scored against
   random filters keeping the same number of signals, drawn from the same signal pool and put
   through the same position lock. The research block ranks; the locked block is read ONCE.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v22")
import v16core as C           # noqa: E402
import v22vol as V            # noqa: E402

TFS = (15, 30)
SIDE = 1
STOP = 2.0
NDRAW = 400
RUNGS = (10, 20, 30, 40, 50, 60, 70, 80, 90)


@njit(cache=True)
def _heat(o, h, l, sig, xb, atr, side, mae, mfe):
    for k in range(len(sig)):
        if xb[k] < 0:
            mae[k] = np.nan
            mfe[k] = np.nan
            continue
        eb = sig[k] + 1
        px = o[eb]
        a = atr[sig[k]]
        lo = px
        hi = px
        for j in range(eb, xb[k] + 1):
            if l[j] < lo:
                lo = l[j]
            if h[j] > hi:
                hi = h[j]
        if side > 0:
            mae[k] = (px - lo) / a
            mfe[k] = (hi - px) / a
        else:
            mae[k] = (hi - px) / a
            mfe[k] = (px - lo) / a


def blocks(sess, frac=0.65):
    u = np.unique(sess)
    return sess < u[int(len(u) * frac)], sess >= u[int(len(u) * frac)]


def hdr(t):
    print("\n" + "=" * 118)
    print(t)
    print("=" * 118)


def load(tf):
    P = C.prep(tf, entry_n=30, exit_n=20, cost_mult=1.44)
    sig = C.signals(P, SIDE)
    O = C.outcomes(P, SIDE, sig, stop_mult=STOP, tp_r=0.0)
    mae = np.empty(len(sig))
    mfe = np.empty(len(sig))
    _heat(P["o"], P["h"], P["l"], sig, O["xb"], P["atr"], SIDE, mae, mfe)
    F = V.build(P["o"], P["h"], P["l"], P["c"])
    # READ EVERY FEATURE AT THE SIGNAL BAR, NEVER AT THE FILL BAR (STUDY_AUCTION).
    Fs = {k: v[sig] for k, v in F.items()}
    res, lock = blocks(P["sess"])
    return P, sig, O, mae, mfe, Fs, res[sig], lock[sig]


def controls(O, pool, k, ndraw=NDRAW, seed=0):
    """ndraw random filters keeping k of the pool's signals, each through the position lock."""
    rng = np.random.default_rng(seed)
    n = len(O["sig"])
    out = np.empty(ndraw)
    cnt = np.empty(ndraw)
    for d in range(ndraw):
        keep = np.zeros(n, bool)
        keep[rng.choice(pool, size=k, replace=False)] = True
        idx = C.take(O, keep)
        out[d] = float(O["R"][idx].mean()) if len(idx) else np.nan
        cnt[d] = len(idx)
    return out, cnt


if __name__ == "__main__":
    D = {}
    for tf in TFS:
        D[tf] = load(tf)

    hdr("B. HEAT BY VOLATILITY DECILE -- MAE and MFE in ATR units, Donchian 30/20 long, 2.0N stop")
    print("   If an ATR stop already absorbs the volatility state, these columns are FLAT. The")
    print("   question is not whether high-vol bars move more in POINTS -- they must -- but whether")
    print("   they move more in units of their own ATR.\n")
    for tf in TFS:
        P, sig, O, mae, mfe, Fs, res, lock = D[tf]
        ok = np.isfinite(mae) & res
        for feat in ("pct_cc20_250", "ts_cc_5_60", "park_cc20"):
            x = Fs[feat]
            g = np.isfinite(x) & ok
            q = np.quantile(x[g], np.linspace(0, 1, 11))
            q[0] -= 1e-9
            dec = np.digitize(x, q) - 1
            print(f"   {tf}m   {feat}")
            print(f"      {'dec':>4}{'n':>7}{'MAE p50':>10}{'MAE p75':>10}{'MAE p90':>10}"
                  f"{'MFE p50':>10}{'MFE p90':>10}{'R/trade':>10}{'stop-out':>10}")
            for d in range(10):
                m = g & (dec == d)
                if m.sum() < 20:
                    continue
                idx = C.take(O, m)
                r = O["R"][idx]
                print(f"      {d+1:>4}{int(m.sum()):>7}{np.nanquantile(mae[m],.50):>10.2f}"
                      f"{np.nanquantile(mae[m],.75):>10.2f}{np.nanquantile(mae[m],.90):>10.2f}"
                      f"{np.nanquantile(mfe[m],.50):>10.2f}{np.nanquantile(mfe[m],.90):>10.2f}"
                      f"{(r.mean() if len(r) else np.nan):>+10.4f}"
                      f"{((O['why'][idx]==C.STOP).mean() if len(idx) else np.nan):>10.1%}")
            print()

    hdr("D. EDGE BY VOLATILITY CONDITION -- every feature x 9 rungs x 2 directions, control-gated")
    rows = []
    for tf in TFS:
        P, sig, O, mae, mfe, Fs, res, lock = D[tf]
        pool_r = np.flatnonzero(res & (O["xb"] >= 0))
        pool_l = np.flatnonzero(lock & (O["xb"] >= 0))
        base_r = C.take(O, res & (O["xb"] >= 0))
        base_l = C.take(O, lock & (O["xb"] >= 0))
        print(f"   {tf}m  research baseline {len(base_r)} trades {O['R'][base_r].mean():+.4f} R"
              f"   |  locked baseline {len(base_l)} trades {O['R'][base_l].mean():+.4f} R")
        # one control bank per selectivity rung, reused by every condition of that rung
        bank = {}
        for rung in RUNGS:
            k = max(10, int(round(len(pool_r) * rung / 100)))
            bank[rung] = controls(O, pool_r, k, seed=1000 + rung)[0]
        for name, x in Fs.items():
            g = np.isfinite(x)
            if g.mean() < 0.9:
                continue
            qs = np.quantile(x[g & res], np.array(RUNGS) / 100.0)
            for rung, thr in zip(RUNGS, qs):
                for sgn, lab in ((+1, ">="), (-1, "<=")):
                    m = (x >= thr) if sgn > 0 else (x <= thr)
                    sel = 100 - rung if sgn > 0 else rung
                    mr = m & g & res & (O["xb"] >= 0)
                    if mr.sum() < 40:
                        continue
                    ir = C.take(O, mr)
                    if len(ir) < 30:
                        continue
                    rr = float(O["R"][ir].mean())
                    b = bank[min(RUNGS, key=lambda z: abs(z - sel))]
                    b = b[np.isfinite(b)]
                    p = float((b >= rr).mean())
                    il = C.take(O, m & g & lock & (O["xb"] >= 0))
                    rl = float(O["R"][il].mean()) if len(il) >= 20 else np.nan
                    rows.append(dict(tf=tf, feat=name, dirn=lab, rung=rung, sel=sel,
                                     n=len(ir), R=rr, ctrl=float(b.mean()), exc=rr - float(b.mean()),
                                     p=p, n_lk=len(il), R_lk=rl,
                                     base_lk=float(O["R"][base_l].mean())))
    df = pd.DataFrame(rows)
    df["exc_lk"] = df.R_lk - df.base_lk
    df.to_csv("results/v22/v22_trade.csv", index=False)

    print(f"\n   {len(df)} scorable conditions. At alpha 0.05 against the matched control,"
          f" {0.05*len(df):.0f} pass by chance;")
    print(f"   observed {int((df.p <= 0.05).sum())}.  Share of the whole population beating its"
          f" own control at all: {float((df.exc > 0).mean()):.1%}")

    hdr("   TOP 50 BY CONTROL EXCESS ON RESEARCH -- the locked read is attached, not selected on")
    top = df.sort_values("exc", ascending=False).head(50)
    print(f"   {'#':>3} {'feature':<18}{'dir':>4}{'rung':>6}{'tf':>5}{'n':>6}{'R/trade':>10}"
          f"{'ctrl':>9}{'excess':>9}{'p':>7}{'|':>3}{'n':>6}{'LOCKED R':>10}{'vs base':>9}")
    for i, (_, r) in enumerate(top.iterrows(), 1):
        print(f"   {i:>3} {r.feat:<18}{r.dirn:>4}{r.rung:>6}{r.tf:>4}m{int(r.n):>6}{r.R:>+10.4f}"
              f"{r.ctrl:>+9.4f}{r.exc:>+9.4f}{r.p:>7.3f}{'|':>3}{int(r.n_lk):>6}"
              f"{r.R_lk:>+10.4f}{r.exc_lk:>+9.4f}")
    print(f"\n   Of these 50, {int((top.exc_lk > 0).sum())} beat the unfiltered baseline out of"
          f" sample. Chance is 50%.")
    print(f"   Research excess vs locked excess, correlation over all {len(df)} conditions:"
          f" {np.corrcoef(df.dropna(subset=['exc_lk']).exc, df.dropna(subset=['exc_lk']).exc_lk)[0,1]:+.3f}")

    hdr("   BY FAMILY -- the marginal average, never the top cell")
    def fam(n):
        return ("chop ratio" if n.startswith(("park_cc", "rs_cc", "gk_cc"))
                else "term structure" if n.startswith("ts_")
                else "state" if n.startswith(("pct", "z_"))
                else "vol of vol" if n.startswith(("vov", "accel"))
                else "semivariance" if n.startswith("semi") else "level")
    df["family"] = df.feat.map(fam)
    g = df.groupby("family").agg(n=("exc", "size"), exc=("exc", "mean"),
                                 pos=("exc", lambda x: float((x > 0).mean())),
                                 exc_lk=("exc_lk", "mean"),
                                 pos_lk=("exc_lk", lambda x: float((x > 0).mean())))
    print(f"   {'family':<18}{'cells':>7}{'mean excess':>14}{'% > ctrl':>11}"
          f"{'mean lk excess':>17}{'% > base lk':>13}")
    for k, r in g.sort_values("exc", ascending=False).iterrows():
        print(f"   {k:<18}{int(r.n):>7}{r.exc:>+14.4f}{r.pos:>10.0%}{r.exc_lk:>+17.4f}"
              f"{r.pos_lk:>12.0%}")
