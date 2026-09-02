"""Donchian breakout x EMA-cross trend alignment x ATR regime.

The user's spec: the most profitable Donchian intraday breakout, trend-following,
with EMA cross and ATR and other indicators, 07:00-11:00 New York, flat at 11:00.

What is already known (trend agent, 244 configs): price-vs-EMA STRUCTURE is dead,
EMA SLOPE is dead, higher-timeframe trend is dead. What has NOT been tested is the
EMA CROSS - fast over slow - as an alignment gate on the breakout, with its
freshness and separation, combined with an ATR regime filter. That is this file.

Every condition is read at the closed SIGNAL bar. Search is RESEARCH ONLY, scored
against the matched control. Walk-forward inside research is the OOS test; the
locked block has been opened twice already and is not touched here.
"""
import numpy as np, pandas as pd, itertools, time, json
import lab
from engine import atr as _atr, ema as _ema

N_ENTRY   = [10, 20, 40]
EMA_PAIRS = [(5,20), (8,21), (9,34), (13,50), (20,50), (50,200)]
EMA_MODE  = ["state", "cross4", "cross8", "sep0.25", "sep0.5"]
ATR_FILT  = ["none", "pct<0.8", "pct0.2-0.8", "exp>1.2"]
GEOM      = [(1.0,2.0), (1.5,2.0), (2.0,3.0)]


def prep(sym):
    df, w, r = lab.research(sym)
    c = df.close.values; n = len(df)
    A = _atr(df, 14)
    # causal trailing ATR percentile over 250 bars, shifted so bar i sees < i
    s = pd.Series(A)
    pct = s.rolling(250).apply(lambda v: (v[:-1] < v[-1]).mean(), raw=True).values
    expn = A / (s.shift(8).values + 1e-12)
    emas = {p: _ema(c, p) for p in sorted({x for pr in EMA_PAIRS for x in pr})}
    return dict(df=df, w=w, r=r, c=c, A=A, pct=pct, expn=expn, emas=emas, n=n,
                tod=df.tod.values)


def ema_gate(P, fast, slow, mode, side):
    f, s, A = P["emas"][fast], P["emas"][slow], P["A"]
    above = f > s
    sep = (f - s) / (A + 1e-12)
    if mode == "state":
        g_long, g_short = above, ~above
    elif mode.startswith("cross"):
        k = int(mode[5:])
        # a cross within the last k bars: state flipped somewhere in (i-k, i]
        up = above & ~np.roll(above, 1); dn = ~above & np.roll(above, 1)
        up[0] = dn[0] = False
        ru = pd.Series(up).rolling(k, min_periods=1).max().values.astype(bool)
        rd = pd.Series(dn).rolling(k, min_periods=1).max().values.astype(bool)
        g_long, g_short = above & ru, ~above & rd
    else:
        t = float(mode[3:])
        g_long, g_short = sep > t, sep < -t
    return g_long if side > 0 else g_short


def atr_gate(P, mode):
    pct, expn = P["pct"], P["expn"]
    if mode == "none":      return np.ones(P["n"], bool)
    if mode == "pct<0.8":   return pct < 0.8
    if mode == "pct0.2-0.8":return (pct >= 0.2) & (pct < 0.8)
    if mode == "exp>1.2":   return expn > 1.2
    raise ValueError(mode)


CKPT = "/home/user/main/data/donchian/emacross_partial.parquet"

def _key(d):
    return (d["sym"], d["n_entry"], d["fast"], d["slow"], d["mode"], d["atr"], d["stop"], d["targ"])

def run(sym, done=None, sink=None):
    """done: config keys already computed (resume). sink: shared list, checkpointed
    every 100 configs so a container restart loses at most 100, not the run."""
    P = prep(sym); df = P["df"]
    rows, k = [], 0
    done = done or set(); sink = sink if sink is not None else []
    t0 = time.time()
    base_idx = {}
    for ne in N_ENTRY:
        idx, side, _ = lab.signals(df, ne)
        ok = P["tod"][idx] > 420
        base_idx[ne] = (idx[ok], side[ok])
    for ne, (fast,slow), mode, af, (sm,tm) in itertools.product(
            N_ENTRY, EMA_PAIRS, EMA_MODE, ATR_FILT, GEOM):
        idx, side = base_idx[ne]
        if (sym, ne, fast, slow, mode, af, sm, tm) in done:
            k += 1; continue
        gl = ema_gate(P, fast, slow, mode, +1)[idx]
        gs = ema_gate(P, fast, slow, mode, -1)[idx]
        ag = atr_gate(P, af)[idx]
        keep = ((side > 0) & gl | (side < 0) & gs) & ag & ~np.isnan(P["pct"][idx])
        if keep.sum() < 60:
            rows.append(dict(sym=sym, n_entry=ne, fast=fast, slow=slow, mode=mode,
                             atr=af, stop=sm, targ=tm, n=int(keep.sum()), exp=np.nan,
                             excess=np.nan, z=np.nan, p=np.nan, sel=float(keep.mean())))
            sink.append(rows[-1]); k += 1; continue
        g, _ = lab.sig_gate(sym, idx[keep], side[keep], stop_mult=sm, targ_mult=tm,
                            n_draws=150, seed=k, quiet=True)
        rows.append(dict(sym=sym, n_entry=ne, fast=fast, slow=slow, mode=mode, atr=af,
                         stop=sm, targ=tm, n=g["n"], exp=g["exp"], excess=g["excess"],
                         z=g["z"], p=g["p"], pf=g["pf"], wr=g["wr"], sel=float(keep.mean())))
        k += 1
        sink.append(rows[-1])
        if k % 100 == 0:
            pd.DataFrame(sink).to_parquet(CKPT)
            print(f"    {sym} {k:>5}/{len(N_ENTRY)*len(EMA_PAIRS)*len(EMA_MODE)*len(ATR_FILT)*len(GEOM)}"
                  f"  {time.time()-t0:>5.0f}s  (checkpointed {len(sink)})", flush=True)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import os
    sink, done = [], set()
    if os.path.exists(CKPT):
        prev = pd.read_parquet(CKPT); sink = prev.to_dict("records")
        done = {_key(d) for d in sink}
        print(f"  resuming: {len(done)} configs already computed", flush=True)
    for sym in ("NAS", "US30"):
        run(sym, done=done, sink=sink)
    R = pd.DataFrame(sink)
    R.to_parquet("/home/user/main/data/donchian/emacross.parquet")
    R.to_csv("/home/user/main/docs/donchian/emacross_search.csv", index=False)
    print(f"\n  {len(R):,} configurations evaluated")
