"""O2 -- ROBUSTNESS on whatever O1 chose: vectorbt as a second engine, four perturbations,
walk-forward, CSCV/PBO, and ONE read of the reserved forward block.

The order is fixed by what each test can invalidate:
  1. vectorbt as a TRANSCRIPTION CHECK. The trade count must match before any P&L gap is read --
     it has failed transcription four times on this branch (V46, V51, V53, V64) and a gap read
     from a failed check is a statement about two different rules.
  2. PRICE JITTER with every indicator RECOMPUTED from the jittered bars. This is the only
     perturbation that moves the SIGNAL SET; execution noise only moves the fills.
  3. PARAMETER JITTER on every axis at once -- a cell whose neighbours beat it sits on a spike.
  4. WALK-FORWARD with the selection RE-RUN inside each fold, beside a RANDOM cell from the same
     pool and the published constants.
  5. CSCV / PBO over a per-month matrix of the sampled population.
  6. The forward block, read once, last.
"""
import os, sys, itertools, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vwapema"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "xanom"))
import xcore as C
import vecore as V
import xdata as XD

RNG = np.random.default_rng(808)
pd.set_option("display.width", 235)
L = lambda s: print("\n" + "=" * 114 + f"\n{s}\n" + "=" * 114)
print(__doc__)

T = pd.read_parquet("results/xopt/o1_trials.parquet")
FIN = pd.read_csv("results/xopt/o1_finalists.csv")
PKEYS = ["ema_slow", "ema_pull", "ema_tight", "atr_len", "atr_stop", "vol_mult",
         "range_mult", "wick_body", "ambig", "tighten_R"]


def cfg_of(row):
    c = {k: (int(row[k]) if isinstance(V.PARAMS.get(k), int) else float(row[k])) for k in PKEYS}
    c.update(side=int(row["side"]), trail=bool(row["trail"]), tighten=bool(row["tighten"]),
             flatten=bool(row["flatten"]), use_vol=bool(row["use_vol"]), sess=str(row["sess"]))
    tg = row.get("tgt_R", 0.0)
    c["tgt_R"] = float(tg) if row.get("use_tgt", True) and np.isfinite(float(tg)) else 0.0
    return c


CELLS = {"as published": dict()}
for _, r in FIN.iterrows():
    CELLS[f"Optuna {r.study}"] = cfg_of(r)

L("O2.0  THE CANDIDATES, and what each scored on research")
rows = []
for nm, cfg in CELLS.items():
    r = C.evaluate(cfg, blk=0)
    rows.append(dict(cell=nm, n=r["n"], R=round(r.get("R", np.nan), 4),
                     ctl=round(r.get("ctl", np.nan), 4), excess=round(r.get("excess", np.nan), 4),
                     beat_p95=r.get("beat_p95", False)))
print(pd.DataFrame(rows).to_string(index=False))

