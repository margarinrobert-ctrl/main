"""CROSS-INSTRUMENT / REGIME agent.

Owns EXTERNAL VALIDITY. The question is not "does the Donchian breakout make
money" (known: it does not, exp -2.6 to -4.0, excess ~0). The question is
whether the flat result is a REGIME ARTEFACT, whether it is instrument-specific,
and whether direction is doing any work.

Every number below is computed on the RESEARCH block only, EXCEPT part E, which
is the independent broker feed US30RTF (2024-08 -> 2026-08). That file is
calendar-disjoint from both research blocks and overlaps the LOCKED period. It
is used ONLY as an engine/feed sanity check and NOTHING is selected on it.

Scoring: matched control everywhere (same side mix, same ATR geometry, same
minute-of-day histogram, and - crucially here - drawn from the SAME REGIME POOL,
so a regime slice is scored against random entries inside that same regime).
"""
import sys, numpy as np, pandas as pd
import lab

pd.set_option("display.width", 200)

BASE = dict(stop_mult=1.5, targ_mult=2.0, max_hold=16, flat_tod=660,
            one_per_session=True)
WIN = (420, 660)
NDRAW = 400

# a global counter so the multiplicity is honest
NCFG = 0


def gate(sym, idx, side, mask=None, label="", n_draws=NDRAW, **kw):
    global NCFG
    NCFG += 1
    k = dict(BASE); k.update(kw)
    g, tr = lab.sig_gate(sym, idx, side, mask=mask, label=label,
                         n_draws=n_draws, **k)
    return g, tr


def sigs(df, n_entry=20, side_only=0, **kw):
    idx, side, a = lab.signals(df, n_entry=n_entry, win=WIN, **kw)
    if side_only:
        m = side == side_only
        idx, side = idx[m], side[m]
    return idx, side


# --------------------------------------------------------------- daily state
def daily_frame(df):
    """One row per SESSION (NY calendar day), OHLC of that day's 15m bars."""
    g = df.groupby("sess")
    d = pd.DataFrame({
        "date": g.date.first(), "open": g.open.first(), "high": g.high.max(),
        "low": g.low.min(), "close": g.close.last(), "n": g.size()})
    return d.sort_index()


def causal_daily(df, ema_fast=20, ema_slow=50, atr_n=14):
    """Per-session state built ONLY from strictly-earlier sessions.

    Everything is shift(1)-ed, so the state a 07:00 bar sees is the state as of
    the previous NY day's final close. No part of the current session leaks in.
    """
    d = daily_frame(df)
    c = d.close.values
    ef = lab.ema(c, ema_fast)
    es = lab.ema(c, ema_slow)
    tr = lab.true_range(d.high.values, d.low.values, c)
    da = lab.ema(tr, atr_n)
    out = pd.DataFrame(index=d.index)
    out["rel"] = np.r_[np.nan, (ef[:-1] - es[:-1]) / es[:-1]]          # shift(1)
    out["atrp"] = np.r_[np.nan, da[:-1] / c[:-1]]                      # shift(1)
    out["ret20"] = np.r_[[np.nan] * 21, (c[20:-1] / c[:-21] - 1.0)]    # shift(1)
    out["date"] = d.date.values
    out["year"] = pd.to_datetime(d.date.values).year
    # warm-up: first ema_slow sessions have an unreliable state
    out.loc[out.index < ema_slow, ["rel", "atrp"]] = np.nan
    return out


def trend_label(rel, band):
    lab_ = np.full(len(rel), "na", dtype=object)
    lab_[rel > band] = "up"
    lab_[rel < -band] = "down"
    lab_[(rel >= -band) & (rel <= band)] = "flat"
    lab_[np.isnan(rel)] = "na"
    return lab_


def sess_mask(df, sessions):
    return np.isin(df.sess.values, np.asarray(sessions))


def hdr(t):
    print(f"\n{'='*104}\n{t}\n{'='*104}")


