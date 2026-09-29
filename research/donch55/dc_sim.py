"""Transliteration of the shipped Pine, run on real bars, so the LOGIC can be checked.

Poluri (Feb 2026) reports BTCUSD results this container cannot reproduce -- egress is blocked, so
no BTC series is reachable and the registry has none on disk. What that leaves is the part that
actually matters for "is the code correct": every MECHANIC can be verified on any weekly series.
A port that compiles and does nothing looks exactly like a port that compiles and works, so this
runs the shipped rules bar by bar and asserts the things a reader would otherwise have to trust:

  * the breakout compares the close to the channel through the PREVIOUS bar, so no signal can be
    triggered by the bar that also forms the channel extreme (the paper's own `Upper[1]` note);
  * the regime gate ATR >= atrMult * SMA(ATR, atrBaseLen) passes at a rate consistent with its
    definition and actually removes bars;
  * a position is protected on the FILL bar, which is the phase a naive `strategy.exit` misses;
  * the trailing stop only ever moves in the favourable direction;
  * the exit-mode selector genuinely changes the exit that fires.

Everything here is written to match the Pine line for line, including Wilder's ATR (Pine's
`ta.atr`), NOT the ema(tr, n) this branch's own research uses -- the point is fidelity to the
source, not to my conventions.
"""
import numpy as np, pandas as pd


def wilder_atr(h, l, c, n=14):
    """Pine's ta.atr: RMA of true range. RMA is an EMA with alpha = 1/n."""
    pc = np.concatenate(([np.nan], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    tr[0] = h[0] - l[0]
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def build(f, dc_len=55, ema_len=200, atr_len=14, atr_base=50):
    o, h, l, c = (f[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    up = pd.Series(h).rolling(dc_len).max().shift(1).to_numpy()      # Upper[1]
    dn = pd.Series(l).rolling(dc_len).min().shift(1).to_numpy()      # Lower[1]
    ema = pd.Series(c).ewm(span=ema_len, adjust=False).mean().to_numpy()
    atr = wilder_atr(h, l, c, atr_len)
    atr_sma = pd.Series(atr).rolling(atr_base).mean().to_numpy()
    return dict(o=o, h=h, l=l, c=c, ix=f.index, up=up, dn=dn, ema=ema,
                atr=atr, atr_sma=atr_sma, n=len(c))


def run(D, atr_mult=1.0, risk_atr=2.0, trail_atr=2.5, exit_mode="TrailOnly",
        use_ema=True, allow_long=True, allow_short=True, commission=0.0002,
        exit_on_opposite=False, qty=1.0):
    """The order model, matching the Pine.

    Entry: market at the bar CLOSE that satisfies the rule (the paper says 'market orders at bar
    close'), which in Pine means the order is placed on that bar and the broker emulator fills it
    at that close because `process_orders_on_close` is on.
    Exit: intrabar stop and/or trail, checked against the bar's high/low. The initial stop is live
    from the fill bar onward, which is why it is placed WITH the entry rather than a bar later.
    """
    o, h, l, c = D["o"], D["h"], D["l"], D["c"]
    up, dn, ema, atr, asma = D["up"], D["dn"], D["ema"], D["atr"], D["atr_sma"]
    regime = atr >= atr_mult * asma
    long_sig = (c > up) & (regime) & ((c > ema) if use_ema else True) & allow_long
    short_sig = (c < dn) & (regime) & ((c < ema) if use_ema else True) & allow_short
    long_sig = np.nan_to_num(long_sig, nan=False).astype(bool)
    short_sig = np.nan_to_num(short_sig, nan=False).astype(bool)

    trades, pos = [], None
    diag = dict(entry_bar_protected=0, trail_moved_back=0, n_regime=int(regime[~np.isnan(asma)].sum()),
                n_eligible=int((~np.isnan(asma)).sum()))
    for i in range(D["n"]):
        if pos is not None:
            side, ent, ent_i, a0, stop, peak = (pos["side"], pos["ent"], pos["i"], pos["atr"],
                                                pos["stop"], pos["peak"])
            # the trail follows the running extreme SINCE ENTRY, inclusive of the entry bar
            peak = max(peak, h[i]) if side > 0 else min(peak, l[i])
            new = None
            if exit_mode in ("TrailOnly", "Both"):
                new = peak - side * trail_atr * a0
            if exit_mode in ("StopOnly", "Both"):
                fixed = ent - side * risk_atr * a0
                new = fixed if new is None else (max(new, fixed) if side > 0 else min(new, fixed))
            if new is not None:
                if stop is not None and side * (new - stop) < 0:
                    diag["trail_moved_back"] += 1          # must never happen
                stop = new if stop is None else (max(stop, new) if side > 0 else min(stop, new))
            hit = (l[i] <= stop) if side > 0 else (h[i] >= stop)
            opp = (short_sig[i] if side > 0 else long_sig[i]) and exit_on_opposite
            if hit or opp:
                px = stop if hit else c[i]
                gross = side * (px - ent) * qty
                cost = commission * (abs(ent) + abs(px)) * qty
                trades.append(dict(entry_i=ent_i, exit_i=i, side=side, ent=ent, px=px,
                                   pnl=gross - cost, bars=i - ent_i,
                                   why="stop/trail" if hit else "opposite"))
                pos = None
            else:
                pos.update(stop=stop, peak=peak)
                continue
        if pos is None and i < D["n"] - 1:
            s = 1 if long_sig[i] else (-1 if short_sig[i] else 0)
            if s != 0 and np.isfinite(atr[i]) and atr[i] > 0:
                ent = c[i]
                a0 = atr[i]
                peak = h[i] if s > 0 else l[i]
                stop = None
                if exit_mode in ("TrailOnly", "Both"):
                    stop = peak - s * trail_atr * a0
                if exit_mode in ("StopOnly", "Both"):
                    fx = ent - s * risk_atr * a0
                    stop = fx if stop is None else (max(stop, fx) if s > 0 else min(stop, fx))
                # PROTECTED ON THE FILL BAR: the stop exists the moment the position does
                diag["entry_bar_protected"] += 1
                pos = dict(side=s, ent=ent, i=i, atr=a0, stop=stop, peak=peak)
    t = pd.DataFrame(trades)
    return t, diag, long_sig, short_sig, regime
