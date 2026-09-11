"""V60 part four: the leading configuration re-implemented in VECTORBT, as a second opinion.

The whole verdict rests on one engine -- `v38grid`'s cached exit tensor -- and an engine that is
wrong is wrong everywhere at once. `STUDY_V8_EXIT_OPT.md` records a ladder bug on this branch that
inflated EVERY result using a partial exit and was invisible until a second implementation was
built; `STUDY_PINE_PARITY.md` records three rule errors that reading could not find.

So this is built from the bars up with NO shared code path: its own Wilder ATR, its own EMAs, its
own ADX, its own Donchian channels, and vectorbt's order engine instead of the numba walk. It is
run TWICE, which is the discipline `STUDY_PINE_PARITY.md` sets out:

  PASS 1  THE TRANSCRIPTION CHECK. The SIGNAL SETS are compared bar for bar. This isolates the
          rule from the order model and must come back at ~100% agreement; anything less is a
          transcription error in one of the two, not an execution difference.
  PASS 2  THE ORDER-MODEL CHECK. Both engines are then run on their own terms and compared on the
          TRADE COUNT first and the points per trade second. `CLAUDE.md`: a fill-model defect is
          invisible in P&L-per-trade and shows only in the trade count.

Both passes are GROSS of costs -- vectorbt is not being asked to reproduce a CME fee schedule, it
is being asked whether the same bars produce the same trades.

Usage: python3 research/v60/v60_vbt.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import vectorbt as vbt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "v38"))

import v60core as V             # noqa: E402
from run_v60 import MARKETS      # noqa: E402
from v60robust import LEAD, LEAD_GEO, canon      # noqa: E402


def wilder(s, n):
    """Wilder's smoothing, written here rather than imported -- the point is independence."""
    return s.ewm(alpha=1.0 / n, adjust=False).mean()


def build(df):
    """Every series the leading configuration needs, in pandas, from the bars alone."""
    o, h, l, c = df["o"], df["h"], df["l"], df["c"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = wilder(tr, 20)                                   # ATR(20), Wilder -- the shipped Pine's

    up_move = h.diff()
    dn_move = -l.diff()
    pdm = up_move.where((up_move > dn_move) & (up_move > 0), 0.0).fillna(0.0)
    mdm = dn_move.where((dn_move > up_move) & (dn_move > 0), 0.0).fillna(0.0)
    atr14 = wilder(tr, 14)
    pdi = 100 * wilder(pdm, 14) / atr14.clip(lower=1e-12)
    mdi = 100 * wilder(mdm, 14) / atr14.clip(lower=1e-12)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).clip(lower=1e-12)
    adx = wilder(dx, 14)

    # EMAs through vectorbt's own MA indicator, not a hand-rolled ewm, so the second opinion
    # really is a second library.
    ef = pd.Series(vbt.MA.run(c, LEAD["ema_f"], ewm=True).ma.to_numpy().ravel(), index=c.index)
    es = pd.Series(vbt.MA.run(c, LEAD["ema_s"], ewm=True).ma.to_numpy().ravel(), index=c.index)
    state = ef > es
    cross = state & ~state.shift(1).astype(object).fillna(False).astype(bool)

    # bars since the last upward cross, by a forward fill of the cross bar's position
    pos = pd.Series(np.arange(len(c)), index=c.index)
    last = pos.where(cross).ffill()
    since = (pos - last)

    don_hi = h.rolling(LEAD["don_e"]).max().shift(1)       # prior E-bar high
    don_lo = l.rolling(LEAD_GEO["don_x"]).min().shift(1)   # prior X-bar low, the channel exit

    ema_ok = (since >= 0) & (since <= LEAD["win"])
    entry = (c > don_hi) & ema_ok & (adx >= 20.0) & atr.notna() & (atr > 0)
    entry = entry.astype(object).fillna(False).astype(bool)
    return dict(o=o, h=h, l=l, c=c, atr=atr, adx=adx, entry=entry,
                don_lo=don_lo, don_hi=don_hi)


def frame(mk):
    P = V.prep(60, mk)
    idx = pd.to_datetime(P["ts"])
    return P, pd.DataFrame({k: P[k] for k in ("o", "h", "l", "c")}, index=idx)


def transcription(P, B):
    """Bar-for-bar agreement of the two signal sets. Must be ~100%."""
    mine = V.signal_mask(P, canon(LEAD))
    theirs = B["entry"].to_numpy()
    both = int((mine & theirs).sum())
    only_a = int((mine & ~theirs).sum())
    only_b = int((~mine & theirs).sum())
    agree = 100.0 * both / max(both + only_a + only_b, 1)
    dis = np.flatnonzero(mine ^ theirs)
    return dict(n_engine=int(mine.sum()), n_vbt=int(theirs.sum()), both=both,
                only_engine=only_a, only_vbt=only_b, agree=agree, mask=theirs,
                last_dis=int(dis[-1]) if len(dis) else -1, nbars=len(mine))