# ================================================================== PART A
def part_A(sym="NAS"):
    hdr(f"A. REGIME CENSUS of the {sym} RESEARCH BLOCK (research sessions only)")
    df, w, r = lab.research(sym)
    st = causal_daily(df)
    rs = np.unique(df.sess.values[r])                 # research sessions
    s = st.loc[st.index.isin(rs)].copy()
    print(f"  research sessions: {len(s):,}   "
          f"{s.date.min().date()} -> {s.date.max().date()}")

    # -- trend state, three bands so the split is not a single arbitrary point
    print("\n  causal daily trend  (ema20 vs ema50 of daily close, both shifted 1 session)")
    print(f"  {'band':>8} {'up':>16} {'flat':>16} {'down':>16} {'warmup/na':>12}")
    for band in (0.0, 0.005, 0.01, 0.02):
        L = trend_label(s.rel.values, band)
        v = pd.Series(L).value_counts()
        tot = len(s)
        row = " ".join(f"{v.get(k,0):>7,} {v.get(k,0)/tot:>7.1%}" for k in ("up", "flat", "down"))
        print(f"  {band:>8.3f} {row} {v.get('na',0):>7,} {v.get('na',0)/tot:>6.1%}")

    # -- volatility terciles (research-block breakpoints; characterisation only)
    a = s.atrp.dropna()
    q1, q2 = a.quantile([1/3, 2/3])
    print(f"\n  daily ATR% (ATR14 of daily bars / close, shifted 1): "
          f"terciles at {q1:.4%} and {q2:.4%}  (median {a.median():.4%})")

    # -- by year
    print("\n  by calendar YEAR (research block):")
    print(f"  {'year':>6} {'sessions':>9} {'%':>7} {'ret of yr':>10} {'med ATR%':>9} "
          f"{'%up':>6} {'%flat':>6} {'%down':>6}")
    L0 = trend_label(s.rel.values, 0.005)
    s = s.assign(lab=L0)
    d = daily_frame(df)
    for y, gg in s.groupby("year"):
        cl = d.loc[gg.index, "close"]
        ret = cl.iloc[-1] / cl.iloc[0] - 1
        vc = gg.lab.value_counts(normalize=True)
        print(f"  {y:>6} {len(gg):>9,} {len(gg)/len(s):>6.1%} {ret:>+9.1%} "
              f"{gg.atrp.median():>8.3%} {vc.get('up',0):>5.0%} {vc.get('flat',0):>5.0%} "
              f"{vc.get('down',0):>5.0%}")
    cl = d.loc[s.index, "close"]
    print(f"  {'ALL':>6} {len(s):>9,} {1.0:>6.1%} {cl.iloc[-1]/cl.iloc[0]-1:>+9.1%}"
          f" {s.atrp.median():>8.3%}")
    return s, q1, q2



# ================================================================== PART B
def regime_masks(df, r, band=0.005):
    """dict name -> (bar mask restricted to research, n sessions)."""
    st = causal_daily(df)
    rs = np.unique(df.sess.values[r])
    s = st.loc[st.index.isin(rs)].copy()
    s["lab"] = trend_label(s.rel.values, band)
    a = s.atrp.dropna()
    q1, q2 = a.quantile([1 / 3, 2 / 3])
    vl = pd.cut(s.atrp, [-np.inf, q1, q2, np.inf], labels=["vol_low", "vol_mid", "vol_high"])
    out = {}
    for k in ("up", "flat", "down"):
        ss = s.index[s.lab == k]
        out[f"trend_{k}"] = (r & sess_mask(df, ss), len(ss))
    for k in ("vol_low", "vol_mid", "vol_high"):
        ss = s.index[vl == k]
        out[k] = (r & sess_mask(df, ss), len(ss))
    for y, gg in s.groupby("year"):
        out[f"y{y}"] = (r & sess_mask(df, gg.index), len(gg))
    out["ALL"] = (r, len(s))
    return out, s


def split_desc(tr, mask_bars):
    t = tr[np.isin(tr.sig_bar, np.where(mask_bars)[0])]
    if len(t) == 0:
        return "-"
    L = t[t.side > 0]; S = t[t.side < 0]
    ex = pd.Series(t.reason).map(lambda i: lab.REASONS[i]).value_counts(normalize=True)
    return (f"L {len(L):>4} {L.net.mean():>+7.2f} | S {len(S):>4} "
            f"{S.net.mean() if len(S) else float('nan'):>+7.2f} | "
            f"stop {ex.get('stop',0):>4.0%} targ {ex.get('target',0):>4.0%} "
            f"flat {ex.get('flatten',0):>4.0%} time {ex.get('time',0):>4.0%}")


def part_B(sym="NAS", n_entry=20, band=0.005):
    hdr(f"B. PLAIN DONCHIAN n={n_entry} BASELINE BY REGIME - {sym} RESEARCH BLOCK\n"
        f"   each slice scored against a control drawn from THAT SAME SLICE")
    df, w, r = lab.research(sym)
    idx, side = sigs(df, n_entry)
    M, s = regime_masks(df, r, band)
    rows = []
    tr_ref = None
    for name, (m, ns) in M.items():
        g, tr = gate(sym, idx, side, mask=m, label=f"{sym} {name}", n_draws=NDRAW)
        tr_ref = tr
        rows.append(dict(slice=name, sess=ns, **{k: g[k] for k in
                    ("n", "exp", "ctrl", "excess", "z", "p", "wr", "pf")}))
    print()
    print(f"  {'slice':<12} {'sess':>6} {'trades':>7} {'exp':>8} {'ctrl':>8} {'excess':>8} "
          f"{'z':>6} {'p':>7}   long/short and exit mix")
    for row, (name, (m, ns)) in zip(rows, M.items()):
        print(f"  {name:<12} {ns:>6,} {row['n']:>7,} {row['exp']:>+8.2f} {row['ctrl']:>+8.2f} "
              f"{row['excess']:>+8.2f} {row['z']:>+6.2f} {row['p']:>7.4f}   "
              f"{split_desc(tr_ref, m)}")
    return pd.DataFrame(rows), tr_ref



