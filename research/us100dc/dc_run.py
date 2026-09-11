"""US100 M15 dual-Donchian, long only -- the given specification, run.

SPEC AS SUPPLIED
  Symbol US100 | M15 | entry Donchian 160 | exit Donchian 60 | ATR 80 | ATR mult 1.5
  trailing ATR mult 2.0 | long only | spread-to-ATR filter 0.20 | deposit $1,000 | leverage 1:100

TWO THINGS THE SPEC LEAVES OPEN, DECIDED ONCE AND STATED
  1. THE SPREAD-TO-ATR FILTER NEEDS A SPREAD, AND NO FEED HERE HAS ONE. Bid/ask is unavailable in
     every feed on this branch, so `spread / ATR <= 0.20` cannot be evaluated as written. With a
     FIXED assumed spread it is exactly an ATR FLOOR: spread/ATR <= 0.20 is ATR >= 5 x spread.
     That is what is implemented, and the assumed spread is swept so the reader can see how much
     the assumption is doing.
  2. THE CHANNELS ARE READ AT THE PRIOR BAR. `highest(high, 160)[1]`, not `[0]` -- otherwise the
     breakout bar's own high forms the level it must exceed and the rule can never fire.

COSTS. US100's all-in round turn on this branch is 1.215 points; slippage is charged per side on
top. The deposit and leverage are carried through to a separate account simulation rather than
mixed into the per-trade statistics, because $1,000 at 1:100 constrains SIZE, not edge.
"""
import numpy as np, pandas as pd
from numba import njit

RT_POINTS = 1.215
SLIP = 0.25
SPLIT = 0.65


def load_us100(path="data/US100_LONG_15m.csv", shift_h=7):
    d = pd.read_csv(path, sep="\t")
    d.columns = [c.strip().lower() for c in d.columns]
    ix = pd.to_datetime(d["datetime"], format="%Y.%m.%d %H:%M:%S") - pd.Timedelta(hours=shift_h)
    f = pd.DataFrame({k: pd.to_numeric(d[k], errors="coerce").to_numpy(float)
                      for k in ("open", "high", "low", "close")}, index=ix)
    f["volume"] = pd.to_numeric(d["tickvolume"], errors="coerce").to_numpy(float)
    f = f[~f.index.duplicated(keep="first")].sort_index()
    return f.dropna(subset=["open", "high", "low", "close"])


def build(f, entry_n=160, exit_n=60, atr_n=80, split=SPLIT):
    o, h, l, c = (f[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    pc = np.concatenate(([np.nan], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    tr[0] = h[0] - l[0]
    atr = pd.Series(tr).ewm(alpha=1 / atr_n, adjust=False).mean().to_numpy()   # Wilder, as ta.atr
    up = pd.Series(h).rolling(entry_n).max().shift(1).to_numpy()
    dn = pd.Series(l).rolling(exit_n).min().shift(1).to_numpy()
    day = f.index.normalize().values.astype("datetime64[D]").astype(np.int64)
    D = dict(o=o, h=h, l=l, c=c, ix=f.index, atr=atr, up=up, dn=dn, day=day, n=len(c))
    ud = np.unique(day)
    D["cut_day"] = int(ud[int(split * len(ud))])
    D["blk"] = (day >= D["cut_day"]).astype(np.int64)
    D["cut_date"] = str(pd.Timestamp(D["cut_day"], unit="D").date())
    D["days"] = ud
    return D


@njit(cache=True)
def walk(o, h, l, c, atr, up, dn, gate, stop_n, trail_n, rt, slip,
         out_i, out_x, out_pts, out_R, out_why, out_mae):
    n = len(c)
    k = 0
    i = 0
    while i < n - 1:
        if gate[i] and np.isfinite(up[i]) and c[i] > up[i] and atr[i] > 0 and np.isfinite(atr[i]):
            a0 = atr[i]
            j = i + 1
            ent = o[j] + slip                       # market at the next open
            risk = stop_n * a0
            stop = ent - risk
            peak = h[j]
            mae = 0.0
            e = j
            why = 0
            px = np.nan
            while e < n:
                if peak < h[e]:
                    peak = h[e]
                tl = peak - trail_n * a0
                if tl > stop:
                    stop = tl
                if l[e] <= stop:
                    px = stop - slip
                    why = 1
                    break
                if (ent - l[e]) > mae:
                    mae = ent - l[e]
                if np.isfinite(dn[e]) and c[e] < dn[e] and e > j:
                    if e + 1 >= n:
                        break
                    px = o[e + 1] - slip            # channel exit fills at the next open
                    why = 2
                    e = e + 1
                    break
                e += 1
            if why == 0:
                break
            out_i[k] = i
            out_x[k] = e
            out_pts[k] = px - ent - rt
            out_R[k] = (px - ent - rt) / risk
            out_why[k] = why
            out_mae[k] = mae / a0
            k += 1
            i = e + 1
        else:
            i += 1
    return k


def run(D, stop_n=1.5, trail_n=2.0, spread_atr=0.20, assumed_spread=1.0,
        rt=RT_POINTS, slip=SLIP, gate_on=True):
    """`spread_atr` is the spec's filter; with a fixed spread it is an ATR FLOOR of spread/0.20."""
    floor = assumed_spread / spread_atr if (gate_on and spread_atr > 0) else 0.0
    gate = (D["atr"] >= floor) if gate_on else np.ones(D["n"], np.bool_)
    gate = np.asarray(np.nan_to_num(gate, nan=False), dtype=np.bool_)
    cap = int(gate.sum()) + 8
    oi = np.zeros(cap, np.int64); ox = np.zeros(cap, np.int64)
    op = np.full(cap, np.nan); oR = np.full(cap, np.nan)
    ow = np.zeros(cap, np.int64); om = np.full(cap, np.nan)
    k = walk(D["o"], D["h"], D["l"], D["c"], D["atr"], D["up"], D["dn"], gate,
             float(stop_n), float(trail_n), float(rt), float(slip),
             oi, ox, op, oR, ow, om)
    t = pd.DataFrame(dict(sig=oi[:k], exit=ox[:k], pts=op[:k], R=oR[:k], why=ow[:k], mae=om[:k]))
    t["blk"] = D["blk"][t.sig.to_numpy()]
    t["day"] = D["day"][t.sig.to_numpy()]
    t["atr0"] = D["atr"][t.sig.to_numpy()]
    t["ts"] = D["ix"][t.sig.to_numpy()]
    t["bars"] = t.exit - t.sig
    return t, float(floor), float(gate.mean())


def stats(t, days_in_block):
    if len(t) == 0:
        return {}
    p = t.pts.to_numpy()
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(eq) - eq))
    ser = pd.Series(p).groupby(pd.Series(t.day.to_numpy())).sum()
    full = pd.Series(0.0, index=pd.Index(days_in_block))
    full.loc[ser.index] = ser.to_numpy()
    sd = full.std(ddof=1)
    return dict(n=len(t), pts=float(p.mean()), R=float(t.R.mean()),
                pf=float(p[p > 0].sum() / max(-p[p < 0].sum(), 1e-9)),
                win=float((p > 0).mean()), total=float(p.sum()), dd=dd,
                ret_dd=float(p.sum() / max(dd, 1e-9)),
                sharpe=float(full.mean() / sd * np.sqrt(252)) if sd > 0 else np.nan,
                hold_h=float(t.bars.mean() * 0.25),
                p_stop=float((t.why == 1).mean()), p_chan=float((t.why == 2).mean()))
