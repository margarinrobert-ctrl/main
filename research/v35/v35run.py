"""Part A -- is 09:30 special? The window swept across the whole session, each against its own
same-length random-start control.

READ THE SURFACE, NOT THE TOP CELL. 44 cells are scored (11 starts x 4 lengths) and the number is
stated before the results. What decides the answer is whether the mechanism has a SHAPE across the
day -- a coherent region -- or whether the best cell is just the maximum of 44 draws.
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v35")
import v35bal as B            # noqa: E402

STARTS = tuple(range(570, 871, 30))          # 09:30 ... 14:30, every 30 minutes
LENGTHS = (30, 60, 90, 120)
DRAWS = 150


def hdr(t):
    print("\n" + "=" * 128)
    print(t)
    print("=" * 128, flush=True)


def hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def control_dist(d, length, block, draws=DRAWS, seed=7):
    """Mean break-R (and extension, and up-rate) over `draws` random same-length windows."""
    rng = np.random.default_rng(seed)
    starts = np.arange(B.RTH_OPEN, B.RTH_CLOSE - length - B.MIN_TAIL + 1, B.TF)
    out = []
    for _ in range(draws):
        s = int(rng.choice(starts))
        T = B.window_table(d, s, length)
        if T is None:
            continue
        T = B.outcomes(d, T)
        T = T[T.sess.isin(block)]
        r = T.R.dropna()
        if len(r) < 50:
            continue
        out.append((float(r.mean()), float(T.ext.mean()), float((T.brk > 0).mean()),
                    float(T.back.mean())))
    a = np.array(out)
    return dict(R=a[:, 0], ext=a[:, 1], up=a[:, 2], back=a[:, 3], n=len(a))


def sweep(d, block_sess, tag):
    rows = []
    ctrl = {}
    for length in LENGTHS:
        ctrl[length] = control_dist(d, length, block_sess)
        for start in STARTS:
            if start + length + B.MIN_TAIL > B.RTH_CLOSE:
                continue
            T = B.window_table(d, start, length)
            if T is None:
                continue
            T = B.outcomes(d, T)
            T = T[T.sess.isin(block_sess)]
            r = T.R.dropna()
            if len(r) < 50:
                continue
            c = ctrl[length]
            rows.append(dict(
                start=start, length=length, n=len(r), R=float(r.mean()),
                pf=float(r[r > 0].sum() / abs(r[r < 0].sum())) if (r < 0).any() else np.nan,
                win=float((r > 0).mean()), ext=float(T.ext.mean()),
                up=float((T.brk > 0).mean()), back=float(T.back.mean()),
                rng_atr=float(T.f_rng_atr.mean()),
                ctrl_R=float(c["R"].mean()), ctrl_ext=float(c["ext"].mean()),
                excess=float(r.mean()) - float(c["R"].mean()),
                p_ctrl=float((c["R"] >= r.mean()).mean()),
                block=tag))
    return pd.DataFrame(rows)


def show(df, tag):
    hdr(f"WINDOW SWEEP -- {tag}.  {len(df)} cells scored of {len(STARTS) * len(LENGTHS)} declared. "
        f"Control = {DRAWS} random same-length windows per length.")
    print(f"   {'window':<16}{'len':>5}{'n':>6}{'R/trade':>10}{'PF':>7}{'win':>7}{'ext ATR':>9}"
          f"{'up%':>7}{'revert':>8}{'rng/ATR':>9}{'  ':>2}{'ctrl R':>9}{'excess':>9}{'p':>7}")
    for r in df.sort_values(["length", "start"]).itertuples():
        star = "  <<< the classic IB" if (r.start == 570 and r.length == 60) else ""
        print(f"   {hhmm(r.start)}-{hhmm(r.start + r.length):<10}{r.length:>5}{r.n:>6}"
              f"{r.R:>+10.4f}{r.pf:>7.3f}{r.win:>7.3f}{r.ext:>9.3f}{r.up:>7.3f}{r.back:>8.3f}"
              f"{r.rng_atr:>9.2f}{'  ':>2}{r.ctrl_R:>+9.4f}{r.excess:>+9.4f}{r.p_ctrl:>7.3f}{star}")
    print(f"\n   cells beating their control at p<=0.05: {int((df.p_ctrl <= 0.05).sum())} of "
          f"{len(df)}   (expected by chance {0.05 * len(df):.1f})")
    print(f"   share of cells with positive excess: {float((df.excess > 0).mean()):.3f}"
          f"   mean excess {df.excess.mean():+.4f}   median {df.excess.median():+.4f}")
    for L, g in df.groupby("length"):
        print(f"   length {L:>3}m  mean excess {g.excess.mean():>+8.4f}   best "
              f"{hhmm(int(g.loc[g.excess.idxmax()].start))} at {g.excess.max():+.4f}"
              f"   worst {hhmm(int(g.loc[g.excess.idxmin()].start))} at {g.excess.min():+.4f}")


if __name__ == "__main__":
    t0 = time.perf_counter()
    d = B.bars(B.TF)
    res, lok = B.blocks(d["sess"])
    res_sess = np.unique(d["sess"][res])
    lok_sess = np.unique(d["sess"][lok])
    hdr("V35 PART A  --  does the balance mechanism live at 09:30, or anywhere?")
    print(f"   NQ {B.TF}m, RTH {B.RTH_OPEN // 60:02d}:{B.RTH_OPEN % 60:02d}-"
          f"{B.RTH_CLOSE // 60:02d}:{B.RTH_CLOSE % 60:02d}, flat {B.FLAT // 60:02d}:"
          f"{B.FLAT % 60:02d}, break trade = next open after the first break, {B.STOP_MULT}N stop, "
          f"held to the flatten")
    print(f"   {len(STARTS)} starts x {len(LENGTHS)} lengths = {len(STARTS) * len(LENGTHS)} "
          f"declared cells.  research {len(res_sess)} sessions / locked {len(lok_sess)}")

    dr = sweep(d, res_sess, "research")
    dr.to_csv("research/v35/v35_sweep_research.csv", index=False)
    show(dr, "RESEARCH")

    hdr("THE 80% RULE, MEASURED")
    print(f"   reversion rate (price returns inside the range after breaking, before the flatten)")
    print(f"      across all {len(dr)} research cells: mean {dr.back.mean():.3f}  "
          f"min {dr.back.min():.3f}  max {dr.back.max():.3f}")
    print(f"      the classic IB: "
          f"{float(dr[(dr.start == 570) & (dr.length == 60)].back.iloc[0]):.3f}")
    print("   Essentially every break comes back inside the range before the close, at EVERY hour "
          "and\n   EVERY length. There is no window where a break 'holds' more often than "
          "elsewhere.")

    dl = sweep(d, lok_sess, "locked")
    dl.to_csv("research/v35/v35_sweep_locked.csv", index=False)
    show(dl, "LOCKED (read once, after research was fixed)")

    hdr("DOES THE SURFACE REPRODUCE?  research excess vs locked excess, cell by cell")
    j = dr.merge(dl, on=["start", "length"], suffixes=("_r", "_l"))
    print(f"   {len(j)} paired cells   Spearman "
          f"{j.excess_r.corr(j.excess_l, method='spearman'):+.3f}   Pearson "
          f"{j.excess_r.corr(j.excess_l):+.3f}   sign kept "
          f"{float(((j.excess_r > 0) == (j.excess_l > 0)).mean()):.3f}")
    top = j.nlargest(5, "excess_r")
    print("   top 5 research cells, read on locked:")
    for r in top.itertuples():
        print(f"      {hhmm(r.start)}+{r.length:>3}m   research excess {r.excess_r:+.4f} "
              f"(p {r.p_ctrl_r:.3f})  ->  locked {r.excess_l:+.4f} (p {r.p_ctrl_l:.3f})")
    print(f"\n   elapsed {time.perf_counter() - t0:.0f}s")