# ================================================================== PART C
def part_C(syms=("NAS", "US30"), band=0.005):
    hdr("C. LONG / SHORT ASYMMETRY - does direction do any work?\n"
        "   the control inherits the book's side mix, so a long-only control is\n"
        "   ALSO all-long: drift is already priced in and cannot create excess.")
    for sym in syms:
        df, w, r = lab.research(sym)
        print(f"\n  --- {sym} ---")
        for n_entry in (10, 20, 40):
            for nm, so in (("both", 0), ("long-only", 1), ("short-only", -1)):
                idx, side = sigs(df, n_entry, side_only=so)
                gate(sym, idx, side, mask=r, label=f"{sym} n={n_entry:<3} {nm}")

    hdr("C2. DIRECTION DICTATED BY THE CAUSAL DAILY TREND\n"
        "    aligned  = take only breakouts that agree with yesterday's daily state\n"
        "    against  = take only the ones that disagree\n"
        "    (both are still Donchian BREAKOUTS - only the side filter changes)")
    for sym in syms:
        df, w, r = lab.research(sym)
        st = causal_daily(df)
        L = pd.Series(trend_label(st.rel.values, band), index=st.index)
        want = L.map({"up": 1, "down": -1}).reindex(df.sess.values).values  # nan for flat/na
        for n_entry in (10, 20, 40):
            idx, side = sigs(df, n_entry)
            wa = want[idx]
            ok = ~pd.isna(wa)
            al = ok & (wa == side)
            ag = ok & (wa == -side)
            gate(sym, idx[al], side[al], mask=r, label=f"{sym} n={n_entry:<3} aligned")
            gate(sym, idx[ag], side[ag], mask=r, label=f"{sym} n={n_entry:<3} against")



# ================================================================== PART D
def causal_volrank(df, look=250, atr_n=14):
    """Trailing percentile rank of yesterday's daily ATR% inside the previous
    `look` sessions. Fully causal: no research-block quantile, no future bars."""
    st = causal_daily(df, atr_n=atr_n)
    v = st.atrp.values
    n = len(v)
    out = np.full(n, np.nan)
    for i in range(n):
        lo = max(0, i - look)
        hist = v[lo:i]
        hist = hist[~np.isnan(hist)]
        if len(hist) >= 60 and not np.isnan(v[i]):
            out[i] = (hist < v[i]).mean()
    return pd.Series(out, index=st.index)


def part_D(syms=("NAS", "US30"), n_entries=(10, 20, 40)):
    hdr("D. VOLATILITY REGIME AS A CAUSAL FILTER\n"
        "   part B showed the top vol tercile is where the money is lost, on BOTH\n"
        "   instruments. Here the tercile is replaced by a trailing percentile rank\n"
        "   (250-session lookback, shifted 1) so the rule is tradeable, and the\n"
        "   threshold is swept: a real regime effect decays smoothly.")
    for sym in syms:
        df, w, r = lab.research(sym)
        vr = causal_volrank(df)
        per_bar = vr.reindex(df.sess.values).values
        print(f"\n  --- {sym} ---   (q = keep sessions whose trailing vol rank <= q)")
        for n_entry in n_entries:
            idx, side = sigs(df, n_entry)
            for q in (0.40, 0.50, 0.60, 0.67, 0.75, 0.85, 1.00):
                keep = per_bar[idx] <= q
                gate(sym, idx[keep], side[keep], mask=r,
                     label=f"{sym} n={n_entry:<3} volrank<={q:.2f}")

    hdr("D2. IS THE VOL EFFECT JUST THE TREND EFFECT? cross-tab on NAS research")
    df, w, r = lab.research("NAS")
    st = causal_daily(df)
    rs = np.unique(df.sess.values[r])
    s2 = st.loc[st.index.isin(rs)].copy()
    s2["trend"] = trend_label(s2.rel.values, 0.005)
    s2["vr"] = causal_volrank(df).reindex(s2.index).values
    s2["volb"] = pd.cut(s2.vr, [-.01, .33, .67, 1.01], labels=["lo", "mid", "hi"])
    print(pd.crosstab(s2.trend, s2.volb, normalize=True).round(3).to_string())


