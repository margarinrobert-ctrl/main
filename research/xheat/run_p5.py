"""P5 -- THE POLICIES HEAD TO HEAD, paired, with one locked read and the trial count stated.

Five DECLARED configurations, written down before any is scored. Each is the previous one plus
exactly one mechanism, so every line of the table is an ablation rather than a separate search:

  A  baseline        no stop, no target, flatten at 11:00
  B  + fixed stop    the best-marginal fixed multiple from P2 (not the best CELL)
  C  + adaptive stop the same base multiple scaled by volatility percentile and by time remaining
  D  + secure        C plus breakeven at 1.0 ATR (+0.25) and a trail armed at 1.0, distance 1.0
  E  + clock tighten D plus halving the trail distance in the last half of the window

Scored PAIRED on the same trades against A, with a day-block bootstrap on the DIFFERENCE, because
the two arms share almost all of their risk and comparing standalone means is the wrong test.

TRIALS COUNTED: P2's declared grid was 4,480 cells per feed-side-entry; P3 screened 30 features
x 2 targets; this phase adds 5 configurations x 2 sides x 2 feeds. Nothing here is deflated as if
it were a discovery, because nothing here IS one -- the entry has no edge (P3.1: 0 of 6 entries
positive on the ISO research block) and this is loss control measured on it.
"""
import sys, os, time
sys.path.insert(0, "research"); sys.path.insert(0, "research/xheat")
import numpy as np, pandas as pd
import xdata as X, xsig as S, xpath as P, xpol as PL

R = "results/xheat/"
os.makedirs(R, exist_ok=True)
print(__doc__)
t0 = time.time()
RNG = np.random.default_rng(23)
FEEDS = {"ISO": X.assemble(X.load_iso()), "MT": X.assemble(X.load_mt())}
BASE_STOP = 2.0          # P2's stop marginal is flat 2.0-3.0; 2.0 is the tighter end of the plateau


def run_cfg(D, idx, side, cfg, vp, ml):
    k = len(idx); wl = D["win_end"] - D["win_start"]
    if cfg["stop"] == "none":
        sm = np.zeros(k)
    elif cfg["stop"] == "fixed":
        sm = np.full(k, BASE_STOP)
    else:
        sm = PL.stop_multiple(BASE_STOP, vp, ml, wl)
    Rr = np.full(k, np.nan); why = np.zeros(k, np.int64)
    hold = np.zeros(k, np.int64); mfe = np.full(k, np.nan); mae = np.full(k, np.nan)
    PL.walk_adaptive(D["o"], D["h"], D["l"], D["c"], D["atr"], idx.astype(np.int64), side,
                     D["last_win"], X.COST_RT, X.SLIP, sm,
                     cfg["arm"], cfg["tr"], cfg["be"], cfg["be_off"], cfg["tight"],
                     Rr, why, hold, mfe, mae)
    return Rr, why, mae, sm


CFG = [
    ("A  baseline",        dict(stop="none",  arm=0.0, tr=0.0, be=0.0, be_off=0.0, tight=0.0)),
    ("B  + fixed stop",    dict(stop="fixed", arm=0.0, tr=0.0, be=0.0, be_off=0.0, tight=0.0)),
    ("C  + adaptive stop", dict(stop="adapt", arm=0.0, tr=0.0, be=0.0, be_off=0.0, tight=0.0)),
    ("D  + secure winner", dict(stop="adapt", arm=1.0, tr=1.0, be=1.0, be_off=0.25, tight=0.0)),
    ("E  + clock tighten", dict(stop="adapt", arm=1.0, tr=1.0, be=1.0, be_off=0.25, tight=0.5)),
]


def day_boot(diff, days, n=2000):
    ud = np.unique(days)
    out = np.empty(n)
    for i in range(n):
        pick = RNG.choice(ud, len(ud), replace=True)
        idx = np.concatenate([np.flatnonzero(days == d) for d in pick])
        out[i] = diff[idx].mean()
    return out


