"""VECTORBT AS A TRANSCRIPTION CHECK, THE 30-SECOND FEED AS THE INTRABAR ARBITER, and White's
reality check over a candidate set large enough to mean something.

WHY EACH SECTION EXISTS.

  5  VECTORBT. A second engine is a second opinion about EXECUTION and never a correction to the
     research. Run it as a TRANSCRIPTION check first -- the trade COUNT must match -- and only then
     read the P&L gap, which on this branch has been worth 2.1x (`STUDY_V38`) and 22.9x
     (`STUDY_V41`) of the reported edge on the same signals, purely from the intrabar
     stop-versus-exit convention. vectorbt 1.1.0 CANNOT express three of this strategy's axes:
     `sl_stop`/`tp_stop` are FRACTIONS OF PRICE and not per-trade ATR multiples (solved for here
     per entry), `td_stop`/`dt_stop` do not exist so a hold cap is unavailable, and there is no
     breakeven ratchet at all. The check therefore runs on the REDUCED geometry both engines can
     represent, with the dropped axes named, and both arms at ZERO COST so the comparison is about
     the fill model alone.

  6  THE 30-SECOND FEED. It cannot add sample -- one trade a session is one trade a session at any
     bar size -- and it overlaps the reserved forward block, so any P&L read here is a SECOND read
     of the same weeks and is descriptive. What it settles is the MEASUREMENT: how often this
     strategy's stop and target fall inside ONE 15-minute bar, and which of them actually came
     first. `STUDY_US30_SCALP_0711` could not answer that and the two conventions differed by more
     than any edge in that study.

  7  WHITE'S REALITY CHECK, over a SAMPLE OF THE TRIAL POPULATION rather than the six finalists.
     Running it over six is the same error as counting six trials: the statistic's whole point is
     to price the MAXIMUM over the candidate set that was actually searched.
"""
from __future__ import annotations