# ================================================================== PART E
def part_E():
    hdr("E. INDEPENDENT BROKER FEED - US30RTF\n"
        "   *** THIS FILE IS CALENDAR-DISJOINT FROM BOTH RESEARCH BLOCKS AND SITS\n"
        "   *** INSIDE THE LOCKED PERIOD. IT IS USED ONLY TO CHECK THAT THE ENGINE\n"
        "   *** AND THE FEED BEHAVE THE SAME WAY. NOTHING IS SELECTED ON IT.")
    dr, wr_, rr = lab.research("US30RTF")
    d2 = lab.bars("US30RTF")[0]          # bars only; the holdout mask is never unpacked
    full = np.ones(len(d2), dtype=bool)
    print(f"  {len(d2):,} bars, {d2.sess.max()+1:,} sessions, "
          f"{d2.ts.min().date()} -> {d2.ts.max().date()}")
    dq = daily_frame(d2)
    print(f"  index level {dq.close.iloc[0]:,.0f} -> {dq.close.iloc[-1]:,.0f} "
          f"({dq.close.iloc[-1]/dq.close.iloc[0]-1:+.1%})")
    w = d2[(d2.tod >= 420) & (d2.tod < 660)]
    print(f"  07:00-11:00 window: {len(w):,} bars over {w.sess.nunique():,} sessions "
          f"({len(w)/max(w.sess.nunique(),1):.1f} bars/session)")
    for n_entry in (10, 20, 40):
        for nm, so in (("both", 0), ("long-only", 1), ("short-only", -1)):
            idx, side = sigs(d2, n_entry, side_only=so)
            gate("US30RTF", idx, side, mask=full,
                 label=f"US30RTF FULLFILE n={n_entry:<3} {nm}")


# ================================================================== PART F
def part_F():
    hdr("F. ARE NAS AND US30 TWO INDEPENDENT TESTS?\n"
        "   they are two US equity indices over the SAME calendar span, so\n"
        "   'it replicates on both' may be one observation, not two.")
    books = {}
    for sym in ("NAS", "US30"):
        df, w, r = lab.research(sym)
        idx, side = sigs(df, 20)
        tr = lab.book(sym, idx, side, **BASE)
        tr = tr[np.isin(tr.sig_bar, np.where(r)[0])]
        d = df.date.values[tr.sig_bar.values]
        books[sym] = pd.DataFrame(dict(date=d, net=tr.net.values,
                                       side=tr.side.values))
    j = books["NAS"].merge(books["US30"], on="date", suffixes=("_n", "_u"))
    print(f"  common research sessions with a trade in both: {len(j):,}")
    print(f"  same side chosen on the same day: {(j.side_n == j.side_u).mean():.1%}")
    print(f"  pearson  corr of per-session net P&L: {j.net_n.corr(j.net_u):+.3f}")
    print(f"  spearman corr of per-session net P&L: {j.net_n.corr(j.net_u, method='spearman'):+.3f}")
    ag = np.sign(j.net_n) == np.sign(j.net_u)
    print(f"  same-sign outcome on the same day:   {ag.mean():.1%}")
    # daily index return correlation for reference
    for sym in ("NAS", "US30"):
        df, w, r = lab.research(sym)
        dq = daily_frame(df)
        books[sym + "_ret"] = pd.DataFrame(
            dict(date=dq.date.values, ret=dq.close.pct_change().values))
    k = books["NAS_ret"].merge(books["US30_ret"], on="date", suffixes=("_n", "_u")).dropna()
    print(f"  daily index-return correlation (research overlap, {len(k):,} days): "
          f"{k.ret_n.corr(k.ret_u):+.3f}")



# ================================================================== PART G
def state_specs(df):
    """Several CAUSAL daily-direction states. All shifted one session."""
    d = daily_frame(df)
    c = d.close.values
    out = {}

    def sh(x):
        return np.r_[np.nan, x[:-1]]

    for f, sl in ((10, 30), (20, 50), (50, 200)):
        rel = sh((lab.ema(c, f) - lab.ema(c, sl)) / lab.ema(c, sl))
        for band in (0.0, 0.005, 0.01):
            out[f"ema{f}/{sl} b{band}"] = pd.Series(
                trend_label(rel, band), index=d.index)
    sma20 = pd.Series(c).rolling(20).mean().values
    out["close>sma20"] = pd.Series(
        trend_label(sh(c / sma20 - 1.0), 0.0), index=d.index)
    r20 = np.r_[[np.nan] * 21, c[20:-1] / c[:-21] - 1.0]
    out["ret20 sign"] = pd.Series(trend_label(r20, 0.0), index=d.index)
    for k in out:
        out[k].iloc[:60] = "na"
    return out


