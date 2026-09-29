"""V41 part 4 -- the control on the cross-market result, and vectorbt as a second engine.

Part 3 produced the shape this branch has now seen three times (`STUDY_V12_DONCHIAN_3020`,
`STUDY_V38_LINREG_GRID`): every candidate FAILS on the NQ it was selected on and is POSITIVE on
US30 and US100, which had no part in the search. US100 PF 1.53-1.67 over 142-322 trades.

That is not evidence yet. Every one of these markets rose, the rule is long only, and a
trailing-exit long system in a rising market is a drift harvester. Two nulls:

  MATCHED CONTROL   random entry bars at the SAME minute of day, same count, same geometry, same
                    one-position lock. Answers "is the TRIGGER worth anything".
  ABLATION CONTROL  the identical configuration with the EMA condition REMOVED -- the grid's own
                    Donchian-alone twin, run on the same market. Answers the brief's actual
                    question: does the EMA cross add anything HERE?

Then vectorbt on the same signals, because three engine bugs on this branch were found exactly
that way and none was visible by reading code.

Usage: python3 research/v41/run_v41d.py
"""
from __future__ import annotations

import pickle
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v39")
sys.path.insert(0, "research/v41")
import indicators as I       # noqa: E402
import v38grid as G          # noqa: E402
import v38feeds as F         # noqa: E402
import v39mc as MC           # noqa: E402
import v41seq as S           # noqa: E402
from run_v41 import hdr                                    # noqa: E402
from run_v41b import trades, tensors, line, KEYS           # noqa: E402
from run_v41c import market_prep, score_of                 # noqa: E402

DRAWS = 400


def matched_control(P, ten, cfg, sb, draws=DRAWS, seed=19):
    xb, pnl, _w = ten[(cfg["don_x"], cfg["stop"], cfg["tp"])]
    mod = P["mod"]
    ok = np.flatnonzero(np.isfinite(P["atr"]) & (P["atr"] > 0) & (xb >= 0))
    pool = {}
    for t in np.unique(mod[sb]):
        q = ok[mod[ok] == t]
        if len(q):
            pool[int(t)] = q
    want = [int(t) for t in mod[sb] if int(t) in pool]
    rng = np.random.default_rng(seed)
    bp = np.zeros(P["n"])
    bs = np.zeros(P["n"], np.int64)
    out = []
    for _ in range(draws):
        pick = np.sort(np.array([rng.choice(pool[t]) for t in want], np.int64))
        k = G._lock(pick, xb, pnl, bp, bs)
        if k < 10:
            continue
        out.append(float(bp[:k].mean()))
    return np.array(out)


