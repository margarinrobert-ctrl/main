"""V41 -- the shipped Pine's ORDER MODEL, re-implemented in Python and diffed against the engine.

`STUDY_PINE_PARITY` is the reason this file exists: a Pine port that was transcribed line by line,
read back twice and shipped lint-clean still did not reproduce the research, and the three rule
differences were found by a harness like this one rather than by reading. So the claim "this Pine
is correct" is not made by inspection here; it is measured.

TWO ORDER-MODEL GAPS ARE STRUCTURAL AND CANNOT BE TRANSCRIBED AWAY. They are modelled explicitly
so their cost is a number rather than a hope:

  1. WHERE THE STOP IS ANCHORED. `run_v41`'s engine sets the stop from the FILL price -- the next
     bar's open -- which does not exist at the moment a script writes its orders. A Pine strategy
     that wants a stop live on the ENTRY BAR must anchor it to the signal bar's CLOSE. (The
     alternative, re-anchoring to `strategy.opentrades.entry_price()` one bar later, leaves the
     entry bar naked, which `STUDY_PINE_PARITY` measured at 4.4-13.0% of trades averaging -33 to
     -118 points. That is the worse of the two.)

  2. WHEN THE CHANNEL EXIT FILLS. The engine closes AT the close of the bar whose close breaks the
     channel. `strategy.close()` cannot sell the close of the bar that triggers it -- it fills at
     the NEXT bar's OPEN. Same fact as `flat_open` in `CLAUDE.md`.

The harness runs twice, exactly as `STUDY_PINE_PARITY` prescribes:
    TRANSCRIPTION CHECK   script model with both gaps switched OFF -- must reproduce the engine
                          trade-for-trade, or the RULES differ and nothing else matters
    AS CONFIGURED         both gaps ON -- the number a Strategy Tester can actually produce

Usage: python3 research/v41/pine_parity.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v41")
import indicators as I       # noqa: E402
import v38grid as G          # noqa: E402
import v38feeds as F         # noqa: E402
import v41seq as S           # noqa: E402
from run_v41b import trades, tensors                        # noqa: E402
from run_v41c import market_prep                            # noqa: E402

CANDS = {
    "TOP": dict(tf=60, ema_f=21, ema_s=48, mode="cross", win=5, don_e=30, don_x=10,
                stop=2.5, tp=0.0, gate="adx>=20"),
    "CONSENSUS": dict(tf=60, ema_f=21, ema_s=48, mode="cross", win=10, don_e=30, don_x=10,
                      stop=2.5, tp=0.0, gate="adx>=20"),
    "BRIEF": dict(tf=60, ema_f=13, ema_s=48, mode="cross", win=40, don_e=55, don_x=20,
                  stop=1.5, tp=0.0, gate="chop<=45"),
}
MAX_HOLD = G.MAX_HOLD


def script_walk(P, cfg, anchor_close, exit_next_open, sess=None):
    """The Pine order model, bar by bar.

    `anchor_close`   True  = stop from the signal bar's close, live on the entry bar (a script)
                     False = stop from the fill price (the engine)
    `exit_next_open` True  = the channel exit fills at the NEXT bar's open (a script)
                     False = it fills at the triggering bar's close (the engine)
    `sess`           None, or (start, end, flat) in New York minutes of day. ENTRIES are
                     restricted to [start, end); EXITS never are, except by the hard flatten at
                     `flat`, which -- like every other close order in Pine -- fills at the NEXT
                     bar's open. `strategy.close_all()` cannot sell the close of the bar that
                     triggers it.
    """
    o, h, l, c = P["o"], P["h"], P["l"], P["c"]
    atr, n, pv = P["atr"], P["n"], P.get("pv", G.PV)
    comm = G.COMM * G.COST_MULT
    ecpv = G.EC * G.COST_MULT * pv
    se = G.SE * G.COST_MULT
    ex_lo = I.shift(I.rmin(l, cfg["don_x"]), 1)
    sig = set(S.signal(P, cfg["ema_f"], cfg["ema_s"], cfg["mode"], cfg["win"],
                       cfg["don_e"], cfg["gate"]).tolist())
    mod = P["mod"]
    out = []
    free = -1
    for i in range(n - 2):
        if i < free or i not in sig:
            continue
        if sess is not None and not (sess[0] <= mod[i] < sess[1]):
            continue
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        f = i + 1
        px = o[f]
        st = (c[i] - cfg["stop"] * a) if anchor_close else (px - cfg["stop"] * a)
        if not anchor_close and px - st <= 0:
            # the ENGINE can skip a non-positive-risk signal because it knows the fill. A SCRIPT
            # cannot: it writes the stop from this bar's close and only finds out where the open
            # landed afterwards. So in script mode the trade is taken and the stop fills at the
            # open on the entry bar, which the walk below already produces. Skipping here instead
            # made this harness optimistic by three trades on the BRIEF preset -- caught by asking
            # what the script actually knows at order time, not by reading the code.
            free = i + 1
            continue
        j, why, xp, xb = f, 0, 0.0, -1
        last = min(f + MAX_HOLD, n - 1)
        while j <= last:
            if l[j] <= st:                                   # the stop is a resting order
                xp = (o[j] if o[j] < st else st) - se
                why, xb = 1, j
                break
            if sess is not None and mod[j] >= sess[2] and j + 1 <= n - 1:
                xp, why, xb = o[j + 1], 3, j + 1          # the flatten, at the NEXT open
                break
            if j > f and np.isfinite(ex_lo[j]) and c[j] < ex_lo[j]:
                if exit_next_open and j + 1 <= n - 1:
                    xp, why, xb = o[j + 1], 2, j + 1        # strategy.close() fills NEXT open
                else:
                    xp, why, xb = c[j], 2, j
                break
            j += 1
        if xb < 0:
            xb, xp, why = last, c[last], 3
        out.append(dict(sig=i, fill=f, entry=px, stop=st, exit_bar=xb, exit=xp, why=why,
                        pnl=(xp - px) * pv - comm - 2.0 * ecpv))
        free = xb
    return pd.DataFrame(out)


def engine_trades(P, cfg):
    ten = tensors(P)
    xb, pnl, why = ten[(cfg["don_x"], cfg["stop"], cfg["tp"])]
    sig = S.signal(P, cfg["ema_f"], cfg["ema_s"], cfg["mode"], cfg["win"], cfg["don_e"], cfg["gate"])
    bp = np.zeros(P["n"])
    bs = np.zeros(P["n"], np.int64)
    k = G._lock(sig, xb, pnl, bp, bs)
    s = bs[:k]
    return pd.DataFrame(dict(sig=s, exit_bar=xb[s], pnl=bp[:k], why=why[s]))


def compare(a, b):
    """Trade-for-trade on the SIGNAL BAR, which is the only stable join key."""
    j = a.merge(b, on="sig", how="outer", suffixes=("_s", "_e"), indicator=True)
    both = j[j._merge == "both"]
    same_exit = float((both.exit_bar_s == both.exit_bar_e).mean()) if len(both) else np.nan
    corr = float(both.pnl_s.corr(both.pnl_e)) if len(both) > 2 else np.nan
    return dict(n_script=len(a), n_engine=len(b), shared=len(both),
                only_script=int((j._merge == "left_only").sum()),
                only_engine=int((j._merge == "right_only").sum()),
                exit_match=same_exit, corr=corr,
                usd_script=float(a.pnl.mean()) if len(a) else np.nan,
                usd_engine=float(b.pnl.mean()) if len(b) else np.nan,
                max_abs_diff=float((both.pnl_s - both.pnl_e).abs().max()) if len(both) else np.nan)


def line(tag, d):
    return (f"      {tag:<30} script {d['n_script']:>4} / engine {d['n_engine']:>4} trades   "
            f"shared {d['shared']:>4}   exit bar match {d['exit_match']:>6.1%}   "
            f"corr {d['corr']:>6.4f}   $/t {d['usd_script']:>+8.2f} vs {d['usd_engine']:>+8.2f}")


def main():
    print("=" * 122)
    print("V41 PINE PARITY -- the script's order model against the engine, US100 60-minute")
    print("=" * 122)
    print("   The transcription check must come back at exit-bar match 100% and correlation 1.0000.")
    print("   Anything less means the RULES differ and the configured gap is not worth reading.\n")
    P = market_prep("US100L", 60)
    rows = []
    for nm, cfg in CANDS.items():
        eng = engine_trades(P, cfg)
        strict = script_walk(P, cfg, anchor_close=False, exit_next_open=False)
        real = script_walk(P, cfg, anchor_close=True, exit_next_open=True)
        a_only = script_walk(P, cfg, anchor_close=True, exit_next_open=False)
        x_only = script_walk(P, cfg, anchor_close=False, exit_next_open=True)
        print(f"   {nm}")
        d0 = compare(strict, eng)
        print(line("TRANSCRIPTION CHECK", d0))
        print(f"      {'':30} max |per-trade diff| ${d0['max_abs_diff']:.6f}   "
              f"{'RULES MATCH' if d0['exit_match'] == 1.0 and d0['corr'] > .9999 else 'RULES DIFFER'}")
        for tag, d in (("+ stop anchored to close", compare(a_only, eng)),
                       ("+ exit at next open", compare(x_only, eng)),
                       ("AS CONFIGURED (both)", compare(real, eng))):
            print(line(tag, d))
        e = float(eng.pnl.mean())
        r = float(real.pnl.mean())
        print(f"      {'':30} order-model gap {r - e:+.2f} $/trade "
              f"({100 * (r / e - 1) if e else float('nan'):+.1f}%)\n")
        rows.append(dict(cand=nm, engine_usd=e, script_usd=r, n_engine=len(eng), n_script=len(real),
                         engine_pf=_pf(eng.pnl.to_numpy()), script_pf=_pf(real.pnl.to_numpy()),
                         exit_match=compare(real, eng)["exit_match"]))
    T = pd.DataFrame(rows)
    T.to_csv("research/v41/v41_pine_parity.csv", index=False)
    print("=" * 122)
    print("WHAT THE SHIPPED SCRIPT ACTUALLY PRODUCES")
    print("=" * 122)
    print(f"   {'candidate':<14}{'engine n':>10}{'engine PF':>11}{'engine $/t':>12}"
          f"{'script n':>10}{'script PF':>11}{'script $/t':>12}{'gap':>10}")
    for r in T.itertuples():
        print(f"   {r.cand:<14}{r.n_engine:>10}{r.engine_pf:>11.3f}{r.engine_usd:>+12.2f}"
              f"{r.n_script:>10}{r.script_pf:>11.3f}{r.script_usd:>+12.2f}"
              f"{r.script_usd - r.engine_usd:>+10.2f}")


def _pf(p):
    w, lo = p[p > 0], p[p < 0]
    return float(w.sum() / abs(lo.sum())) if len(lo) else float("inf")


if __name__ == "__main__":
    main()