def part_G(syms=("NAS", "US30"), n_entry=20):
    hdr("G. ROBUSTNESS OF THE DIRECTION RESULT ACROSS DAILY-STATE DEFINITIONS\n"
        "   if 'against the daily trend' is a mechanism it should not care which\n"
        "   reasonable causal definition of the daily trend is used.")
    for sym in syms:
        df, w, r = lab.research(sym)
        idx, side = sigs(df, n_entry)
        print(f"\n  --- {sym} n_entry={n_entry} ---")
        for nm, L in state_specs(df).items():
            want = L.map({"up": 1, "down": -1}).reindex(df.sess.values).values
            wa = want[idx]; ok = ~pd.isna(wa)
            for tag, sel in (("aligned", ok & (wa == side)), ("against", ok & (wa == -side))):
                gate(sym, idx[sel], side[sel], mask=r,
                     label=f"{sym} {nm:<16} {tag}")


def part_H(sym="NAS", n_entry=20, band=0.005, nperm=400):
    hdr(f"H. PERMUTATION TEST on the direction result - {sym}\n"
        "   H0: the causal daily state carries NO information about which side of\n"
        "   the breakout wins. Shuffle the state labels ACROSS RESEARCH SESSIONS\n"
        "   (keeps the label frequencies, destroys the day-to-day pairing) and\n"
        "   recompute mean(against) - mean(aligned).")
    df, w, r = lab.research(sym)
    idx, side = sigs(df, n_entry)
    tr = lab.book(sym, idx, side, one_per_session=False, **{k: v for k, v in
                  BASE.items() if k != "one_per_session"})
    tr = tr[np.isin(tr.sig_bar, np.where(r)[0])].reset_index(drop=True)
    sess_of = df.sess.values[tr.sig_bar.values]
    st = causal_daily(df)
    L = pd.Series(trend_label(st.rel.values, band), index=st.index)
    rs = np.unique(df.sess.values[r])
    lab_r = L.loc[L.index.isin(rs)]
    lab_r = lab_r[lab_r.isin(["up", "down"])]

    def stat(mapping):
        w_ = pd.Series(sess_of).map(mapping).values
        ok = ~pd.isna(w_)
        al = ok & (w_ == tr.side.values); ag = ok & (w_ == -tr.side.values)
        if al.sum() < 30 or ag.sum() < 30:
            return np.nan
        return tr.net.values[ag].mean() - tr.net.values[al].mean()

    base_map = lab_r.map({"up": 1, "down": -1}).to_dict()
    obs = stat(base_map)
    rng = np.random.default_rng(7)
    vals = np.array(lab_r.map({"up": 1, "down": -1}).values, dtype=float)
    keys = np.array(lab_r.index)
    null = np.empty(nperm)
    for i in range(nperm):
        null[i] = stat(dict(zip(keys, rng.permutation(vals))))
    null = null[~np.isnan(null)]
    z = (obs - null.mean()) / null.std(ddof=1)
    print(f"  observed  mean(against) - mean(aligned) = {obs:+.2f} pts/trade "
          f"(all triggers, not one-per-session)")
    print(f"  permutation null: mean {null.mean():+.2f}  sd {null.std(ddof=1):.2f}  "
          f"z = {z:+.2f}   p(two-sided) = {(np.abs(null-null.mean())>=abs(obs-null.mean())).mean():.4f}")
    return obs, null


def part_I(syms=("NAS", "US30"), n_entry=20, band=0.005):
    hdr("I. IS THE DIRECTION RESULT CONCENTRATED IN ONE OR TWO YEARS?\n"
        "   per-year mean net of the aligned and against legs (research block).")
    for sym in syms:
        df, w, r = lab.research(sym)
        idx, side = sigs(df, n_entry)
        st = causal_daily(df)
        L = pd.Series(trend_label(st.rel.values, band), index=st.index)
        want = L.map({"up": 1, "down": -1}).reindex(df.sess.values).values
        rows = []
        for tag, mult in (("aligned", 1), ("against", -1)):
            wa = want[idx]; ok = ~pd.isna(wa)
            sel = ok & (wa == mult * side)
            tr = lab.book(sym, idx[sel], side[sel], **BASE)
            tr = tr[np.isin(tr.sig_bar, np.where(r)[0])]
            yr = pd.to_datetime(df.date.values[tr.sig_bar.values]).year
            rows.append(pd.DataFrame(dict(year=yr, net=tr.net.values, tag=tag)))
        a = pd.concat(rows)
        t = a.pivot_table(index="year", columns="tag", values="net",
                          aggfunc=["mean", "count"])
        print(f"\n  --- {sym} ---")
        print(t.round(2).to_string())
        print(f"  ALL  aligned {a[a.tag=='aligned'].net.mean():+.2f} "
              f"(n={ (a.tag=='aligned').sum() })   "
              f"against {a[a.tag=='against'].net.mean():+.2f} "
              f"(n={ (a.tag=='against').sum() })")
        # leave-one-year-out on the gap
        print("  leave-one-year-out gap (against - aligned):")
        for y in sorted(a.year.unique()):
            b = a[a.year != y]
            g = b[b.tag == "against"].net.mean() - b[b.tag == "aligned"].net.mean()
            print(f"     drop {y}: {g:+.2f}")


