"""Initial Balance features, built for M4's ACTUAL mechanism.

`m4_anatomy.py` establishes three things that decide how this module is built:

  * M4's barriers are near-inert -- widening the stop to infinity changes nothing -- so the trade
    is "long from here to the 16:00 flatten" and the thing worth predicting is the DAY.
  * M4's entry bar carries no information: on the same days, entering at a random first-hour bar
    does as well (p = 0.187 on win rate, 0.556 on net). So the entry time is free to move.
  * M4's window IS the Initial Balance, 09:30-10:30.

Put together: the natural feature set for M4 is the completed IB, and the natural entry is 10:30,
the first moment the IB is known. That is what this module builds.

CAUSALITY. On 30-minute bars the IB is exactly the mod=570 and mod=600 bars. Every feature is
computed from those two and nothing after; the signal bar is the mod=600 bar and the fill is the
next bar's open, the same convention as every other strategy here. Rolling normalisations are
shifted by one session so today is never in its own baseline.

SELECTION. Features are ranked on the RESEARCH block. Candidates are scored against a matched
control -- the same COUNT of days drawn at random, same 10:30 entry, same geometry, which prices
in drift, session timing and barrier width at once -- and that control is a GATE, not a final
check (CLAUDE.md). Benjamini-Hochberg across the family. The locked block is read once, last, and
never sorted on.

Usage: python3 research/ib_features.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
import indicators as I
from oner_union import _cut, _sim, bars

TF, SIDE, AM, FLAT = 30, 1, 4.0, 960
IB = (570, 630)


def day_table(tf=TF):
    """One row per session, from the IB bars only. Returns the table and the bar dict."""
    d = bars(tf)
    si, cut, _ = _cut(d)
    o, h, l, c, v, atr = d["o"], d["h"], d["l"], d["c"], d["v"], d["atr"]
    mod, sess = d["mod"], d["sess"]
    am20 = I.sma(atr, 20)
    rows = []
    for s in np.unique(sess):
        k = np.flatnonzero((sess == s) & (mod >= IB[0]) & (mod < IB[1]))
        if len(k) < 2:
            continue
        kk = k[-1]                       # IB complete at this bar's close
        if kk < 300 or kk + 1 >= len(c) - 1:
            continue
        ibh, ibl = h[k].max(), l[k].min()
        ibo, ibc = o[k[0]], c[kk]
        rng = max(ibh - ibl, 1e-9)
        rows.append(dict(
            sess=s, sig=kk, ib_range=rng, ib_body=abs(ibc - ibo) / rng,
            ib_dir=float(np.sign(ibc - ibo)), ib_close_pos=(ibc - ibl) / rng,
            ib_open_pos=(ibo - ibl) / rng, ib_range_atr=rng / max(atr[kk], 1e-9),
            ib_vol=v[k].sum(), ib_upwick=(ibh - max(ibo, ibc)) / rng,
            ib_dnwick=(min(ibo, ibc) - ibl) / rng,
            atr_ratio=atr[kk] / max(am20[kk], 1e-9),
            gap=(ibo - c[k[0] - 1]) / max(atr[kk], 1e-9)))
    T = pd.DataFrame(rows)
    for col in ("ib_range", "ib_vol"):                       # trailing, today excluded
        T[col + "_z"] = T[col] / T[col].shift(1).rolling(20).mean()
    T["prev_ib_range"] = T["ib_range"].shift(1)
    T = T.dropna().reset_index(drop=True)
    sig = T["sig"].to_numpy().astype(np.int64)
    pnl, eb, _x, _w, _g = _sim(d, sig, SIDE, AM, FLAT)
    assert len(pnl) == len(sig), f"{len(pnl)} trades from {len(sig)} signals -- overlap dropped some"
    T["pnl"] = pnl
    T["res"] = si[eb] < cut
    return T, d, si, cut


def _run(d, si, cut, sigs, m):
    """Filter the TRIGGERS and re-simulate. Never split realised trades (CLAUDE.md)."""
    t = sigs[m]
    if len(t) < 10:
        return None
    p, e, _x, _w, _g = _sim(d, t, SIDE, AM, FLAT)
    r = si[e] < cut
    return dict(nr=int(r.sum()), win_r=100 * float((p[r] > 0).mean()), net_r=float(p[r].sum()),
                per_r=float(p[r].mean()), nl=int((~r).sum()),
                win_l=100 * float((p[~r] > 0).mean()) if (~r).sum() else np.nan,
                net_l=float(p[~r].sum()), per_l=float(p[~r].mean()) if (~r).sum() else np.nan)


def control(d, si, cut, sigs, res, m, draws=2000, seed=5):
    nr = int((m & res).sum())
    if nr < 10:
        return None
    pool = np.flatnonzero(res)
    rng = np.random.default_rng(seed)
    sims = []
    for _ in range(draws):
        p, e, _x, _w, _g = _sim(d, np.sort(sigs[rng.choice(pool, size=nr, replace=False)]),
                                SIDE, AM, FLAT)
        rr = si[e] < cut
        if rr.sum() >= 5:
            sims.append((100 * (p[rr] > 0).mean(), p[rr].sum()))
    A = np.array(sims)
    r = _run(d, si, cut, sigs, m & res)
    return dict(c_win=float(A[:, 0].mean()), c_net=float(A[:, 1].mean()),
                p_win=float(((A[:, 0] >= r["win_r"]).sum() + 1) / (len(A) + 1)),
                p_net=float(((A[:, 1] >= r["net_r"]).sum() + 1) / (len(A) + 1)))


def run(fdr=0.10):
    T, d, si, cut = day_table()
    sigs = T["sig"].to_numpy().astype(np.int64)
    res = T["res"].to_numpy()
    print(f"IB day table: {len(T)} sessions ({res.sum()} research / {(~res).sum()} locked)")
    print(f"Baseline -- long at 10:30 EVERY day, {AM}xATR stop, flat 16:00:")
    for tag, m in (("research", res), ("locked", ~res)):
        p = T["pnl"].to_numpy()[m]
        print(f"    {tag:<10}{len(p):>4} trades{100*(p>0).mean():>7.1f}% win"
              f"{p.sum():>10,.0f}{p.mean():>9.1f}/trade")

    from scipy.stats import spearmanr
    R = T[T["res"]]
    feats = [c for c in T.columns if c not in ("sess", "sig", "pnl", "res")]
    print(f"\n{len(feats)} IB features, ranked on the RESEARCH block only:")
    print(f"    {'feature':<18}{'IC':>8}{'top-third $/t':>15}{'bot-third $/t':>15}{'spread':>9}")
    rank = []
    for f in feats:
        x, y = R[f].to_numpy(), R["pnl"].to_numpy()
        if np.std(x) == 0:
            continue
        q1, q2 = np.quantile(x, [1 / 3, 2 / 3])
        top, bot = y[x >= q2], y[x <= q1]
        rank.append((f, spearmanr(x, y).statistic, top.mean(), bot.mean(), top.mean() - bot.mean()))
    for f, ic, t, b, sp in sorted(rank, key=lambda r: -abs(r[4])):
        print(f"    {f:<18}{ic:>8.3f}{t:>15.1f}{b:>15.1f}{sp:>9.1f}")

    body = T["ib_body"].to_numpy(); cpos = T["ib_close_pos"].to_numpy()
    rat = T["ib_range_atr"].to_numpy(); dirn = T["ib_dir"].to_numpy()
    med = float(np.median(rat[res]))                      # threshold from RESEARCH only
    cand = {
        "A  ib_body<0.30 (M4's condition, day scale)": body < 0.30,
        "B  ib_close_pos>0.66": cpos > 0.66,
        "C  ib_dir up": dirn > 0,
        "D  ib_range_atr < research median": rat < med,
        "E  A and B": (body < 0.30) & (cpos > 0.66),
        "F  A and D": (body < 0.30) & (rat < med),
        "G  B and D": (cpos > 0.66) & (rat < med),
        "H  A and B and D": (body < 0.30) & (cpos > 0.66) & (rat < med),
    }
    print(f"\nMULTIPLICITY: {len(cand)} pre-declared candidates, thresholds fixed on research.")
    print(f"    {'candidate':<46}{'n_r':>5}{'win%':>7}{'ctrl':>7}{'p_win':>7}{'$/t':>8}{'p_net':>7}")
    rows = []
    for k, m in cand.items():
        r = _run(d, si, cut, sigs, m)
        ct = control(d, si, cut, sigs, res, m)
        if r is None or ct is None:
            continue
        rows.append((k, r, ct))
        print(f"    {k:<46}{r['nr']:>5}{r['win_r']:>7.1f}{ct['c_win']:>7.1f}{ct['p_win']:>7.3f}"
              f"{r['per_r']:>8.1f}{ct['p_net']:>7.3f}")

    ps = sorted((ct["p_net"], k) for k, _r, ct in rows)
    m_tot = len(ps)
    print(f"\n    Benjamini-Hochberg, FDR {fdr}, m={m_tot}:")
    passed = set()
    for i, (p, k) in enumerate(ps, 1):
        thr = fdr * i / m_tot
        if p <= thr:
            passed.add(k)
        print(f"      {k[:44]:<46}p={p:.3f}  thr {thr:.3f}  {'PASS' if p <= thr else 'fail'}")
    if not passed:
        print("      nothing survives on the research block.")

    print(f"\n    LOCKED BLOCK -- read once, after everything above was fixed:")
    print(f"    {'candidate':<46}{'n_l':>5}{'win%':>7}{'$/t':>8}{'net $':>10}{'research gate':>15}")
    for k, r, _ct in rows:
        print(f"    {k:<46}{r['nl']:>5}{r['win_l']:>7.1f}{r['per_l']:>8.1f}{r['net_l']:>10,.0f}"
              f"{('PASS' if k in passed else 'fail'):>15}")


if __name__ == "__main__":
    run()
