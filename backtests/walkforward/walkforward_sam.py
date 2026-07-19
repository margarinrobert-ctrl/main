#!/usr/bin/env python3
"""Walk-forward test of SAM-Best (SemivarianceContrarianV2.pine) on 30m NAS100 data.

Independent re-implementation of the Pine v6 strategy logic (VALIDATION.md §17:
second-researcher replication) plus the walk-forward program of VALIDATION.md §1:

  A. "Refit best single W"  - each fold, pick W in 1..30 by in-sample Sharpe,
     trade it binary out-of-sample (the selection process the study reported
     collapsing to OOS Sharpe 0.19 / WFE 0.16).
  B. "Fixed plateau ensemble W 2..30" - nothing fitted; evaluated on the same
     stitched OOS windows (the deployed configuration).
  C. "Meta-selection" - each fold picks the IS-best among {30 binary Ws,
     ensemble} (VALIDATION.md §1.11: walking the meta-choice forward).

Both rolling (IS=756d fixed) and anchored (expanding IS, min 756d) variants,
OOS=126d, matching the study. Also produces:
  - full-sample replication check vs the study's claimed headline stats,
  - paired alpha vs exposure-matched buy & hold, Newey-West t (Gap 3),
  - net-of-financing variants at 6.5%/yr on held notional (Gap 4),
  - +1-bar execution-delay check (§7.3.3).

Data: tab-separated 30m OHLC with 'DateTime' like '2016.11.15 06:30:00'
(MT-export style). Usage:  python3 walkforward_sam.py <csv> [out.md]

Faithfulness notes vs the Pine script (v1 defaults):
  - day boundary = calendar date of the bar timestamp (Pine: time("D"));
  - first bar of a day contributes log(C/O) so the overnight gap never
    enters RS+/RS-; later bars contribute log(C_t/C_{t-1});
  - days with < 20 bars are dropped from signal history but still traded;
  - decision on day d uses completed days <= d-1; fills at the close of
    day d's first 30m bar (process_orders_on_close on the first bar);
  - rebalance skipped when |target - held| < 10% of full size (fraction
    approximation of the qty-vs-equity test; equity drift is second order);
  - commission 2 bps per side of traded notional; long only, 1x cap.
"""
import sys
import numpy as np
import pandas as pd

W_MIN, W_MAX = 2, 30
HIST_CAP = 30
MIN_BARS = 20
REBAL = 0.10
COST_SIDE = 0.0002          # 2 bps per side
FIN_RATE = 0.065            # financing p.a. for the net variant
IS_LEN, OOS_LEN = 756, 126
ANN = 252


def load_days(path):
    df = pd.read_csv(path, sep="\t")
    df["DateTime"] = pd.to_datetime(df["DateTime"], format="%Y.%m.%d %H:%M:%S")
    df = (df.dropna(subset=["DateTime", "Open", "Close"])
            .drop_duplicates(subset="DateTime")
            .sort_values("DateTime").reset_index(drop=True))
    df["date"] = df["DateTime"].dt.date
    recs = []
    for date, g in df.groupby("date", sort=True):
        o = g["Open"].to_numpy(float)
        c = g["Close"].to_numpy(float)
        r = np.empty(len(g))
        r[0] = np.log(c[0] / o[0])            # gap-excluded first bar
        if len(g) > 1:
            r[1:] = np.log(c[1:] / c[:-1])
        recs.append((date,
                     float((r[r > 0] ** 2).sum()),
                     float((r[r < 0] ** 2).sum()),
                     c[0],                     # fill px: close of 1st 30m bar
                     c[1] if len(c) > 1 else c[0],   # +1-bar-delay fill px
                     len(g)))
    d = pd.DataFrame(recs, columns=["date", "rsp", "rsn", "px", "px2", "nbars"])
    d["valid"] = d["nbars"] >= MIN_BARS
    return d


def build_signals(d):
    """strength (ensemble vote share) and per-W SAM<0 flags for day-d decisions,
    using only days <= d-1, replicating the Pine update order."""
    n = len(d)
    strength = np.full(n, np.nan)
    samneg = np.zeros((n, W_MAX + 1), dtype=bool)   # col W = 1..30
    hp, hn = [], []
    rsp, rsn, valid = d["rsp"].to_numpy(), d["rsn"].to_numpy(), d["valid"].to_numpy()
    for i in range(n):
        if i > 0 and valid[i - 1]:                  # finalize yesterday
            hp.append(rsp[i - 1]); hn.append(rsn[i - 1])
            if len(hp) > HIST_CAP:
                hp.pop(0); hn.pop(0)
        if len(hp) == HIST_CAP:
            cp = np.cumsum(hp[::-1]); cn = np.cumsum(hn[::-1])
            sam = cp - cn                            # sam[w-1] = SAM_W
            samneg[i, 1:] = sam[:W_MAX] < 0
            strength[i] = samneg[i, W_MIN:W_MAX + 1].mean()
    return strength, samneg