def part_J():
    hdr("J. FEED SANITY: US30 vs US30RTF on overlapping BARS ONLY\n"
        "   raw bar returns and bar geometry - NO P&L, NO strategy, nothing\n"
        "   selected. This only checks the two feeds are the same instrument on\n"
        "   the same clock (the timezone claim in data.py).")
    a = lab.bars("US30")[0][["ts", "open", "high", "low", "close"]]
    b = lab.bars("US30RTF")[0][["ts", "open", "high", "low", "close"]]
    j = a.merge(b, on="ts", suffixes=("_m", "_r"))
    print(f"  overlapping 15m timestamps: {len(j):,}  "
          f"{j.ts.min()} -> {j.ts.max()}")
    if len(j) > 100:
        rm = j.close_m.pct_change(); rr = j.close_r.pct_change()
        print(f"  15m close-return correlation: {rm.corr(rr):+.4f}")
        print(f"  mean level offset (m - r): {(j.close_m - j.close_r).mean():+.1f} pts "
              f"(sd {(j.close_m - j.close_r).std():.1f})")
        print(f"  mean bar range: main {(j.high_m-j.low_m).mean():.1f} pts, "
              f"rtf {(j.high_r-j.low_r).mean():.1f} pts")
        for k in (1, 2, -1, -2):
            print(f"    lag {k:+d} return corr: {rm.corr(rr.shift(k)):+.4f}")



# ================================================================== PART K
def part_K(syms=("NAS", "US30"), band=0.005):
    hdr("K. THE CLEAN DIRECTION TEST - control drawn from the SAME SESSION POOL\n"
        "   In parts C2/G the 'against' book is ~70% short while its control drew\n"
        "   shorts from ALL research sessions, so the trend-state composition was\n"
        "   only approximately matched. Here the mask restricts BOTH the book and\n"
        "   the control pool to one trend state, and long vs short are compared\n"
        "   inside it. This is the test that decides the direction question.")
    for sym in syms:
        df, w, r = lab.research(sym)
        st = causal_daily(df)
        L = pd.Series(trend_label(st.rel.values, band), index=st.index)
        print(f"\n  --- {sym} ---")
        for state in ("up", "down", "flat"):
            ss = L.index[L == state]
            m = r & sess_mask(df, ss)
            for n_entry in (10, 20, 40):
                for nm, so in (("long ", 1), ("short", -1)):
                    idx, side = sigs(df, n_entry, side_only=so)
                    gate(sym, idx, side, mask=m,
                         label=f"{sym} {state:<4} n={n_entry:<3} {nm}")
            print()



# ================================================================== PART L
def _upmask(df, r, band=0.005, spec="ema20/50"):
    st = causal_daily(df)
    L = pd.Series(trend_label(st.rel.values, band), index=st.index)
    return r & sess_mask(df, L.index[L == "up"]), L


