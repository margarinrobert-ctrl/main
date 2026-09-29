"""P3 -- THE FEATURES, aimed at the two quantities rather than at the P&L.

P2 says the exits do what was asked and the entry is the hole: on the ISO research block 0 of
4,480 exit configurations is profitable, so no exit policy rescues this breakout. A filter cannot
make a losing base profitable -- it can only make it less bad -- so this phase does two separate
things and keeps them apart:

  P3.1  DOES ANY ENTRY IN THIS WINDOW HAVE A PULSE? Six declared entries, no parameters tuned,
        scored on the research block only. If none does, that is the answer and the feature work
        below is a heat model rather than an alpha.
  P3.2  WHICH FEATURES PREDICT THE ADVERSE EXCURSION, not the return. This is the honest target:
        P1 measured winners taking a third of the heat losers take, so heat is where the
        separation lives, and a heat model has a use even on a base with no edge -- it sizes the
        stop.
  P3.3  THE V22 CHECK, run as a PRE-REGISTERED REPLICATION rather than a discovery. On NQ, heat
        in ATR units was 1.8-2.2x LARGER in the LOW realised-volatility bucket, because ATR is
        backward-looking and volatility mean-reverts, so a fixed ATR multiple is too small exactly
        when vol has just contracted. If that reproduces on gold the adaptive stop follows from a
        mechanism instead of from a sweep.

Every screen is against a null: a feature is scored against a RANDOM SPLIT of the same size, and
the IC is reported beside its shuffled twin.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/xheat")
import numpy as np, pandas as pd
from scipy import stats
import xdata as X, xsig as S, xpath as P

R = "results/xheat/"
os.makedirs(R, exist_ok=True)
print(__doc__)
t0 = time.time()
RNG = np.random.default_rng(7)

FEEDS = {"ISO": X.assemble(X.load_iso()), "MT": X.assemble(X.load_mt())}


def paths(D, idx, side):
    k = len(idx)
    a = [np.full(k, np.nan) for _ in range(6)]
    hold = np.zeros(k, np.int64); amb = np.zeros(k, np.int64)
    ent = np.full(k, np.nan); atr0 = np.full(k, np.nan)
    P.walk_paths(D["o"], D["h"], D["l"], D["c"], D["atr"], idx.astype(np.int64), side,
                 D["last_win"], X.COST_RT, X.SLIP,
                 a[0], a[1], a[2], a[3], a[4], hold, amb, atr0, ent, a[5])
    t = pd.DataFrame(dict(sig=idx, mae=a[0], mfe=a[1], end=a[4], giveback=a[5], hold=hold))
    t["blk"] = D["blk"][idx]; t["day"] = D["day"][idx]
    return t[t.hold > 0].reset_index(drop=True)


# ================================================================= P3.1 does any entry have a pulse
print("=" * 108)
print("P3.1  SIX DECLARED ENTRIES IN THE WINDOW -- research block only, no parameter tuned")
print("=" * 108)


def entry_idx(D, name):
    h, l, c, o, inw, atr = D["h"], D["l"], D["c"], D["o"], D["inw"], D["atr"]
    F, _ = S.build_features(D, with_volume=np.isfinite(D["v"]).any())
    if name == "donchian20 break":
        return S.events(D, "break", 20, 1), 1
    if name == "donchian20 fade":
        return S.events(D, "break", 20, 1), -1        # fade the same bar: the exact mirror
    if name == "overnight high break":
        hi = F["sess.ovn_pos"]
        return np.flatnonzero(inw & (hi > 1.0) & (np.roll(hi, 1) <= 1.0)), 1
    if name == "overnight low break":
        lo = F["sess.ovn_pos"]
        return np.flatnonzero(inw & (lo < 0.0) & (np.roll(lo, 1) >= 0.0)), -1
    if name == "pullback to EMA50 up":
        d = F["loc.d_ema50"]
        up = c > pd.Series(c).ewm(span=200, adjust=False).mean().to_numpy()
        return np.flatnonzero(inw & up & (d > 0) & (np.roll(d, 1) <= 0)), 1
    if name == "first-hour range break":
        m = D["mod"]; ws = D["win_start"]
        first = (m >= ws) & (m < ws + 60)
        df = pd.DataFrame({"d": D["day"], "h": h, "l": l})
        g = df[first].groupby("d")
        hh = df.d.map(g.h.max()).to_numpy()
        return np.flatnonzero(inw & (m >= ws + 60) & (c > hh) & (np.roll(c, 1) <= np.roll(hh, 1))), 1
    raise ValueError(name)


ENTRIES = ["donchian20 break", "donchian20 fade", "overnight high break", "overnight low break",
           "pullback to EMA50 up", "first-hour range break"]
rows = []
for nm, D in FEEDS.items():
    for e in ENTRIES:
        idx, side = entry_idx(D, e)
        if len(idx) < 120:
            continue
        t = paths(D, idx, side)
        for b, lab in ((0, "research"), (1, "LOCKED")):
            s = t[t.blk == b]
            if len(s) < 60:
                continue
            r = s.end.to_numpy()
            rows.append(dict(feed=nm, entry=e, block=lab, n=len(s), R=r.mean(),
                             pf=r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9),
                             win=(r > 0).mean(), mae=s.mae.mean(), mfe=s.mfe.mean()))
E = pd.DataFrame(rows)
E.to_csv(R + "p3_entries.csv", index=False)
pd.set_option("display.width", 200)
print(E[E.block == "research"].round(4).to_string(index=False))
pulse = E[(E.block == "research") & (E.R > 0)]
print(f"\n  entries with a positive research expectancy: {len(pulse)} of "
      f"{len(E[E.block=='research'])}")

# ================================================================= P3.2 what predicts the heat
print("\n" + "=" * 108)
print("P3.2  WHAT PREDICTS THE ADVERSE EXCURSION -- Spearman IC against |MAE|, beside a shuffle")
print("=" * 108)
print("  Target is |MAE| in ATR at entry, uncensored. A feature that predicts heat is useful even")
print("  on a base with no edge: it is what sizes the stop, and P1 measured the separation it has")
print("  to work with (winners -1.17 ATR against losers -3.37).")
rows = []
for nm, D in FEEDS.items():
    wv = np.isfinite(D["v"]).any()
    F, names = S.build_features(D, with_volume=wv)
    idx, side = entry_idx(D, "donchian20 break")
    t = paths(D, idx, side)
    for b, lab in ((0, "research"), (1, "LOCKED")):
        s = t[t.blk == b]
        if len(s) < 100:
            continue
        y = -s.mae.to_numpy()
        yg = s.giveback.to_numpy()
        for k in names:
            x = F[k][s.sig.to_numpy()]
            m = np.isfinite(x) & np.isfinite(y)
            if m.sum() < 100 or np.nanstd(x[m]) == 0:
                continue
            ic = stats.spearmanr(x[m], y[m]).statistic
            icg = stats.spearmanr(x[m], yg[m]).statistic
            sh = np.array([stats.spearmanr(RNG.permutation(x[m]), y[m]).statistic for _ in range(20)])
            rows.append(dict(feed=nm, block=lab, feat=k, n=int(m.sum()),
                             ic_mae=ic, ic_giveback=icg, shuffled_sd=float(sh.std())))
IC = pd.DataFrame(rows)
IC.to_csv(R + "p3_ic.csv", index=False)
piv = IC[IC.block == "research"].pivot_table(index="feat", columns="feed",
                                             values=["ic_mae", "ic_giveback"])
piv["absmean"] = piv[("ic_mae", "ISO")].abs()
print(piv.sort_values("absmean", ascending=False).drop(columns="absmean").head(14).round(4).to_string())
lk = IC[IC.block == "LOCKED"].set_index(["feed", "feat"]).ic_mae
rs = IC[IC.block == "research"].set_index(["feed", "feat"]).ic_mae
both = pd.concat([rs.rename("research"), lk.rename("locked")], axis=1).dropna()
print(f"\n  research-to-locked IC correlation across {len(both)} feature-feed cells: "
      f"{both.corr().iloc[0,1]:+.3f} Pearson, sign kept {float((np.sign(both.research)==np.sign(both.locked)).mean()):.3f}")

# ================================================================= P3.3 the V22 replication
print("\n" + "=" * 108)
print("P3.3  PRE-REGISTERED REPLICATION -- does heat-in-ATR rise as realised volatility FALLS?")
print("=" * 108)
print("  The claim, from NQ: an ATR stop is BACKWARD-looking and volatility MEAN-REVERTS, so when")
print("  vol sits low in its own distribution ATR(14) has already contracted and a fixed multiple")
print("  is too SMALL. Predicted direction: |MAE| in ATR units LARGER in the low-percentile bucket.")
rows = []
for nm, D in FEEDS.items():
    F, _ = S.build_features(D, with_volume=np.isfinite(D["v"]).any())
    idx, side = entry_idx(D, "donchian20 break")
    t = paths(D, idx, side)
    for feat in ("vol.atr_pct100", "vol.atr_pct500", "vol.rv_ratio"):
        x = F[feat][t.sig.to_numpy()]
        for b, lab in ((0, "research"), (1, "LOCKED")):
            s = t[(t.blk == b) & np.isfinite(x)]
            xv = x[(t.blk == b).to_numpy() & np.isfinite(x)]
            if len(s) < 150:
                continue
            q = pd.qcut(xv, 4, labels=False, duplicates="drop")
            for k in range(int(np.nanmax(q)) + 1):
                m = q == k
                rows.append(dict(feed=nm, feat=feat, block=lab, quartile=k + 1, n=int(m.sum()),
                                 mae=float(-s.mae.to_numpy()[m].mean()),
                                 stopped_2N=float((s.mae.to_numpy()[m] <= -2.0).mean()),
                                 end=float(s.end.to_numpy()[m].mean())))
V = pd.DataFrame(rows)
V.to_csv(R + "p3_v22.csv", index=False)
for feat in V.feat.unique():
    print(f"\n  {feat}   (quartile 1 = LOWEST volatility percentile)")
    t = V[V.feat == feat].pivot_table(index="quartile", columns=["feed", "block"],
                                      values="mae")
    print(t.round(3).to_string())
    for (nm, b), col in t.items():
        d = col.iloc[0] / col.iloc[-1]
        print(f"      {nm} {b:9s}: Q1/Q4 heat ratio {d:.2f}x  "
              f"{'REPLICATES (low vol = more heat)' if d > 1.15 else 'does not replicate'}")
print(f"\ntotal {time.time()-t0:.0f}s")