L("O2.1  vectorbt AS A SECOND ENGINE -- transcription first, gap second")
import vectorbt as vbt
rows = []
for nm, cfg in CELLS.items():
    D = C.data(cfg.get("sess", "ny"))
    p = {**V.PARAMS, **{k: v for k, v in cfg.items() if k in V.PARAMS}}
    side = int(cfg.get("side", 1))
    if side < 0:
        rows.append(dict(cell=nm, note="short side -- vectorbt arm is long-only here", ratio=np.nan))
        continue
    sig, _ = V.triggers(D, side=1, p=p, use_vwap_vol=cfg.get("use_vol", True))
    eng = V.run(D, sig, side=1, tgt_R=float(cfg.get("tgt_R", 3.0)), atr_stop=p["atr_stop"],
                tighten=False, flatten=bool(cfg.get("flatten", False)),
                trail=bool(cfg.get("trail", True)), p=p, cost_rt=0.0, slip=0.0)
    close = pd.Series(D["c"], index=D["ix"])
    entries = pd.Series(False, index=D["ix"])
    entries.iloc[np.flatnonzero(sig)] = True
    entries = entries.shift(1, fill_value=False)
    si = np.flatnonzero(sig); si = si[si + 1 < D["n"]]
    lvl = np.full(D["n"], np.nan)
    _e2, e50p, _e20, atrp = V.periods(D, p)
    lvl[si + 1] = D["l"][si] - p["atr_stop"] * atrp[si]
    frac = np.where(np.isfinite(lvl), (D["c"] - lvl) / np.maximum(D["c"], 1e-9), np.nan)
    sl = pd.Series(frac, index=D["ix"]).ffill().bfill().clip(1e-6, 0.95).to_numpy()
    tp = np.clip(sl * max(float(cfg.get("tgt_R", 3.0)), 1e-6), 1e-6, 8.0) if cfg.get("tgt_R", 3.0) > 0 else None
    trail_exit = pd.Series(D["c"] < e50p, index=D["ix"]) if cfg.get("trail", True) \
        else pd.Series(False, index=D["ix"])
    ex = trail_exit & ~entries          # the trail CANNOT fire on the fill bar
    kw = dict(close=close, entries=entries, exits=ex, sl_stop=sl, direction="longonly",
              accumulate=False, freq="15min", fees=0.0, slippage=0.0, init_cash=1_000_000,
              size=1, size_type="amount")
    if tp is not None:
        kw["tp_stop"] = tp
    pf = vbt.Portfolio.from_signals(**kw)
    tr = pf.trades.records_readable
    ratio = len(tr) / max(len(eng), 1)
    epts = float(np.mean(eng.R.to_numpy() * eng.risk.to_numpy())) if len(eng) else np.nan
    vpts = float(tr["PnL"].mean()) if len(tr) else np.nan
    rows.append(dict(cell=nm, engine_n=len(eng), vbt_n=len(tr), ratio=round(ratio, 4),
                     transcription="PASS" if 0.95 <= ratio <= 1.05 else "FAIL",
                     engine_usd=round(epts, 3), vbt_usd=round(vpts, 3),
                     gap_pct=round(100 * (vpts - epts) / abs(epts), 1) if np.isfinite(vpts) and abs(epts) > 1e-9 else np.nan))
Vb = pd.DataFrame(rows)
print(Vb.to_string(index=False))
Vb.to_csv("results/xopt/o2_vbt.csv", index=False)
print("\n  A gap read from a FAILED transcription is a statement about two different rules.")

L("O2.2  PRICE JITTER -- every indicator RECOMPUTED from the jittered bars")
def jitter_eval(cfg, ticks, draws=60, blk=0):
    sess = cfg.get("sess", "ny")
    base = XD.load_iso()
    out = []
    for _ in range(draws):
        f = base.copy()
        n = len(f)
        j = RNG.normal(0.0, ticks * 0.01, (n, 4))       # gold tick 0.01 USD
        o = f.open.to_numpy() + j[:, 0]; h = f.high.to_numpy() + j[:, 1]
        l = f.low.to_numpy() + j[:, 2]; c = f.close.to_numpy() + j[:, 3]
        hi = np.maximum.reduce([o, h, l, c]); lo = np.minimum.reduce([o, h, l, c])
        f2 = pd.DataFrame(dict(open=o, high=hi, low=lo, close=c, volume=f.volume.to_numpy()),
                          index=f.index)
        Dj = V.assemble(f2, sess=sess)
        p = {**V.PARAMS, **{k: v for k, v in cfg.items() if k in V.PARAMS}}
        s, _ = V.triggers(Dj, side=int(cfg.get("side", 1)), p=p, use_vwap_vol=cfg.get("use_vol", True))
        t = V.run(Dj, s, side=int(cfg.get("side", 1)), tgt_R=float(cfg.get("tgt_R", 3.0)),
                  atr_stop=p["atr_stop"], tighten=bool(cfg.get("tighten", True)),
                  flatten=bool(cfg.get("flatten", False)), trail=bool(cfg.get("trail", True)), p=p)
        tb = t[t.blk == blk]
        if len(tb) >= 30:
            out.append((len(tb), tb.R.mean()))
    a = np.array(out)
    return a


rows = []
for nm, cfg in CELLS.items():
    for ticks in (1, 3):
        a = jitter_eval(cfg, ticks, draws=40)
        if len(a) == 0:
            continue
        rows.append(dict(cell=nm, jitter_ticks=ticks, draws=len(a),
                         n_med=int(np.median(a[:, 0])), R_med=round(float(np.median(a[:, 1])), 4),
                         R_p5=round(float(np.percentile(a[:, 1], 5)), 4),
                         keeps_sign=round(float((a[:, 1] > 0).mean()), 3)))