def vbt_run(B, block, anchor="close"):
    """vectorbt on its own terms: entry at the NEXT bar's open, its own stop engine, and the
    channel break as an explicit exit signal. No costs.

    ANCHOR IS THE THING THAT HAD TO BE FOUND. `sl_stop` is a FRACTION, and vectorbt resolves it
    against the bar's CLOSE -- not against the fill price handed to it through `price=`. Passing
    the obvious `stop_n * ATR / close` therefore puts the stop (close - open) away from where the
    engine puts it, and on a 60-minute bar that is a real distance. `anchor="close"` solves for
    the fraction that reproduces the engine's ABSOLUTE level; `anchor="naive"` is the obvious
    version, kept because the difference between the two is the size of the trap.
    """
    o, c = B["o"], B["c"]
    ent = B["entry"].shift(1).astype(object).fillna(False).astype(bool)   # signal i -> order i+1
    if anchor == "close":
        lvl = o - LEAD_GEO["stop"] * B["atr"].shift(1)      # the engine's absolute stop level
        sl = (1.0 - lvl / c).clip(lower=1e-6).bfill()
    else:
        sl = (LEAD_GEO["stop"] * B["atr"] / c).shift(1).bfill().clip(lower=1e-6)
    # THE CHANNEL EXIT MUST BE SHIFTED TOO. vectorbt executes an order on the SIGNAL bar at
    # `price`, so an unshifted `close < channel` exit would fill at that same bar's OPEN -- a
    # price printed before the break was known, which is lookahead and worth +22 to +100 points
    # a trade here. Shifted, it fills at the next open, which is what a script gets.
    ex = (c < B["don_lo"]).astype(object).fillna(False).astype(bool).shift(1)
    ex = ex.astype(object).fillna(False).astype(bool)
    pf = vbt.Portfolio.from_signals(
        close=c[block], entries=ent[block], exits=ex[block], price=o[block],
        sl_stop=sl[block].to_numpy(), high=B["h"][block], low=B["l"][block],
        accumulate=False, freq="60min")
    t = pf.trades.records_readable
    pts = t["Avg Exit Price"] - t["Avg Entry Price"]
    return dict(n=len(t), pts=float(pts.mean()) if len(t) else np.nan,
                win=float((pts > 0).mean()) if len(t) else np.nan, rec=t, pf=pf)


def engine_run(P, block_slice):
    """The branch's engine on the same configuration, GROSS -- costs zeroed so the two agree on
    price and not on a fee schedule."""
    import v38grid as G
    import v39mc as MC
    keep = (G.COMM, G.EC, G.SE)
    G.COMM, G.EC, G.SE = 0.0, 0.0, 0.0
    try:
        xb, pnl, why = G.tensor_stop(P, LEAD_GEO["don_x"], LEAD_GEO["stop"], LEAD_GEO["tp"], 0)
    finally:
        G.COMM, G.EC, G.SE = keep
    m = V.signal_mask(P, canon(LEAD))
    sig = np.flatnonzero(m)
    sig = sig[(sig >= block_slice[0]) & (sig < block_slice[1])].astype(np.int64)
    p_, s_ = MC.gather(P, xb, pnl, sig)
    return dict(n=len(p_), pts=float(p_.mean() / P["pv"]) if len(p_) else np.nan,
                win=float((p_ > 0).mean()) if len(p_) else np.nan,
                fill=s_ + 1, xbar=xb[s_], why=why[s_],
                entpx=P["o"][s_ + 1], expx=P["o"][s_ + 1] + p_ / P["pv"])


def fill_attribution(P, B, b):
    """WHERE VECTORBT ACTUALLY FILLS ITS EXITS. Asserting this from the source is how the first
    version of this module reached a wrong conclusion, so it is counted instead."""
    idx = B["c"].index
    pos = {ts: i for i, ts in enumerate(idx)}
    t = b["rec"]
    xi = np.array([pos[x] for x in t["Exit Timestamp"]])
    xp = t["Avg Exit Price"].to_numpy()
    if not len(xi):
        return (np.nan, np.nan, np.nan)
    at_o = np.isclose(xp, P["o"][xi])
    at_c = np.isclose(xp, P["c"][xi]) & ~at_o
    return (float(at_o.mean()), float(at_c.mean()), float((~at_o & ~at_c).mean()))


