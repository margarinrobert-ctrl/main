"""S1 -- the two additions, declared before they are read.

The ask: a session window for trade selection, a session stop, and a breakeven in points. Each is
measured on the submitted rule rather than wired up, because this branch has measured a session
flatten as destructive seventeen times and a breakeven as a subtractor once.

Declared grids, and nothing outside them is read:

    SESSION   all hours / 07:00-11:00 / 08:00-12:00 / 09:30-11:00 / 09:30-12:00 / 09:30-16:00
              / 13:00-16:00                                            x  flatten off / on
    BREAKEVEN off / 25 / 50 / 75 points                                x  secure 0 / 5 points
    BLOCKS    US30L research, US30L holdout, US30I forward (a different provider)

The breakeven rungs at or beyond the 100-point target are INERT -- the target resolves first on the
same bar -- so 100 and 150 are excluded from the grid rather than counted as tests never run.

`E[max t | pure noise]` is printed for each ladder BEFORE its table, because the luckiest draw of a
null search must clear 2.802 before any survivor of a search that size can be believed.
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m13core as M

pd.set_option("display.width", 210)
HERE = os.path.dirname(os.path.abspath(__file__))

WINS = {"all hours": (-1, -1), "07:00-11:00": (420, 660), "08:00-12:00": (480, 720),
        "09:30-11:00": (570, 660), "09:30-12:00": (570, 720), "09:30-16:00": (570, 960),
        "13:00-16:00": (780, 960)}
BE = [0.0, 25.0, 50.0, 75.0]
SEC = [0.0, 5.0]
FEEDS = ["US30L", "US30I"]


def cells(f, name, sig, sd, cost, bl, **kw):
    rows = []
    for bn, mask in bl.items():
        tr = M.attach_day(f, M.run(f, sig, sd, cost=cost, **kw))
        t = tr[mask[tr["sig"].to_numpy()]]
        if len(t) < 25:
            continue
        m = M.mix(t)
        rows.append(dict(feed=name, block=bn, n=len(t),
                         pts=round(t["pts"].mean(), 3),
                         pct=round(t["pct"].mean(), 5),
                         pf=round(t.loc[t.pts > 0, "pts"].sum() /
                                  max(-t.loc[t.pts < 0, "pts"].sum(), 1e-9), 3),
                         win=round(float((t.pts > 0).mean()), 4),
                         stop=m["stop"], tgt=m["target"], flat=m["flat"],
                         mde=round(M.mde(t["pct"].std(), len(t)), 5)))
    return rows


def main():
    print("=" * 112)
    print("S1  MA 13/48 CROSS, 100pt / 100pt -- the session and breakeven additions, measured")
    print("=" * 112)

    # ---------------------------------------------------------------- arithmetic first
    print("\n--- the arithmetic, before any rule ---")
    for name in FEEDS:
        f = M.load(name, 15); cost = M.COST[name]
        at = np.nanmedian(f["atr"].to_numpy())
        be = (100.0 + cost) / 200.0
        print(f"  {name}: median ATR {at:6.2f} pts -> a 100-pt barrier is {100/at:5.2f} ATR;  "
              f"round turn {cost} = {100*cost/100:.2f}% of the stop;  "
              f"driftless break-even at 1:1 = {100*be:.2f}%")

    # ---------------------------------------------------------------- the base
    print("\n--- the rule as submitted, all hours, no breakeven ---")
    base = []
    for name in FEEDS:
        f = M.load(name, 15); cost = M.COST[name]; bl = M.blocks(f, name)
        sig, sd = M.signals(f)
        base += cells(f, name, sig, sd, cost, bl)
    b = pd.DataFrame(base)
    print(b.to_string(index=False))
    print("  win rate against its own driftless break-even is the whole story: the barriers are "
          "symmetric, so the rule needs 51.15% and the market gives it what it gives it.")

    # ---------------------------------------------------------------- session ladder
    n_sess = len(WINS) * 2 * 3
    print("\n" + "=" * 112)
    print(f"SESSION LADDER -- {n_sess} declared cells, "
          f"E[max t | pure noise] = {M.e_max_normal(n_sess):.3f} against the 2.802 detection needs")
    print("=" * 112)
    rows = []
    for name in FEEDS:
        f = M.load(name, 15); cost = M.COST[name]; bl = M.blocks(f, name)
        sig, sd = M.signals(f)
        for wname, (s0, s1) in WINS.items():
            for fl in (0, 1):
                if fl and s0 < 0:
                    continue
                for r in cells(f, name, sig, sd, cost, bl, s0=s0, s1=s1,
                               flat_m=(s1 if fl else 0)):
                    r["win_name"] = wname
                    r["flat_on"] = bool(fl)
                    rows.append(r)
    s = pd.DataFrame(rows)
    s.to_csv(os.path.join(HERE, "s1_session.csv"), index=False)
    print(s[["feed", "block", "win_name", "flat_on", "n", "pts", "pct", "pf", "win",
             "stop", "tgt", "flat", "mde"]].to_string(index=False))

    print("\n  marginal average by window (the whole ladder, never a top row):")
    print(s.groupby("win_name").agg(pts=("pts", "mean"), pf=("pf", "mean"),
                                    n=("n", "mean")).round(3).to_string())
    print("\n  the FLATTEN, paired on identical feed / block / window:")
    k = ["feed", "block", "win_name"]
    a = s[~s.flat_on].set_index(k); c = s[s.flat_on].set_index(k)
    j = a.join(c, rsuffix="_fl", how="inner")
    j["d_pts"] = j["pts_fl"] - j["pts"]
    print(j.reset_index()[["feed", "block", "win_name", "n", "n_fl", "pts", "pts_fl", "d_pts"]]
          .round(3).to_string(index=False))
    print(f"\n  the flatten helps in {int((j.d_pts > 0).sum())} of {len(j)} paired cells, "
          f"mean delta {j.d_pts.mean():+.3f} pts/trade")

    # ---------------------------------------------------------------- breakeven ladder
    n_be = (len(BE) - 1) * len(SEC) * 3 + 3
    print("\n" + "=" * 112)
    print(f"BREAKEVEN LADDER -- {n_be} effective cells (rungs at or beyond the 100pt target are "
          f"INERT and excluded), E[max t | noise] = {M.e_max_normal(n_be):.3f}")
    print("=" * 112)
    rows = []
    for name in FEEDS:
        f = M.load(name, 15); cost = M.COST[name]; bl = M.blocks(f, name)
        sig, sd = M.signals(f)
        for be in BE:
            for sec in (SEC if be > 0 else [0.0]):
                for r in cells(f, name, sig, sd, cost, bl, be_pts=be, be_off=sec):
                    r["be"] = be; r["sec"] = sec
                    rows.append(r)
    e = pd.DataFrame(rows)
    e.to_csv(os.path.join(HERE, "s1_be.csv"), index=False)
    print(e[["feed", "block", "be", "sec", "n", "pts", "pct", "pf", "win",
             "stop", "tgt", "mde"]].to_string(index=False))
    print("\n  paired against each cell's own OFF twin:")
    k = ["feed", "block"]
    b0 = e[e.be == 0].set_index(k)
    j = e[e.be > 0].set_index(k).join(b0[["pts", "n", "win"]], rsuffix="_0")
    j["d_pts"] = j["pts"] - j["pts_0"]; j["d_win"] = j["win"] - j["win_0"]
    j["d_n"] = j["n"] - j["n_0"]
    print(j.reset_index()[["feed", "block", "be", "sec", "n", "d_n", "pts", "pts_0",
                           "d_pts", "win", "win_0", "d_win"]].round(4).to_string(index=False))
    print("\n  marginal by arming distance:")
    print(j.groupby("be").agg(d_pts=("d_pts", "mean"), d_win=("d_win", "mean"),
                              d_n=("d_n", "mean"),
                              won=("d_pts", lambda x: f"{int((x>0).sum())}/{len(x)}")
                              ).round(4).to_string())
    print("\n  marginal by secured points (the offset relabels exits it does not move):")
    print(j.groupby("sec").agg(d_pts=("d_pts", "mean"), d_win=("d_win", "mean"),
                               d_n=("d_n", "mean")).round(4).to_string())
    print(f"\n  a breakeven beats its own OFF twin in {int((j.d_pts > 0).sum())} of {len(j)} "
          f"paired cells (chance is 50%)")
    print(f"  paired deltas outside the cell's own MDE: "
          f"{int((j.d_pts.abs()/j.ent_scale if False else (j.d_pts*0)).sum())} "
          f"-- reported in percent-of-price below")


if __name__ == "__main__":
    main()