def run(target, d, fin_rate=0.0, px_col="px"):
    """Daily strategy returns for a target-fraction series (nan = warmup)."""
    n = len(d)
    px = d[px_col].to_numpy(float)
    held, fr = 0.0, np.zeros(n)
    for i in range(n):
        t = target[i]
        if not np.isnan(t):
            if t < 0.001 and held > 0:
                held = 0.0
            elif abs(t - held) >= REBAL:
                held = t
        fr[i] = held
    pxret = np.zeros(n)
    pxret[:-1] = px[1:] / px[:-1] - 1.0
    turn = np.abs(np.diff(np.concatenate([[0.0], fr])))
    nights = np.ones(n)
    dd = pd.to_datetime(d["date"]).diff().dt.days.shift(-1).fillna(1).to_numpy()
    nights = np.clip(dd, 1, 5)
    strat = fr * pxret - turn * COST_SIDE - fr * fin_rate * nights / 360.0
    return strat, fr


def sharpe(x):
    s = np.nanstd(x)
    return 0.0 if s == 0 else float(np.nanmean(x) / s * np.sqrt(ANN))


def stats(x, label=""):
    eq = np.cumprod(1 + x)
    yrs = len(x) / ANN
    cagr = eq[-1] ** (1 / yrs) - 1 if yrs > 0 else 0.0
    dd = 1 - eq / np.maximum.accumulate(eq)
    t = np.mean(x) / (np.std(x) / np.sqrt(len(x))) if np.std(x) > 0 else 0.0
    return dict(label=label, sharpe=sharpe(x), cagr=cagr, maxdd=dd.max(),
                tstat=t, days=len(x))


def nw_t(x, lags=10):
    """Newey-West t-stat for mean(x) > 0."""
    x = np.asarray(x, float)
    T = len(x)
    mu = x.mean()
    e = x - mu
    lrv = (e ** 2).mean()
    for l in range(1, lags + 1):
        lrv += 2 * (1 - l / (lags + 1)) * (e[l:] * e[:-l]).mean()
    return float(mu / np.sqrt(lrv / T))


def walk_forward(cands, names, n0, n, anchored=False):
    """cands: dict name -> daily return series (already net of costs).
    Returns per-fold picks + stitched OOS return series + WFE."""
    folds, oos = [], []
    start = n0
    while start + IS_LEN + OOS_LEN <= n:
        is_lo = n0 if anchored else start
        is_hi = start + IS_LEN if not anchored else start + IS_LEN
        # anchored: IS = [n0, start+IS_LEN); rolling: [start, start+IS_LEN)
        lo = n0 if anchored else start
        hi = start + IS_LEN
        is_sr = {k: sharpe(v[lo:hi]) for k, v in cands.items()}
        best = max(is_sr, key=is_sr.get)
        o = cands[best][hi:hi + OOS_LEN]
        folds.append(dict(fold=len(folds) + 1, pick=best, is_sharpe=is_sr[best],
                          oos_sharpe=sharpe(o), oos_ret=float(np.prod(1 + o) - 1)))
        oos.append(o)
        start += OOS_LEN
    stitched = np.concatenate(oos)
    wfe = sharpe(stitched) / np.mean([f["is_sharpe"] for f in folds])
    return folds, stitched, wfe