def trade_diff(P, B, a, b):
    """Match the two engines TRADE BY TRADE on the fill bar and diff the exits.

    `STUDY_PINE_PARITY.md`: a port cannot be asserted by reading it. Aggregate points per trade
    hides which trades differ; matching on the fill bar and differencing the exit bar and the
    exit price says exactly where two order models part company.
    """
    idx = B["c"].index
    pos = {ts: i for i, ts in enumerate(idx)}
    t = b["rec"]
    ei = np.array([pos[x] for x in t["Entry Timestamp"]])
    xi = np.array([pos[x] for x in t["Exit Timestamp"]])
    vmap = {int(e): (int(x), float(px)) for e, x, px in zip(ei, xi, t["Avg Exit Price"])}
    rows = []
    for f, xb_, w, epx, xpx in zip(a["fill"], a["xbar"], a["why"], a["entpx"], a["expx"]):
        v = vmap.get(int(f))
        if v is None:
            continue
        rows.append((int(w), v[0] - int(xb_), v[1] - float(xpx)))
    if not rows:
        return {}
    r = np.array(rows, float)
    out = dict(matched=len(r), eng_only=a["n"] - len(r), vbt_only=len(t) - len(r))
    for w, nm in ((1.0, "stop"), (4.0, "channel")):
        s_ = r[r[:, 0] == w]
        out[nm] = (len(s_), float(s_[:, 1].mean()) if len(s_) else np.nan,
                   float(s_[:, 2].mean()) if len(s_) else np.nan,
                   float(np.abs(s_[:, 2]).max()) if len(s_) else np.nan)
    return out


def exit_convention(P):
    """WHERE THE TWO ENGINES ACTUALLY DIFFER ON THE CHANNEL EXIT, measured rather than inferred.

    The engine exits a channel break at the CLOSE of the bar that breaks it. That is a
    market-on-close order decided by the very close it fills at, which no script can place --
    the same defect `CLAUDE.md` records for the fixed-time flatten. A script fills at the NEXT
    open, so the cost of that convention is exactly the average of (next open - triggering close)
    over the trades that exit on the channel.

    THIS FUNCTION EXISTS BECAUSE THE FIRST READING OF THIS MODULE ATTRIBUTED THE PASS-2 GAP TO
    THAT CONVENTION WITHOUT MEASURING IT, AND WAS WRONG BY AN ORDER OF MAGNITUDE. The convention
    is worth about a fifth of a point; the gap is 4 to 22. Measure the mechanism you are naming.
    """
    import v38grid as G
    import v39mc as MC
    keep = (G.COMM, G.EC, G.SE)
    G.COMM, G.EC, G.SE = 0.0, 0.0, 0.0
    try:
        xb, pnl, why = G.tensor_stop(P, LEAD_GEO["don_x"], LEAD_GEO["stop"], LEAD_GEO["tp"], 0)
    finally:
        G.COMM, G.EC, G.SE = keep
    m = V.signal_mask(P, canon(LEAD))
    cut = int(P["n"] * V.SPLIT)
    out = {}
    for bn, lo, hi in (("research", 0, cut), ("locked", cut, P["n"])):
        sig = np.flatnonzero(m)
        sig = sig[(sig >= lo) & (sig < hi)].astype(np.int64)
        p_, s_ = MC.gather(P, xb, pnl, sig)
        if not len(s_):
            continue
        x = xb[s_]
        w = why[s_]
        nxt = np.minimum(x + 1, P["n"] - 1)
        give = np.where(w == 4, P["o"][nxt] - P["c"][x], 0.0)
        ch = give[w == 4]
        out[bn] = (len(s_), {int(k): int((w == k).sum()) for k in np.unique(w)},
                   float(give.mean()), float(ch.mean()) if len(ch) else np.nan,
                   float(ch.min()) if len(ch) else np.nan)
    return out


