"""The SHIPPED Pine's own order model, written out in Python and run on real bars.

`STUDY_FTM_ORB_BACKTEST` recorded the reason this file has to exist: a port that compiles and does
nothing looks exactly like a port that compiles and works. PIN_POSTERIOR shipped with a
comma-separated declaration Pine rejects, so it produced no trades at all, and the linter passed it
because the CLI silently ignored the file argument. Both are fixed; this is the check that the
FIXED script actually trades, and that it trades the same thing the research measured.

Two deliberate differences from `run_g4.py`, both stated in the script itself:
  * the volume normaliser is an EXPANDING mean of in-window sub-bar volume rather than the
    research's full-sample constant, because a script cannot read the whole sample;
  * `strategy.exit(loss=)` is a fill-relative bracket in TICKS, so the stop is rounded to the
    instrument's tick where the research holds it in points.
Neither can be removed, so the harness reports the gap rather than asserting equality.
"""
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/pin")
import scalp5.s5data as S                                       # noqa: E402
import pin_core as P                                            # noqa: E402

TF = 10
MINTICK = 0.25


def build(use_vol=True, win=120, k=1.0, vwarm=500):
    D = P.load(tf=TF)
    b1 = D["base"]
    c, o = b1["close"].to_numpy(), b1["open"].to_numpy()
    v = b1["volume"].to_numpy().astype(float)
    mod1 = (b1.index.hour * 60 + b1.index.minute).to_numpy()
    day1 = b1.index.normalize().values.astype("datetime64[D]").astype(np.int64)
    on1 = (mod1 >= D["win_open"]) & (mod1 < D["win_close"])

    # --- the script's causal normaliser: the mean of the in-window volume seen BEFORE this bar
    csum = np.cumsum(np.where(on1, v, 0.0))
    cnt = np.cumsum(on1.astype(float))
    prev_sum = np.concatenate([[0.0], csum[:-1]])
    prev_n = np.concatenate([[0.0], cnt[:-1]])
    with np.errstate(invalid="ignore", divide="ignore"):
        vbar = np.where(prev_n >= vwarm, prev_sum / np.maximum(prev_n, 1.0), np.nan)
    w = (v / vbar) if use_vol else np.ones_like(v)

    f = pd.DataFrame({"b": np.where(on1 & (c > o), w, 0.0),
                      "s": np.where(on1 & (c < o), w, 0.0),
                      "d": day1, "c": c, "o": o}, index=b1.index)
    ok = on1 & np.isfinite(f.b.to_numpy()) & np.isfinite(f.s.to_numpy())
    f.loc[~ok, ["b", "s"]] = 0.0

    agg = f[ok].groupby("d").agg(B=("b", "sum"), S=("s", "sum"),
                                 first=("o", "first"), last=("c", "last")).sort_index()
    agg["ret"] = (agg["last"] / agg["first"] - 1.0) * 100.0
    F = agg.reset_index().rename(columns={"d": "day"})
    params = {int(F.day.iloc[i]): P.fit_causal(F, i, window=win, k=k) for i in range(len(F))}

    cb = f.groupby("d").b.cumsum().to_numpy()
    cs = f.groupby("d").s.cumsum().to_numpy()
    cb[~on1] = np.nan
    cs[~on1] = np.nan
    Bt = pd.Series(cb, index=b1.index).reindex(D["ix"], method="ffill").to_numpy()
    St = pd.Series(cs, index=b1.index).reindex(D["ix"], method="ffill").to_numpy()

    wl = D["win_close"] - D["win_open"]
    pg = np.full(D["n"], np.nan)
    pb = np.full(D["n"], np.nan)
    for i in np.flatnonzero(D["inw"]):
        p = params.get(int(D["day"][i]))
        if p is None or not np.isfinite(Bt[i]):
            continue
        fr = min(max((D["mod"][i] + TF - D["win_open"]) / wl, 1e-3), 1.0)
        g, bb, _ = P.posterior(Bt[i], St[i], p, fr)
        pg[i] = g
        pb[i] = bb
    return D, pg, pb, params