rows = []
for nm, D in FEEDS.items():
    F, _ = S.build_features(D, with_volume=np.isfinite(D["v"]).any())
    for side in (1, -1):
        idx = S.events(D, "break", 20, side)
        vp = F["vol.atr_pct500"][idx]
        ml = F["sess.mins_left"][idx]
        days = D["day"][idx]; blk = D["blk"][idx]
        res = {}
        for lab, cfg in CFG:
            Rr, why, mae, sm = run_cfg(D, idx, side, cfg, vp, ml)
            res[lab] = (Rr, why, mae, sm)
        A = res["A  baseline"][0]
        for lab, _ in CFG:
            Rr, why, mae, sm = res[lab]
            for b, bl in ((0, "research"), (1, "LOCKED")):
                m = (blk == b) & np.isfinite(Rr) & np.isfinite(A)
                if m.sum() < 60:
                    continue
                r = Rr[m]; neg = r[r < 0]; pos = r[r > 0]
                d = r - A[m]
                bs = day_boot(d, days[m]) if lab != "A  baseline" else np.zeros(1)
                rows.append(dict(
                    feed=nm, side="L" if side > 0 else "S", block=bl, cfg=lab, n=int(m.sum()),
                    R=float(r.mean()), pf=float(pos.sum() / max(-neg.sum(), 1e-9)),
                    win=float((r > 0).mean()),
                    mean_loss=float(neg.mean()) if len(neg) else 0.0,
                    p95_loss=float(np.percentile(r, 5)),
                    worst=float(r.min()), mean_mae=float(np.nanmean(mae[m])),
                    dd=float(np.max(np.maximum.accumulate(np.cumsum(r)) - np.cumsum(r))),
                    stop_mult=float(np.nanmean(sm[m])) if sm.any() else 0.0,
                    p_stop=float((why[m] == 1).mean()),
                    dR=float(d.mean()),
                    boot_p=float((bs <= 0).mean()) if lab != "A  baseline" else np.nan))
T = pd.DataFrame(rows)
T.to_csv(R + "p5_configs.csv", index=False)
pd.set_option("display.width", 240); pd.set_option("display.max_columns", 40)

for nm in FEEDS:
    for side in ("L", "S"):
        s = T[(T.feed == nm) & (T.side == side)]
        if s.empty:
            continue
        print("\n" + "=" * 108)
        print(f"{nm}  {'LONG' if side=='L' else 'SHORT'}  -- Donchian-20 break, 07:00-11:00 NY, flat 11:00")
        print("=" * 108)
        print(s[["block", "cfg", "n", "R", "pf", "win", "mean_loss", "p95_loss", "worst",
                 "mean_mae", "dd", "stop_mult", "p_stop", "dR", "boot_p"]]
              .to_string(index=False, float_format=lambda v: f"{v:+.4f}"))

print("\n" + "=" * 108)
print("WHAT THE ASK ACTUALLY BOUGHT -- the two quantities the request named, ISO long, research")
print("=" * 108)
s = T[(T.feed == "ISO") & (T.side == "L") & (T.block == "research")].set_index("cfg")
a, e = s.loc["A  baseline"], s.loc["E  + clock tighten"]
print(f"  mean LOSS per losing trade  {a.mean_loss:+.3f} ATR  ->  {e.mean_loss:+.3f} ATR   "
      f"({(1-e.mean_loss/a.mean_loss)*100:+.0f}%)")
print(f"  5th-percentile trade        {a.p95_loss:+.3f} ATR  ->  {e.p95_loss:+.3f} ATR")
print(f"  worst single trade          {a.worst:+.3f} ATR  ->  {e.worst:+.3f} ATR")
print(f"  max drawdown                {a.dd:.1f} ATR      ->  {e.dd:.1f} ATR   "
      f"({(1-e.dd/a.dd)*100:+.0f}%)")
print(f"  win rate                    {a.win:.1%}        ->  {e.win:.1%}")
print(f"  expectancy                  {a.R:+.4f} ATR   ->  {e.R:+.4f} ATR   "
      f"(dR {e.dR:+.4f}, day-block bootstrap p {e.boot_p:.3f})")
print(f"\ntotal {time.time()-t0:.0f}s")
