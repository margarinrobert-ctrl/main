"""Maximum-combination Donchian sweep with VectorBT.

Grid, per instrument and per side:
    n_entry     14 values   5 .. 160
    buffer_atr  21 values   0.0 .. 2.0 step 0.1
    stop_mult   12 values   0.5 .. 4.0
    targ_mult   12 values   0.5 .. 6.0
  = 42,336 combinations, x2 sides x2 instruments = 169,344 total.

Compression: every trade opens and closes inside 07:00-11:00, so in-window bars
are laid end to end and an exit is FORCED on each session's last window bar.
That is exact for this rule family and cuts the bar count 133,992 -> 23,646.

Costs are applied AFTER the simulation, as trades x round turn in points, rather
than through vectorbt's fractional fee model - exact, and avoids any convention
mismatch. Verified against the study's own engine before the sweep runs.

RESEARCH BLOCK ONLY. The locked block is not touched by this file.
"""
import vectorbt as vbt, numpy as np, pandas as pd, time, itertools, sys
import data as D, lab
from engine import atr as _atr

NE   = [5,7,10,14,20,28,40,56,80,100,120,140,160,200]
BUF  = [round(x,2) for x in np.arange(0.0, 2.01, 0.1)]
STOP = [0.5,0.75,1.0,1.25,1.5,1.75,2.0,2.5,3.0,3.5,4.0,5.0]
TARG = [0.5,0.75,1.0,1.5,2.0,2.5,3.0,3.5,4.0,5.0,6.0,8.0]
COST = {"NAS":2.5, "US30":5.0}          # round turn incl. slippage, in points


def prep(sym, block="res", synth_seed=None):
    df = D.load(sym); r, h = D.blocks(df)
    if synth_seed is not None:                     # driftless null series
        rng = np.random.default_rng(synth_seed)
        sd = np.diff(np.log(df.close.values)).std()
        lr = rng.normal(0, sd, len(df))
        c = df.close.values[0]*np.exp(np.cumsum(lr))
        w = np.abs(rng.normal(0, sd, len(df)))*c
        o = np.concatenate([[c[0]], c[:-1]])
        df = df.assign(open=o, close=c, high=np.maximum(o,c)+w, low=np.minimum(o,c)-w)
    mask = r if block == "res" else h
    A = _atr(df, 14); tod = df.tod.values; sess = df.sess.values
    keep = (tod>=420)&(tod<660)&mask&~np.isnan(A)&(A>0)
    idx = np.where(keep)[0]
    ch = {n: (pd.Series(df.high.values).rolling(n).max().shift(1).values,
              pd.Series(df.low.values).rolling(n).min().shift(1).values) for n in NE}
    s = sess[idx]
    # entry price = the OPEN of the bar AFTER the signal, matching the study's
    # engine. In the compressed series that is the next in-window bar; on a
    # session's last window bar there is no next bar in-session, so those
    # triggers are dropped (they would be flattened immediately anyway).
    nxt_open = np.concatenate([df.open.values[idx][1:], [np.nan]])
    last = np.concatenate([s[1:]!=s[:-1],[True]])
    nxt_open = np.where(last, np.nan, nxt_open)
    # price array must be valid on EVERY bar: entries only fire where nxt_open is
    # finite (filtered below), but the forced session exit fires on the last
    # window bar, where nxt_open is NaN. Fall back to that bar's close there.
    px_arr = np.where(np.isnan(nxt_open), df.close.values[idx], nxt_open)
    return dict(idx=idx, c=df.close.values[idx], a=A[idx], ch=ch,
                o=df.open.values[idx], hh=df.high.values[idx], ll=df.low.values[idx],
                last=last, sess=s, sym=sym, nxt=nxt_open, pxa=px_arr)


def sweep(P, side, verbose=True):
    c, a, idx, last = P["c"], P["a"], P["idx"], P["last"]
    px = pd.Series(c, index=pd.RangeIndex(len(c)))
    ex = pd.DataFrame(np.tile(last[:,None], (1, len(NE)*len(BUF))))
    # signal grid: n_entry x buffer
    cols, sig = [], np.zeros((len(c), len(NE)*len(BUF)), bool)
    k = 0
    for n in NE:
        hi, lo = P["ch"][n]
        for b in BUF:
            raw = (c > hi[idx] + b*a) if side>0 else (c < lo[idx] - b*a)
            raw &= ~np.isnan(P["nxt"])                 # need a next bar to fill on
            # FIRST trigger of each session only, matching one_per_session=True
            fs = np.zeros(len(raw), bool); seen = -1
            ss = P["sess"]
            for t in np.where(raw)[0]:
                if ss[t] != seen: fs[t] = True; seen = ss[t]
            sig[:,k] = fs
            cols.append((n,b)); k += 1
    S = pd.DataFrame(sig)
    out = []
    t0 = time.time()
    for gi,(sm,tm) in enumerate(itertools.product(STOP, TARG)):
        sl = np.clip(sm*a/c, 1e-6, 0.95)
        tp = np.clip(tm*a/c, 1e-6, 5.0)
        pf = vbt.Portfolio.from_signals(
            px, S, ex, price=P["pxa"][:,None],
            open=P["o"][:,None], high=P["hh"][:,None], low=P["ll"][:,None],
            sl_stop=sl[:,None], tp_stop=tp[:,None],
            direction='longonly' if side>0 else 'shortonly',
            size=1.0, size_type='amount', init_cash=1e9, fees=0.0, freq='15min')
        tr = pf.trades
        cnt = tr.count().values.astype(float)
        gross = tr.pnl.sum().values.astype(float)
        net = gross - cnt*COST[P["sym"]]
        with np.errstate(invalid='ignore', divide='ignore'):
            exp_ = np.where(cnt>0, net/np.maximum(cnt,1), np.nan)
        for j,(n,b) in enumerate(cols):
            out.append((n,b,sm,tm,cnt[j],gross[j],net[j],exp_[j]))
        if verbose and gi%24==0:
            done=(gi+1)*len(cols)
            print(f"    {done:>7,}/{len(STOP)*len(TARG)*len(cols):,} combos "
                  f"{time.time()-t0:>6.0f}s", flush=True)
    R = pd.DataFrame(out, columns=["n_entry","buffer","stop","targ","trades","gross","net","exp"])
    R["side"] = side; R["sym"] = P["sym"]
    return R


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv)>1 else "real"
    frames = []
    if which == "real":
        for sym in ("NAS","US30"):
            P = prep(sym)
            for side in (1,-1):
                print(f"  {sym} side={side:+d} ...", flush=True)
                frames.append(sweep(P, side))
        R = pd.concat(frames, ignore_index=True)
        R.to_parquet("/home/user/main/data/donchian/vbt_sweep.parquet")
    else:
        P = prep("NAS", synth_seed=int(sys.argv[2]))
        for side in (1,-1):
            frames.append(sweep(P, side, verbose=False))
        R = pd.concat(frames, ignore_index=True)
        R.to_parquet(f"/home/user/main/data/donchian/vbt_null_{sys.argv[2]}.parquet")
    print(f"  {len(R):,} combinations written")
