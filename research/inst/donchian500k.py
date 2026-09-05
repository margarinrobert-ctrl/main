"""A Donchian trend-following breakout sweep of 504,000 configurations for the Edge Finder.

Space (declared before running): 3 timeframes (5/15/30m) x 2 entry sessions (RTH 09:30-15:30 NY,
all hours) x 5 entry channels x 4 MA200-floor readings x 4 CHOP ceilings x 3 exit channels x
5 stops x 7 targets x 5 hold caps x adaptive stop on/off = 504,000 cells. Long only. Every cell
pays MNQ costs. Selection is on the RESEARCH block; the locked column is read for the population
(the transfer statistics) and for the envelope cells only."""
import os, sys, warnings, time
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/inst"):
    sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 126 + f"\n{t}\n" + "=" * 126)
ENTS = (15, 20, 30, 40, 55); MA = (-99.0, 0.0, 1.0, 2.0); CHOPS = (99.0, 50.0, 45.0, 40.0)
STOPS = (1.0, 1.5, 2.0, 2.5, 3.0); TPS = (0.0, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0)
HOLD_H = {"2h": 2.0, "4h": 4.0, "6.5h": 6.5, "2d": 48.0, "swing": 480.0}
def geometry(tf):
    rows = []
    for ei, e in enumerate(V.EXITS):
        for st in STOPS:
            for tp in TPS:
                for hn, hh in HOLD_H.items():
                    hb = 480 if hn == "swing" else max(1, int(round(hh * 60 / tf)))
                    for ad in (0, 1):
                        rows.append(dict(exN=e, ei=ei, stop=st, tp=tp, hold=hb, hold_name=hn, adapt=ad, shi=st, slo=(st - 1.0) if ad else st))
    return pd.DataFrame(rows)
def signal_sets(D, mask):
    h, n = D["h"], D["n"]
    base = np.asarray(h > D["ent_hi"][min(ENTS)], bool).copy()
    base[:1000] = False; base[-500:] = False
    base &= np.isfinite(D["atr"]) & (D["atr"] > 0) & np.isfinite(D["vpct"]) & mask
    rows = np.flatnonzero(base)
    ent_m = {e: np.asarray(h[rows] > D["ent_hi"][e][rows], bool) for e in ENTS}
    dm, ch = D["d_ma"][rows], D["chop"][rows]
    offs = [0]; vals = []; keys = []
    for e in ENTS:
        for ma in MA:
            for cp in CHOPS:
                m = ent_m[e].copy()
                if ma > -50: m &= np.isfinite(dm) & (dm >= ma)
                if cp < 90: m &= np.isfinite(ch) & (ch <= cp)
                idx = np.flatnonzero(m); vals.append(idx); offs.append(offs[-1] + len(idx))
                keys.append(dict(ent=e, ma=ma, chop=cp, k=0, w=0, psh=0))
    return rows, np.asarray(offs, np.int64), np.concatenate(vals).astype(np.int64), pd.DataFrame(keys)
frames = []; t0 = time.time()
for tf in (5, 15, 30):
    D = V.build(tf)
    Gd = geometry(tf)
    exlo = np.vstack([D["ex_lo"][e] for e in V.EXITS])
    calm = np.zeros(D["n"], np.bool_); v = D["vpct"]; calm[np.isfinite(v)] = v[np.isfinite(v)] <= 0.5
    for sname, mask in (("RTH", (D["mod"] >= 570) & (D["mod"] < 930)), ("all", np.ones(D["n"], bool))):
        rows, offs, vals, K = signal_sets(D, mask)
        xb, R, pts = V._tensor(D["o"], D["h"], D["l"], D["c"], D["atr"], rows.astype(np.int64), exlo, calm,
                               Gd["ei"].to_numpy(np.int64), Gd["shi"].to_numpy(float), Gd["slo"].to_numpy(float),
                               Gd["tp"].to_numpy(float), Gd["hold"].to_numpy(np.int64), V.COST, V.SLIP, D["n"])
        epx = D["o"][np.minimum(rows + 1, D["n"] - 1)]
        st = V._sweep(offs, vals, rows.astype(np.int64), xb, R, pts, epx, D["cut"], len(Gd))
        ls = V._sweep_loss(offs, vals, rows.astype(np.int64), xb, R, D["cut"], len(Gd))
        d = V.table(dict(G=Gd, K=K, stat=st, loss=ls), tf)
        d["hold_name"] = Gd["hold_name"].to_numpy()[np.tile(np.arange(len(Gd)), len(K))]
        d["session"] = sname
        frames.append(d); print(f"  tf {tf} {sname}: {len(d):,} cells  ({time.time()-t0:.0f}s)")
