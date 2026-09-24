"""Runs INSIDE the vectorbt venv. Reads _vbt_in.npz, prints one JSON line."""
import os, json
import numpy as np, pandas as pd, vectorbt as vbt
d = np.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_vbt_in.npz"))
idx = pd.RangeIndex(len(d["o"]))
recs = []
for side, direction in [("long", "longonly"), ("short", "shortonly")]:
    if d[f"ent_{side}"].sum() == 0:
        continue
    pf = vbt.Portfolio.from_signals(
        close=pd.Series(d["c"], index=idx), open=pd.Series(d["o"], index=idx),
        high=pd.Series(d["h"], index=idx), low=pd.Series(d["l"], index=idx),
        entries=pd.Series(d[f"ent_{side}"], index=idx), exits=pd.Series(d[f"ex_{side}"], index=idx),
        price=pd.Series(d["o"], index=idx),
        sl_stop=pd.Series(d[f"sl_{side}"], index=idx), tp_stop=pd.Series(d[f"sl_{side}"], index=idx),
        stop_entry_price="fillprice", size=1.0, size_type="amount", fees=0.0, slippage=0.0,
        init_cash=1e12, accumulate=False, direction=direction)
    r = pf.trades.records_readable
    ec = next(c for c in ("Entry Index", "Entry Timestamp", "entry_idx") if c in r.columns)
    xc = next(c for c in ("Exit Index", "Exit Timestamp", "exit_idx") if c in r.columns)
    pc = next(c for c in ("PnL", "pnl") if c in r.columns)
    recs.append(pd.DataFrame({"e": r[ec].astype(int), "x": r[xc].astype(int), "p": r[pc].astype(float)}))
r = pd.concat(recs) if recs else pd.DataFrame(columns=["e", "x", "p"])
print(json.dumps(dict(n=int(len(r)), mean_pnl=float(r.p.mean()) if len(r) else float("nan"),
                      entry_idx=r.e.tolist(), exit_idx=r.x.tolist())))
