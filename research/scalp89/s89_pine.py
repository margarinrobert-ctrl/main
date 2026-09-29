"""The submitted script's order model as TradingView's broker emulator runs it at BAR CLOSE with no
execution option ticked -- written out, because the first transliteration (`s89_core.walk`) got
the FILL BAR wrong.

What the original script actually places (read from its source, `orig_scalp.pine` lines 195-231):
  * `strategy.exit("XL", "Long", stop = slPrice, limit = tpPrice, trail_points = ..., trail_offset = ...)`
    is called on EVERY bar, including the SIGNAL bar, before the entry fills. Pine attaches an exit
    placed before its entry fills. On the signal bar `slPrice` and `tpPrice` are `na` (they are set
    only once `strategy.position_size` is non-zero, i.e. at the FILL bar's close), while the trail
    distances come from `pending*` variables set BEFORE `strategy.entry`. So on the FILL BAR the
    position has a live TRAILING STOP (arm 15 pts, offset 8) and NO stop and NO target. From the
    next bar all three are live.
  * `s89_core.walk(protect_fill=0)` left the fill bar entirely naked and, worse, never let the trail
    arm from the fill bar's extreme. That is the transcription gap this module closes.
  * The emulator walks each bar open -> nearer extreme -> farther extreme -> close and fills every
    order along that path; a trailing stop arms when the path reaches the activation level and then
    follows the running extreme. Slippage applies to market and stop fills, NOT to limit fills.

`fill_mode`: 0 = naked fill bar (the first transliteration), 1 = trail only on the fill bar (THE
SCRIPT), 2 = everything live on the fill bar (the v2 fix). `path` 1 = Pine's ordering, 0 = stop first.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from numba import njit
import s89_core as M


@njit(cache=True)
def walk_pine(o, h, l, c, atr, side, stop_mult, tgt_mult, trail_on, trail_arm, trail_off,
              fee, slip, fill_mode, path, mod, flat_mod, use_flat, max_hold, trail_atr, delay):
    n = len(c); mx = 40000
    e_bar = np.full(mx, -1, np.int64); x_bar = np.full(mx, -1, np.int64); s_arr = np.zeros(mx, np.int64)
    e_px = np.full(mx, np.nan); x_px = np.full(mx, np.nan); code = np.full(mx, -1, np.int64)
    risk = np.full(mx, np.nan); fillbar = np.zeros(mx, np.int64)
    cnt = 0; i = 200
    pts = np.zeros(4)
    while i < n - 2:
        s = side[i]
        if s == 0:
            i += 1; continue
        a = i + 1
        px = o[a] + s * slip
        A = atr[i]
        stp = px - s * stop_mult * A
        tgt = px + s * tgt_mult * A
        rk = stop_mult * A
        t_arm = trail_arm * A if trail_atr == 1 else trail_arm
        t_off = trail_off * A if trail_atr == 1 else trail_off
        armed = 0; tstop = 0.0
        out = np.nan; xb = -1; cd = -1
        j = a
        while j < n:
            hard = 1
            trl = trail_on
            if j - a < delay:
                # the bars before the chart bar that follows the fill closes: on the chart's own
                # bars delay=1 (the fill bar); on the 1-minute path delay=tf minutes
                if fill_mode == 0:
                    hard = 0; trl = 0
                elif fill_mode == 1:
                    hard = 0
            # the path
            if path == 1:
                lo_first = (o[j] - l[j]) <= (h[j] - o[j])
            else:
                lo_first = True if s > 0 else False
            if lo_first:
                pts[0] = o[j]; pts[1] = l[j]; pts[2] = h[j]; pts[3] = c[j]
            else:
                pts[0] = o[j]; pts[1] = h[j]; pts[2] = l[j]; pts[3] = c[j]
            done = 0
            # at the open (j > a only: at the fill bar the open IS the fill)
            if j > a and hard == 1 and j - a >= delay:
                eff = stp
                if armed == 1 and s * (tstop - eff) > 0:
                    eff = tstop
                if s * (o[j] - eff) <= 0:
                    out = o[j] - s * slip; xb = j; cd = 0 if (armed == 0 or eff == stp) else 2; done = 1
                elif s * (o[j] - tgt) >= 0:
                    out = o[j]; xb = j; cd = 1; done = 1
            prev = pts[0]
            k = 1
            while done == 0 and k < 4:
                p = pts[k]
                if s * (p - prev) > 0:
                    # favourable leg: target first (it sits beyond the arm level in every config here)
                    if hard == 1 and s * (p - tgt) >= 0 and s * (prev - tgt) < 0:
                        out = tgt; xb = j; cd = 1; done = 1
                    if done == 0 and trl == 1:
                        if armed == 0 and s * (p - px) >= t_arm:
                            armed = 1
                        if armed == 1:
                            cand = p - s * t_off
                            if tstop == 0.0 or s * (cand - tstop) > 0:
                                tstop = cand
                elif s * (p - prev) < 0:
                    # adverse leg: the effective stop is the higher of the hard stop and the trail
                    eff = 0.0; have = 0
                    if hard == 1:
                        eff = stp; have = 1
                    if armed == 1 and trl == 1:
                        if have == 0 or s * (tstop - eff) > 0:
                            eff = tstop
                        have = 1
                    if have == 1 and s * (p - eff) <= 0 and s * (prev - eff) > 0:
                        out = eff - s * slip; xb = j; cd = 0 if (hard == 1 and eff == stp) else 2; done = 1
                prev = p
                k += 1
            if done == 1:
                break
            if use_flat == 1 and mod[j] >= flat_mod:
                out = c[j] - s * slip; xb = j; cd = 3; break
            if max_hold > 0 and (j - a) >= max_hold:
                out = c[j] - s * slip; xb = j; cd = 5; break
            j += 1
        if xb < 0:
            xb = n - 1; out = c[xb] - s * slip; cd = 4
        if cnt < mx:
            e_bar[cnt] = a; x_bar[cnt] = xb; s_arr[cnt] = s; e_px[cnt] = px; x_px[cnt] = out
            code[cnt] = cd; risk[cnt] = rk; fillbar[cnt] = 1 if xb == a else 0
            cnt += 1
        i = xb + 1
    return e_bar[:cnt], x_bar[:cnt], s_arr[:cnt], e_px[:cnt], x_px[:cnt], code[:cnt], risk[:cnt], fillbar[:cnt]


def run(D, cfg=M.CFG, fill_mode=1, path=1, use_flat=0, flat_mod=15 * 60 + 55, slip=None, fee=None,
        side_override=None, max_hold=0, trail_atr=0, delay=1):
    """`fee` is the per-side commission in POINTS (the script's 1.24 $/contract at $2/pt = 0.62);
    `slip` the per-side slippage in points (the script's 1 tick = 0.25). Default = the script."""
    side = M.signals(D, cfg) if side_override is None else side_override
    slip = D["tick"] if slip is None else slip
    fee = 1.24 / cfg["pv"] if fee is None else fee
    eb, xb, s, ep, xp, cd, rk, fb = walk_pine(D["o"], D["h"], D["l"], D["c"], D["atr"], side,
                                              float(cfg["stop_mult"]), float(cfg["tgt_mult"]),
                                              int(cfg["trail_on"]), float(cfg["trail_arm"]),
                                              float(cfg["trail_off"]), float(fee), float(slip),
                                              int(fill_mode), int(path), D["mod"], int(flat_mod),
                                              int(use_flat), int(max_hold), int(trail_atr), int(delay))
    if len(eb) == 0:
        return pd.DataFrame()
    gross = s * (xp - ep)
    net = gross - 2 * fee
    t = pd.DataFrame(dict(entry_bar=eb, exit_bar=xb, side=s, entry_px=ep, exit_px=xp, code=cd, risk=rk,
                          net_pts=net, gross_pts=gross, pct=100.0 * net / ep, R=net / np.maximum(rk, 1e-9),
                          hold=xb - eb, usd=net * cfg["pv"] * cfg["qty"], on_fill_bar=fb))
    t["ts"] = D["ts"][eb]; t["sess"] = D["sess"][eb]
    t["block"] = np.where(t["sess"] < D["cut"], "research", "locked")
    t["exit"] = t["code"].map({0: "stop", 1: "target", 2: "trail", 3: "flat", 4: "eod", 5: "hold"})
    return t
