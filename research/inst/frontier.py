"""PF 2.0 at 200+ trades a year, intraday: the arithmetic, then the EMPIRICAL FRONTIER over the
largest verified configuration space on this branch (the V61 exit tensor: Donchian entry x
channel exit x ATR stop x target x hold x adaptive stop x CVD gate x MA200 floor x CHOP x
prior-session-high), with INTRADAY hold caps added and entries confined to RTH, on NQ 5/15/30m.
Research block only for the frontier; the envelope cells are then read ONCE on locked with the
multiplicity stated. Then the deflated Sharpe of the best research cell at the trial count."""
import os, sys, warnings, math
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56"):
    sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V
import v53abs as A
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 126 + f"\n{t}\n" + "=" * 126)

def signal_sets(D, mask):
    h, n = D["h"], D["n"]
    base = np.asarray(h > D["ent_hi"][min(V.ENTS)], bool).copy()
    base[:1000] = False; base[-(500 + 5):] = False
    base &= np.isfinite(D["atr"]) & (D["atr"] > 0) & np.isfinite(D["vpct"]) & mask
    rows = np.flatnonzero(base)
    ent_m = {e: np.asarray(h[rows] > D["ent_hi"][e][rows], bool) for e in V.ENTS}
    cvd_m = {(0, 0): np.ones(len(rows), bool)}
    for k in V.KS:
        es = D["pats"][k][0]
        for w in V.WS:
            cvd_m[(k, w)] = A.recent(es, w)[rows]
    dm, ch, ps, c = D["d_ma"][rows], D["chop"][rows], D["psh"][rows], D["c"][rows]
    offs = [0]; vals = []; keys = []
    for e in V.ENTS:
        for ck in cvd_m:
            for ma in V.MA200:
                for cp in V.CHOPS:
                    for pg in V.PSH:
                        m = ent_m[e] & cvd_m[ck]
                        if ma > -50: m = m & np.isfinite(dm) & (dm >= ma)
                        if cp < 90: m = m & np.isfinite(ch) & (ch <= cp)
                        if pg: m = m & np.isfinite(ps) & (c > ps)
                        idx = np.flatnonzero(m); vals.append(idx); offs.append(offs[-1] + len(idx))
                        keys.append(dict(ent=e, k=ck[0], w=ck[1], ma=ma, chop=cp, psh=pg))
    return rows, np.asarray(offs, np.int64), np.concatenate(vals).astype(np.int64), pd.DataFrame(keys)

def geometry(tf):
    bars_per_hour = 60 // tf
    holds = {"2h": 2 * bars_per_hour, "4h": 4 * bars_per_hour, "6.5h": int(6.5 * bars_per_hour), "swing": 480}
    rows = []
    for ei, e in enumerate(V.EXITS):
        for st in (1.0, 1.5, 2.0, 2.5, 3.0):
            for tp in (0.0, 1.0, 2.0, 3.0, 4.0, 6.0):
                for hn, hd in holds.items():
                    for ad in (0, 1):
                        rows.append(dict(exN=e, ei=ei, stop=st, tp=tp, hold=hd, hold_name=hn, adapt=ad,
                                         shi=st, slo=(st - 1.0) if ad else st))
    return pd.DataFrame(rows)



