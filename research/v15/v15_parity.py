"""The V15 Pine's order model in Python, diffed against the engine.

This is the port that carries the most that can go wrong: a RESTING LIMIT whose fill has to be
ordered against the exits, a bracket that must cover the fill bar, and an exit level that is
computed on one bar and live on the next. Three earlier ports on this branch were wrong in exactly
those three places and none of the errors were visible by reading the script.

WHAT THIS MODELS, LINE FOR LINE:
  * the limit rests from the bar AFTER the signal for `lim_wait` bars, then cancels -- and while it
    rests the script IGNORES new signals, where the engine drops the unfilled signal and re-reads
    the very next bar. That is the one deliberate difference and it is a difference in TRADE COUNT,
    not in any trade's outcome.
  * on the FILL BAR only the ATR stop is live (bracket `x0`, `loss` only). No channel, no target --
    the fill happened because the bar traded UP to the limit, so paying that same bar's low for a
    target assumes an intrabar sequence nobody can know. That was a Sharpe-11 artifact once.
  * from the next bar the working stop is the NEARER of the ATR stop and the exit channel, where
    the channel is `ta.highest(high, n)` read at the PLACING bar -- which is the same window the
    engine reads at the bar the order is live on. Writing `[1]` there, the obvious-looking choice,
    makes the script one bar staler than the engine on every trade.
  * a buy stop cannot rest below the market. Pine triggers such an order at the next bar's OPEN;
    the engine caps the level at the previous CLOSE. That gap is the residual reported below.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd
sys.path.insert(0, "research/v15"); sys.path.insert(0, "research/v8opt")
import eem  # noqa: E402

COLS = ["sig", "ent", "exit", "px0", "exitpx", "pnl", "reason"]


def run_pine(d, atr, C, mask, *, side=-1, atr_mult=2.5, tp_r=None, cost=1.72,
             lim_mult=0.75, lim_atr=None, lim_wait=8, exit_key=None, arm="hold", force=None):
    """A bar-by-bar state machine with ONE live order, which is all a script can have.

    `arm` is the only free choice in the port and it is worth more than every other line:

      hold     the order rests untouched for `lim_wait` bars and NEW SIGNALS ARE IGNORED while it
               does. The plain reading of the script.
      replace  a fresh signal RE-PRICES the resting order to the new bar's level, resetting the
               clock. Chases the market and is the worst of the three.
      best     a fresh signal re-prices ONLY if the new level is FURTHER IN OUR FAVOUR, and resets
               the clock when it does. Keeps the deepest level on offer, which is the thing the
               engine's forward scan is really buying.

    The ENGINE is none of these. It scans forward from each signal in turn and takes the first bar
    that reaches THAT signal's level, so an eight-bar-old level outranks a newer, nearer one -- an
    ordering that needs eight simultaneous resting limits AND for the far one to fill first. Read
    the trade counts below before believing any limit-entry number on this branch.
    """
    o, h, l, c = d["o"], d["h"], d["l"], d["c"]
    n = len(c)
    ent_k = "hi1" if side > 0 else "elo1"
    ex_k = exit_key or ("lo1" if side > 0 else "xhi1")
    better = (lambda a, b: a < b) if side > 0 else (lambda a, b: a > b)
    rows = []
    armed = False; px = np.nan; pend = -1; a = np.nan; sig = -1
    i = 1
    while i < n - 1:
        # ---- the entry block, at the close of bar i, only while flat
        # `force` replaces the RULE, not the geometry -- that is what makes a matched control a
        # control: same side, same stop, same target, same order type, same minute of day, and no
        # Donchian break. Anything the rule earns has to show up as the gap between the two.
        fired = (bool(force[i]) if force is not None else
                 (mask[i] and np.isfinite(atr[i]) and atr[i] > 0 and np.isfinite(C[ent_k][i])
                  and ((h[i] > C[ent_k][i]) if side > 0 else (l[i] < C[ent_k][i]))))
        if fired and not (np.isfinite(atr[i]) and atr[i] > 0):
            fired = False
        if armed and i - pend >= lim_wait:
            armed = False                               # strategy.cancel_all()
        if fired:
            new = (c[i] - side * lim_mult * lim_atr[i]) if lim_mult else np.nan
            if not armed or arm == "replace" or (arm == "best" and better(new, px)):
                armed, px, pend, a, sig = True, new, i, atr[i], i
        if not armed:
            i += 1
            continue
        j = i + 1                                       # the order is live from the next bar
        if lim_mult:
            hit = (l[j] <= px) if side > 0 else (h[j] >= px)
            if not hit:
                i += 1
                continue
            px0 = px
        else:
            px0 = o[j]                                  # market at the next open, fills always
        armed = False
        # ---- the trade
        stop = px0 - side * atr_mult * a
        tgt = None if tp_r is None else px0 + side * tp_r * atr_mult * a
        pnl = -cost
        eb = j
        while j < n:
            if j == eb and lim_mult:                    # bracket x0 on the fill bar: loss only
                lvl = stop
                if (l[j] <= lvl) if side > 0 else (h[j] >= lvl):
                    pnl += side * (lvl - px0)
                    rows.append((sig, eb, j, px0, lvl, pnl, "stop"))
                    break
                j += 1
                continue
            ch = C[ex_k][j]
            lvl = stop
            if np.isfinite(ch):
                lvl = max(lvl, ch) if side > 0 else min(lvl, ch)
            # A SELL STOP CANNOT REST ABOVE THE MARKET. The script caps the level at the placing
            # bar's close, which is what the engine does, so the two agree instead of gapping.
            cap = c[j - 1]
            lvl = min(lvl, cap) if side > 0 else max(lvl, cap)
            if (l[j] <= lvl) if side > 0 else (h[j] >= lvl):   # stop wins an inside-bar tie
                pnl += side * (lvl - px0)
                rows.append((sig, eb, j, px0, lvl, pnl, "stop"))
                break
            if tgt is not None and ((h[j] >= tgt) if side > 0 else (l[j] <= tgt)):
                pnl += side * (tgt - px0)
                rows.append((sig, eb, j, px0, tgt, pnl, "tp"))
                break
            j += 1
        else:
            break
        i = j + 1
    return pd.DataFrame(rows, columns=COLS)


if __name__ == "__main__":
    import v15book as B

    ARM = sys.argv[1] if len(sys.argv) > 1 else "hold"
    print(f"V15: the engine vs the shipped script's order model  [arm = {ARM}]\n")
    hdr = (f"{'market / leg':<22}{'eng n':>7}{'pine n':>8}{'sig match':>11}{'exit bar':>10}"
           f"{'eng PF':>9}{'pine PF':>9}{'eng R':>9}{'pine R':>9}{'corr':>9}")
    print(hdr); print("-" * len(hdr))
    pf = lambda x: (x[x > 0].sum() / abs(x[x < 0].sum())) if (x < 0).any() else np.nan
    frac = B.cost_frac()
    for nm, path in [("US30", "data/US30_ISO_15m.csv"), ("US100", "data/US100_ISO_15m.csv")]:
        d, ix = B.load(path)
        F = B.feats(d); C = B.channels(d)
        cost = frac * 2 * float(np.nanmedian(F["atr"]))
        block = np.ones(len(d["c"]), bool)
        M = B.legs(d, F, block)
        for leg in ("short", "long"):
            e = B.run_leg(d, F, C, M[leg], leg, cost, lim=True)
            kw = (dict(side=-1, atr_mult=2.5, tp_r=2.0, exit_key="xhi1") if leg == "short"
                  else dict(side=1, atr_mult=2.0, tp_r=None, exit_key="lo1"))
            q = run_pine(d, F["atr"], C[leg], M[leg], cost=cost, lim_atr=F["atr5"],
                         lim_wait=8, arm=ARM, **kw)
            R = lambda t, mult: t.pnl.to_numpy() / (mult * F["atr"][t.sig.to_numpy()])
            mult = 2.5 if leg == "short" else 2.0
            j = e.set_index("sig").join(q.set_index("sig"), how="inner", lsuffix="_e", rsuffix="_q")
            sx = float((j["exit_e"] == j["exit_q"]).mean()) if len(j) else np.nan
            cr = np.corrcoef(j.pnl_e, j.pnl_q)[0, 1] if len(j) > 2 else np.nan
            ov = len(set(e.sig) & set(q.sig)) / max(len(set(e.sig)), 1)
            print(f"{nm+' '+leg:<22}{len(e):>7}{len(q):>8}{ov:>10.1%}{sx:>10.1%}"
                  f"{pf(e.pnl.to_numpy()):>9.2f}{pf(q.pnl.to_numpy()):>9.2f}"
                  f"{R(e,mult).sum():>+9.1f}{R(q,mult).sum():>+9.1f}{cr:>9.4f}")