import os
import sys
import time
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append("/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_"
                "641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
import na_core as N   # noqa: E402
import na_opt as O    # noqa: E402
import na_30s as T    # noqa: E402
from gates import reality_check  # noqa: E402

CFG_KEYS = ("range_end", "side", "buf_atr", "atr_n", "stop_mode", "stop_atr", "stop_pts",
            "tgt_mode", "tgt_r", "tgt_pts", "flat_m", "be_pts", "be_off", "ma_mode",
            "cross_min", "m200_form", "x_mode", "conf", "conf_tol")


def cfg_from_row(r):
    p = {}
    for k in CFG_KEYS:
        v = r.get(f"p_{k}")
        if v is None or (isinstance(v, float) and np.isnan(v)):
            continue
        p[k] = int(v) if k in ("range_end", "atr_n", "flat_m", "cross_min") else v
    return p


# ------------------------------------------------------------------ 5  vectorbt
def vbt_check(ctx, p, block, tag):
    """Both engines, ZERO cost, LONG only, on the reduced geometry vectorbt can express."""
    import vectorbt as vbt
    dropped = []
    q = dict(p)
    q["side"] = "long"
    if q.get("be_pts", 0):
        dropped.append("breakeven ratchet (no vbt equivalent)")
        q["be_pts"] = 0.0; q["be_off"] = 0.0
    if q.get("x_mode", "off") != "off":
        dropped.append("opposite-cross exit (would need a second signal array)")
        q["x_mode"] = "off"
    if q.get("stop_mode") == "range":
        dropped.append("range stop -> ATR 1.5N (vbt sl_stop is a fraction of price)")
        q["stop_mode"] = "atr"; q["stop_atr"] = 1.5
    q["cost_mult"] = 0.0
    s, tr = O.score(ctx, q, block, min_tpy=0.0)
    if tr is None or len(tr) < 20:
        return None
    f = ctx.atr_frame(int(q.get("atr_n", 14)))
    n = len(f)
    eb = tr["eb"].to_numpy(); ent = tr["ent"].to_numpy(); risk = tr["risk"].to_numpy()
    entries = np.zeros(n, bool); entries[eb] = True
    sl = np.full(n, np.nan); sl[eb] = risk / ent
    tp = np.full(n, np.nan)
    tm = q.get("tgt_mode", "none")
    if tm == "r":
        tp[eb] = (q["tgt_r"] * risk) / ent
    elif tm == "points":
        tp[eb] = q["tgt_pts"] / ent
    mod = f["mod"].to_numpy()
    exits = np.zeros(n, bool)
    fm = int(q.get("flat_m", 960))
    if fm > 0:
        exits[1:] = (mod[1:] >= fm) & (mod[:-1] < fm)
    idx = f.index
    pf = vbt.Portfolio.from_signals(
        close=pd.Series(f["close"].to_numpy(), index=idx),
        open=pd.Series(f["open"].to_numpy(), index=idx),
        high=pd.Series(f["high"].to_numpy(), index=idx),
        low=pd.Series(f["low"].to_numpy(), index=idx),
        entries=pd.Series(entries, index=idx), exits=pd.Series(exits, index=idx),
        price=pd.Series(f["open"].to_numpy(), index=idx),
        sl_stop=pd.Series(sl, index=idx), tp_stop=pd.Series(tp, index=idx),
        stop_entry_price="fillprice", size=1.0, size_type="amount",
        fees=0.0, slippage=0.0, init_cash=1e9, accumulate=False, direction="longonly",
        freq=f"{ctx.tf}min")
    rec = pf.trades.records_readable
    m = np.isin(tr["eday"].to_numpy(), ctx._days[block])
    eng = tr[m]
    col = next(c for c in ("PnL", "pnl") if c in rec.columns)
    ec = next(c for c in ("Entry Timestamp", "Entry Index", "entry_idx") if c in rec.columns)
    lo, hi = idx[np.flatnonzero(ctx.blocks[block])[[0, -1]]]
    rv = rec[(rec[ec] >= lo) & (rec[ec] <= hi)]
    return dict(tag=tag, block=block, eng_n=len(eng), vbt_n=len(rv),
                ratio=len(rv) / max(len(eng), 1),
                eng_pts=float(eng["pts"].mean()),
                vbt_pts=float(rv[col].mean()) if len(rv) else np.nan,
                dropped="; ".join(dropped) or "none")


# ------------------------------------------------------------------ 6  the 30-second arbiter
def arbiter(stops, tgts, use_range=False):
    """For each 15-minute trade, walk the 30-SECOND path and ask which barrier came first.

    THE TRIGGER IS NOT THE QUESTION HERE -- whether a stop and a target fall inside one bar is a
    property of the GEOMETRY -- so the default entry is a long at the 09:30 open on EVERY session.
    That matters on this feed: it OMITS bars with no activity, and the 09:00-09:30 pre-open is
    exactly where a Dow CFD is quiet, so only 92 of 293 sessions carry the strategy's own range
    while 270 carry a 09:30 bar. Asking the geometry question on every session is a 3.3x larger
    sample of the thing being measured, not a different question. `use_range = True` reproduces
    the rule's own trigger for comparison.
    """
    f15 = T.frame(15.0); f30 = T.frame(0.5)
    rhi, rlo, _ = N.ranges(f15, N.RS, 570)
    if use_range:
        sig, sd = N.events(f15, rhi, rlo, side="long", re_=570)
    else:
        mod = f15["mod"].to_numpy(); day = f15["day"].to_numpy()
        first = np.flatnonzero((mod >= 570) & (np.r_[True, day[1:] != day[:-1]] |
                                               (np.r_[True, mod[:-1] < 570])))
        seen = set(); keep = []
        for i in first:
            if day[i] not in seen:
                seen.add(day[i]); keep.append(i)
        sig = np.asarray(keep, np.int64); sd = np.ones(len(sig), np.int64)
    h30 = f30["high"].to_numpy(); l30 = f30["low"].to_numpy()
    t30 = f30.index.values
    t15 = f15.index.values
    out = []
    for sp in stops:
        for tg in tgts:
            tr = O.run2(f15, sig, sd, stop_pts=sp, tgt_pts=tg, flat_m=960, cost=2.29,
                        rhi=rhi, rlo=rlo, fix=1)
            amb = tr[tr["amb"] == 1]
            first = {"stop": 0, "tgt": 0, "tie": 0}
            for _, r in amb.iterrows():
                e = f15["open"].to_numpy()[int(r["eb"])]
                st = e - sp; tp = e + tg
                a = np.searchsorted(t30, t15[int(r["xb"])])
                b = np.searchsorted(t30, t15[int(r["xb"])] + np.timedelta64(15, "m"))
                hs = np.flatnonzero(l30[a:b] <= st)
                ht = np.flatnonzero(h30[a:b] >= tp)
                if len(hs) and len(ht):
                    first["stop" if hs[0] < ht[0] else ("tgt" if ht[0] < hs[0] else "tie")] += 1
                elif len(hs):
                    first["stop"] += 1
                elif len(ht):
                    first["tgt"] += 1
                else:
                    first["tie"] += 1
            res = first["stop"] + first["tgt"]
            out.append(dict(stop_pts=sp, tgt_pts=tg, n=len(tr), amb=len(amb),
                            amb_share=len(amb) / max(len(tr), 1),
                            resolved=res / max(len(amb), 1) if len(amb) else np.nan,
                            stop_first=first["stop"] / max(res, 1) if res else np.nan,
                            tgt_first=first["tgt"] / max(res, 1) if res else np.nan,
                            unresolved=first["tie"]))
    return pd.DataFrame(out)


def main():
    t0 = time.time()
    print("=" * 122)
    print("SECOND-ENGINE, INTRABAR AND DEFLATION CHECKS ON THE 09:00-RANGE BREAKOUT")
    print("=" * 122)
    fdf = pd.read_csv(os.path.join(HERE, "n16_finalists.csv"))
    arms = {str(r["study"]): cfg_from_row(r) for _, r in fdf.iterrows()}
    arms["DEFAULT"] = dict(O.DEFAULT)
    arms["USER"] = dict(O.USER)
    cL = O.Ctx("US30L")

    print("\n" + "-" * 122)
    print("5  VECTORBT 1.1.0 AS A TRANSCRIPTION CHECK -- count first, ZERO cost in both arms")
    print("-" * 122)
    print(f"   {'arm':<20s}{'block':<12s}{'engine n':>9s}{'vbt n':>8s}{'ratio':>8s}"
          f"{'eng pts':>10s}{'vbt pts':>10s}{'gap':>9s}  axes vbt cannot express")
    rows = []
    for tag, p in arms.items():
        for b in ("A_research", "B_holdout"):
            try:
                r = vbt_check(cL, p, b, tag)
            except Exception as e:                                  # noqa: BLE001
                print(f"   {tag:<20s}{b:<12s}  vbt failed: {type(e).__name__}: {e}")
                continue
            if r is None:
                continue
            gap = r["vbt_pts"] - r["eng_pts"]
            flag = "PASS" if 0.97 <= r["ratio"] <= 1.03 else "FAIL"
            print(f"   {tag:<20s}{b:<12s}{r['eng_n']:>9d}{r['vbt_n']:>8d}{r['ratio']:>8.3f}"
                  f"{r['eng_pts']:>10.3f}{r['vbt_pts']:>10.3f}{gap:>+9.3f}  {flag}  "
                  f"{r['dropped']}")
            rows.append(dict(**r, gap=gap, transcription=flag))
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "n18_vbt.csv"), index=False)
    print("\n   A count ratio outside [0.97, 1.03] means the two engines are not running the same")
    print("   strategy and no P&L comparison is admissible. Where the count matches, the gap is a")
    print("   statement about the intrabar convention and never a correction to the research.")

    print("\n" + "-" * 122)
    print("6  THE 30-SECOND FEED AS THE INTRABAR ARBITER (US30_30s, 390,552 bars, 2025-08 .. "
          "2026-09)")
    print("-" * 122)
    f15c = T.frame(15.0)
    modc = f15c["mod"].to_numpy(); dayc = f15c["day"].to_numpy()
    rhic, _, _ = N.ranges(f15c, N.RS, 570)
    print(f"   COVERAGE FIRST. This feed omits bars with no activity: of "
          f"{len(np.unique(dayc))} sessions, {int((modc == 570).sum())} carry a 09:30 bar and "
          f"only {len(np.unique(dayc[np.isfinite(rhic)]))} carry the 09:00-09:30 pre-open the")
    print("   strategy's own range is built from. The geometry question is therefore asked on a")
    print("   09:30-open long on EVERY session; the rule's own trigger is run beside it.")
    A = arbiter((50.0, 75.0, 100.0, 150.0), (50.0, 100.0, 200.0))
    print("\n   [09:30-open long, every session]")
    print(A.round(4).to_string(index=False))
    B = arbiter((50.0, 100.0), (50.0, 100.0), use_range=True)
    print("\n   [the rule's own 09:00-range trigger, the 92 sessions that carry it]")
    print(B.round(4).to_string(index=False))
    B.to_csv(os.path.join(HERE, "n18_arbiter_rule.csv"), index=False)
    A.to_csv(os.path.join(HERE, "n18_arbiter.csv"), index=False)
    tot_amb = A["amb"].sum(); tot_res = (A["resolved"].fillna(0) * A["amb"]).sum()
    wsf = np.nansum(A["stop_first"] * A["resolved"].fillna(0) * A["amb"]) / max(tot_res, 1)
    print(f"\n   pooled: {int(tot_amb)} ambiguous 15-minute trades, {tot_res / max(tot_amb,1):.4f}"
          f" of them resolve at 30 seconds, and of those the STOP came first "
          f"{wsf:.4f} of the time.")
    print("   The branch's convention is stop-always. Read against this, it is CONSERVATIVE as")
    print("   intended and right about that fraction of the time rather than all of it.")

    print("\n" + "-" * 122)
    print("7  WHITE'S REALITY CHECK OVER A SAMPLE OF THE TRIAL POPULATION")
    print("-" * 122)
    pool = []
    for obj in ("intraday_sharpe", "intraday_sortino", "intraday_retdd",
                "free_sharpe", "free_sortino", "free_retdd"):
        fp = os.path.join(HERE, f"n16_trials_{obj}.csv")
        if os.path.exists(fp):
            d = pd.read_csv(fp)
            pool.append(d[d["ok"]])
    pool = pd.concat(pool, ignore_index=True)
    rng = np.random.default_rng(21)
    take = rng.choice(len(pool), size=min(250, len(pool)), replace=False)
    cols = []
    for i in take:
        p = cfg_from_row(pool.iloc[i])
        _, tr = O.score(cL, p, "A_research", min_tpy=0.0)
        if tr is not None and len(tr) >= 30:
            cols.append(O.daily(tr, cL._days["A_research"]))
    Rm = np.column_stack(cols)
    print(f"   candidates in the reality check: {Rm.shape[1]} of {len(pool)} scorable trials, "
          f"{Rm.shape[0]} sessions")
    rc = reality_check(Rm, block_mean=5, n_boot=2000, seed=4)
    print(f"   p {rc['reality_check_p']:.4f}   {rc['verdict']}")
    print("   Note what block this is on: the RESEARCH block, where the candidates were chosen.")
    print("   It prices the maximum against the search, not against a fresh sample -- section 2")
    print("   of run_n17 is the fresh-sample answer and 0 of 6 finalists cleared there.")
    print(f"\n[run_n18 done in {time.time() - t0:.0f}s]")


if __name__ == "__main__":
    main()
