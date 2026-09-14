"""Tier 2 -- the pre-registered reads. Everything below the PRE-REGISTRATION block was frozen from
Tier 0/1 on NQ RESEARCH before any of these feeds was opened, and each read is taken ONCE.

PRE-REGISTRATION (2026-09-05)
  rule      Donchian 10/10 long breakout, fill next open, entries 07:00-11:00 New York, stop 3.0 x ATR(14 Wilder)
            (Tier 1.2: best R/trade and total/p99 inside the gate on research), target 2.3 ATR, hold 230 min, one position
  gate      prior-session TPO single print strictly above the close's bin, 30-minute letters, bin = 0.10 x the session's
            median ATR (Tier 1.1: scale-invariant, best marginal), ceiling 4 ATR PRIMARY (handoff 2.2), 3 ATR secondary
  MA cells  at most three, thresholds fixed from NQ research signal-bar quantiles, each ONE read:
            A  gate AND EMA13 < EMA48            B  gate AND (close-EMA200)/ATR <= NQ-research 2/3 quantile (not extended)
            C  gate AND (close-VWAP07)/ATR <= NQ-research 1/3 quantile (CFD tick volume: flagged, weakest of the three)
  reads     US100 BEFORE 2022-12-26 (primary; ~7 years the NQ selection never saw, same underlying), US100 after (feed
            parity only, never pooled), US30 whole file (mechanism test), short mirror on NQ research (falsification)
  nulls     same-selectivity random filter, bar-matched AND day-clustered (250 each); random ENTRY at the same rate;
            day-block bootstrap P(mean<=0); PSR.  13 pre-registered reads in total -- stated, not corrected.
  verdict   toward shipping: US100 pre-2022 gate PF > 1.25 with clustered p <= 0.05 and P(mean<=0) < 0.05;
            toward abandoning: US100 pre-2022 PF < 1.10.  US30 decides regime vs mechanism.
"""
import os, sys, warnings, time, numpy as np, pandas as pd
from numba import njit
from scipy.stats import norm, skew, kurtosis
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/v63", "research/v64", "research/inst"): sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V, v64opt as O, v63feeds as FD, vp_tpo as T, vp_tpo2 as T2
warnings.filterwarnings("ignore"); pd.set_option("display.width", 220)
def line(t): print("\n" + "=" * 122 + f"\n{t}\n" + "=" * 122, flush=True)
print(__doc__)
t0 = time.time()
STOP, TP, HOLD, ENTN, EXN = 3.0, 2.3, 15, 10, 10
BIN, LETTER, CEIL, CEIL2 = 0.10, 30, 4.0, 3.0
def pf(q): return q[q > 0].sum() / max(1e-9, -q[q <= 0].sum())
def dd(q): e = np.cumsum(q); return float(np.max(np.maximum.accumulate(e) - e)) if len(q) else np.nan
rng = np.random.default_rng(71)