G = pd.concat(frames, ignore_index=True)
G["tpy_res"] = G.n_res / V.YEARS["res"]; G["tpy_lock"] = G.n_lock / V.YEARS["lock"]
G["tot_res"] = G.n_res * G.pct_res; G["tot_lock"] = G.n_lock * G.pct_lock
G.to_parquet("results/inst/donchian500k.parquet")
line(f"A. THE POPULATION -- {len(G):,} Donchian breakout configurations, long only, MNQ costs")
ok = G[G.n_res >= 40].copy()
print(f"  cells with >= 40 research trades: {len(ok):,} ({100*len(ok)/len(G):.1f}%)")
print(f"  profitable on research: {100*(ok.pct_res > 0).mean():.1f}%   median PF {ok.pf_res.median():.3f}   median trades/yr {ok.tpy_res.median():.0f}")
print(f"  profitable on locked:   {100*(ok.pct_lock > 0).mean():.1f}%   median PF {ok.pf_lock.median():.3f}")
print(f"  corr(PF research, PF locked): {ok[['pf_res','pf_lock']].corr().iloc[0,1]:+.3f}  Spearman {ok[['pf_res','pf_lock']].corr('spearman').iloc[0,1]:+.3f}")
top = ok.sort_values("tot_res", ascending=False)
for q in (100, 1000, len(ok)//100):
    s = top.head(q); print(f"  top {q:>6,} by research total: mean PF {s.pf_res.mean():.3f} -> locked {s.pf_lock.mean():.3f}   total {s.tot_res.mean():+.1f}% -> {s.tot_lock.mean():+.1f}%   share locked-profitable {100*(s.pct_lock>0).mean():.0f}%")
line("B. MARGINAL AVERAGE PER AXIS (research PF | locked PF | trades/yr) -- read this, never the top row")
for ax in ("tf", "session", "ent", "exN", "stop", "tp", "hold_name", "adapt", "ma", "chop"):
    print(f"  {ax:>9}: " + "   ".join(f"{k}: {v.pf_res.mean():.3f}|{v.pf_lock.mean():.3f}|{v.tpy_res.mean():.0f}" for k, v in ok.groupby(ax)))
line("C. THE ENVELOPE -- best research PF at each minimum trade count, then THAT cell on locked")
for mn in (25, 50, 100, 150, 200, 300, 500):
    s = ok[ok.tpy_res >= mn]
    if len(s) == 0: continue
    b = s.loc[s.pf_res.idxmax()]
    print(f"  >= {mn:>3}/yr: {len(s):>7,} cells  best research PF {b.pf_res:.3f} ({b.tpy_res:.0f}/yr, tf{b.tf} {b.session} ent{b.ent} ex{b.exN} stop{b.stop} tp{b.tp} {b.hold_name} adapt{b.adapt} ma{b.ma} chop{b.chop}) -> locked {b.pf_lock:.3f} ({b.tpy_lock:.0f}/yr)")
print(f"\n  cells at PF >= 2.0 and >= 200/yr on research: {int(((ok.pf_res >= 2) & (ok.tpy_res >= 200)).sum())}")
line("D. TOP 15 BY RESEARCH TOTAL RETURN, with the locked column (the max of many draws; shape only)")
print(top.head(15)[["tf","session","ent","exN","stop","tp","hold_name","adapt","ma","chop","n_res","pf_res","tot_res","n_lock","pf_lock","tot_lock"]].to_string(index=False))