def main(csv, out_md):
    d = load_days(csv)
    strength, samneg = build_signals(d)
    n = len(d)
    n0 = int(np.argmax(~np.isnan(strength)))         # first tradable day
    print(f"days={n} tradable from index {n0} ({d['date'][n0]}) "
          f"valid_days={int(d['valid'].sum())} "
          f"span={d['date'].iloc[0]}..{d['date'].iloc[-1]}")

    # ---- candidate daily return series (gross of financing, net of 2bps) ----
    rets, frs = {}, {}
    for W in range(1, W_MAX + 1):
        tgt = np.where(np.isnan(strength), np.nan, samneg[:, W].astype(float))
        rets[f"W{W}"], frs[f"W{W}"] = run(tgt, d)
    rets["ENS"], frs["ENS"] = run(strength, d)

    bh = np.zeros(n)
    bh[:-1] = d["px"].to_numpy()[1:] / d["px"].to_numpy()[:-1] - 1.0

    sl = slice(n0, n - 1)                            # drop last (no next px)
    ens, bhs = rets["ENS"][sl], bh[sl]
    exp_bar = float(np.mean(frs["ENS"][sl]))

    lines = ["# Walk-forward results — SAM-Best v2 on user 30m NAS100 data", ""]
    lines += [f"Data: `{csv.split('/')[-1]}` — {n} sessions "
              f"({d['date'].iloc[0]} → {d['date'].iloc[-1]}), "
              f"{int(d['valid'].sum())} valid (≥{MIN_BARS} bars), "
              f"decisions from {d['date'][n0]}.", ""]

    # ---- replication check ----
    rep = [stats(ens, "Ensemble W2-30 (2bps, gross of financing)"),
           stats(rets["W8"][sl], "Single W=8 (2bps)"),
           stats(bhs, "Buy & hold"),
           stats(run(strength, d, fin_rate=FIN_RATE)[0][sl],
                 f"Ensemble net of {FIN_RATE:.1%} financing"),
           stats(run(strength, d, px_col="px2")[0][sl],
                 "Ensemble, +1-bar delayed fills")]
    lines += ["## Full-sample replication check (study claims: ens Sharpe 0.83,"
              " CAGR 15.1%, maxDD -24.9%, t 2.51, exposure 0.58x; W8 1.02;"
              " B&H 0.73)", "",
              "| Series | Sharpe | CAGR | maxDD | t | days |", "|---|---|---|---|---|---|"]
    for s in rep:
        lines.append(f"| {s['label']} | {s['sharpe']:.2f} | {s['cagr']:.1%} | "
                     f"-{s['maxdd']:.1%} | {s['tstat']:.2f} | {s['days']} |")
    lines += ["", f"Average ensemble exposure: **{exp_bar:.2f}x**", ""]

    # ---- paired alpha (Gap 3) ----
    spread = ens - exp_bar * bhs
    spread_net = run(strength, d, fin_rate=FIN_RATE)[0][sl] - exp_bar * bhs
    lines += ["## Paired alpha vs exposure-matched buy & hold (VALIDATION.md Gap 3)", "",
              f"- gross spread: mean {np.mean(spread)*ANN:.2%}/yr, NW t = **{nw_t(spread):.2f}**",
              f"- net-of-financing spread: mean {np.mean(spread_net)*ANN:.2%}/yr, "
              f"NW t = **{nw_t(spread_net):.2f}**", ""]

    # ---- walk-forward ----
    single = {k: v for k, v in rets.items() if k != "ENS"}
    for anchored in (False, True):
        tag = "Anchored (expanding IS)" if anchored else "Rolling (IS=756d)"
        fA, sA, wA = walk_forward(single, None, n0, n - 1, anchored)
        fC, sC, wC = walk_forward(rets, None, n0, n - 1, anchored)
        # fixed ensemble on identical stitched OOS days
        oos_idx = []
        start = n0
        while start + IS_LEN + OOS_LEN <= n - 1:
            oos_idx.append((start + IS_LEN, start + IS_LEN + OOS_LEN))
            start += OOS_LEN
        sB = np.concatenate([rets["ENS"][a:b] for a, b in oos_idx])
        bhB = np.concatenate([bh[a:b] for a, b in oos_idx])
        is_ens = np.mean([sharpe(rets["ENS"][(n0 if anchored else a - IS_LEN):a])
                          for a, b in oos_idx])
        wB = sharpe(sB) / is_ens
        posA = np.mean([f["oos_sharpe"] > 0 for f in fA])
        posC = np.mean([f["oos_sharpe"] > 0 for f in fC])
        picksA = [f["pick"] for f in fA]
        picksC = [f["pick"] for f in fC]
        lines += [f"## Walk-forward — {tag}, OOS=126d, {len(fA)} folds", "",
                  "| Process | stitched OOS Sharpe | OOS CAGR | OOS maxDD | WFE | folds>0 |",
                  "|---|---|---|---|---|---|"]
        for nm, s, w, pos in (("A: refit best single W", sA, wA, posA),
                              ("B: fixed ensemble W2-30", sB, wB,
                               np.mean([sharpe(rets['ENS'][a:b]) > 0 for a, b in oos_idx])),
                              ("C: meta-select {W's, ENS}", sC, wC, posC)):
            st = stats(s)
            lines.append(f"| {nm} | {st['sharpe']:.2f} | {st['cagr']:.1%} | "
                         f"-{st['maxdd']:.1%} | {w:.2f} | {pos:.0%} |")
        stb = stats(bhB)
        lines.append(f"| (benchmark) B&H on same OOS days | {stb['sharpe']:.2f} | "
                     f"{stb['cagr']:.1%} | -{stb['maxdd']:.1%} | — | — |")
        lines += ["", f"Process A picks per fold: {', '.join(picksA)}",
                  f"Process C picks per fold: {', '.join(picksC)}", ""]

    # ---- per-fold table for the rolling run (primary) ----
    fA, _, _ = walk_forward(single, None, n0, n - 1, False)
    fC, _, _ = walk_forward(rets, None, n0, n - 1, False)
    oos_idx = []
    start = n0
    while start + IS_LEN + OOS_LEN <= n - 1:
        oos_idx.append((start + IS_LEN, start + IS_LEN + OOS_LEN))
        start += OOS_LEN
    lines += ["## Per-fold detail (rolling)", "",
              "| fold | OOS start | A pick | A IS SR | A OOS SR | B (ENS) OOS SR | C pick | C OOS SR |",
              "|---|---|---|---|---|---|---|---|"]
    for i, ((a, b), fa, fc) in enumerate(zip(oos_idx, fA, fC)):
        ens_sr = sharpe(rets["ENS"][a:b])
        lines.append(f"| {i+1} | {d['date'][a]} | {fa['pick']} | {fa['is_sharpe']:.2f} | "
                     f"{fa['oos_sharpe']:.2f} | {ens_sr:.2f} | {fc['pick']} | {fc['oos_sharpe']:.2f} |")
    lines.append("")

    md = "\n".join(lines)
    print(md)
    if out_md:
        with open(out_md, "w") as f:
            f.write(md + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