def main():

    line("A. THE ARITHMETIC -- win rate PF 2.0 needs, by target ratio q (stop = 1) and all-in cost c in stop units")
    print(f"  driftless base = 1/(1+q); w* = 2(1+c) / (2(1+c) + q - c)")
    print(f"  {'q':>5} {'base':>7}" + "".join(f"{'c=' + str(c):>9}" for c in (0.0, 0.03, 0.06, 0.10, 0.20)) + "   lift needed at c=0.06")
    for q in (0.5, 0.75, 1.0, 1.5, 2.0, 3.0):
        base = 1 / (1 + q); row = f"  {q:>5} {base:>7.1%}"
        for c in (0.0, 0.03, 0.06, 0.10, 0.20):
            w = 2 * (1 + c) / (2 * (1 + c) + q - c); row += f"{w:>9.1%}"
        w6 = 2 * 1.06 / (2 * 1.06 + q - 0.06)
        print(row + f"   {100*(w6-base):+.1f} pts")
    print("  Cost as a fraction of the stop on this data (round turn / stop): NQ 5m 0.75xATR ~24%, NQ 15m 1.5xATR ~5%,")
    print("  US100 15m 2.5xATR ~2%. The best honest lifts measured on this branch are +1 to +5 points over base.")

    line("B. THE EMPIRICAL FRONTIER -- V61 tensor with INTRADAY hold caps, RTH entries, NQ 5/15/30m, RESEARCH")
    frames = []
    for tf in (5, 15, 30):
        D = V.build(tf)
        rth = (D["mod"] >= 570) & (D["mod"] < 930)          # 09:30-15:30 NY entries
        Gd = geometry(tf)
        rows, offs, vals, K = signal_sets(D, rth)
        exlo = np.vstack([D["ex_lo"][e] for e in V.EXITS])
        calm = np.zeros(D["n"], np.bool_); v = D["vpct"]; calm[np.isfinite(v)] = v[np.isfinite(v)] <= 0.5
        xb, R, pts = V._tensor(D["o"], D["h"], D["l"], D["c"], D["atr"], rows.astype(np.int64), exlo, calm,
                               Gd["ei"].to_numpy(np.int64), Gd["shi"].to_numpy(float), Gd["slo"].to_numpy(float),
                               Gd["tp"].to_numpy(float), Gd["hold"].to_numpy(np.int64), V.COST, V.SLIP, D["n"])
        epx = D["o"][np.minimum(rows + 1, D["n"] - 1)]
        st = V._sweep(offs, vals, rows.astype(np.int64), xb, R, pts, epx, D["cut"], len(Gd))
        ls = V._sweep_loss(offs, vals, rows.astype(np.int64), xb, R, D["cut"], len(Gd))
        d = V.table(dict(G=Gd, K=K, stat=st, loss=ls), tf)
        for col in ("hold_name",):
            d[col] = Gd[col].to_numpy()[np.tile(np.arange(len(Gd)), len(K))]
        frames.append(d)
        print(f"  tf {tf}: {len(d):,} cells, {len(rows):,} candidate signal bars")
    G = pd.concat(frames, ignore_index=True)
    G["tpy_res"] = G["n_res"] / V.YEARS["res"]; G["tpy_lock"] = G["n_lock"] / V.YEARS["lock"]
    G["tot_res"] = G["n_res"] * G["pct_res"]; G["tot_lock"] = G["n_lock"] * G["pct_lock"]
    G.to_parquet("results/inst/frontier_grid.parquet")
    intra = G[G.hold_name != "swing"]
    ok = intra[intra.n_res >= 40]
    print(f"\n  INTRADAY cells (hold <= 6.5h): {len(intra):,}; with >= 40 research trades: {len(ok):,}")
    print(f"  share profitable on research: {100*(ok.pct_res > 0).mean():.1f}%; median PF {ok.pf_res.median():.3f}; median trades/yr {ok.tpy_res.median():.0f}")
    hit = ok[(ok.pf_res >= 2.0) & (ok.tpy_res >= 200)]
    print(f"  cells meeting PF >= 2.0 AND >= 200 trades/yr ON RESEARCH: {len(hit):,}")
    print(f"  cells with PF >= 2.0 at ANY count: {int((ok.pf_res >= 2.0).sum()):,}  (median trades/yr among them: "
          f"{ok[ok.pf_res >= 2.0].tpy_res.median() if (ok.pf_res >= 2.0).any() else float('nan'):.0f})")
    print("\n  THE ENVELOPE -- best research PF available at each minimum trades-per-year, and what that cell then does on LOCKED (one read):")
    print(f"  {'>= trades/yr':>13} {'cells':>7} {'best PF res':>12} {'tpy':>6} {'tf':>4} {'hold':>5} {'stop':>5} {'tp':>4} {'cvd':>6} | {'PF lock':>8} {'tpy lock':>9} {'pct lock':>9}")
    env = []
    for thr in (25, 50, 100, 150, 200, 300, 500, 800):
        sub = ok[ok.tpy_res >= thr]
        if len(sub) == 0: print(f"  {thr:>13} {0:>7}"); continue
        b = sub.loc[sub.pf_res.idxmax()]
        env.append(b)
        print(f"  {thr:>13} {len(sub):>7,} {b.pf_res:>12.3f} {b.tpy_res:>6.0f} {int(b.tf):>4} {b.hold_name:>5} {b.stop:>5.1f} {b.tp:>4.0f} {str((int(b.k),int(b.w))):>6} | "
              f"{b.pf_lock:>8.3f} {b.tpy_lock:>9.0f} {b.pct_lock:>+9.4f}")
    print(f"  multiplicity of that locked read: {len(ok):,} research cells were seen; 8 envelope cells read.")
    print("\n  The POPULATION transfer, intraday cells: corr(PF research, PF locked) = "
          f"{ok[['pf_res','pf_lock']].dropna().corr().iloc[0,1]:+.3f} Pearson; top 1% by research PF: "
          f"mean PF {ok.nlargest(max(1,len(ok)//100),'pf_res').pf_res.mean():.3f} -> locked {ok.nlargest(max(1,len(ok)//100),'pf_res').pf_lock.mean():.3f}; "
          f"whole population locked PF mean {ok.pf_lock.mean():.3f}")
    print("\n  marginal PF on research and locked by HOLD CAP (the intraday constraint priced directly):")
    for hn, sub in G[G.n_res >= 40].groupby("hold_name"):
        print(f"    {hn:>6}: research PF {sub.pf_res.mean():.3f}  locked PF {sub.pf_lock.mean():.3f}  trades/yr {sub.tpy_res.mean():.0f}  pct/trade res {sub.pct_res.mean():+.4f} lock {sub.pct_lock.mean():+.4f}")

    line("C. DEFLATED SHARPE of the best research cell, at the trial count actually run")
    b = ok.loc[ok.pf_res.idxmax()]
    # per-trade Sharpe from the sums the sweep kept: mean and variance of pct per trade
    n = b.n_res; mu = b.pct_res; var = b.sq_res / n - mu * mu; sr = mu / math.sqrt(max(var, 1e-12))
    N = len(ok)
    # variance of the per-trade SR across all trials
    srs = (ok.pct_res / np.sqrt(np.maximum(ok.sq_res / ok.n_res - ok.pct_res ** 2, 1e-12))).to_numpy()
    vsr = np.nanvar(srs)
    from scipy.stats import norm
    g = 0.5772156649
    sr0 = math.sqrt(vsr) * ((1 - g) * norm.ppf(1 - 1 / N) + g * norm.ppf(1 - 1 / (N * math.e)))
    se = math.sqrt(max((1 - 0 * sr + (3 - 1) / 4 * sr * sr) / (n - 1), 1e-12))   # skew 0, kurt 3 assumed (conservative here)
    dsr = norm.cdf((sr - sr0) / se)
    print(f"  best research cell: PF {b.pf_res:.3f}, {b.tpy_res:.0f} trades/yr, per-trade SR {sr:.3f}; trials N = {N:,}; SR0 (expected best of noise) {sr0:.3f}")
    print(f"  DEFLATED SHARPE {dsr:.4f}   (the probability the observed SR beats what {N:,} noise draws would give)")
    print(f"  same cell, LOCKED: PF {b.pf_lock:.3f}, {b.tpy_lock:.0f} trades/yr")


if __name__ == "__main__":
    main()
