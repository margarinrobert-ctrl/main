"""Tier 1.1 -- profile-construction robustness, research block only. Bin size in three modes x
letter length x ceiling, each cell scored against a same-selectivity random filter; then the
Lopez de Prado CSCV probability of backtest overfitting over the whole construction x stop grid,
using zero-filled daily returns. Picks the SCALE-INVARIANT definition to port (Tier 2)."""
import os, sys, warnings, itertools, time, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/v64", "research/inst"): sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V, v64opt as O, vp_tpo as T, vp_tpo2 as T2
warnings.filterwarnings("ignore"); pd.set_option("display.width", 220)
def line(t): print("\n" + "=" * 118 + f"\n{t}\n" + "=" * 118, flush=True)
t0 = time.time()
D = O.build(15); n = D["n"]; CUT = D["cut"]; c, h, l, o, atr, mod = D["c"], D["h"], D["l"], D["o"], D["atr"], D["mod"]; ix = pd.DatetimeIndex(D["ix"])
WIN = (mod >= 420) & (mod < 660); ENT = D["ent_all"][0]; EXL = D["exl_all"][0]
day = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
def walk(gate, stop=3.19): return O._walk(o, h, l, c, atr, D["calm"], ENT, EXL, gate, D["d_ma"], D["chop"], D["psh_ok"], int(CUT), stop, stop, 2.3, 15, 0, 0.0, 0, 0.0, 0, V.COST, V.SLIP, int(D["last_bar"]))
def pf(q): return q[q > 0].sum() / max(1e-9, -q[q <= 0].sum())
F, L = T.build(D)
sp0, _ = T2.single_print_above(o, h, l, c, atr, mod, ix, 2.5, 30, "abs")
both = np.isfinite(sp0) & np.isfinite(L["pr_spa"]); print(f"parity of the parameterised feature with vp_tpo.build at (2.5 pts, 30 min): exact on {100*np.mean(np.isclose(sp0[both], L['pr_spa'][both])):.2f}% of {both.sum()} bars, one-sided NaN {int((np.isfinite(sp0) ^ np.isfinite(L['pr_spa'])).sum())}")
sigbar = np.zeros(n, bool); sigbar[1000:D["last_bar"]] = (h[1000:D["last_bar"]] > ENT[1000:D["last_bar"]]) & WIN[1000:D["last_bar"]]
sig_res = sigbar & (np.arange(n) < CUT); res_idx = np.flatnonzero(sig_res); rng = np.random.default_rng(41)
ctl_cache = {}
def ctl(keep, ndraw=100):
    kk = int(round(keep / 10) * 10)
    if kk not in ctl_cache:
        out = []
        for _ in range(ndraw):
            gg = np.zeros(n, bool); gg[rng.choice(res_idx, size=min(kk, len(res_idx)), replace=False)] = True; R_, p_, b_, s_ = walk(gg); out.append(pf(p_[b_ == 0]))
        ctl_cache[kk] = np.array(out)
    return ctl_cache[kk]

line("1.1  BIN SIZE x LETTER LENGTH x CEILING on research -- PF, keep share, same-selectivity control p (locked in brackets, descriptive)")
BINS = [("abs 1.0 pt", 1.0, "abs"), ("abs 2.5 pt (shipped)", 2.5, "abs"), ("abs 5 pt", 5.0, "abs"), ("abs 10 pt", 10.0, "abs"),
        ("pct 0.0125% of price", 1.25e-4, "pct"), ("pct 0.025%", 2.5e-4, "pct"), ("atr 0.10 x session ATR", 0.10, "atr"), ("atr 0.20 x session ATR", 0.20, "atr")]
LETTERS = (15, 30, 60); CEILS = (2.0, 3.0, 4.0)
feat = {}
rows = []
print(f"  {'bin':26s} {'letter':>6} {'ceil':>4} {'keep%':>5} {'n res':>5} {'PF res':>6} {'R res':>7} {'ctl PF':>6} {'p':>6}  [n lock  PF lock  R lock]")
for (bn, tb, mode) in BINS:
    for lt in LETTERS:
        sp, bs = T2.single_print_above(o, h, l, c, atr, mod, ix, tb, lt, mode); feat[(bn, lt)] = sp
        dist = (sp - c) / atr
        for ce in CEILS:
            g = np.nan_to_num((dist <= ce).astype(float)).astype(bool) & (dist >= 0)
            R_, p_, b_, s_ = walk(WIN & g); keep = int((g & sig_res).sum()); m0 = b_ == 0; m1 = b_ == 1
            cc = ctl(keep); pr = pf(p_[m0]); pv = np.nanmean(cc >= pr)
            rows.append(dict(bin=bn, mode=mode, tbin=tb, letter=lt, ceil=ce, keep=100 * keep / len(res_idx), n=m0.sum(), pf=pr, R=R_[m0].mean(), ctl=np.nanmedian(cc), p=pv, n_lock=m1.sum(), pf_lock=pf(p_[m1]), R_lock=R_[m1].mean(), med_bin=np.nanmedian(bs)))
            print(f"  {bn:26s} {lt:>6} {ce:4.1f} {100*keep/len(res_idx):5.0f} {m0.sum():>5} {pr:6.3f} {R_[m0].mean():+7.4f} {np.nanmedian(cc):6.3f} {pv:6.3f}  [{m1.sum():>5}  {pf(p_[m1]):6.3f}  {R_[m1].mean():+7.4f}]", flush=True)
