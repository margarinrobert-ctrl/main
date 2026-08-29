"""Portfolio combination: lowest correlation x highest Monte-Carlo mean/PF.

SELECTION USES THE RESEARCH BLOCK ONLY. Choosing legs on locked-block means or
locked-block correlation would put the holdout inside the selection, which is the
first rule in CLAUDE.md. The locked evaluation at the end is a SECOND look at the
holdout and is labelled as such.

Sizing follows the house rule: fixed one contract per leg, aggregated across legs
(no leg-level scaling, no optimiser on the weights).

Doctrine being tested (CLAUDE.md): "A decorrelated leg still has to have an edge.
Adding a coin-flip signal at |rho| 0.25 raised the book's net profit, cut its
Sharpe 3.73 -> 3.23 and more than doubled its drawdown. A correlation matrix
alone will talk you into that trade."
"""
import numpy as np, pandas as pd, itertools
import lab
from reveal import rules

NDRAW = 10000
PTVAL = {"NAS": 1.0, "US30": 1.0}      # both reported in index points


def legs():
    out = {}
    for sym in ("NAS", "US30"):
        df, w, r, h, rr = rules(sym)
        for name, (idx, side, sm, tm) in rr.items():
            bk = lab.book(sym, idx, side, stop_mult=sm, targ_mult=tm)
            bk = bk.assign(date=df.date.values[bk.sig_bar.values])
            key = f"{sym}|{name.split()[0]}"
            out[key] = dict(sym=sym, rule=name.split()[0],
                            res=bk[np.isin(bk.sig_bar, np.where(r)[0])].copy(),
                            lok=bk[np.isin(bk.sig_bar, np.where(h)[0])].copy())
    return out


def mc_stats(net, n=NDRAW, seed=0):
    """Bootstrap mean AND profit factor."""
    r = np.random.default_rng(seed); m = len(net)
    if m < 5: return None
    idx = r.integers(0, m, size=(n, m))
    S = net[idx]
    mean = S.mean(1)
    win = np.where(S > 0, S, 0).sum(1)
    los = -np.where(S <= 0, S, 0).sum(1)
    pf = np.where(los > 0, win / np.maximum(los, 1e-9), np.nan)
    return dict(mean=mean.mean(), mean_lo=np.percentile(mean, 2.5),
                mean_hi=np.percentile(mean, 97.5), p_pos=(mean > 0).mean(),
                pf=np.nanmean(pf), pf_lo=np.nanpercentile(pf, 2.5),
                pf_hi=np.nanpercentile(pf, 97.5), p_pf1=np.nanmean(pf > 1.0))


def daily(book_map, blk):
    s = {}
    for k, v in book_map.items():
        b = v[blk]
        if len(b) < 5: continue
        s[k] = b.groupby("date").net.sum()
    M = pd.DataFrame(s).fillna(0.0)
    return M[(M != 0).any(axis=1)]


if __name__ == "__main__":
    L = legs()
    print("=" * 116)
    print("STEP 1 - per-leg Monte Carlo on the RESEARCH BLOCK ONLY (selection input)")
    print("=" * 116)
    print(f"  {'leg':<12} {'n':>5} {'MC mean':>9} {'mean 95% CI':>20} {'P(m>0)':>8} "
          f"{'MC PF':>7} {'PF 95% CI':>16} {'P(PF>1)':>8}")
    st = {}
    for i, (k, v) in enumerate(L.items()):
        net = v["res"].net.values.astype(float)
        s = mc_stats(net, seed=10 + i)
        if s is None: continue
        st[k] = s
        print(f"  {k:<12} {len(net):>5} {s['mean']:>+9.2f} [{s['mean_lo']:>+8.2f},{s['mean_hi']:>+8.2f}] "
              f"{s['p_pos']:>8.3f} {s['pf']:>7.3f} [{s['pf_lo']:>6.3f},{s['pf_hi']:>6.3f}] {s['p_pf1']:>8.3f}")

    Mres = daily(L, "res"); Cres = Mres.corr()
    print("\n" + "=" * 116)
    print("STEP 2 - candidate legs: MC mean > 0 AND MC PF > 1 on research")
    print("=" * 116)
    cand = [k for k in st if st[k]["mean"] > 0 and st[k]["pf"] > 1.0]
    for k in st:
        mark = "KEEP" if k in cand else "drop"
        print(f"  {mark}  {k:<12} mean {st[k]['mean']:>+6.2f}  PF {st[k]['pf']:>5.3f}")
    print(f"\n  {len(cand)} legs qualify: {cand}")
    if len(cand) < 2:
        print("  Fewer than two qualifying legs - no combination is possible."); raise SystemExit

    print("\n  pairwise RESEARCH correlation among qualifying legs:")
    sub = Cres.loc[cand, cand]
    print("   " + "".join(f"{c:>14}" for c in cand))
    for a in cand:
        print(f"  {a:<12}" + "".join(f"{sub.loc[a,b]:>14.3f}" for b in cand))

    print("\n" + "=" * 116)
    print("STEP 3 - every subset of the qualifying legs, ranked by RESEARCH Sharpe")
    print("  Equal weight, one contract per leg, aggregated daily (house sizing rule).")
    print("=" * 116)
    rows = []
    for rsz in range(1, len(cand) + 1):
        for combo in itertools.combinations(cand, rsz):
            # SAME day universe for every subset, so Sharpe is comparable:
            # you hold the portfolio every session; a leg that does not trade
            # contributes 0 that day. Filtering zeros for k=1 only would inflate
            # single-leg Sharpe against the combinations.
            d = Mres[list(combo)].sum(axis=1)
            if len(d) < 30: continue
            sd = d.std(ddof=1)
            sh = d.mean() / sd * np.sqrt(252) if sd > 0 else 0
            eq = d.cumsum(); mdd = float((np.maximum.accumulate(eq) - eq).max())
            wn = d[d > 0].sum(); ls = -d[d < 0].sum()
            pf = wn / ls if ls > 0 else np.inf
            mx = sub.loc[list(combo), list(combo)].values
            maxr = (mx[~np.eye(len(combo), dtype=bool)].max() if len(combo) > 1 else 0.0)
            rows.append(dict(legs="+".join(c.replace("|", "") for c in combo), k=len(combo),
                             days=len(d), mean_day=d.mean(), total=d.sum(), pf=pf,
                             sharpe=sh, mdd=mdd, max_pair_r=maxr))
    R = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    print(f"  {'legs':<28} {'k':>2} {'days':>5} {'mean/day':>9} {'total':>9} {'PF':>6} "
          f"{'Sharpe':>7} {'MDD':>8} {'max r':>7}")
    for _, x in R.head(12).iterrows():
        print(f"  {x.legs:<28} {int(x.k):>2} {int(x.days):>5} {x.mean_day:>+9.2f} {x.total:>+9.0f} "
              f"{x.pf:>6.3f} {x.sharpe:>7.2f} {x.mdd:>8.0f} {x.max_pair_r:>7.3f}")
    R.to_csv("/home/user/main/docs/donchian/combine_research.csv", index=False)

    best = R.iloc[0]
    lowest = R[R.k > 1].sort_values("max_pair_r").iloc[0]
    print(f"\n  highest research Sharpe : {best.legs} (Sharpe {best.sharpe:.2f}, max pair r {best.max_pair_r:.3f})")
    print(f"  lowest max correlation  : {lowest.legs} (max pair r {lowest.max_pair_r:.3f}, Sharpe {lowest.sharpe:.2f})")
    np.save("/home/user/main/data/donchian/_combo.npy",
            np.array([best.legs, lowest.legs], dtype=object), allow_pickle=True)