def part_L(syms=("NAS", "US30")):
    hdr("L. NEIGHBOURHOOD OF THE ONE LIVE EFFECT\n"
        "   'SHORT Donchian breakout, 07:00-11:00 NY, only on sessions whose causal\n"
        "   daily state is UP.'  A real effect decays smoothly in every knob.\n"
        "   NOTE: this is counter-trend AT THE DAILY SCALE and may sit outside the\n"
        "   lab charter. It is reported, not claimed.")
    for sym in syms:
        df, w, r = lab.research(sym)
        print(f"\n  --- {sym} : trend band sweep (n_entry=20) ---")
        for band in (0.0, 0.005, 0.01, 0.02):
            m, _ = _upmask(df, r, band)
            idx, side = sigs(df, 20, side_only=-1)
            gate(sym, idx, side, mask=m, label=f"{sym} up(b={band:.3f}) n=20 short")
        m, _ = _upmask(df, r, 0.005)
        print(f"  --- {sym} : entry lookback sweep (band 0.005) ---")
        for n_entry in (5, 10, 15, 20, 30, 40, 60, 80):
            idx, side = sigs(df, n_entry, side_only=-1)
            gate(sym, idx, side, mask=m, label=f"{sym} up n={n_entry:<3} short")
        print(f"  --- {sym} : exit geometry (n=20) ---")
        idx, side = sigs(df, 20, side_only=-1)
        for st_, tg in ((1.0, 1.5), (1.5, 1.5), (1.5, 2.0), (1.5, 3.0), (2.0, 2.0), (2.0, 3.0)):
            gate(sym, idx, side, mask=m, stop_mult=st_, targ_mult=tg,
                 label=f"{sym} up n=20 short stop{st_} targ{tg}")
        print(f"  --- {sym} : max_hold (n=20, 1.5/2.0) ---")
        for mh in (4, 8, 16, 32):
            gate(sym, idx, side, mask=m, max_hold=mh,
                 label=f"{sym} up n=20 short hold{mh}")
        print(f"  --- {sym} : sub-window ---")
        for win in ((420, 540), (420, 570), (570, 660), (420, 660)):
            i2, s2 = sigs(df, 20, side_only=-1)
            keep = (df.tod.values[i2] >= win[0]) & (df.tod.values[i2] < win[1])
            gate(sym, i2[keep], s2[keep], mask=m, flat_tod=win[1],
                 label=f"{sym} up n=20 short win{win}")
        print(f"  --- {sym} : cost multiplier (n=20) ---")
        for cm in (0.0, 1.0, 2.0):
            trx = lab.book(sym, idx, side, cost_mult=cm, **BASE)
            g = lab.gate(sym, trx, 1.5, 2.0, mask=m, n_draws=NDRAW,
                         label=f"{sym} up n=20 short cost x{cm}")
            globals()["NCFG"] += 1


def part_M(syms=("NAS", "US30"), band=0.005):
    hdr("M. LEAVE-ONE-YEAR-OUT on the short-in-uptrend book (research block)")
    for sym in syms:
        df, w, r = lab.research(sym)
        m, _ = _upmask(df, r, band)
        for n_entry in (10, 20):
            idx, side = sigs(df, n_entry, side_only=-1)
            tr = lab.book(sym, idx, side, **BASE)
            keep = np.isin(tr.sig_bar, np.where(m)[0])
            tr = tr[keep]
            yr = pd.to_datetime(df.date.values[tr.sig_bar.values]).year
            print(f"\n  {sym} n={n_entry}  overall exp {tr.net.mean():+.2f}  n={len(tr)}")
            for y in sorted(set(yr)):
                sub = tr.net.values[yr == y]
                print(f"     {y}: n={len(sub):>4} exp={sub.mean():>+7.2f}   "
                      f"| LOYO exp={tr.net.values[yr != y].mean():>+7.2f}")



# ================================================================== PART N
def part_N():
    hdr("N. THE KILL SHOT: the NAS effect lives entirely PRE-CASH-OPEN, where the\n"
        "   cost model is most optimistic (a 2.0 pt round turn + 0.25 slippage does\n"
        "   not widen the pre-RTH spread). How much cost does it take to erase it?\n"
        "   And US30 puts the SAME effect in the OPPOSITE half of the session.")
    for sym, win in (("NAS", (420, 570)), ("NAS", (570, 660)),
                     ("US30", (420, 570)), ("US30", (570, 660))):
        df, w, r = lab.research(sym)
        m, _ = _upmask(df, r, 0.005)
        idx, side = sigs(df, 20, side_only=-1)
        keep = (df.tod.values[idx] >= win[0]) & (df.tod.values[idx] < win[1])
        print(f"\n  {sym} short-in-uptrend, window {win}:")
        for cm in (0.0, 1.0, 1.5, 2.0, 3.0):
            trx = lab.book(sym, idx[keep], side[keep], cost_mult=cm,
                           flat_tod=win[1], **{k: v for k, v in BASE.items()
                                               if k != "flat_tod"})
            lab.gate(sym, trx, 1.5, 2.0, mask=m, n_draws=NDRAW, flat_tod=win[1],
                     label=f"    cost x{cm} ({lab.COST[sym]*cm:.2f}+{lab.SLIP[sym]*cm:.2f} pts)")
            globals()["NCFG"] += 1

    hdr("N2. minute-of-day profile of the short-in-uptrend triggers")
    for sym in ("NAS", "US30"):
        df, w, r = lab.research(sym)
        m, _ = _upmask(df, r, 0.005)
        idx, side = sigs(df, 20, side_only=-1)
        tr = lab.book(sym, idx, side, **BASE)
        tr = tr[np.isin(tr.sig_bar, np.where(m)[0])]
        tod = df.tod.values[tr.sig_bar.values]
        g = pd.DataFrame(dict(tod=tod, net=tr.net.values)).groupby("tod").net.agg(["count", "mean"])
        print(f"\n  {sym}:")
        print("    " + "  ".join(f"{int(t//60):02d}:{int(t%60):02d} n={int(row['count']):>3} "
                                 f"{row['mean']:>+6.1f}" for t, row in g.iterrows()))