G = pd.DataFrame(rows); G.to_parquet(os.path.join(ROOT, "results/inst/vp_next1_grid.parquet"))
print("\n  marginal averages (research PF / control p / share of cells at p<=0.05):")
for ax in ("bin", "letter", "ceil"):
    m = G.groupby(ax).agg(pf=("pf", "mean"), p=("p", "mean"), clear=("p", lambda x: 100 * (x <= 0.05).mean()), keep=("keep", "mean"), pf_lock=("pf_lock", "mean"))
    print(f"  by {ax}:"); print(m.to_string(float_format=lambda x: f"{x:7.3f}"))
print(f"\n  cells clearing p<=0.05 on research: {int((G.p <= 0.05).sum())} of {len(G)} ({100*(G.p<=0.05).mean():.0f}%);  corr(research PF, locked PF) over the grid: {np.corrcoef(G.pf, G.pf_lock)[0,1]:+.3f} (descriptive)")
print("  median bin in points by mode:", G.groupby("bin").med_bin.first().round(2).to_dict())

line("CSCV -- probability of backtest overfitting over the construction x stop grid (Bailey, Borwein, Lopez de Prado, Zhu), research daily returns, S = 16")
STOPS = (2.0, 2.5, 3.0, 3.19, 4.0)
alld = np.unique(day[(np.arange(n) < CUT) & (np.arange(n) >= 1000)])
M = []; names = []
for (bn, tb, mode) in BINS:
    for lt in LETTERS:
        dist = (feat[(bn, lt)] - c) / atr
        for ce in CEILS:
            g = np.nan_to_num((dist <= ce).astype(float)).astype(bool) & (dist >= 0)
            for st in STOPS:
                R_, p_, b_, s_ = walk(WIN & g, st); m0 = b_ == 0
                dl = pd.Series(p_[m0]).groupby(day[s_[m0]]).sum().reindex(alld).fillna(0.0).to_numpy(); M.append(dl); names.append((bn, lt, ce, st))
M = np.array(M).T                                   # T days x N configs
Tn, N = M.shape; S = 16; blocks = np.array_split(np.arange(Tn), S)
def sharpe(x): s = x.std(0); return np.where(s > 0, x.mean(0) / s, 0.0)
logits = []; is_best = []; oos_rank = []
for comb in itertools.combinations(range(S), S // 2):
    tr = np.concatenate([blocks[i] for i in comb]); te = np.concatenate([blocks[i] for i in range(S) if i not in comb])
    sr_tr = sharpe(M[tr]); sr_te = sharpe(M[te]); k = int(np.argmax(sr_tr))
    w = (np.argsort(np.argsort(sr_te))[k] + 1) / (N + 1); logits.append(np.log(w / (1 - w))); is_best.append(sr_tr[k]); oos_rank.append(w)
logits = np.array(logits); pbo = np.mean(logits <= 0)
print(f"  configs {N} (8 bins x 3 letters x 3 ceilings x 5 stops), {Tn} research days, {len(logits)} train/test splits")
print(f"  PBO = P(the in-sample best ranks below the OOS median) = {pbo:.3f}   mean OOS rank of the IS best {np.mean(oos_rank):.3f} (0.5 = random)")
is_sr = np.array([sharpe(M[np.concatenate([blocks[i] for i in comb])]) for comb in itertools.islice(itertools.combinations(range(S), S // 2), 200)])
# performance degradation: OOS SR of the IS-best vs IS SR, over splits
deg = []
for comb in itertools.islice(itertools.combinations(range(S), S // 2), 2000):
    tr = np.concatenate([blocks[i] for i in comb]); te = np.concatenate([blocks[i] for i in range(S) if i not in comb]); k = int(np.argmax(sharpe(M[tr]))); deg.append((sharpe(M[tr])[k], sharpe(M[te])[k]))
deg = np.array(deg); slope = np.polyfit(deg[:, 0], deg[:, 1], 1)[0]
print(f"  performance degradation: IS-best SR/day mean {deg[:,0].mean():+.4f} -> its OOS SR/day mean {deg[:,1].mean():+.4f}; slope OOS~IS {slope:+.3f}; P(OOS SR < 0 | IS best) {np.mean(deg[:,1] < 0):.3f}")
# the shipped cell's rank in the population, for reference
k0 = names.index(("abs 2.5 pt (shipped)", 30, 3.0, 3.19)); full_sr = sharpe(M); print(f"  shipped cell rank on the full research block: {int((full_sr > full_sr[k0]).sum()) + 1} of {N}; whole-population median SR/day {np.median(full_sr):+.4f}, shipped {full_sr[k0]:+.4f}")
print(f"\n  runtime {time.time()-t0:.0f}s")
