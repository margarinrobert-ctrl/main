"""ONE READ OF THE OPTUNA FINALISTS, then the checks that decide whether the read means anything.

SIX SECTIONS, and the order is the argument:

  1  ONE READ EACH of the holdout and the reserved different-provider forward block, for the six
     finalists, the shipped DEFAULT, the USER's own configuration and a RANDOM cell drawn from the
     same declared space. The random arm is not decoration: three of the fifteen re-optimisers on
     this branch lost to a random cell from their own grid, so it is the cheapest test of whether
     the search found anything beyond a decent region. Hold length in MINUTES and the exit mix go
     in the same table, because a ratio bought by the clock and a ratio bought by an exit look the
     same in a Sharpe column.

  2  A MATCHED RANDOM ENTRY on every cell and every block: a random bar at or after 09:30 on the
     SAME sessions, same side, same geometry, same exits, same cost, drawn bars SORTED so the
     position lock keeps the same fraction each draw (`STUDY_V59`). The control's OWN level is
     printed beside the p-value, because a rule that beats a control which loses money is still a
     losing rule (`STUDY_IB_US30_OPTUNA`) and a rule that beats a control earning +0.05% a trade
     has done something different.

  3  THE MINIMUM DETECTABLE EFFECT beside a day-block bootstrap. "Clears its control" and "is
     inside its MDE" are both true of most things measured on this market and answer different
     questions: a control's draws are SUBSETS OF THE SAME SIGNAL SET so its null sd is 3-10x
     tighter than the MDE, which prices the rule against zero from scratch.

  4  DEFLATION. `var_trials` measured over the TRIAL SHARPES at the stated count, which is the
     error `STUDY_XAU_TWO_LAYER` made in one direction and `STUDY_VP_TPO_NEXT` in the other, plus
     White's reality check over the finalists' daily streams -- the right statistic for the
     maximum over a candidate set, where the DSR deflates a single Sharpe.

  5  VECTORBT AS A TRANSCRIPTION CHECK, count first. It has failed that check three times on this
     branch and 1.1.0 cannot express a breakeven ratchet, a clock flatten as a stop, or a
     per-trade ATR multiple (`sl_stop` is a fraction of price; `td_stop`/`dt_stop` do not exist),
     so the check runs on the REDUCED geometry both engines can represent and says explicitly
     which axes it dropped. Any P&L gap is a statement about the intrabar convention, never a
     correction to the research.

  6  THE 30-SECOND FEED. It cannot add sample -- a one-trade-a-session rule has the same rate at
     any bar size -- and it overlaps the reserved forward block, so a read there is a SECOND read
     of the same weeks. What it settles is the MEASUREMENT: how often a finalist's stop and target
     fall inside one 15-minute bar, and which one actually came first.
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

try:
    from gates import deflated_sharpe, expected_max_sharpe, reality_check
    HAVE_GATES = True
except Exception:                                                  # noqa: BLE001
    HAVE_GATES = False

NDRAW = int(os.environ.get("NDRAW", 400))
NBOOT = 2000
N_TRIALS_TOTAL = 6000       # stated, not inferred: 1000 x 3 objectives x 2 flatten regimes
CFG_KEYS = ("range_end", "side", "buf_atr", "atr_n", "stop_mode", "stop_atr", "stop_pts",
            "tgt_mode", "tgt_r", "tgt_pts", "flat_m", "be_pts", "be_off", "ma_mode",
            "cross_min", "m200_form", "x_mode", "conf", "conf_tol")


def load_finalists():
    d = pd.read_csv(os.path.join(HERE, "n16_finalists.csv"))
    out = {}
    for _, r in d.iterrows():
        p = {}
        for k in CFG_KEYS:
            v = r.get(f"p_{k}")
            if pd.isna(v):
                continue
            p[k] = int(v) if k in ("range_end", "atr_n", "flat_m", "cross_min") else v
        out[str(r["study"])] = p
    return out


def main():
    t0 = time.time()
    print("=" * 122)
    print("ONE READ OF THE OPTUNA FINALISTS -- 09:00-RANGE BREAKOUT, US30")
    print("=" * 122)
    fin = load_finalists()
    rng = np.random.default_rng(11)
    arms = dict(fin)
    arms["DEFAULT (shipped)"] = dict(O.DEFAULT)
    arms["USER (their inputs)"] = dict(O.USER)
    for i in range(3):
        arms[f"RANDOM cell {i + 1}"] = O.random_cell(rng)

    ctxs = [("US30L", O.Ctx("US30L")), ("US30I", O.Ctx("US30I"))]
    cells = []
    for nm, c in ctxs:
        for b in c.blocks:
            for tag, p in arms.items():
                s, tr = O.score(c, p, b, min_tpy=0.0)
                pr = O.profile(c, tr) if tr is not None and len(tr) else {}
                cells.append(dict(arm=tag, feed=nm, block=b,
                                  **{k: v for k, v in s.items() if k != "ok"}, **pr))
    D = pd.DataFrame(cells)

    # ------------------------------------------------------------------ 1  one read
    print("\n" + "-" * 122)
    print("1  ONE READ.  A_research is where the search happened; B_holdout and C_forward (a")
    print("   DIFFERENT PROVIDER over a span the search never saw) are the reads.")
    print("-" * 122)
    for b, feed in (("A_research", "US30L"), ("B_holdout", "US30L"), ("C_forward", "US30I")):
        print(f"\n   [{feed} {b}]")
        sub = D[(D.block == b) & (D.feed == feed)]
        for _, r in sub.iterrows():
            hold = r.get("hold_med", np.nan)
            print("     " + O.row(r["arm"], r) +
                  f"  hold {hold:>6.0f}m  stop {r.get('x_stop', 0):.2f} "
                  f"tgt {r.get('x_target', 0):.2f} flat {r.get('x_flatten', 0):.2f} "
                  f"cross {r.get('x_cross', 0):.2f}")
    D.to_csv(os.path.join(HERE, "n17_read.csv"), index=False)

    # ------------------------------------------------------------------ 2  matched control
    print("\n" + "-" * 122)
    print(f"2  MATCHED RANDOM ENTRY, {NDRAW} draws, re-walked end to end")
    print("-" * 122)
    print(f"   {'arm':<24s}{'block':<12s}{'rule %/tr':>11s}{'ctrl med':>10s}"
          f"{'ctrl p95':>10s}{'p':>7s}{'verdict':>10s}")
    ctrl = []
    for nm, c in ctxs:
        for b in c.blocks:
            for tag, p in arms.items():
                s, tr = O.score(c, p, b, min_tpy=0.0)
                if tr is None or len(tr) < 30:
                    continue
                atr_n = int(p.get("atr_n", 14))
                f = c.atr_frame(atr_n)
                rhi, rlo, _ = c.ranges(p["range_end"])
                xm = p.get("x_mode", "off")
                cx = None if xm == "off" else (c.cx_cross if xm == "cross" else c.cx_state)
                sm = p.get("stop_mode", "atr"); tm = p.get("tgt_mode", "none")
                kw = dict(stop_a=p.get("stop_atr", 1.5) if sm == "atr" else 1.5,
                          stop_pts=p.get("stop_pts", 0.0) if sm == "points" else 0.0,
                          use_rng=(sm == "range"),
                          tgt_r=p.get("tgt_r", 0.0) if tm == "r" else 0.0,
                          tgt_pts=p.get("tgt_pts", 0.0) if tm == "points" else 0.0,
                          flat_m=int(p.get("flat_m", 960)), cost=c.cost, rhi=rhi, rlo=rlo,
                          be_pts=p.get("be_pts", 0.0), be_off=p.get("be_off", 0.0), cx=cx)
                nul = _control(c, f, tr, NDRAW, kw)
                pv = N.pval(s["per"], nul)
                nul = nul[np.isfinite(nul)]
                print(f"   {tag:<24s}{b:<12s}{s['per']:>+11.4f}{np.median(nul):>+10.4f}"
                      f"{np.percentile(nul, 95):>+10.4f}{pv:>7.3f}"
                      f"{('CLEARS' if pv <= 0.05 else ''):>10s}")
                ctrl.append(dict(arm=tag, feed=nm, block=b, per=s["per"],
                                 ctrl_med=float(np.median(nul)),
                                 ctrl_p95=float(np.percentile(nul, 95)), p=pv, n=s["n"]))
    pd.DataFrame(ctrl).to_csv(os.path.join(HERE, "n17_control.csv"), index=False)

    # ------------------------------------------------------------------ 3  MDE + bootstrap
    print("\n" + "-" * 122)
    print("3  MDE AND THE DAY-BLOCK BOOTSTRAP -- two questions, both reported")
    print("-" * 122)
    print(f"   {'arm':<24s}{'block':<12s}{'n':>6s}{'per %':>10s}{'sd':>9s}{'MDE':>9s}"
          f"{'per/MDE':>9s}{'boot CI':>22s}{'P(<=0)':>8s}")
    mrows = []
    for nm, c in ctxs:
        for b in c.blocks:
            for tag, p in arms.items():
                s, tr = O.score(c, p, b, min_tpy=0.0)
                if tr is None or len(tr) < 30:
                    continue
                tr = tr.copy(); tr["_day"] = tr["eday"]
                sd = float(tr["pct"].std(ddof=1))
                m = N.mde(sd, len(tr))
                bo = N.boot_edge(tr, n=NBOOT, seed=3, col="pct")
                lo, hi = np.percentile(bo, [2.5, 97.5])
                print(f"   {tag:<24s}{b:<12s}{len(tr):>6d}{s['per']:>+10.4f}{sd:>9.4f}"
                      f"{m:>9.4f}{abs(s['per']) / m:>9.2f}"
                      f"   [{lo:>+8.4f},{hi:>+8.4f}]{float((bo <= 0).mean()):>8.3f}")
                mrows.append(dict(arm=tag, feed=nm, block=b, n=len(tr), per=s["per"], sd=sd,
                                  mde=m, ratio=abs(s["per"]) / m, ci_lo=lo, ci_hi=hi,
                                  p_le0=float((bo <= 0).mean())))
    pd.DataFrame(mrows).to_csv(os.path.join(HERE, "n17_mde.csv"), index=False)

    # ------------------------------------------------------------------ 4  deflation
    print("\n" + "-" * 122)
    print("4  DEFLATION AT THE STATED TRIAL COUNT")
    print("-" * 122)
    srs = []
    for obj in ("intraday_sharpe", "intraday_sortino", "intraday_retdd",
                "free_sharpe", "free_sortino", "free_retdd"):
        fp = os.path.join(HERE, f"n16_trials_{obj}.csv")
        if os.path.exists(fp):
            d = pd.read_csv(fp)
            k = d[d["ok"]]
            srs.append(k["r_sharpe"].to_numpy() / np.sqrt(O.ANN))   # back to PER-DAY units
    srs = np.concatenate(srs) if srs else np.array([0.0])
    vt = float(np.var(srs, ddof=1))
    print(f"   scorable trials {len(srs)}   per-DAY trial Sharpe: mean {srs.mean():+.5f}  "
          f"sd {np.sqrt(vt):.5f}  best {srs.max():+.5f}")
    if HAVE_GATES:
        e0 = expected_max_sharpe(vt, N_TRIALS_TOTAL)
        print(f"   E[max per-day Sharpe | pure noise] at N={N_TRIALS_TOTAL}: {e0:+.5f}")
        print(f"   best achieved / noise floor: {srs.max() / e0:.3f}  "
              f"{'ABOVE' if srs.max() > e0 else 'BELOW ITS OWN NOISE FLOOR'}")
        best = D[(D.block == "A_research") & (~D.arm.str.startswith(("DEFAULT", "USER", "RANDOM")))]
        best = best.loc[best.sharpe.idxmax()]
        nd = len(O.Ctx("US30L")._days["A_research"])
        ds = deflated_sharpe(float(best["sharpe"]) / np.sqrt(O.ANN), nd, N_TRIALS_TOTAL, vt,
                             skew=0.0, kurtosis=3.0)
        print(f"   DSR of the best research finalist ({best['arm']}, Sharpe "
              f"{best['sharpe']:.3f}): {ds['dsr']:.4f}  -> {ds['verdict']}")
        # White's reality check over the finalists' daily streams on the RESEARCH block
        c = O.Ctx("US30L")
        cols = []
        for tag in fin:
            _, tr = O.score(c, arms[tag], "A_research", min_tpy=0.0)
            if tr is not None and len(tr):
                cols.append(O.daily(tr, c._days["A_research"]))
        if len(cols) >= 2:
            Rm = np.column_stack(cols)
            rc = reality_check(Rm, block_mean=5, n_boot=2000, seed=4)
            print(f"   White's reality check over the {Rm.shape[1]} finalist daily streams "
                  f"({Rm.shape[0]} sessions): p {rc['reality_check_p']:.4f}")
            print(f"     {rc['verdict']}")
    else:
        print("   gates.py unavailable -- deflation not computed")

    print(f"\n[run_n17 sections 1-4 in {time.time() - t0:.0f}s]")


def _control(c, f, tr, ndraw, kw):
    """The matched random entry, using the CORRECTED walker so both arms share a fill model."""
    mod = f["mod"].to_numpy(); day = f["day"].to_numpy()
    ok = (mod >= N.OPEN_M) & (mod < 960)
    sig = tr["sig"].to_numpy(); sides = tr["side"].to_numpy()
    days = day[sig]
    uniq, inv = np.unique(days, return_inverse=True)
    pos = {d: k for k, d in enumerate(uniq)}
    elig = np.flatnonzero(ok & np.isin(day, uniq))
    ed = np.array([pos[d] for d in day[elig]], np.int64)
    o = np.argsort(ed, kind="stable"); elig = elig[o]; ed = ed[o]
    cnt = np.bincount(ed, minlength=len(uniq))
    start = np.r_[0, np.cumsum(cnt)[:-1]]
    keep = cnt[inv] > 0
    inv_k = inv[keep]; sd_k = sides[keep]
    g = np.random.default_rng(5)
    out = np.full(ndraw, np.nan)
    for s in range(ndraw):
        off = (g.random(len(inv_k)) * cnt[inv_k]).astype(np.int64)
        pick = elig[start[inv_k] + off]
        q = np.argsort(pick, kind="stable")
        t = O.run2(f, pick[q], sd_k[q], fix=c.fix, **kw)
        out[s] = t["pct"].mean() if len(t) else np.nan
    return out


if __name__ == "__main__":
    main()
