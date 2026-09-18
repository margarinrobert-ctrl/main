"""Drop-one on the survivor: the single print can only sit ABOVE the close when the close is BELOW the
prior session's high, so 'single print within 3 ATR above' co-selects 'below yesterday's high' 100%.
Which of the two carries it? Both blocks shown; the locked column is descriptive (the pre-declared
locked read was taken in run_vp_scalp.py)."""
import os, sys, warnings; import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/v64", "research/inst"): sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V, v64opt as O, vp_tpo as T
warnings.filterwarnings("ignore")
D = O.build(15); n = D["n"]; CUT = D["cut"]; c, h, l, o, atr, mod = D["c"], D["h"], D["l"], D["o"], D["atr"], D["mod"]
WIN = (mod >= 420) & (mod < 660); ENT = D["ent_all"][0]; EXL = D["exl_all"][0]
F, L = T.build(D); g = lambda k: F[k].to_numpy()
def walk(gate): return O._walk(o, h, l, c, atr, D["calm"], ENT, EXL, gate, D["d_ma"], D["chop"], D["psh_ok"], int(CUT), 3.19, 3.19, 2.3, 15, 0, 0.0, 0, 0.0, 0, V.COST, V.SLIP, int(D["last_bar"]))
def st(pct, blk, b):
    q = pct[blk == b]; return len(q), q[q > 0].sum() / max(1e-9, -q[q <= 0].sum()), q.sum(), q.mean()
sigbar = np.zeros(n, bool); sigbar[1000:D["last_bar"]] = (h[1000:D["last_bar"]] > ENT[1000:D["last_bar"]]) & WIN[1000:D["last_bar"]]
sig_res = sigbar & (np.arange(n) < CUT); rng = np.random.default_rng(5)
def ctl(keep, b, nd=200):
    pool = np.flatnonzero(sig_res if b == 0 else sigbar & (np.arange(n) >= CUT)); out = []
    for _ in range(nd):
        gg = np.zeros(n, bool); gg[rng.choice(pool, size=min(keep, len(pool)), replace=False)] = True; R, pct, blk, sg = walk(gg); out.append(st(pct, blk, b)[1])
    return np.array(out)
spa = g("tpo.prior_single_above_atr"); near = np.nan_to_num((spa <= 3.0).astype(float)).astype(bool)
below_hi = g("vp.prior_hi_atr") < 0; below_tpo_vah = g("tpo.prior_vah_atr") < 0; psh = D["psh_ok"]
conds = {
 "close ABOVE prior RTH high (V17 gate, psh_ok)": psh, "close BELOW prior RTH high": ~psh,
 "below prior high AND single print <= 3 ATR above": below_hi & near,
 "below prior high AND NO single print <= 3 ATR above": below_hi & ~near,
 "below prior high AND single print > 3 ATR above (exists)": below_hi & np.isfinite(spa) & (spa > 3),
 "below prior high AND NO single print at all above": below_hi & ~np.isfinite(spa),
 "below prior TPO VAH": below_tpo_vah,
 "below prior TPO VAH AND single print <= 3 above": below_tpo_vah & near,
 "above prior TPO VAH AND single print <= 3 above": ~below_tpo_vah & near,
 "above prior TPO VAH AND NO single print <= 3 above": ~below_tpo_vah & ~near,
}
print(f"{'condition':58s} keep%   n_res  PF_res  tot_res  R_res | ctlPF  p_res  ||  n_lock PF_lock tot_lock  p_lock (descriptive)")
for nm, m in conds.items():
    m = np.nan_to_num(m.astype(float)).astype(bool); R, pct, blk, sg = walk(WIN & m); a = st(pct, blk, 0); b = st(pct, blk, 1)
    k0 = int((m & sig_res).sum()); k1 = int((m & sigbar & (np.arange(n) >= CUT)).sum()); c0 = ctl(k0, 0); c1 = ctl(k1, 1, 120)
    print(f"{nm:58s} {100*k0/sig_res.sum():5.0f} {a[0]:>6} {a[1]:6.3f} {a[2]:+7.2f} {a[3]:+6.3f} | {np.nanmedian(c0):5.3f} {np.nanmean(c0>=a[1]):6.3f}  || {b[0]:>5} {b[1]:6.3f} {b[2]:+7.2f} {np.nanmean(c1>=b[1]):6.3f}", flush=True)