def script_walk(D, pg, pb, thresh=0.70, stop_n=2.5, arm=1.0, tr=1.0, tgt_r=0.0,
                do_long=True, do_short=True):
    """The Pine, statement for statement.

    Entry at the NEXT bar's open; the bracket is fill-relative and in ticks, placed WITH the entry
    so the fill bar is protected; the trail acts on the CLOSE and cannot act on the fill bar; the
    flatten fills at the next open. The stop is taken before the target inside one bar.
    """
    o, h, l, c = D["o"], D["h"], D["l"], D["c"]
    atr, inw, lastw = D["atr"], D["inw"], D["last_win"]
    n = D["n"]
    rt, slip = S.RT_POINTS, S.SLIP_POINTS
    lg = np.nan_to_num(pg, nan=0.0) >= thresh
    sh = np.nan_to_num(pb, nan=0.0) >= thresh

    rows = []
    i, lock = 0, -1
    while i < n - 1:
        can = (i > lock) and inw[i] and not lastw[i] and np.isfinite(atr[i]) and atr[i] > 0
        go_l = can and do_long and lg[i]
        go_s = can and do_short and sh[i] and not go_l
        if not (go_l or go_s):
            i += 1
            continue
        side = 1 if go_l else -1
        j = i + 1
        ent = o[j] + side * slip
        risk_pts = stop_n * atr[i]
        ticks = max(1, int(round(risk_pts / MINTICK)))         # the script rounds to ticks
        risk = ticks * MINTICK
        stop = ent - side * risk
        tgt = ent + side * tgt_r * risk if tgt_r > 0 else np.nan
        peak = np.nan
        e, px, why = j, np.nan, ""
        while e < n:
            hs = (l[e] <= stop) if side > 0 else (h[e] >= stop)
            ht = False if not np.isfinite(tgt) else ((h[e] >= tgt) if side > 0 else (l[e] <= tgt))
            if hs:
                px, why = stop - side * slip, "stop"
                break
            if ht:
                px, why = tgt - side * slip, "target"
                break
            if e > j and arm > 0:                              # never on the fill bar
                adv = side * (c[e] - ent) / risk
                peak = adv if not np.isfinite(peak) else max(peak, adv)
                if peak >= arm:
                    lvl = ent + side * (peak - tr) * risk
                    if (side > 0 and c[e] < lvl) or (side < 0 and c[e] > lvl):
                        if e + 1 >= n:
                            break
                        px, why = o[e + 1] - side * slip, "trail"
                        break
            if lastw[e]:
                if e + 1 >= n:
                    break
                px, why = o[e + 1] - side * slip, "flat"
                break
            e += 1
        if not why:
            break
        rows.append(dict(sig=i, ex=e, side=side, pts=side * (px - ent) - rt, why=why,
                         blk=D["blk"][i], day=D["day"][i]))
        lock, i = e, e + 1
    return pd.DataFrame(rows)


if __name__ == "__main__":
    pd.set_option("display.width", 190)
    print("=" * 100)
    print("PIN PARITY -- the shipped script's order model, run on bars")
    print("=" * 100)
    D, pg, pb, params = build(use_vol=True)
    fit = sum(v is not None for v in params.values())
    print(f"  bars {D['n']:,}   sessions {len(params)}   sessions with a usable fit {fit}")
    print(f"  posterior finite on {np.isfinite(pg).sum():,} bars   "
          f"max P(good) {np.nanmax(pg):.3f}   max P(bad) {np.nanmax(pb):.3f}")

    print(f"\n{'thresh':>7} {'block':>9} {'n':>5} {'pts/trade':>10} {'PF':>7} {'win%':>7} "
          f"{'stop':>5} {'trail':>6} {'flat':>5}")
    for th in (0.50, 0.70, 0.85, 0.95):
        t = script_walk(D, pg, pb, thresh=th)
        if not len(t):
            print(f"{th:>7} {'-- NO TRADES --':>40}")
            continue
        for blk, name in ((0, "research"), (1, "LOCKED")):
            s = t[t.blk == blk]
            if len(s) < 10:
                continue
            r = s.pts.to_numpy()
            pf = r[r > 0].sum() / max(-r[r < 0].sum(), 1e-9)
            wy = s.why.value_counts()
            print(f"{th:>7} {name:>9} {len(s):>5} {r.mean():>10.2f} {pf:>7.3f} "
                  f"{(r > 0).mean() * 100:>6.1f}% {wy.get('stop', 0):>5} "
                  f"{wy.get('trail', 0):>6} {wy.get('flat', 0):>5}")
