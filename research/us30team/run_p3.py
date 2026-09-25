"""P3 -- THE DELIVERABLE. Does pooling change the RESOLUTION, and is there a common effect to pool?

Three questions, in this order, because the third decides whether the first two mean anything.

  1. THE MDE LADDER. What the minimum detectable effect at 80% power is for each market alone,
     each pair, and all three -- all from DATE-CLUSTERED standard errors, so the answer already
     prices the fact that US30 and US100 share 710 research dates and 39.8% of their signal bars.

  2. WHAT A PROFIT FACTOR REQUIRES ON THIS GEOMETRY, against that MDE. `STUDY_US30_SCALP_0711` did
     this on one cell in points; here it is done per cell from the cell's OWN win/loss sizes, which
     is the only way to compare a 0.97N and a 3.2N geometry. The deliverable is the PF at which
     "detectable" and "worth trading" cross.

  3. IS THE EFFECT COMMON ACROSS MARKETS? Pooling adds power only if the three markets estimate the
     SAME quantity. Cochran's Q and I^2 on the per-market means with their clustered errors. If the
     markets are heterogeneous, pooling does not concentrate an effect -- it averages one away, and
     a smaller standard error around a smaller mean buys nothing.

Plus the matched random-entry control per market and pooled, drawn from the same eligible in-window
bars, SORTED (`STUDY_V59`).
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pool as P

HERE = os.path.dirname(os.path.abspath(__file__))


def hdr(s):
    print("\n" + "=" * 108)
    print(s)
    print("=" * 108)


FF = P.load_all(15)
SPL = {k: P.split(FF[k]) for k in P.MARKETS}
BLK = {k: SPL[k][0] for k in P.MARKETS}
ELIG = {k: P.eligible(FF[k]) for k in P.MARKETS}
SIG = {(k, d): P.donchian(FF[k], d, 1) for k in P.MARKETS for d in P.DONCH}
G = pd.read_csv(os.path.join(HERE, "p2_grid.csv"))


def run_cell(c, block="research"):
    per = {}
    for k in P.MARKETS:
        s, sd = SIG[(k, c["don"])]
        t = P.run(FF[k], s, sd, c["stop"], c["tgt"], cost=P.COST[k],
                  use_pts=1 if c["param"] == "pts" else 0, block=BLK[k][block])
        if t is not None and len(t):
            t = t.copy(); t["mkt"] = k
            per[k] = t
    tp = pd.concat(per.values(), ignore_index=True) if per else None
    return per, tp


# The two DECLARED consensus cells from P2.2's marginal averages, plus the ATR grid's best-t cell
# named as a top row and treated as one (its p-value is post-selection over 54 cells).
CELLS = [
    dict(name="ATR marginal consensus", don=20, stop=P.STOP_ATR[0], tgt=P.NO_TARGET, param="atr"),
    dict(name="ATR best-t (post-selection)", don=20, stop=P.STOP_ATR[1], tgt=P.NO_TARGET,
         param="atr"),
    dict(name="PTS marginal consensus", don=20, stop=30, tgt=100, param="pts"),
]

hdr("P3.1  THE MDE LADDER -- one market, two markets, three, all from date-clustered errors")
print("  MDE at 80% power, two-sided alpha 0.05, in ATR UNITS per trade. The pooled figure is not")
print("  sd/sqrt(n): trades on the same date in different markets move together, so every standard")
print("  error here is clustered on the CALENDAR DATE across whichever markets are in the subset.\n")
SUBS = [("US30",), ("US100",), ("NQ",), ("US30", "US100"), ("US30", "NQ"), ("US100", "NQ"),
        ("US30", "US100", "NQ")]
LAD = {}
for cell in CELLS:
    per, _ = run_cell(cell)
    print(f"  --- {cell['name']}: {P.cell_name(cell)} ---")
    print(f"  {'subset':22s} {'n':>7s} {'days':>6s} {'n_eff':>7s} {'mean':>9s} {'sd':>7s}"
          f" {'SE':>8s} {'t':>7s} {'MDE80':>8s} {'vs US30':>8s} {'in?':>4s}"
          f" {'MDE pts@US30':>13s}")
    base = None
    for sub in SUBS:
        fr = [per[k] for k in sub if k in per]
        if not fr:
            continue
        tp = pd.concat(fr, ignore_index=True)
        v = tp["atr_u"].to_numpy()
        se, n_eff, nd = P.cluster_se(v, tp["date"].to_numpy())
        m, _z = P.mde(se)
        if sub == ("US30",):
            base = m
        ins = "YES" if abs(v.mean()) >= m else "no"
        LAD[(cell["name"], sub)] = dict(n=len(v), mean=v.mean(), se=se, mde=m, n_eff=n_eff)
        print(f"  {'+'.join(sub):22s} {len(v):>7,d} {nd:>6,d} {n_eff:>7,.0f} {v.mean():>+9.4f}"
              f" {v.std(ddof=1):>7.3f} {se:>8.4f} {v.mean() / se:>+7.3f} {m:>8.4f}"
              f" {m / base:>7.2f}x {ins:>4s} {m * P.ATR30:>12.2f}")
    print()

hdr("P3.2  WHAT A PROFIT FACTOR REQUIRES ON EACH CELL'S OWN GEOMETRY, AGAINST ITS OWN MDE")
print("  From the cell's realised mean win W, mean loss L and win rate: PF = w*W / ((1-w)*L), so")
print("  the win rate a target PF needs is w* = PF*L / (W + PF*L) and the edge it implies is")
print("  w*W - (1-w*)L. `STUDY_US30_SCALP_0711` S9 did this on one cell in points; the point of")
print("  doing it per cell is that a 0.97N and a 3.2N geometry are not the same trade.\n")


def pf_table(tp, unit="atr_u"):
    v = tp[unit].to_numpy()
    w, l = v[v > 0], v[v < 0]
    if len(w) < 5 or len(l) < 5:
        return None
    W, L = w.mean(), -l.mean()
    obs_w = len(w) / len(v)
    se, n_eff, _ = P.cluster_se(v, tp["date"].to_numpy())
    m, _ = P.mde(se)
    out = []
    for target in (1.05, 1.1, 1.2, 1.5, 2.0):
        ws = target * L / (W + target * L)
        edge = ws * W - (1 - ws) * L
        out.append(dict(pf=target, need_win=ws, d_win=ws - obs_w, edge=edge,
                        detect=edge >= m, ratio=edge / m))
    return dict(W=W, L=L, obs_w=obs_w, obs_pf=P.pf(v), mean=v.mean(), mde=m, rows=out)


for cell in CELLS:
    per, tp = run_cell(cell)
    for lab, t in (("POOLED (3 markets)", tp), ("US30 alone", per.get("US30"))):
        if t is None or not len(t):
            continue
        r = pf_table(t)
        if r is None:
            continue
        print(f"  --- {cell['name']} :: {lab} ---")
        print(f"      n {len(t):,d}   observed PF {r['obs_pf']:.4f}   mean {r['mean']:+.4f} ATR"
              f"   win {100 * r['obs_w']:.1f}%   W {r['W']:.4f}   L {r['L']:.4f}"
              f"   MDE80 {r['mde']:.4f} ATR ({r['mde'] * P.ATR30:.2f} US30 pts)")
        print(f"      {'PF':>5s} {'needs win':>10s} {'(delta)':>9s} {'= edge/trade':>13s}"
              f" {'in US30 pts':>12s} {'edge/MDE':>9s} {'detectable?':>12s}")
        for x in r["rows"]:
            print(f"      {x['pf']:>5.2f} {100 * x['need_win']:>9.2f}% {100 * x['d_win']:>+8.2f}p"
                  f" {x['edge']:>+13.4f} {x['edge'] * P.ATR30:>+12.2f} {x['ratio']:>8.2f}x"
                  f" {('YES' if x['detect'] else 'no'):>12s}")
        print()

hdr("P3.3  IS THERE A COMMON EFFECT TO POOL? -- Cochran's Q and I^2 on the per-market means")
print("  Pooling adds power only if the three markets estimate the SAME quantity. Under a common")
print("  effect Q ~ chi-square with 2 df (critical 5.99 at alpha 0.05); I^2 is the share of the")
print("  spread across markets that is real heterogeneity rather than sampling noise.\n")
try:
    from scipy.stats import chi2
    def qp(q, df):
        return float(chi2.sf(q, df))
except Exception:
    def qp(q, df):
        return np.nan

print(f"  {'cell':30s} " + " ".join(f"{k:>18s}" for k in P.MARKETS)
      + f" {'Q':>7s} {'p':>7s} {'I^2':>7s} {'FE mean':>9s} {'FE SE':>8s}")
HET = []
for param in ("atr", "pts"):
    for c in P.grid(param):
        per, _ = run_cell(c)
        ms, ses = [], []
        for k in P.MARKETS:
            if k not in per:
                ms.append(np.nan); ses.append(np.nan); continue
            v = per[k]["atr_u"].to_numpy()
            se, _, _ = P.cluster_se(v, per[k]["date"].to_numpy())
            ms.append(v.mean()); ses.append(se)
        ms, ses = np.array(ms), np.array(ses)
        ok = np.isfinite(ms) & np.isfinite(ses) & (ses > 0)
        if ok.sum() < 2:
            continue
        w = 1.0 / ses[ok] ** 2
        fe = float((w * ms[ok]).sum() / w.sum())
        fese = float(np.sqrt(1.0 / w.sum()))
        Q = float((w * (ms[ok] - fe) ** 2).sum())
        df = ok.sum() - 1
        I2 = max(0.0, (Q - df) / Q) if Q > 0 else 0.0
        HET.append(dict(param=param, cell=P.cell_name(c), Q=Q, p=qp(Q, df), I2=I2,
                        fe=fe, fese=fese, **{f"m_{k}": ms[i] for i, k in enumerate(P.MARKETS)}))
H = pd.DataFrame(HET)
for _, r in H.iterrows():
    print(f"  {r.cell:30s} " + " ".join(f"{r[f'm_{k}']:>+18.4f}" for k in P.MARKETS)
          + f" {r.Q:>7.2f} {r.p:>7.4f} {100 * r.I2:>6.1f}% {r.fe:>+9.4f} {r.fese:>8.4f}")
print(f"\n  cells with Q significant at 0.05: {int((H.p <= 0.05).sum())} of {len(H)}"
      f"   ({100 * (H.p <= 0.05).mean():.1f}%)   median I^2 {100 * H.I2.median():.1f}%")
print(f"  sign agreement across all three markets: "
      f"{int((np.sign(H.m_US30) == np.sign(H.m_US100)).sum())}/{len(H)} US30-US100, "
      f"{int((np.sign(H.m_US30) == np.sign(H.m_NQ)).sum())}/{len(H)} US30-NQ, "
      f"{int((np.sign(H.m_US100) == np.sign(H.m_NQ)).sum())}/{len(H)} US100-NQ")
print(f"  cells positive on ALL THREE markets: "
      f"{int(((H.m_US30 > 0) & (H.m_US100 > 0) & (H.m_NQ > 0)).sum())} of {len(H)}")
H.to_csv(os.path.join(HERE, "p3_het.csv"), index=False)

hdr("P3.4  MATCHED RANDOM ENTRY -- per market and POOLED draw-for-draw")
print("  Same number of signals drawn from the same eligible in-window bars of the same market,")
print("  same side, SORTED so the position lock rejects the same share. 300 draws. Draws are")
print("  combined ACROSS MARKETS draw-for-draw, so the pooled null carries the same market mix.\n")
NDRAW = 300
for cell in CELLS:
    per, tp = run_cell(cell)
    tot_s = np.zeros(NDRAW); tot_n = np.zeros(NDRAW)
    print(f"  --- {cell['name']}: {P.cell_name(cell)} ---")
    print(f"  {'market':10s} {'n':>7s} {'rule ATR':>10s} {'null med':>10s} {'null sd':>9s}"
          f" {'excess':>9s} {'p':>7s}")
    for k in P.MARKETS:
        if k not in per:
            continue
        d = P.control_draws(FF[k], len(per[k]), per[k]["side"].to_numpy(), ELIG[k], cell,
                            P.COST[k], n_draw=NDRAW, seed=17, block=BLK[k]["research"])
        if d is None:
            continue
        ok = d[:, 3] > 0
        means = np.where(ok, d[:, 0] / np.maximum(d[:, 3], 1), np.nan)
        tot_s += d[:, 0]; tot_n += d[:, 3]
        obs = per[k]["atr_u"].mean()
        p = float((means >= obs).mean())
        print(f"  {k:10s} {len(per[k]):>7,d} {obs:>+10.4f} {np.nanmedian(means):>+10.4f}"
              f" {np.nanstd(means):>9.4f} {obs - np.nanmedian(means):>+9.4f} {p:>7.3f}")
    pm = tot_s / np.maximum(tot_n, 1)
    obs = tp["atr_u"].mean()
    p = float((pm >= obs).mean())
    print(f"  {'POOLED':10s} {len(tp):>7,d} {obs:>+10.4f} {np.median(pm):>+10.4f}"
          f" {pm.std():>9.4f} {obs - np.median(pm):>+9.4f} {p:>7.3f}")
    print(f"  null-spread diagnostic (`STUDY_V59`): sd(null mean) / rule SE ="
          f" {pm.std() / P.cluster_se(tp['atr_u'].to_numpy(), tp['date'].to_numpy())[0]:.3f}"
          f"   null trade count {tot_n.mean():,.0f} +- {tot_n.std():.0f}"
          f" against a target of {len(tp):,d}\n")
