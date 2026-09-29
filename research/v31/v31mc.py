"""Monte Carlo over EVERY reproducible result on this branch, and the mean of them.

THE ASK: run a Monte Carlo on all the data results and see their mean. That is two different
Monte Carlos and this branch has already learned not to confuse them.

  BOOTSTRAP WITH REPLACEMENT answers the EDGE question -- how uncertain is the mean R per trade.
  It must resample whole DAYS WITH THEIR TRADES ATTACHED, because a breakout fires two or three
  times on the same move and 300 trades are ~120 days (`fast.score_block_bootstrap`).

  PERMUTATION answers the PATH question -- how deep a drawdown this edge can produce. Reordering
  the realised trades CANNOT CHANGE THE ENDPOINT, so no endpoint distribution is printed from it
  (an earlier version of this project reported a 5th-95th spread of 0.6R on +27R and it was
  meaningless). Realised drawdown is ONE draw from that distribution; `STUDY_V11_MARKET` found it
  TRIPLING out of sample, and V19 found the realised path had been LUCKY against an MC median.

WHAT IS IN THE POOL. Every configuration below is one this branch has already TESTED AND REPORTED
-- the shipped rule, the regime rungs around it, the geometry axes, the five additions that were
rejected (momentum, MA state, MA cross, linreg cross, linreg state), the entry windows and the
short mirror. Nothing here is searched. The point of a fixed declared pool is that the MEAN over it
is readable: it says what the average thing this branch has measured actually earns.

THREE WARNINGS THAT TRAVEL WITH THE MEAN, none of which the arithmetic can remove:

  1. THE POOL IS NOT A RANDOM SAMPLE OF STRATEGIES. It is the neighbourhood of one family that
     survived a long search, so its mean is biased UP relative to "a strategy you might have
     written". Read it as "what our own tested variants earn", never as an unconditional expectancy.

  2. THE LOCKED BLOCK IS POST-SELECTION FOR MOST ROWS. CHOP <= 40 and the 30m/15m choice were made
     with research in hand. A bootstrap prices sampling error inside a block; it does NOT price the
     selection that chose the block's row. The research -> locked DECAY column is the honest read.

  3. TRADES ARE SHARED ACROSS ROWS. The rungs of one ladder are the same trades filtered differently
     (V21 measured 68.3% of the bars CHOP keeps already passing ADX), so the pooled mean is not an
     average of independent experiments and its equal-weight bootstrap understates correlation. Both
     the equal-weight and the trade-weighted pooled figure are printed; they answer different
     questions and neither is a portfolio result.

COSTS. NQ carries the real MNQ stack (cost_mult 1.44 -- COMM 1.00 was broker-only). US30 has no
itemised model here, so its multiplier is set to put the round turn at ~2.50 points, the figure
`research/v30/run_opt.py` uses; that is a stated assumption, not a measurement.

Usage: python3 research/v31/v31mc.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v20")
sys.path.insert(0, "research/v21")
sys.path.insert(0, "research/v22")
sys.path.insert(0, "research/v27")
sys.path.insert(0, "research/v28")
import indicators as I        # noqa: E402
import v16core as C           # noqa: E402
import v20linreg as LR        # noqa: E402
import v21regime as RG        # noqa: E402
import v22vol as V22          # noqa: E402
import v28data as D28         # noqa: E402

US30_COST_MULT = 2.09         # -> ~2.50 points round turn, matching research/v30/run_opt.py
VOL_STATE = "pct_cc20_250"    # V22's realised-volatility percentile, read at the signal bar
BOOT = 4000
PERM = 4000
MIN_TRADES = 30


# ------------------------------------------------------------------------------------------------
# bars
# ------------------------------------------------------------------------------------------------
def load(market, tf):
    if market == "NQ":
        import fastbars
        b = fastbars.bars(tf)
        return dict(o=b["o"], h=b["h"], l=b["l"], c=b["c"], mod=b["mod"], sess=b["sess"],
                    ts=b["ts"])
    import v27run as R27
    d = pd.DataFrame(R27.load_us30())
    if tf == 15:
        return {k: d[k].to_numpy() for k in ("ts", "o", "h", "l", "c", "mod", "sess")}
    d["blk"] = np.arange(len(d)) // (tf // 15)
    g = d.groupby("blk")
    return dict(ts=g.ts.first().to_numpy(), o=g.o.first().to_numpy(), h=g.h.max().to_numpy(),
                l=g.l.min().to_numpy(), c=g.c.last().to_numpy(),
                mod=g["mod"].first().to_numpy(), sess=g.sess.first().to_numpy())


_PREP: dict = {}


def prep(market, tf, entry_n, exit_n):
    key = (market, tf, entry_n, exit_n)
    if key in _PREP:
        return _PREP[key]
    cm = 1.44 if market == "NQ" else US30_COST_MULT
    if market == "NQ":
        P = C.prep(tf, entry_n=entry_n, exit_n=exit_n, cost_mult=cm, atr_len=14)
    else:
        P = D28.prep_bars(load(market, tf), entry_n=entry_n, exit_n=exit_n, cost_mult=cm,
                          atr_len=14)
    P["feat"] = features(P)
    _PREP[key] = P
    return P


def features(P):
    h, l, c = P["h"], P["l"], P["c"]
    _pd, _md, adx = I.adx_di(h, l, c, 14)
    lrv9, lrs9, _r9 = LR.linreg(c, 9)
    lrv21, _s21, _r21 = LR.linreg(c, 21)
    lrv50, _s50, _r50 = LR.linreg(c, 50)
    up = np.isfinite(lrv9) & np.isfinite(lrv21) & (lrv9 > lrv21)
    crossed = up & ~np.r_[False, up[:-1]]
    e9, e21 = I.ema(c, 9), I.ema(c, 21)
    eup = np.isfinite(e9) & np.isfinite(e21) & (e9 > e21)
    ecross = eup & ~np.r_[False, eup[:-1]]
    return dict(
        adx=adx,
        chop=RG.chop(h, l, c, 14),
        rsi=I.rsi(c, 14),
        lr_state=up,
        lr_cross=pd.Series(crossed).rolling(5, min_periods=1).max().to_numpy() > 0,
        lr_close_gt=np.isfinite(lrv50) & (c > lrv50),
        lr_slope=np.isfinite(lrs9) & (lrs9 > 0),
        ema_state=eup,
        ema_cross=pd.Series(ecross).rolling(5, min_periods=1).max().to_numpy() > 0,
        volpct=V22.build(P["o"], h, l, c)[VOL_STATE],
    )


def blocks(sess, frac=0.65):
    u = np.unique(sess)
    return sess < u[int(len(u) * frac)], sess >= u[int(len(u) * frac)]


# ------------------------------------------------------------------------------------------------
# the declared pool -- every row is a result this branch has already reported
# ------------------------------------------------------------------------------------------------
def cfg(tag, family, market="NQ", tf=30, entry=30, exit=20, stop=2.0, tp=0.0, side=1,
        adx=None, chop=None, extra=None, win=None, adaptive=None):
    return dict(tag=tag, family=family, market=market, tf=tf, entry=entry, exit=exit, stop=stop,
                tp=tp, side=side, adx=adx, chop=chop, extra=extra, win=win, adaptive=adaptive)


CONFIGS = [
    # A. the shipped rule and the regime ladder around it (V21, V23, V24)
    cfg("30m base, no filter", "A regime"),
    cfg("30m CHOP<=50", "A regime", chop=50.0),
    cfg("30m CHOP<=45", "A regime", chop=45.0),
    cfg("30m CHOP<=40  << SHIPPED", "A regime", chop=40.0),
    cfg("30m CHOP<=35", "A regime", chop=35.0),
    cfg("30m ADX>=20", "A regime", adx=20.0),
    cfg("30m ADX>=25", "A regime", adx=25.0),
    cfg("30m ADX>=25 & CHOP<=35", "A regime", adx=25.0, chop=35.0),
    # B. the same on 15m
    cfg("15m base, no filter", "B 15m", tf=15),
    cfg("15m CHOP<=40", "B 15m", tf=15, chop=40.0),
    # C. geometry axes on the shipped base (V18, V21, V23 all read these)
    cfg("30m CHOP<=40, 1.5N stop", "C geometry", chop=40.0, stop=1.5),
    cfg("30m CHOP<=40, 2.5N stop", "C geometry", chop=40.0, stop=2.5),
    cfg("30m CHOP<=40, 3.0N stop", "C geometry", chop=40.0, stop=3.0),
    cfg("30m CHOP<=40, 2R target", "C geometry", chop=40.0, tp=2.0),
    cfg("30m CHOP<=40, exit ch 10", "C geometry", chop=40.0, exit=10),
    cfg("30m CHOP<=40, entry ch 55", "C geometry", chop=40.0, entry=55),
    # D. the five additions that were tested and rejected
    cfg("30m CHOP<=40 + RSI>=55", "D additions", chop=40.0, extra="rsi55"),
    cfg("30m CHOP<=40 + EMA 9/21 state", "D additions", chop=40.0, extra="ema_state"),
    cfg("30m CHOP<=40 + EMA 9/21 cross", "D additions", chop=40.0, extra="ema_cross"),
    cfg("30m CHOP<=40 + linreg 9/21 cross", "D additions", chop=40.0, extra="lr_cross"),
    cfg("30m CHOP<=40 + linreg close>val", "D additions", chop=40.0, extra="lr_close_gt"),
    # E. entry windows (V16, V20 -- entry gate only, no flatten)
    cfg("30m CHOP<=40, 09:30-11:00", "E windows", chop=40.0, win=(570, 660)),
    cfg("30m CHOP<=40, 07:00-11:00", "E windows", chop=40.0, win=(420, 660)),
    cfg("30m CHOP<=40, 08:00-12:00", "E windows", chop=40.0, win=(480, 720)),
    cfg("30m CHOP<=40, 13:00-16:00", "E windows", chop=40.0, win=(780, 960)),
    # F. the short mirror
    cfg("30m CHOP<=40 SHORT", "F side", chop=40.0, side=-1),
    cfg("30m base SHORT", "F side", side=-1),
    # G. V22's adaptive volatility stop -- the one thing that shipped as a sizing correction
    cfg("30m adaptive 2.5/1.5N", "G adaptive", adaptive=(2.5, 1.5)),
    cfg("15m adaptive 2.5/1.5N", "G adaptive", tf=15, adaptive=(2.5, 1.5)),
    cfg("30m adaptive INVERSE 1.5/2.5N", "G adaptive", adaptive=(1.5, 2.5)),
    # H. the second market, same rules, cost stated not measured
    cfg("US30 30m base", "H US30", market="US30"),
    cfg("US30 30m CHOP<=40", "H US30", market="US30", chop=40.0),
    cfg("US30 30m CHOP<=40 SHORT", "H US30", market="US30", chop=40.0, side=-1),
    cfg("US30 15m CHOP<=40", "H US30", market="US30", tf=15, chop=40.0),
]


def build(c):
    """Trade R and the session of each trade, for the research and locked blocks."""
    P = prep(c["market"], c["tf"], c["entry"], c["exit"])
    F = P["feat"]
    sig = C.signals(P, c["side"])
    if c["adaptive"] is not None:
        lo, hi = c["adaptive"]
        A = C.outcomes(P, c["side"], sig, stop_mult=lo, tp_r=c["tp"])
        B = C.outcomes(P, c["side"], sig, stop_mult=hi, tp_r=c["tp"])
        s = F["volpct"][sig]
        low = np.where(np.isfinite(s), s <= 0.5, False)
        O = dict(xb=np.where(low, A["xb"], B["xb"]), R=np.where(low, A["R"], B["R"]),
                 why=np.where(low, A["why"], B["why"]), sig=sig)
        keep = np.isfinite(s)
    else:
        O = C.outcomes(P, c["side"], sig, stop_mult=c["stop"], tp_r=c["tp"])
        keep = np.ones(len(sig), bool)
    keep &= O["xb"] >= 0
    if c["adx"] is not None:
        keep &= np.isfinite(F["adx"][sig]) & (F["adx"][sig] >= c["adx"])
    if c["chop"] is not None:
        keep &= np.isfinite(F["chop"][sig]) & (F["chop"][sig] <= c["chop"])
    if c["extra"] is not None:
        k = F["rsi"][sig] >= 55.0 if c["extra"] == "rsi55" else F[c["extra"]][sig]
        keep &= np.asarray(k, bool)
    if c["win"] is not None:
        a, b = c["win"]
        m = P["mod"][sig]
        keep &= (m >= a) & (m < b)
    res, lk = blocks(P["sess"])
    out = {}
    for name, blk in (("research", res), ("locked", lk)):
        idx = C.take(O, keep & blk[sig])
        out[name] = (O["R"][idx], P["sess"][O["sig"][idx]])
    return out


# ------------------------------------------------------------------------------------------------
# the two Monte Carlos
# ------------------------------------------------------------------------------------------------
def boot_days(R, days, draws=BOOT, seed=11):
    """Resample whole days WITH their trades attached; trade-weighted mean each draw."""
    rng = np.random.default_rng(seed)
    _u, inv = np.unique(days, return_inverse=True)
    nd = inv.max() + 1
    by = [np.flatnonzero(inv == j) for j in range(nd)]
    out = np.empty(draws)
    for k in range(draws):
        pick = np.concatenate([by[j] for j in rng.integers(0, nd, nd)])
        out[k] = R[pick].mean()
    return out


def max_dd(r):
    eq = np.cumsum(r)
    return float(np.max(np.maximum.accumulate(eq) - eq))


def perm_dd(R, draws=PERM, seed=13):
    """Reorder the REALISED trades. Answers drawdown ONLY -- the endpoint is invariant."""
    rng = np.random.default_rng(seed)
    r = np.asarray(R, float).copy()
    out = np.empty(draws)
    for k in range(draws):
        rng.shuffle(r)
        out[k] = max_dd(r)
    return out


def row(R, days):
    if len(R) < MIN_TRADES or not (R < 0).any():
        return None
    b = boot_days(R, days)
    p = perm_dd(R)
    dd = max_dd(R)
    return dict(n=len(R), days=len(np.unique(days)), R=float(R.mean()),
                pf=float(R[R > 0].sum() / abs(R[R < 0].sum())),
                b05=float(np.percentile(b, 5)), b50=float(np.percentile(b, 50)),
                b95=float(np.percentile(b, 95)), pneg=float((b <= 0).mean()),
                dd=dd, dd50=float(np.percentile(p, 50)), dd95=float(np.percentile(p, 95)),
                dd99=float(np.percentile(p, 99)), dd_pct=float((p <= dd).mean()))


def hdr(t):
    print("\n" + "=" * 132)
    print(t)
    print("=" * 132)


def main():
    rows = []
    for c in CONFIGS:
        try:
            d = build(c)
        except Exception as e:                                     # noqa: BLE001
            print(f"   !! {c['tag']}: {type(e).__name__} {e}")
            continue
        rows.append(dict(cfg=c, research=row(*d["research"]), locked=row(*d["locked"]),
                         trades=d))

    hdr("PART 1  BOOTSTRAP -- the EDGE question.  Resample whole DAYS with their trades attached, "
        f"{BOOT:,} draws.")
    print(f"   {'configuration':<34}{'RESEARCH':>44}{'|':>3}{'LOCKED':>44}")
    print(f"   {'':<34}{'n':>6}{'R/trade':>10}{'boot p05':>10}{'boot p95':>10}{'P(<=0)':>8}"
          f"{'|':>3}{'n':>6}{'R/trade':>10}{'boot p05':>10}{'boot p95':>10}{'P(<=0)':>8}")
    fam = None
    for r in rows:
        if r["cfg"]["family"] != fam:
            fam = r["cfg"]["family"]
            print(f"   -- {fam}")
        line = f"   {r['cfg']['tag']:<34}"
        for k in ("research", "locked"):
            s = r[k]
            if s is None:
                line += f"{'--':>6}{'':>38}" if k == "research" else f"{'--':>6}{'':>38}"
            else:
                line += (f"{s['n']:>6}{s['R']:>+10.4f}{s['b05']:>+10.4f}{s['b95']:>+10.4f}"
                         f"{s['pneg']:>8.3f}")
            if k == "research":
                line += f"{'|':>3}"
        print(line)

    hdr(f"PART 2  PERMUTATION -- the PATH question.  Reorder the realised trades, {PERM:,} draws. "
        "Max drawdown in R.  THE ENDPOINT IS INVARIANT AND IS NOT REPORTED.")
    print(f"   {'configuration':<34}{'block':>9}{'n':>6}{'realised DD':>13}{'MC p50':>9}"
          f"{'MC p95':>9}{'MC p99':>9}{'realised pctile':>17}")
    for r in rows:
        for k in ("research", "locked"):
            s = r[k]
            if s is None:
                continue
            print(f"   {r['cfg']['tag']:<34}{k:>9}{s['n']:>6}{s['dd']:>13.2f}{s['dd50']:>9.2f}"
                  f"{s['dd95']:>9.2f}{s['dd99']:>9.2f}{s['dd_pct']:>17.3f}")

    hdr("PART 3  THE MEAN OF ALL RESULTS.  Two weightings, because they answer different questions.")
    for k in ("research", "locked"):
        ok = [r for r in rows if r[k] is not None]
        per = np.array([r[k]["R"] for r in ok])
        rng = np.random.default_rng(5)
        cb = np.array([per[rng.integers(0, len(per), len(per))].mean() for _ in range(BOOT)])
        allR = np.concatenate([r["trades"][k][0] for r in ok])
        # days are namespaced per configuration so one calendar day in two rows resamples apart
        alld = np.concatenate([r["trades"][k][1].astype(np.int64) + i * 1_000_000_000
                               for i, r in enumerate(ok)])
        tb = boot_days(allR, alld, seed=17)
        print(f"\n   {k.upper()}   {len(ok)} scorable configurations, {len(allR):,} trades")
        print(f"      equal-weight over configurations   mean {per.mean():>+8.4f} R"
              f"   [{np.percentile(cb, 5):>+7.4f}, {np.percentile(cb, 95):>+7.4f}]"
              f"   P(mean <= 0) {float((cb <= 0).mean()):.3f}")
        print(f"      trade-weighted over the pooled set mean {allR.mean():>+8.4f} R"
              f"   [{np.percentile(tb, 5):>+7.4f}, {np.percentile(tb, 95):>+7.4f}]"
              f"   P(mean <= 0) {float((tb <= 0).mean()):.3f}")
        print(f"      share of configurations positive   {float((per > 0).mean()):.3f}"
              f"   ({int((per > 0).sum())} of {len(per)})")
        print(f"      median configuration               {np.median(per):>+8.4f} R"
              f"   best {per.max():>+7.4f}   worst {per.min():>+7.4f}")

    both = [r for r in rows if r["research"] is not None and r["locked"] is not None]
    dec = np.array([r["locked"]["R"] - r["research"]["R"] for r in both])
    rr = np.array([r["research"]["R"] for r in both])
    ll = np.array([r["locked"]["R"] for r in both])
    print(f"\n   DECAY, the only column selection cannot flatter ({len(both)} configurations on both "
          "blocks)")
    print(f"      mean research {rr.mean():>+8.4f} R  ->  mean locked {ll.mean():>+8.4f} R"
          f"   mean change {dec.mean():>+8.4f}")
    print(f"      configurations that got WORSE on locked   {int((dec < 0).sum())} of {len(dec)}"
          f"   ({float((dec < 0).mean()):.3f})")
    if len(rr) > 2:
        print(f"      research-to-locked R correlation (Pearson) {np.corrcoef(rr, ll)[0, 1]:>+7.3f}"
              f"   (Spearman {pd.Series(rr).corr(pd.Series(ll), method='spearman'):>+7.3f})")
    print(f"      configurations whose locked bootstrap excludes zero (P(<=0) < 0.05): "
          f"{sum(1 for r in both if r['locked']['pneg'] < 0.05)} of {len(both)}")

    hdr("PART 4  WHAT THE TWO MONTE CARLOS SAY WHEN THEY ARE READ TOGETHER.")

    print("\n   4a. THE REALISED PATH AGAINST ITS OWN REORDERINGS.  A percentile near 0 means the "
          "realised\n       equity curve was SMOOTHER than a random ordering of the same trades; "
          "near 1 means rougher.")
    for k in ("research", "locked"):
        pc = np.array([r[k]["dd_pct"] for r in rows if r[k] is not None])
        print(f"      {k:<9} n={len(pc):>3}   mean pctile {pc.mean():.3f}   median {np.median(pc):.3f}"
              f"   share > 0.50 {float((pc > 0.5).mean()):.3f}"
              f"   share > 0.95 {float((pc > 0.95).mean()):.3f}")
    print("      A drawdown at a high percentile is not evidence of a broken rule -- it is one draw. "
          "But the\n      SIZE to plan for is the MC p99, not the realised figure; V19 found the "
          "realised path had been LUCKY\n      against an MC median of 22.4R on a realised 15.5R, "
          "with p99 at 60.8R.")
    worst = sorted((r for r in rows if r["locked"] is not None),
                   key=lambda r: -r["locked"]["dd99"] / max(r["locked"]["dd"], 1e-9))[:3]
    for r in worst:
        s_ = r["locked"]
        print(f"      locked p99 / realised = {s_['dd99'] / s_['dd']:>4.2f}x   "
              f"{r['cfg']['tag']:<34} realised {s_['dd']:.1f}R -> plan for {s_['dd99']:.1f}R")

    print("\n   4b. THE ROWS THE BOOTSTRAP CALLED SIGNIFICANT ON RESEARCH, READ ONCE ON LOCKED.")
    sig_r = [r for r in both if r["research"]["pneg"] < 0.05]
    if not sig_r:
        print("      none")
    for r in sig_r:
        a, b = r["research"], r["locked"]
        print(f"      {r['cfg']['tag']:<34} research {a['R']:>+8.4f} P(<=0) {a['pneg']:.3f}"
              f"   ->   locked {b['R']:>+8.4f} P(<=0) {b['pneg']:.3f}"
              f"   {'HOLDS' if b['pneg'] < 0.05 else 'does not hold'}")
    held = sum(1 for r in sig_r if r["locked"]["pneg"] < 0.05)
    print(f"      {held} of {len(sig_r)} hold.  At alpha 0.05 on {len(both)} configurations, "
          f"{0.05 * len(both):.1f} research passes are expected by chance alone.")

    print("\n   4c. THE ROWS THE BOOTSTRAP CALLS SIGNIFICANT ON LOCKED, AND WHAT THEY DID ON "
          "RESEARCH.")
    sig_l = [r for r in both if r["locked"]["pneg"] < 0.05]
    if not sig_l:
        print("      none")
    for r in sig_l:
        a, b = r["research"], r["locked"]
        shape = "WRONG SHAPE -- better on locked than research" if b["R"] > a["R"] else "right shape"
        print(f"      {r['cfg']['tag']:<34} research {a['R']:>+8.4f} P(<=0) {a['pneg']:.3f}"
              f"   ->   locked {b['R']:>+8.4f} P(<=0) {b['pneg']:.3f}   {shape}")


if __name__ == "__main__":
    main()