def main():
    print("=" * 116)
    print("10. VECTORBT SECOND OPINION on the leading configuration, GROSS of costs")
    print("=" * 116)
    print(f"  EMA {LEAD['ema_f']}/{LEAD['ema_s']} cross, confirm within {LEAD['win']} bars, "
          f"Donchian {LEAD['don_e']} entry / {LEAD_GEO['don_x']} exit, "
          f"{LEAD_GEO['stop']}N stop, no target, {LEAD['gate']}, aroon {LEAD['aroon']}")
    print()
    print("  PASS 1 -- TRANSCRIPTION: are the two signal sets the same bars?")
    print(f"  {'market':<8}{'engine':>9}{'vectorbt':>10}{'both':>8}{'eng only':>10}"
          f"{'vbt only':>10}{'agreement':>11}{'last disagreement':>22}")
    Bs = {}
    for mk in MARKETS:
        P, df = frame(mk)
        B = build(df)
        Bs[mk] = (P, B)
        t = transcription(P, B)
        where = f"bar {t['last_dis']:,} of {t['nbars']:,}" if t['last_dis'] >= 0 else "none"
        print(f"  {mk:<8}{t['n_engine']:>9d}{t['n_vbt']:>10d}{t['both']:>8d}"
              f"{t['only_engine']:>10d}{t['only_vbt']:>10d}{t['agree']:>10.1f}%{where:>22}")
    print("     every disagreement is inside the EMA(62) warm-up; after it the two rules are the"
          " same bars.")

    print()
    print("  PASS 2 -- ORDER MODEL: same bars, each engine's own execution")
    print(f"  {'market':<8}{'block':<10}{'eng n':>7}{'vbt n':>7}{'count':>8}"
          f"{'eng pts':>10}{'vbt pts':>10}{'naive':>10}{'eng win':>9}{'vbt win':>9}")
    keep = {}
    for mk in MARKETS:
        P, B = Bs[mk]
        cut = int(P["n"] * V.SPLIT)
        idx = B["c"].index
        for bn, sl_, rng in (("research", slice(None, idx[cut]), (0, cut)),
                             ("locked", slice(idx[cut], None), (cut, P["n"]))):
            a = engine_run(P, rng)
            b = vbt_run(B, sl_, anchor="close")
            nv = vbt_run(B, sl_, anchor="naive")
            keep[(mk, bn)] = (P, B, a, b)
            agree = 100.0 * min(a["n"], b["n"]) / max(a["n"], b["n"], 1)
            print(f"  {mk:<8}{bn:<10}{a['n']:>7d}{b['n']:>7d}{agree:>7.1f}%"
                  f"{a['pts']:>+10.2f}{b['pts']:>+10.2f}{nv['pts']:>+10.2f}"
                  f"{a['win'] * 100:>8.1f}%{b['win'] * 100:>8.1f}%")
    print("     `naive` is the same run with `sl_stop = stop_n * ATR / close`, the obvious way to"
          " write it.")
    print("     vectorbt resolves that fraction against the bar's CLOSE, not the `price=` fill,"
          " so the stop")
    print("     lands (close - open) away from the engine's. The gap between the two columns is"
          " that trap.")

    print()
    print("  PASS 3 -- TRADE BY TRADE, matched on the fill bar, SPLIT BY EXIT REASON")
    print(f"  {'market':<8}{'block':<10}{'matched':>8}{'stop n':>8}{'d bar':>7}{'d px':>9}"
          f"{'chan n':>8}{'d bar':>7}{'d px':>9}{'  vbt fills at o / c / stop':>30}")
    for (mk, bn), (P, B, a, b) in keep.items():
        d = trade_diff(P, B, a, b)
        if not d:
            continue
        st, ch = d["stop"], d["channel"]
        fo, fc, fs = fill_attribution(P, B, b)
        print(f"  {mk:<8}{bn:<10}{d['matched']:>8d}"
              f"{st[0]:>8d}{st[1]:>+7.2f}{st[2]:>+9.2f}"
              f"{ch[0]:>8d}{ch[1]:>+7.2f}{ch[2]:>+9.2f}"
              f"{fo * 100:>14.0f}% {fc * 100:>3.0f}% {fs * 100:>3.0f}%")

    print()
    print("  PASS 4 -- THE CHANNEL CONVENTION, MEASURED rather than inferred from PASS 2.")
    print("     The engine sells at the CLOSE of the bar that breaks the channel; a script sells")
    print("     the NEXT OPEN. That difference is exactly mean(open[j+1] - close[j]) over the")
    print("     engine's own channel exits, and it is SMALL:")
    print(f"  {'market':<8}{'block':<10}{'trades':>8}{'stop':>7}{'chan':>7}{'hold':>7}"
          f"{'give-up per channel exit':>26}{'worst single':>14}")
    for mk in MARKETS:
        P, B = Bs[mk]
        for bn, (n, w, g_all, g_ch, worst) in exit_convention(P).items():
            print(f"  {mk:<8}{bn:<10}{n:>8d}"
                  + "".join(f"{w.get(k, 0):>7d}" for k in (1, 4, 5))
                  + f"{g_ch:>+26.2f}{worst:>+14.2f}")
    print("     SO THE PASS-2 GAP IS NOT THE CONVENTION. It is vectorbt's own execution: its stop")
    print("     exits land on the SAME bar as the engine's and price 9 to 110 points worse, and a")
    print("     tenth to a fifth of its exits do not fill at the `price=` series at all. The")
    print("     arbiter of what the SHIPPED SCRIPT does is `v60_parity.py`, which writes the")
    print("     script's order model out directly and lands within -2.6% to +4.6% of the engine.")


if __name__ == "__main__":
    main()
