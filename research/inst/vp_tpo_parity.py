"""The shipped Pine's TPO profile (pine/inst/VP_TPO_SCALP_strategy.pine), transliterated bar by bar
with its own array growth / letter tracking / freeze rule, diffed against vp_tpo.build's
prior-session single print, POC, VAH, VAL and the developing IB high on every NQ 15m bar."""
import os, sys, math, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/v64", "research/inst"): sys.path.insert(0, os.path.join(ROOT, p))
import v64opt as O, vp_tpo as T
D = O.build(15); n = D["n"]; h, l, c, mod = D["h"], D["l"], D["c"], D["mod"]; ix = pd.DatetimeIndex(D["ix"])
F, L = T.build(D); TB = T.TBIN
nyday = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
binMin = None; cnt = []; lastL = []; built = False; ibHi = ibLo = np.nan
prevSP = []; prevPOC = prevVAH = prevVAL = np.nan
sp_out = np.full(n, np.nan); poc_out = np.full(n, np.nan); vah_out = np.full(n, np.nan); val_out = np.full(n, np.nan); ib_out = np.full(n, np.nan)
def freeze():
    nb = len(cnt)
    if nb == 0: return np.nan, np.nan, np.nan, []
    p = 0; tot = 0; sp = []
    for k in range(nb):
        ck = cnt[k]; tot += ck
        if ck > cnt[p]: p = k
        if ck == 1: sp.append((binMin + k + 0.5) * TB)
    lo = hi = p; acc = cnt[p]
    while acc < 0.7 * tot and (lo > 0 or hi < nb - 1):
        up = cnt[hi + 1] if hi + 1 < nb else -1; dn = cnt[lo - 1] if lo - 1 >= 0 else -1
        if up >= dn: hi += 1; acc += max(up, 0)
        else: lo -= 1; acc += max(dn, 0)
    return (binMin + p + 0.5) * TB, (binMin + hi + 1) * TB, (binMin + lo) * TB, sp
for i in range(n):
    inRTH = 570 <= mod[i] < 960; newDay = i > 0 and nyday[i] != nyday[i - 1]; inRTH1 = i > 0 and 570 <= mod[i - 1] < 960
    if built and ((not inRTH and inRTH1) or (newDay and inRTH)):
        prevPOC, prevVAH, prevVAL, prevSP = freeze(); built = False
    if inRTH:
        if not built:
            cnt = []; lastL = []; binMin = math.floor(l[i] / TB); built = True; ibHi = ibLo = np.nan
        Lt = (mod[i] - 570) // 30; a = math.floor(l[i] / TB); b = math.floor(h[i] / TB)
        while a < binMin: cnt.insert(0, 0); lastL.insert(0, -1); binMin -= 1
        while b - binMin >= len(cnt): cnt.append(0); lastL.append(-1)
        for k in range(a - binMin, b - binMin + 1):
            if lastL[k] != Lt: cnt[k] += 1; lastL[k] = Lt
        if Lt < 2: ibHi = h[i] if np.isnan(ibHi) else max(ibHi, h[i]); ibLo = l[i] if np.isnan(ibLo) else min(ibLo, l[i])
        ib_out[i] = ibHi
    cb = math.floor(c[i] / TB); s = np.nan
    for ctr in prevSP:
        if math.floor(ctr / TB) > cb: s = ctr; break
    sp_out[i] = s; poc_out[i] = prevPOC; vah_out[i] = prevVAH; val_out[i] = prevVAL
def cmp(nm, a, b):
    both = np.isfinite(a) & np.isfinite(b); one = np.isfinite(a) ^ np.isfinite(b)
    print(f"  {nm:28s} both finite {both.sum():>6}  exact {100*np.mean(np.isclose(a[both], b[both], atol=1e-6)):6.2f}%  max|diff| {np.nanmax(np.abs(a[both]-b[both])):.4f}  one-sided NaN {one.sum()} ({100*one.mean():.2f}%)")
print("Pine TPO transliteration vs vp_tpo.build (NQ 15m, %d bars)" % n)
cmp("prior single print above", sp_out, L["pr_spa"]); cmp("prior POC", poc_out, L["pr_poc"]); cmp("prior VAH", vah_out, L["pr_vah"]); cmp("prior VAL", val_out, np.where(np.isfinite(F["tpo.prior_val_atr"].to_numpy()), c - F["tpo.prior_val_atr"].to_numpy() * D["atr"], np.nan)); cmp("developing IB high", ib_out, L["ib_hi"])
gate_pine = np.isfinite(sp_out) & ((sp_out - c) / D["atr"] <= 3.0) & ((sp_out - c) >= 0); gate_res = np.nan_to_num((F["tpo.prior_single_above_atr"].to_numpy() <= 3.0).astype(float)).astype(bool)
print(f"  gate 'single print within 3 ATR above': agree on {100*np.mean(gate_pine == gate_res):.3f}% of bars; Pine {gate_pine.sum()} vs research {gate_res.sum()} true bars")
