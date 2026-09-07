#!/usr/bin/env python3
"""Exhaustive intraday (flat-by-close) search for SAM-Best on 30m NAS100 data.

Converts the swing strategy into a day-trading candidate and searches ALL
combinations honestly:

  grid = entry slot x exit slot (46 half-hour session slots, x > e)
       x signal variant {graded strength, binary >=0.25/0.50/0.75,
                         ALWAYS-in (time-of-day control), graded momentum}
  ~6,200 configurations, all evaluated net of 2 bps/side (4 bps/round trip).

Discipline (VALIDATION.md §12): with N ~ 6,200 correlated trials on ~9 years,
the expected best in-sample Sharpe from PURE NOISE is ~1.2 — any full-sample
winner below/near that is presumed snooped. The decision evidence is therefore:
  1. the payoff decomposition (does the SAM edge even live intraday?),
  2. walk-forward of the SELECTION PROCESS (refit best config per fold),
  3. walk-forward of a few pre-specified structural candidates,
  4. signal-vs-ALWAYS paired test (separates SAM timing from time-of-day
     seasonality), and cost sensitivity.

Usage: python3 intraday_grid.py <csv> [RESULTS.md]
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "walkforward"))
from walkforward_sam import load_days, build_signals, sharpe, IS_LEN, OOS_LEN

ANN = 252
RT_COST = 2 * 0.0002          # entry + exit, 2 bps per side
MIN_COV = 0.85


def nw_t(x, lags=10):
    x = np.asarray(x, float)
    mu = x.mean()
    e = x - mu
    lrv = (e ** 2).mean()
    for l in range(1, lags + 1):
        lrv += 2 * (1 - l / (lags + 1)) * (e[l:] * e[:-l]).mean()
    return float(mu / np.sqrt(lrv / len(x)))


def stats(x):
    eq = np.cumprod(1 + x)
    yrs = len(x) / ANN
    dd = 1 - eq / np.maximum.accumulate(eq)
    return dict(sharpe=sharpe(x), cagr=eq[-1] ** (1 / yrs) - 1 if yrs > 0 else 0,
                maxdd=float(dd.max()))


def main(csv, out_md=None):
    # ---------- data ----------
    daily = load_days(csv)
    strength, _ = build_signals(daily)
    n0 = int(np.argmax(~np.isnan(strength)))

    df = pd.read_csv(csv, sep="\t")
    df["DateTime"] = pd.to_datetime(df["DateTime"], format="%Y.%m.%d %H:%M:%S")
    df = (df.dropna(subset=["DateTime", "Close"]).drop_duplicates(subset="DateTime")
            .sort_values("DateTime"))
    df["date"] = df["DateTime"].dt.date
    df["slot"] = df["DateTime"].dt.strftime("%H:%M")
    piv = df.pivot_table(index="date", columns="slot", values="Close", aggfunc="last")
    piv = piv.reindex(index=daily["date"].to_numpy())
    cov = piv.notna().mean()
    slots = [s for s in sorted(piv.columns) if cov[s] >= MIN_COV]
    M = piv[slots].to_numpy(float)[n0:]
    S = len(slots)
    val = ~np.isnan(M)
    st = strength[n0:]
    Dn = len(st)

    lines = [f"# Intraday (flat-by-close) search — SAM-Best on 30m NAS100", "",
             f"{Dn} decision days, {S} session slots ({slots[0]}–{slots[-1]} server time,"
             f" US cash ≈ 16:30–23:00), costs 2 bps/side (4 bps/round trip).", ""]

    # ---------- 1. payoff decomposition ----------
    px = daily["px"].to_numpy(float)[n0:]        # first-bar close (decision fill)
    lc = piv.ffill(axis=1).iloc[:, -1].to_numpy(float)[n0:]   # last session close
    intr = lc / px - 1.0                          # rest-of-day leg
    ovn = np.empty(Dn); ovn[:-1] = px[1:] / lc[:-1] - 1.0; ovn[-1] = 0.0
    lines += ["## Where does the SAM payoff live? (mean return per day, bps)", "",
              "| strength bucket | days | intraday leg (fill→session close) |"
              " overnight leg (close→next fill) |", "|---|---|---|---|"]
    for lab, m in [("0 (flat)", st == 0), ("(0, 1/3]", (st > 0) & (st <= 1/3)),
                   ("(1/3, 2/3]", (st > 1/3) & (st <= 2/3)), ("(2/3, 1]", st > 2/3)]:
        lines.append(f"| {lab} | {int(m.sum())} | {intr[m].mean()*1e4:+.1f} "
                     f"(t={nw_t(intr[m]):.1f}) | {ovn[m].mean()*1e4:+.1f} "
                     f"(t={nw_t(ovn[m]):.1f}) |")
    lines.append("")

    # ---------- 2. full grid ----------
    variants = {"GRAD": st.copy(),
                "BIN25": (st >= 0.25).astype(float),
                "BIN50": (st >= 0.50).astype(float),
                "BIN75": (st >= 0.75).astype(float),
                "ALWAYS": np.ones(Dn),
                "MOM": 1.0 - st}
    cfgs, blocks = [], []
    for vn, fr in variants.items():
        for e in range(S - 1):
            w = M[:, e + 1:] / M[:, [e]] - 1.0
            ok = val[:, [e]] & val[:, e + 1:]
            w = np.where(ok, w, 0.0)
            traded = ok & (fr[:, None] > 0)
            blk = fr[:, None] * w - RT_COST * fr[:, None] * traded
            blocks.append(blk.astype(np.float32))
            cfgs += [(vn, e, x) for x in range(e + 1, S)]
    R = np.concatenate(blocks, axis=1)
    del blocks
    mu, sd = R.mean(0), R.std(0)
    sr_full = np.where(sd > 0, mu / sd * np.sqrt(ANN), -9.9)

    lines += [f"## Full-sample grid ({len(cfgs)} configs) — read with deflation!", "",
              "Expected best IS Sharpe from pure noise at N≈6,200 trials over"
              " 8.9y ≈ **1.24** (E[max Z]≈3.7 / √years). Any winner below that"
              " is presumed selection noise until it survives the walk-forward.", "",
              "| rank | config (variant, entry→exit) | full-sample net Sharpe |",
              "|---|---|---|"]
    order = np.argsort(-sr_full)
    for r in range(10):
        vn, e, x = cfgs[order[r]]
        lines.append(f"| {r+1} | {vn} {slots[e]}→{slots[x]} | {sr_full[order[r]]:.2f} |")
    for vn in variants:
        idx = [i for i, c in enumerate(cfgs) if c[0] == vn]
        best = max(idx, key=lambda i: sr_full[i])
        lines.append(f"| best {vn} | {slots[cfgs[best][1]]}→{slots[cfgs[best][2]]} "
                     f"| {sr_full[best]:.2f} |")
    lines.append("")

    # ---------- 3. walk-forward of the selection process ----------
    def wf(universe_idx, label):
        folds, oos = [], []
        start = 0
        while start + IS_LEN + OOS_LEN <= Dn:
            lo, hi = start, start + IS_LEN
            m = R[lo:hi].mean(0)[universe_idx]
            s = R[lo:hi].std(0)[universe_idx]
            srs = np.where(s > 0, m / s * np.sqrt(ANN), -9.9)
            pick = universe_idx[int(np.argmax(srs))]
            o = R[hi:hi + OOS_LEN, pick].astype(float)
            folds.append((cfgs[pick], float(srs.max()), sharpe(o)))
            oos.append(o)
            start += OOS_LEN
        stitched = np.concatenate(oos)
        wfe = sharpe(stitched) / np.mean([f[1] for f in folds])
        pos = np.mean([f[2] > 0 for f in folds])
        return folds, stitched, wfe, pos

    all_idx = np.arange(len(cfgs))
    sig_idx = np.array([i for i, c in enumerate(cfgs) if c[0] != "ALWAYS" and c[0] != "MOM"])
    lines += ["## Walk-forward of the selection process (rolling IS=756d, OOS=126d)", "",
              "| universe | stitched OOS Sharpe | OOS CAGR | OOS maxDD | WFE | folds>0 |",
              "|---|---|---|---|---|---|"]
    fold_detail = {}
    for label, uni in [("all 6,210 configs", all_idx),
                       ("signal configs only (no ALWAYS/MOM)", sig_idx)]:
        folds, stitched, wfe, pos = wf(uni, label)
        s = stats(stitched)
        fold_detail[label] = folds
        lines.append(f"| refit best of {label} | {s['sharpe']:.2f} | {s['cagr']:.1%} | "
                     f"-{s['maxdd']:.1%} | {wfe:.2f} | {pos:.0%} |")

    # ---------- 4. pre-specified structural candidates ----------
    def cfg_index(vn, es, xs):
        return cfgs.index((vn, slots.index(es), slots.index(xs)))
    cand = {
        "C1 GRAD US session 16:30→23:00": cfg_index("GRAD", "16:30", "23:00"),
        "C2 GRAD full session 01:00→23:30": cfg_index("GRAD", slots[0], slots[-1]),
        "C3 BIN50 US session 16:30→23:00": cfg_index("BIN50", "16:30", "23:00"),
        "B0 ALWAYS US session (control)": cfg_index("ALWAYS", "16:30", "23:00"),
        "B1 ALWAYS full session (control)": cfg_index("ALWAYS", slots[0], slots[-1]),
    }
    oos_lo = IS_LEN  # evaluate candidates on the same OOS union as the WF
    oos_hi = ((Dn - IS_LEN) // OOS_LEN) * OOS_LEN + IS_LEN
    lines += ["", "## Pre-specified candidates (nothing fitted) on the identical"
              " walk-forward OOS days", "",
              "| candidate | full-sample Sharpe | OOS-days Sharpe | OOS CAGR | OOS maxDD |",
              "|---|---|---|---|---|"]
    for nm, i in cand.items():
        o = R[oos_lo:oos_hi, i].astype(float)
        s = stats(o)
        lines.append(f"| {nm} | {sr_full[i]:.2f} | {s['sharpe']:.2f} | {s['cagr']:.1%} |"
                     f" -{s['maxdd']:.1%} |")

    # ---------- 5. signal vs time-of-day control (paired, NW) ----------
    lines += ["", "## Does the SAM signal add anything intraday? (paired vs ALWAYS,"
              " same window, exposure-matched, Newey-West t)", ""]
    for nm, i, bi in [("C1 vs B0 (US session)", cand["C1 GRAD US session 16:30→23:00"],
                       cand["B0 ALWAYS US session (control)"]),
                      ("C2 vs B1 (full session)", cand["C2 GRAD full session 01:00→23:30"],
                       cand["B1 ALWAYS full session (control)"])]:
        fr = variants["GRAD"]
        xbar = fr.mean()
        spread = R[:, i].astype(float) - xbar * R[:, bi].astype(float)
        lines.append(f"- {nm}: spread {spread.mean()*ANN:+.2%}/yr, NW t = **{nw_t(spread):.2f}**")

    # ---------- 6. cost sensitivity of the best defensible candidate ----------
    lines += ["", "## Cost sensitivity (per-side commission multiples)", "",
              "| candidate | 1x (2bps) | 2x | 3x |", "|---|---|---|---|"]
    for nm in ["C1 GRAD US session 16:30→23:00", "C2 GRAD full session 01:00→23:30"]:
        vn, e, x = cfgs[cand[nm]]
        fr = variants[vn]
        w = M[:, x] / M[:, e] - 1.0
        ok = val[:, e] & val[:, x]
        w = np.where(ok, w, 0.0)
        traded = ok & (fr > 0)
        row = []
        for mult in (1, 2, 3):
            ret = fr * w - mult * RT_COST * fr * traded
            row.append(f"{sharpe(ret):.2f}")
        lines.append(f"| {nm} | {row[0]} | {row[1]} | {row[2]} |")

    # ---------- 7. per-fold picks of the process WF ----------
    lines += ["", "## Per-fold picks — refit best of ALL configs", "",
              "| fold | pick | IS SR | OOS SR |", "|---|---|---|---|"]
    for k, ((c, is_sr, oos_sr)) in enumerate(fold_detail["all 6,210 configs"]):
        vn, e, x = c
        lines.append(f"| {k+1} | {vn} {slots[e]}→{slots[x]} | {is_sr:.2f} | {oos_sr:.2f} |")
    lines.append("")

    # save Sharpe surface for plotting
    np.savez(os.path.join(os.path.dirname(os.path.abspath(__file__)), "grid.npz"),
             sr_full=sr_full, cfgs=np.array([(c[0], c[1], c[2]) for c in cfgs], dtype=object),
             slots=np.array(slots))

    md = "\n".join(lines)
    print(md)
    if out_md:
        with open(out_md, "w") as f:
            f.write(md + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
