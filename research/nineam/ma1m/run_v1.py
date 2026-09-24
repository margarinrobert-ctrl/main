"""vectorbt as a SECOND ENGINE, transcription first, on the four declared picks.

vectorbt 1.1.0 cannot express the breakeven ratchet, so BOTH engines run the reduced geometry: no
breakeven, zero cost, everything else as traded -- market order at the next bar's open, 100-point
stop and target as fractions of each fill, flat at 11:00, the pick's own MA exit. vectorbt is handed
exactly the research engine's ENTRIES (so the lock cannot differ) and decides every EXIT itself.
Exit signals are SHIFTED one bar (a cross read at bar j's close fills at j+1's open); an unshifted
exit with price=open is look-ahead (CLAUDE.md). Longs and shorts run as separate portfolios.
"""
import os, sys, json, subprocess
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import m_core as M

VENV = "/tmp/claude-0/-home-user-main/e473d7de-e277-515e-b24b-75724aaa9da5/scratchpad/vbtenv/bin/python"
B = M.Base()
f = B.f; n = len(f); mod = f["mod"].to_numpy()
z = np.load(os.path.join(HERE, "s1_sweep.npz")); meta = z["meta"]
picks = json.load(open(os.path.join(HERE, "s2_picks.json")))
ob = json.load(open(os.path.join(HERE, "o1_best.json")))["best"]
cells = []
for k, r in picks.items():
    pid, rem = r // 48, r % 48
    kf, ks, nf, ns = meta[pid]
    cells.append((k, M.TYPES[kf], int(nf), M.TYPES[ks], int(ns), M.cfg_dict(rem // 3, rem % 3)))
q = dict(M.P0, ma_mode="state" if ob["gate_mode"] == "state" else "xcross", x_mode=ob["exit"])
if ob["gate_mode"] != "state": q["cross_min"] = ob["cross_min"]
cells.append(("D Optuna best", ob["fast_type"], ob["fast_len"], ob["slow_type"], ob["slow_len"], q))

flat = np.zeros(n, bool); flat[1:] = (mod[1:] >= 660) & (mod[:-1] < 660)
rows = []
for name, kf, nf, ks, ns, cfg in cells:
    c = M.ctx_for(B, kf, nf, ks, ns)
    red = dict(cfg, be_pts=0.0, be_off=0.0, cost_mult=0.0)
    tr = c.trades(red)
    cx = {"cross": c.cx_cross, "state": c.cx_state}.get(red["x_mode"])
    payload = {}
    for side, lab in [(1, "long"), (-1, "short")]:
        t = tr[tr.side == side]
        ent = np.zeros(n, bool); ent[t.eb.to_numpy()] = True
        ex = flat.copy()
        if cx is not None:
            against = (side * cx) < 0
            ex[1:] |= against[:-1]                   # read at j's close, filled at j+1's open
        ex[t.eb.to_numpy()] = False                  # the engine never exits on the fill bar's own open
        sl = np.full(n, np.nan); sl[t.eb.to_numpy()] = 100.0 / t.ent.to_numpy()
        payload[lab] = dict(ent=ent, ex=ex, sl=sl)
    np.savez(os.path.join(HERE, "_vbt_in.npz"), o=f.open.to_numpy(), h=f.high.to_numpy(),
             l=f.low.to_numpy(), c=f.close.to_numpy(),
             **{f"{k}_{s}": v for s, d in payload.items() for k, v in d.items()})
    res = subprocess.run([VENV, os.path.join(HERE, "vbt_side.py")], capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stderr[-2000:]); raise SystemExit("vbt side failed")
    v = json.loads(res.stdout.strip().splitlines()[-1])
    eng_n, eng_pts = len(tr), float(tr.pts.mean())
    same_exit = v["same_exit_frac"] if "same_exit_frac" in v else np.nan
    # exit-bar agreement, trade by trade
    vx = np.asarray(v["exit_idx"]); ve = np.asarray(v["entry_idx"])
    m_eng = dict(zip(tr.eb.to_numpy(), tr.xb.to_numpy()))
    agree = np.mean([m_eng.get(e, -1) == x for e, x in zip(ve, vx)]) if len(ve) else np.nan
    rows.append(dict(pick=name, eng_n=eng_n, vbt_n=v["n"], ratio=v["n"] / max(eng_n, 1),
                     same_exit_bar=agree, eng_pts=eng_pts, vbt_pts=v["mean_pnl"],
                     gap=v["mean_pnl"] - eng_pts))
    print(f"  {name:40s} engine {eng_n:3d} / vbt {v['n']:3d} (ratio {v['n']/max(eng_n,1):.3f})  "
          f"same exit bar {agree:.1%}   pts/trade engine {eng_pts:+.2f} vbt {v['mean_pnl']:+.2f}", flush=True)
pd.DataFrame(rows).to_csv(os.path.join(HERE, "v1_vbt.csv"), index=False)
os.remove(os.path.join(HERE, "_vbt_in.npz"))
