"""Monte Carlo over the eight studies: 10,000 draws each, plus the correlation matrix.

Two distinct Monte Carlos, because they answer different questions:
  1. BOOTSTRAP (resample trades WITH replacement) -> the sampling distribution of
     the MEAN. This is the one that says whether the observed expectancy is
     distinguishable from zero.
  2. PERMUTATION (reshuffle trade ORDER) -> the distribution of DRAWDOWN. Total
     P&L is invariant to ordering, so only path statistics move here.

CORRELATION MATRIX is built on SESSION-ALIGNED net P&L, not on the trade lists:
the books have different trade counts and different bars, so the only common
index is the calendar session. Sessions with no trade contribute 0. Within an
instrument D and E are strict subsets of A, so high correlation is expected and
is exactly what tells us these are not independent tests.
"""
import numpy as np, pandas as pd
from engine import atr as _atr, true_range
import lab, data as D
from reveal import rules, state

NDRAW = 10000
rng = np.random.default_rng(20260829)


def books():
    """The eight studies, as (label, instrument, block, trade frame)."""
    out = []
    for sym in ("NAS", "US30"):
        df, w, r, h, rr = rules(sym)
        for name, (idx, side, sm, tm) in rr.items():
            bk = lab.book(sym, idx, side, stop_mult=sm, targ_mult=tm)
            sess = df.sess.values; date = df.date.values
            for blk, mask in (("research", r), ("locked", h)):
                sel = np.isin(bk.sig_bar, np.where(mask)[0])
                b = bk[sel].copy()
                b["sess"] = sess[b.sig_bar.values]
                b["date"] = date[b.sig_bar.values]
                out.append((f"{sym}|{name.split()[0]}", sym, blk, b))
    return out


def boot_mean(net, n=NDRAW, seed=0):
    r = np.random.default_rng(seed)
    m = len(net)
    if m < 5: return None
    idx = r.integers(0, m, size=(n, m))
    return net[idx].mean(1)


def perm_mdd(net, n=NDRAW, seed=0):
    r = np.random.default_rng(seed)
    out = np.empty(n)
    for i in range(n):
        eq = np.cumsum(r.permutation(net))
        out[i] = (np.maximum.accumulate(eq) - eq).max()
    return out


if __name__ == "__main__":
    B = books()
    print("=" * 122)
    print(f"MONTE CARLO - {NDRAW:,} draws per study")
    print("  bootstrap resamples trades with replacement -> distribution of the MEAN")
    print("  permutation reshuffles trade order -> distribution of DRAWDOWN (total P&L is order-invariant)")
    print("=" * 122)
    hdr = (f"  {'study':<22} {'block':<9} {'n':>5} {'obs mean':>9} {'boot mean':>10} {'boot sd':>8} "
           f"{'95% CI':>20} {'P(mean>0)':>10} {'med MDD':>9} {'p95 MDD':>9}")
    print(hdr); print("  " + "-" * 118)
    rows = []
    for k, (lab_, sym, blk, b) in enumerate(B):
        net = b.net.values.astype(float)
        if len(net) < 5:
            print(f"  {lab_:<22} {blk:<9} {len(net):>5}   too few trades"); continue
        bm = boot_mean(net, seed=100 + k)
        md = perm_mdd(net, n=2000, seed=200 + k)
        lo, hi = np.percentile(bm, [2.5, 97.5])
        rows.append(dict(study=lab_, block=blk, n=len(net), obs=net.mean(),
                         boot=bm.mean(), sd=bm.std(ddof=1), lo=lo, hi=hi,
                         p_pos=(bm > 0).mean(), mdd=np.median(md), mdd95=np.percentile(md, 95)))
        print(f"  {lab_:<22} {blk:<9} {len(net):>5} {net.mean():>+9.2f} {bm.mean():>+10.2f} "
              f"{bm.std(ddof=1):>8.2f} [{lo:>+8.2f},{hi:>+8.2f}] {(bm>0).mean():>10.3f} "
              f"{np.median(md):>9,.0f} {np.percentile(md,95):>9,.0f}")
    R = pd.DataFrame(rows)
    R.to_csv("/home/user/main/docs/donchian/montecarlo.csv", index=False)

    # ---------------------------------------------------------------- correlation
    for blk in ("research", "locked"):
        sel = [(l, b) for (l, s, bl, b) in B if bl == blk]
        if not sel: continue
        ser = {}
        for l, b in sel:
            if len(b) < 5: continue
            ser[l] = b.groupby("date").net.sum()
        M = pd.DataFrame(ser).fillna(0.0)
        # keep only dates where at least one study traded
        M = M[(M != 0).any(axis=1)]
        C = M.corr()
        print("\n" + "=" * 122)
        print(f"CORRELATION MATRIX - session-aligned daily net P&L, {blk.upper()} block "
              f"({len(M):,} sessions with at least one trade)")
        print("=" * 122)
        cols = list(C.columns)
        print("  " + " " * 22 + "".join(f"{c.split('|')[0][:3]+' '+c.split('|')[1]:>12}" for c in cols))
        for i, a in enumerate(cols):
            line = f"  {a:<22}"
            for j, bnm in enumerate(cols):
                v = C.loc[a, bnm]
                line += f"{v:>12.3f}" if i != j else f"{'1.000':>12}"
            print(line)
        off = C.values[~np.eye(len(C), dtype=bool)]
        print(f"\n  mean |off-diagonal| = {np.abs(off).mean():.3f}   max = {off.max():.3f}   min = {off.min():.3f}")
        # within-instrument vs cross-instrument
        wi, xi = [], []
        for i, a in enumerate(cols):
            for j, bnm in enumerate(cols):
                if j <= i: continue
                (wi if a.split("|")[0] == bnm.split("|")[0] else xi).append(C.loc[a, bnm])
        print(f"  within-instrument mean r = {np.mean(wi):.3f}   cross-instrument mean r = {np.mean(xi):.3f}")
        C.to_csv(f"/home/user/main/docs/donchian/corr_{blk}.csv")
    print("\n  written: docs/donchian/montecarlo.csv, corr_research.csv, corr_locked.csv")
