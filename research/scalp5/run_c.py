"""C -- the marginal-consensus geometry, the five as a BOOK, and one locked read.

B's marginals are unanimous and they all say the same thing: Sharpe rises monotonically as the
stop WIDENS (1.0N -1.89 to 3.0N -0.70), NO TAKE PROFIT is the best target rung, and the breakeven
and trail each help slightly. That is the marginal consensus, and this branch reads a grid by its
marginal average and never by its top row -- the top row is the maximum of 160 draws per design.

So all five are given the SAME geometry, chosen by that consensus and not per design:
    stop 3.0 x ATR, NO take profit, breakeven to +0.25R at 1R, trail armed at 1R one R behind,
    flat at 11:00, one position at a time.

Then the part the five were designed for. Their daily P&L correlates |0.046| on average, so a book
is not five names for one strategy -- and a portfolio of near-independent legs is where Sharpe
actually comes from. The book is equal-weight, one unit a leg, no optimisation of the weights.

ONE LOCKED READ, with the trial count stated: 800 geometry cells were scored in B and the
geometry here was chosen from their marginals, so the multiplicity is 800 plus the five design
specifications. Nothing is deflated as a discovery unless it survives its control first.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5")
import numpy as np, pandas as pd
import s5data as S, s5sig as SG, s5walk as W

R = "results/scalp5/"
os.makedirs(R, exist_ok=True)
print(__doc__)
t0 = time.time()
RNG = np.random.default_rng(17)
GEOM = dict(stop=3.0, tgt=0.0, be=1.0, be_off=0.25, arm=1.0, tr=1.0)
base = S.load_1m()


def walk(D, lg, sh, g=GEOM):
    sig = lg | sh
    side = np.where(lg, 1, np.where(sh, -1, 0)).astype(np.int64)
    cap = int(sig.sum()) + 4
    a = [np.zeros(cap, np.int64), np.zeros(cap, np.int64)]
    b = [np.full(cap, np.nan) for _ in range(4)]
    w = np.zeros(cap, np.int64); am = np.zeros(cap, np.int64)
    k = W.walk(D["o"], D["h"], D["l"], D["c"], D["atr"], sig, side, D["last_win"],
               S.RT_POINTS, S.SLIP_POINTS, g["stop"], g["tgt"], g["be"], g["be_off"],
               g["arm"], g["tr"], a[0], a[1], b[0], b[1], w, b[2], b[3], am)
    t = pd.DataFrame(dict(sig=a[0][:k], exit=a[1][:k], R=b[0][:k], pts=b[1][:k], why=w[:k],
                          mae=b[2][:k], mfe=b[3][:k]))
    t["side"] = side[t.sig.to_numpy()]
    t["blk"] = D["blk"][t.sig.to_numpy()]
    t["day"] = D["day"][t.sig.to_numpy()]
    return t


def control(D, n_target, side_mix, blk, draws=400):
    elig = np.flatnonzero(D["inw"])
    rate = min(1.0, n_target / max(len(elig), 1))
    out = np.empty(draws)
    for i in range(draws):
        m = np.zeros(D["n"], bool)
        m[elig[RNG.random(len(elig)) < rate]] = True
        sd = RNG.random(D["n"]) < side_mix
        t = walk(D, m & sd, m & ~sd)
        s = t[t.blk == blk]
        out[i] = s.pts.mean() if len(s) else np.nan
    return out


def day_boot(days, pts, all_days, n=2000):
    s = pd.Series(pts).groupby(pd.Series(days)).sum()
    full = pd.Series(0.0, index=pd.Index(all_days)); full.loc[s.index] = s.to_numpy()
    v = full.to_numpy(); out = np.empty(n)
    for i in range(n):
        out[i] = v[RNG.integers(0, len(v), len(v))].mean()
    return out


TF = 5
f = S.resample(base, TF)
D = S.assemble(f, TF)
F = SG.build(D, base)
DAYS = {0: D["all_days"][D["all_days"] < D["cut_day"]], 1: D["all_days"][D["all_days"] >= D["cut_day"]]}
print(f"NQ {TF}m  {D['n']:,} bars  {D['n_sessions']} window sessions  "
      f"research to {D['cut_date']} ({len(DAYS[0])} days), locked {len(DAYS[1])} days")

rows, legs = [], {}
for nm, (fn, p) in SG.DESIGNS.items():
    lg, sh = fn(D, F, p)
    t = walk(D, lg, sh)
    legs[nm] = t
    side_mix = float(lg.sum() / max((lg | sh).sum(), 1))
    for b, lab in ((0, "research"), (1, "LOCKED")):
        s = t[t.blk == b]
        if len(s) < 25:
            continue
        pts = s.pts.to_numpy(); r = s.R.to_numpy()
        shp, daily = S.day_sharpe(s.day.to_numpy(), pts, DAYS[b])
        ctl = control(D, len(s), side_mix, b)
        bs = day_boot(s.day.to_numpy(), pts, DAYS[b])
        eq = np.cumsum(daily.to_numpy())
        rows.append(dict(design=nm, block=lab, n=len(s),
                         per_yr=len(s) / (len(DAYS[b]) / 252),
                         EV=pts.mean(), R=r.mean(),
                         pf=r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9),
                         win=(r > 0).mean(), sharpe=shp,
                         hold_min=(s.exit - s.sig).mean() * TF,
                         dd=float(np.max(np.maximum.accumulate(eq) - eq)),
                         ctl=float(np.nanmedian(ctl)), p_ctl=float(np.nanmean(ctl >= pts.mean())),
                         boot_p=float((bs <= 0).mean())))
C = pd.DataFrame(rows)
C.to_csv(R + "c_legs.csv", index=False)
pd.set_option("display.width", 230); pd.set_option("display.max_columns", 30)
print("\n" + "=" * 112)
print("C.1  THE FIVE AT THE MARGINAL-CONSENSUS GEOMETRY  (3.0N stop, no target, BE+trail, flat 11:00)")
print("=" * 112)
print(C.round(4).to_string(index=False))
print("\n  `ctl` is what a RANDOM entry in the same window at the same rate and geometry earns.")
print("  `p_ctl` is the share of 400 control draws that beat the design. `boot_p` is a day")
print("  bootstrap against ZERO -- two different questions, and a leg can pass one and fail the other.")

# ---------------------------------------------------------------- the book
print("\n" + "=" * 112)
print("C.2  THE BOOK -- equal weight, one unit a leg, no weight optimisation")
print("=" * 112)
rows = []
for b, lab in ((0, "research"), (1, "LOCKED")):
    dl = {}
    for nm, t in legs.items():
        s = t[t.blk == b]
        _, d = S.day_sharpe(s.day.to_numpy(), s.pts.to_numpy(), DAYS[b])
        dl[nm] = d
    P = pd.DataFrame(dl)
    tot = P.sum(axis=1)
    eq = tot.cumsum().to_numpy()
    sd = tot.std(ddof=1)
    shp = float(tot.mean() / sd * np.sqrt(252)) if sd > 0 else np.nan
    ntr = sum(int((t.blk == b).sum()) for t in legs.values())
    pos = tot[tot > 0].sum(); neg = -tot[tot < 0].sum()
    rows.append(dict(block=lab, days=len(P), trades=ntr, per_yr=ntr / (len(P) / 252),
                     EV_per_trade=tot.sum() / max(ntr, 1), pts_per_day=tot.mean(),
                     sharpe=shp, pf=pos / max(neg, 1e-9),
                     dd=float(np.max(np.maximum.accumulate(eq) - eq)),
                     ret_dd=float(tot.sum() / max(np.max(np.maximum.accumulate(eq) - eq), 1e-9)),
                     best_leg_sharpe=float(C[C.block == lab].sharpe.max())))
    if b == 0:
        Pres = P
B = pd.DataFrame(rows)
B.to_csv(R + "c_book.csv", index=False)
print(B.round(4).to_string(index=False))
print("\n  correlation of the five legs' DAILY P&L (research):")
print(Pres.corr().round(3).to_string())
off = Pres.corr().to_numpy()[np.triu_indices(5, 1)]
print(f"  mean |rho| {np.abs(off).mean():.3f}   max {np.abs(off).max():.3f}")
print(f"\ntotal {time.time()-t0:.0f}s")