def main():
    t0 = time.perf_counter()
    with open("research/v41/v41_cands.pkl", "rb") as fh:
        cands = pickle.load(fh)

    hdr("14. THE TWO CONTROLS ON THE MARKETS THAT CHOSE NOTHING")
    rows = []
    for mkt in ("US30L", "US100L"):
        print(f"\n   --- {mkt}  (${F.INSTR[mkt]['pv']:.0f}/point)")
        for nm, c in cands.items():
            Q = market_prep(mkt, int(c["tf"]))
            ten = tensors(Q)
            s = score_of(Q, ten, c)
            if s is None:
                continue
            m, p, sb = s
            A = matched_control(Q, ten, c, sb)
            pm = float(((A >= m["usd"]).sum() + 1) / (len(A) + 1))
            abl = dict(c)
            abl["mode"], abl["win"] = "cross", 0        # the Donchian-alone twin
            sa = score_of(Q, ten, abl)
            print(f"\n   {nm}")
            print(line("rule", m))
            print(line("SAME config, EMA REMOVED", sa[0] if sa else None))
            print(f"      matched control mean {A.mean():>+8.2f}  p95 "
                  f"{np.percentile(A, 95):>+8.2f}   rule {m['usd']:>+8.2f}   p = {pm:.3f}   "
                  f"{'CLEARS' if pm <= 0.05 else 'FAILS'}")
            if sa and sa[0]:
                d = m["usd"] - sa[0]["usd"]
                print(f"      EMA contribution: {d:>+8.2f} $/trade   "
                      f"({m['n']} trades against {sa[0]['n']}, "
                      f"{100 * m['n'] / max(sa[0]['n'], 1) - 100:+.0f}%)   "
                      f"PF {m['pf']:.3f} vs {sa[0]['pf']:.3f}")
            rows.append(dict(mkt=mkt, cand=nm, pf=m["pf"], usd=m["usd"], n=m["n"], p_ctrl=pm,
                             abl_pf=(sa[0]["pf"] if sa and sa[0] else np.nan),
                             abl_usd=(sa[0]["usd"] if sa and sa[0] else np.nan)))
    R = pd.DataFrame(rows)
    R.to_csv("research/v41/v41_xmkt_controls.csv", index=False)
    hdr("VERDICT ON THE CONTROLS")
    print(f"   cells clearing the matched control at p<=0.05: "
          f"{int((R.p_ctrl <= 0.05).sum())} of {len(R)}")
    beats = int((R.usd > R.abl_usd).sum())
    print(f"   cells where the EMA beats its own no-EMA twin: {beats} of {len(R)} "
          f"(chance 50% = {len(R) / 2:.1f})")
    print(f"   mean EMA contribution {float((R.usd - R.abl_usd).mean()):+.2f} $/trade")

    hdr("15. VECTORBT -- an independently written engine on the same signals")
    import vectorbt as vbt
    print(f"   vectorbt {vbt.__version__}")
    for mkt in ("US30L", "US100L"):
        for nm, c in cands.items():
            Q = market_prep(mkt, int(c["tf"]))
            ten = tensors(Q)
            s = score_of(Q, ten, c)
            if s is None:
                continue
            m, _p, _sb = s
            d = F.frame(mkt, int(c["tf"]))
            idx = pd.to_datetime(d["ts"])
            sig = S.signal(Q, c["ema_f"], c["ema_s"], c["mode"], c["win"], c["don_e"], c["gate"])
            ent = np.zeros(Q["n"], bool)
            ent[np.minimum(sig + 1, Q["n"] - 1)] = True
            ex_lo = I.shift(I.rmin(Q["l"], c["don_x"]), 1)
            xit = np.zeros(Q["n"], bool)
            xit[1:] = Q["c"][1:] < ex_lo[1:]
            slf = pd.Series(c["stop"] * Q["atr"] / np.maximum(Q["c"], 1e-9),
                            index=idx).shift(1).bfill().to_numpy()
            pv = F.INSTR[mkt]["pv"]
            pf = vbt.Portfolio.from_signals(
                close=pd.Series(Q["c"], index=idx), entries=pd.Series(ent, index=idx),
                exits=pd.Series(xit, index=idx), price=pd.Series(Q["o"], index=idx),
                sl_stop=slf, accumulate=False, size=1, size_type="amount", fees=0.0,
                fixed_fees=G.COMM * G.COST_MULT + 2.0 * G.EC * G.COST_MULT * pv,
                init_cash=1_000_000, freq=f"{c['tf']}min")
            tr = pf.trades.records_readable
            nv, netv = len(tr), float(tr["PnL"].sum()) * pv if len(tr) else 0.0
            print(f"\n   {mkt} {c['tf']}m -- {nm}")
            print(f"      {'my engine':<26} n {m['n']:>5}  $/t {m['usd']:>+9.2f}  "
                  f"net ${m['net']:>+11,.0f}")
            print(f"      {'vectorbt':<26} n {nv:>5}  $/t {netv / max(nv, 1):>+9.2f}  "
                  f"net ${netv:>+11,.0f}")
            agree = abs(nv - m["n"]) <= 0.10 * max(m["n"], 1)
            print(f"      trade-count ratio {nv / max(m['n'], 1):.3f}   "
                  f"{'SIGNAL SETS AGREE' if agree else 'SIGNAL COUNTS DIFFER -- entry logic is not the same'}")
    print("\n   The two engines share a signal definition and differ in how a stop and a channel")
    print("   exit inside ONE bar are ordered: mine takes the stop, the pessimistic branch. A")
    print("   matching COUNT with a different net is that convention; a mismatched count is a bug.")
    print(f"\n   elapsed {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