# ================================================================== PART O
def part_O():
    hdr("O. HOW CONCENTRATED IS THE NAS PRE-OPEN EFFECT IN A FEW MINUTES?\n"
        "   the control matches the minute-of-day HISTOGRAM, so this is not about\n"
        "   the control being wrong - it is about how many trades carry the number.")
    sym = "NAS"
    df, w, r = lab.research(sym)
    m, _ = _upmask(df, r, 0.005)
    idx, side = sigs(df, 20, side_only=-1)
    base = (df.tod.values[idx] >= 420) & (df.tod.values[idx] < 570)
    for drop, tag in (((), "all 07:00-09:30"),
                      ((420,), "drop 07:00"),
                      ((510,), "drop 08:30"),
                      ((420, 510), "drop 07:00 + 08:30"),
                      ((420, 435, 510), "drop 07:00,07:15,08:30")):
        keep = base & ~np.isin(df.tod.values[idx], drop)
        gate(sym, idx[keep], side[keep], mask=m, flat_tod=570,
             label=f"NAS up n=20 short 0700-0930 {tag}")

    hdr("O2. SAME RULE, BOTH INSTRUMENTS, BOTH SESSION HALVES - side by side")
    print(f"  {'':22} {'NAS excess':>12} {'p':>8}   {'US30 excess':>12} {'p':>8}")
    for win in ((420, 570), (570, 660), (420, 660)):
        out = []
        for sy in ("NAS", "US30"):
            d2, w2, r2 = lab.research(sy)
            mm, _ = _upmask(d2, r2, 0.005)
            i2, s2 = sigs(d2, 20, side_only=-1)
            k2 = (d2.tod.values[i2] >= win[0]) & (d2.tod.values[i2] < win[1])
            g, _t = lab.sig_gate(sy, i2[k2], s2[k2], mask=mm, flat_tod=win[1],
                                 n_draws=NDRAW, quiet=True,
                                 **{k: v for k, v in BASE.items() if k != "flat_tod"})
            globals()["NCFG"] += 1
            out.append(g)
        print(f"  window {str(win):<15} {out[0]['excess']:>+12.2f} {out[0]['p']:>8.4f}   "
              f"{out[1]['excess']:>+12.2f} {out[1]['p']:>8.4f}")



# ================================================================== PART P
def part_P():
    hdr("P. THE KNOWN NAS BASELINE TABLE, REPRODUCED ON US30 RESEARCH\n"
        "   (NAS is already known: exp -2.6..-4.0, excess ~0, z -1.36..+0.03)")
    for sym in ("NAS", "US30"):
        df, w, r = lab.research(sym)
        print(f"\n  --- {sym} research, 07:00-11:00, stop1.5/targ2.0, 1/session ---")
        for n_entry in (5, 10, 15, 20, 30, 40, 60, 80):
            idx, side = sigs(df, n_entry)
            gate(sym, idx, side, mask=r, label=f"{sym} n_entry={n_entry}")


def part_ALL():
    part_A("NAS"); part_A("US30")
    part_P()
    part_B("NAS"); part_B("US30")
    part_F()
    part_C(); part_G(); part_K(); part_H(); part_I()
    part_D(); part_L(); part_M(); part_N(); part_O()
    part_E(); part_J()


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "A"
    sym = sys.argv[2] if len(sys.argv) > 2 else "NAS"
    if what == "A":
        part_A(sym)
    elif what == "B":
        part_B(sym)
    elif what == "C":
        part_C()
    elif what == "D":
        part_D()
    elif what == "E":
        part_E()
    elif what == "F":
        part_F()
    elif what == "P":
        part_P()
    elif what == "ALL":
        part_ALL()
    elif what == "O":
        part_O()
    elif what == "N":
        part_N()
    elif what == "L":
        part_L()
    elif what == "M":
        part_M()
    elif what == "K":
        part_K()
    elif what == "J":
        part_J()
    elif what == "I":
        part_I()
    elif what == "H":
        part_H()
    elif what == "G":
        part_G()
    print(f"\n[configurations gated so far in this run: {NCFG}]")