def make(market):
    f = FD.bars(market, 15); o, h, l, c, v = (f[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume")); n = len(c)
    ix = pd.DatetimeIndex(f.index); mod = (ix.hour * 60 + ix.minute).to_numpy(); day = (ix.year * 10000 + ix.month * 100 + ix.day).to_numpy()
    atr = V._atr(h, l, c); S = pd.Series
    ent = S(h).rolling(ENTN).max().shift(1).to_numpy(); exl = S(l).rolling(EXN).min().shift(1).to_numpy()
    ent_lo = S(l).rolling(ENTN).min().shift(1).to_numpy(); ex_hi = S(h).rolling(EXN).max().shift(1).to_numpy()
    e13, e48, e200 = (S(c).ewm(span=k, adjust=False).mean().to_numpy() for k in (13, 48, 200))
    m = mod >= 420; tp_ = (h + l + c) / 3; d = pd.DataFrame({"pv": np.where(m, tp_ * v, 0.0), "vv": np.where(m, v, 0.0), "s": day}); gg = d.groupby("s", sort=False)
    vw = (gg["pv"].cumsum() / gg["vv"].cumsum().replace(0, np.nan)).to_numpy(); vw[~m] = np.nan
    sp, _ = T2.single_print_above(o, h, l, c, atr, mod, ix, BIN, LETTER, "atr"); spb, _ = T2.single_print_above(o, h, l, c, atr, mod, ix, BIN, LETTER, "atr", side="below")
    return dict(market=market, n=n, o=o, h=h, l=l, c=c, v=v, ix=ix, mod=mod, day=day, atr=atr, ent=ent, exl=exl, ent_lo=ent_lo, ex_hi=ex_hi,
                d_sp=(sp - c) / atr, d_spb=(c - spb) / atr, e1348=(e13 - e48) / atr, e200=(c - e200) / atr, dvw=(c - vw) / atr, win=(mod >= 420) & (mod < 660),
                cost=FD.COST[market][0], slip={"NQ": V.SLIP, "US100": 0.1, "US30": 0.1}[market], last=n - 25,
                calm=np.zeros(n, np.bool_), zf=np.zeros(n), zb=np.zeros(n, np.bool_))
def walk(M, gate, cut):
    # vp_tpo.walk_tp (exact against O._walk on NQ, capacity 6,000 trades -- a nine-year feed overflows O._walk's 4,000)
    nxt = np.append(M["o"][1:], np.nan) + M["slip"]
    R_, p_, b_, s_, w_ = T.walk_tp(M["o"], M["h"], M["l"], M["c"], M["atr"], M["ent"], M["exl"], gate, int(cut), np.full(M["n"], STOP), nxt + TP * M["atr"], HOLD, M["cost"], M["slip"], int(M["last"]))
    return R_, p_, b_, s_
@njit(cache=True)
def walk_short(o, h, l, c, atr, ent_lo, ex_hi, gate, cut, stop, tp, hold, cost, slip, last_bar):
    m = len(c); n_max = 6000; R = np.full(n_max, np.nan); pct = np.full(n_max, np.nan); blk = np.zeros(n_max, np.int64); sig = np.zeros(n_max, np.int64); cnt = 0; busy = -1
    for i in range(1000, last_bar):
        if i <= busy: continue
        a = i + 1; anchor = atr[i]
        if not np.isfinite(anchor) or anchor <= 0.0 or not np.isfinite(ent_lo[i]) or l[i] >= ent_lo[i] or not gate[i]: continue
        px = o[a] - slip; risk = stop * anchor; fixed = px + risk; tgt = px - tp * anchor; end = min(a + hold, m - 2); out = np.nan; j = a
        while j <= end:
            lvl = fixed; ch = ex_hi[j]
            if np.isfinite(ch) and ch < lvl: lvl = ch
            cap = c[j - 1]
            if np.isfinite(cap) and lvl < cap: lvl = cap
            if h[j] >= lvl: out = (lvl if o[j] < lvl else o[j]) + slip; break
            if l[j] <= tgt: out = (tgt if o[j] > tgt else o[j]) + slip; break
            j += 1
        if not np.isfinite(out): j = end; out = c[j] + slip
        if cnt < n_max: R[cnt] = (px - out - cost) / risk; pct[cnt] = 100.0 * (px - out - cost) / px; blk[cnt] = 0 if i < cut else 1; sig[cnt] = i; cnt += 1
        busy = j
    return R[:cnt], pct[:cnt], blk[:cnt], sig[:cnt]

# ---- thresholds for cells B and C from NQ RESEARCH signal bars (fixed before any other feed is touched)
NQ = make("NQ"); Dnq = O.build(15); CUTNQ = int(Dnq["cut"])
sig_nq = np.zeros(NQ["n"], bool); sig_nq[1000:NQ["last"]] = (NQ["h"][1000:NQ["last"]] > NQ["ent"][1000:NQ["last"]]) & NQ["win"][1000:NQ["last"]]; sig_nq &= np.arange(NQ["n"]) < CUTNQ
QB = float(np.nanquantile(NQ["e200"][sig_nq], 2 / 3)); QC = float(np.nanquantile(NQ["dvw"][sig_nq], 1 / 3))
print(f"thresholds from NQ research signal bars: cell B (close-EMA200)/ATR <= {QB:.3f};  cell C (close-VWAP07)/ATR <= {QC:.3f}")

def cells(M):
    g4 = np.nan_to_num((M["d_sp"] <= CEIL).astype(float)).astype(bool) & (M["d_sp"] >= 0); g3 = np.nan_to_num((M["d_sp"] <= CEIL2).astype(float)).astype(bool) & (M["d_sp"] >= 0)
    return {"base (no gate)": M["win"], "gate: single print <= 4 ATR above [PRIMARY]": M["win"] & g4, "gate: single print <= 3 ATR above [secondary]": M["win"] & g3,
            "A: gate4 AND EMA13 < EMA48": M["win"] & g4 & (M["e1348"] < 0), "B: gate4 AND not extended (e200 <= q2/3)": M["win"] & g4 & np.nan_to_num((M["e200"] <= QB).astype(float)).astype(bool),
            "C: gate4 AND below VWAP07 (dvw <= q1/3)": M["win"] & g4 & np.nan_to_num((M["dvw"] <= QC).astype(float)).astype(bool)}

def stats_line(M, nm, gate, cut, blk, base_pct=None, ndraw=250):
    R_, p_, b_, s_ = walk(M, gate, cut); m = b_ == blk; q = p_[m]; r = R_[m]; sg = s_[m]
    if len(q) < 20: print(f"  {nm:46s} n {len(q):>4}  (too few)"); return None
    n = M["n"]; inb = (np.arange(n) < cut) if blk == 0 else (np.arange(n) >= cut)
    sigbar = np.zeros(n, bool); sigbar[1000:M["last"]] = (M["h"][1000:M["last"]] > M["ent"][1000:M["last"]]) & M["win"][1000:M["last"]]
    sig_idx = np.flatnonzero(sigbar & inb); keep = int((gate & sigbar & inb).sum()); day = M["day"]; sdays = day[sig_idx]; udays = np.unique(sdays)
    gdays = np.unique(day[sig_idx[gate[sig_idx]]]); ob = []; od = []; oe = []
    if keep < len(sig_idx):
        for _ in range(ndraw):
            gg = np.zeros(n, bool); gg[rng.choice(sig_idx, size=keep, replace=False)] = True; R2, p2, b2, s2 = walk(M, gg, cut); ob.append((pf(p2[b2 == blk]), p2[b2 == blk].mean()))
            dp = rng.choice(udays, size=len(gdays), replace=False); cand = sig_idx[np.isin(sdays, dp)]; kk = rng.choice(cand, size=min(keep, len(cand)), replace=False)
            gg = np.zeros(n, bool); gg[kk] = True; R2, p2, b2, s2 = walk(M, gg, cut); od.append((pf(p2[b2 == blk]), p2[b2 == blk].mean()))
    # random ENTRY at the same count inside the window
    pool = np.flatnonzero(M["win"] & inb & (np.arange(n) >= 1000) & (np.arange(n) < M["last"]))
    for _ in range(150):
        bars = np.sort(rng.choice(pool, size=min(len(q) * 3, len(pool)), replace=False))
        pc = O._walk_at(M["o"], M["h"], M["l"], M["c"], M["atr"], M["calm"], M["exl"], bars, STOP, STOP, TP, HOLD, M["cost"], M["slip"], int(M["last"])); pc = pc[np.isfinite(pc)][:len(q)]; oe.append((pf(pc), pc.mean()))
    ob = np.array(ob) if len(ob) else None; od = np.array(od) if len(od) else None; oe = np.array(oe)
    # bootstrap and PSR
    dl = pd.Series(q).groupby(day[sg]).sum(); ud = dl.index.to_numpy(); boot = np.array([np.concatenate([q[day[sg] == d_] for d_ in rng.choice(ud, size=len(ud), replace=True)]).mean() for _ in range(1000)])
    alld = np.unique(day[inb & (np.arange(n) >= 1000)]); dz = dl.reindex(alld).fillna(0.0).to_numpy(); sr = dz.mean() / dz.std(); g3, g4 = skew(dz), kurtosis(dz, fisher=False)
    psr = norm.cdf(sr * np.sqrt(len(dz) - 1) / np.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr * sr))
    yrs = pd.Series(q).groupby(M["ix"].year.to_numpy()[sg]).apply(lambda x: pf(x.to_numpy()))
    print(f"  {nm:46s} n {len(q):>4} PF {pf(q):6.3f} win {100*(q>0).mean():4.1f}% %/tr {q.mean():+.4f} R/tr {r.mean():+.4f} tot {q.sum():+7.2f}% DD {dd(q):5.2f}% SRann {sr*np.sqrt(252):+.2f} PSR {psr:.3f} P(m<=0) {np.mean(boot<=0):.3f}"
          + (f" | filter null bar p {np.mean(ob[:,0]>=pf(q)):.3f}/{np.mean(ob[:,1]>=q.mean()):.3f} day p {np.mean(od[:,0]>=pf(q)):.3f}/{np.mean(od[:,1]>=q.mean()):.3f} (ctl PF {np.nanmedian(od[:,0]):.3f})" if ob is not None else " | (base)")
          + f" | entry null PF {np.nanmedian(oe[:,0]):.3f} p {np.mean(oe[:,0]>=pf(q)):.3f}/{np.mean(oe[:,1]>=q.mean()):.3f}")
    print(f"  {'':46s} years PF: " + " ".join(f"{y}:{v:.2f}" for y, v in yrs.items()) + f"   keep {100*keep/max(len(sig_idx),1):.0f}% of {len(sig_idx)} signal bars, {len(gdays)}/{len(udays)} days")
    return dict(cell=nm, market=M["market"], block=blk, n=len(q), pf=pf(q), pct=q.mean(), R=r.mean(), tot=q.sum(), dd=dd(q), psr=psr, pboot=np.mean(boot <= 0),
                p_bar=np.mean(ob[:, 0] >= pf(q)) if ob is not None else np.nan, p_day=np.mean(od[:, 0] >= pf(q)) if od is not None else np.nan, p_day_mean=np.mean(od[:, 1] >= q.mean()) if od is not None else np.nan, p_entry=np.mean(oe[:, 0] >= pf(q)))

rows = []
line("2.1  US100 BEFORE 2022-12-26 -- the primary read (block 0); AFTER 2022-12-26 is the feed-parity block (block 1), never pooled")
U = make("US100"); cutU = int(np.searchsorted(U["ix"].values, np.datetime64("2022-12-26")))
print(f"  US100 15m: {U['n']:,} bars {U['ix'][0]} -> {U['ix'][-1]}; pre-2022-12-26 block {cutU:,} bars; cost {U['cost']} pts rt + {U['slip']}/side slip; median bin {np.nanmedian(0.10*U['atr']):.2f} pts (NQ 3.42)")
for blk, bn in ((0, "PRE 2022-12-26 (primary)"), (1, "post 2022-12-26 (parity with NQ, same weeks)")):
    print(f"\n  -- {bn} --")
    for nm, g in cells(U).items():
        r = stats_line(U, nm, g, cutU, blk); rows.append(r) if r else None
line("2.2  US30 (Dow) -- the mechanism test; whole file as one block, then by the feed's own research / validation / test split (descriptive)")
W = make("US30"); print(f"  US30 15m: {W['n']:,} bars {W['ix'][0]} -> {W['ix'][-1]}; cost {W['cost']} pts rt + {W['slip']}/side; median bin {np.nanmedian(0.10*W['atr']):.2f} pts")
for nm, g in cells(W).items():
    r = stats_line(W, nm, g, W["n"], 0); rows.append(r) if r else None
B = FD.blocks("US30", W["ix"]); Rg, pg, bg, sg = walk(W, cells(W)["gate: single print <= 4 ATR above [PRIMARY]"], W["n"]); Rb, pb, bb, sb = walk(W, W["win"], W["n"])
print("  by the feed's split (descriptive): " + "; ".join(f"{k}: gate n {int(B[k][sg].sum())} PF {pf(pg[B[k][sg]]):.3f} / base n {int(B[k][sb].sum())} PF {pf(pb[B[k][sb]]):.3f}" for k in B))
line("2.3  SHORT MIRROR on NQ research -- downside Donchian 10/10 breakout, prior-session single print within 4 ATR BELOW")
gs = np.nan_to_num((NQ["d_spb"] <= CEIL).astype(float)).astype(bool) & (NQ["d_spb"] >= 0)
for nm, g in (("short base (no gate)", NQ["win"]), ("short gate: single print <= 4 ATR below", NQ["win"] & gs)):
    R_, p_, b_, s_ = walk_short(NQ["o"], NQ["h"], NQ["l"], NQ["c"], NQ["atr"], NQ["ent_lo"], NQ["ex_hi"], g, CUTNQ, STOP, TP, HOLD, NQ["cost"], NQ["slip"], int(NQ["last"]))
    for blk, bn in ((0, "research"), (1, "locked (descriptive)")):
        q = p_[b_ == blk]; print(f"  {nm:42s} {bn:22s} n {len(q):>4} PF {pf(q):6.3f} win {100*(q>0).mean():4.1f}% %/tr {q.mean():+.4f} R/tr {R_[b_==blk].mean():+.4f} tot {q.sum():+7.2f}%")
# same-selectivity null for the short gate on research
sigS = np.zeros(NQ["n"], bool); sigS[1000:NQ["last"]] = (NQ["l"][1000:NQ["last"]] < NQ["ent_lo"][1000:NQ["last"]]) & NQ["win"][1000:NQ["last"]]; sigS &= np.arange(NQ["n"]) < CUTNQ
idx = np.flatnonzero(sigS); keep = int((gs & sigS).sum()); R_, p_, b_, s_ = walk_short(NQ["o"], NQ["h"], NQ["l"], NQ["c"], NQ["atr"], NQ["ent_lo"], NQ["ex_hi"], NQ["win"] & gs, CUTNQ, STOP, TP, HOLD, NQ["cost"], NQ["slip"], int(NQ["last"])); obs = pf(p_[b_ == 0]); out = []
for _ in range(250):
    gg = np.zeros(NQ["n"], bool); gg[rng.choice(idx, size=keep, replace=False)] = True; R2, p2, b2, s2 = walk_short(NQ["o"], NQ["h"], NQ["l"], NQ["c"], NQ["atr"], NQ["ent_lo"], NQ["ex_hi"], gg, CUTNQ, STOP, TP, HOLD, NQ["cost"], NQ["slip"], int(NQ["last"])); out.append(pf(p2[b2 == 0]))
print(f"  short gate vs same-selectivity random filter (research): keep {100*keep/len(idx):.0f}%, control PF median {np.nanmedian(out):.3f}, p {np.mean(np.array(out) >= obs):.3f}")
pd.DataFrame([r for r in rows if r]).to_parquet(os.path.join(ROOT, "results/inst/vp_next2.parquet"))
print(f"\n  runtime {time.time()-t0:.0f}s")