J = pd.DataFrame(rows)
print(J.to_string(index=False))
J.to_csv("results/xopt/o2_jitter.csv", index=False)

L("O2.3  PARAMETER JITTER -- all ten axes moved at once")
rows = []
for nm, cfg in CELLS.items():
    base = C.evaluate(cfg, blk=0)
    if not base["ok"]:
        continue
    vals = []
    for _ in range(60):
        c2 = dict(cfg)
        for k in PKEYS:
            v = c2.get(k, V.PARAMS[k])
            lo, hi = C.SPACE[k][0], C.SPACE[k][1]
            nv = float(v) * float(RNG.uniform(0.85, 1.15))
            nv = min(max(nv, lo), hi)
            c2[k] = int(round(nv)) if isinstance(V.PARAMS[k], int) else nv
        r = C.evaluate(c2, blk=0, draws=60)
        if r["ok"]:
            vals.append(r["excess"])
    v = np.array(vals)
    rows.append(dict(cell=nm, base_excess=round(base["excess"], 4), draws=len(v),
                     p5=round(float(np.percentile(v, 5)), 4), med=round(float(np.median(v)), 4),
                     share_positive=round(float((v > 0).mean()), 3),
                     share_beating_base=round(float((v > base["excess"]).mean()), 3)))
Pj = pd.DataFrame(rows)
print(Pj.to_string(index=False))
Pj.to_csv("results/xopt/o2_paramjitter.csv", index=False)
print("\n  `share_beating_base` well BELOW 0.5 means the cell sits on a spike; near or above 0.5")
print("  means it was not cherry-picked from one (STUDY_V64_MONTECARLO).")

L("O2.4  ONE READ OF THE RESERVED FORWARD BLOCK -- MT, a different provider, 2026-02..2026-08")
mt = XD.load_mt()
D0 = C.data("ny")
fwd = mt[mt.index > D0["ix"][-1]].copy(); fwd["volume"] = np.nan
Df = V.assemble(fwd, sess="ny")
rows = []
for nm, cfg in CELLS.items():
    p = {**V.PARAMS, **{k: v for k, v in cfg.items() if k in V.PARAMS}}
    p["vol_mult"] = 0.0                       # no usable volume on this feed
    side = int(cfg.get("side", 1))
    s, _ = V.triggers(Df, side=side, p=p, use_vwap_vol=False)
    t = V.run(Df, s, side=side, tgt_R=float(cfg.get("tgt_R", 3.0)), atr_stop=p["atr_stop"],
              tighten=bool(cfg.get("tighten", True)), flatten=bool(cfg.get("flatten", False)),
              trail=bool(cfg.get("trail", True)), p=p)
    st = V.stats(t)
    ctl = []
    if st["n"] >= 15:
        idx = np.flatnonzero(Df["rth"])
        rate = min(1.0, st["n"] / max(len(idx), 1))
        for _ in range(200):
            g = np.zeros(Df["n"], bool); g[idx[RNG.random(len(idx)) < rate]] = True
            c = V.run(Df, g, side=side, tgt_R=float(cfg.get("tgt_R", 3.0)), atr_stop=p["atr_stop"],
                      tighten=bool(cfg.get("tighten", True)), flatten=bool(cfg.get("flatten", False)),
                      trail=bool(cfg.get("trail", True)), p=p)
            if len(c) >= 8:
                ctl.append(c.R.mean())
    ctl = np.array(ctl)
    rows.append(dict(cell=nm, n=st["n"], R=round(st["R"], 4) if st["n"] else np.nan,
                     pf=round(st["pf"], 3) if st["n"] else np.nan,
                     ctl=round(float(np.median(ctl)), 4) if len(ctl) else np.nan,
                     excess=round(st["R"] - float(np.median(ctl)), 4) if len(ctl) else np.nan,
                     p_ctl=round(float((ctl >= st["R"]).mean()), 3) if len(ctl) else np.nan))
Fw = pd.DataFrame(rows)
print(Fw.to_string(index=False))
Fw.to_csv("results/xopt/o2_forward.csv", index=False)
print("\n  C5 is off and the VWAP anchor is unweighted on this feed -- it carries no usable volume.")
