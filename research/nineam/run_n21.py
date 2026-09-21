"""30-SECOND US30, the user's own settings: what the feed can carry, and the IS/OOS read.

Order is deliberate. A coverage check costs two lines and can make every number downstream
meaningless, so it runs first; the transcription and the degeneracy assertion run before any
P&L; the fill-model artifact is priced before the result is quoted, because this configuration
sets a breakeven ratchet and `na_core._walk` books a through-the-market stop at its level.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import na_core as N    # noqa: E402
import na_opt as O     # noqa: E402
import na_30s as T     # noqa: E402
import na_s30 as S     # noqa: E402
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '.'))
import daykey as DK  # noqa: E402  (pandas 3 made us the default resolution; see the module)

OUT = HERE
pd.set_option("display.width", 200)


def hd(t):
    print("\n" + "=" * 96); print(t); print("=" * 96)


# =============================================================================== 0  coverage
hd("0  WHAT THE 30-SECOND FEED CAN CARRY AT THESE SETTINGS")
f = T.frame(tf=0.5, atr_n=14)
mod = f["mod"].to_numpy(); day = f["day"].to_numpy()
sess = np.unique(day[mod >= 570])
rows = []
for lo, hi, lab in [(540, 545, "range 09:00-09:04:30 (540-545)"),
                    (540, 570, "the full half hour (540-570)"),
                    (568, 570, "the arm minutes 568-570"),
                    (568, 960, "the entry window 568-960")]:
    m = (mod >= lo) & (mod < hi)
    d = np.unique(day[m])
    k = pd.Series(day[m]).value_counts()
    rows.append(dict(window=lab, sessions=len(d), share=len(d) / len(sess),
                     med_bars=float(k.median()) if len(k) else 0.0))
cov = pd.DataFrame(rows)
print(f"file: {len(f):,} bars, {f.index[0]} -> {f.index[-1]}, {len(sess)} sessions with a 09:30+ bar")
print(cov.to_string(index=False, float_format=lambda v: f"{v:.3f}"))

have = np.unique(day[(mod >= 540) & (mod < 545)])
mo = pd.DataFrame({"m": DK.from_day(pd.Series(sess)).dt.to_period("M").astype(str),
                   "have": np.isin(sess, have)}).groupby("m")["have"].agg(["sum", "size"])
print("\nsessions carrying the 09:00-09:05 range, by month:")
print(mo.to_string())
print(f"\nthe range exists on {len(have)} of {len(sess)} sessions ({100*len(have)/len(sess):.1f}%), "
      f"first {DK.from_day(have.min()).date()} "
      f"last {DK.from_day(have.max()).date()}")
print("""
  `US30_30s` OMITS BARS WITH NO ACTIVITY, and the pre-open is exactly where a Dow CFD is quiet.
  Coverage of the 09:00 half hour is ALL-OR-NOTHING per session -- where it exists it is the full
  ten bars, where it does not there is no bar at all -- and it begins 2026-04-30, three days after
  the volume column starts. So the export's behaviour changed mid-file and the tradeable sample is
  not the file: it is a 4.5-month tail. Everything below is on those sessions.""")
cov.to_csv(os.path.join(OUT, "n21_coverage.csv"), index=False)

# =============================================================================== 1  the config
hd("1  THE CONFIGURATION, TRANSCRIBED -- AND WHAT A BAR COUNT MEANS AT 30 SECONDS")
c = S.ctx(tf=0.5, fix=1)
p = dict(S.CFG)
for k, v in p.items():
    print(f"  {k:12s} {v}")
tfm = 0.5
print(f"""
  atr_n = {p['atr_n']} bars = {p['atr_n']*tfm:.0f} MINUTES here, against {p['atr_n']*15} minutes on the
    15-minute chart the study was built on -- the same number is a different indicator.
  cross_min = {p['cross_min']} MINUTES = {max(1,int(round(p['cross_min']/tfm)))} bars here, {max(1,int(round(p['cross_min']/15)))} bar on 15m. The script converts from minutes,
    so this one is portable and the ATR is not.""")

# the degeneracy, asserted on the signal set rather than argued from the source
hd("1b  THE BYPASS IS AN IDENTITY AT THESE SETTINGS -- ASSERTED, NOT ARGUED")
cb = max(1, int(round(p["cross_min"] / tfm)))
loose_u, loose_d = (c.age_up <= cb), (c.age_dn <= cb)
sig_all, sd_all = c.events(p["range_end"], p["side"], p["buf_atr"], p["atr_n"], p["end_m"], p["open_m"])
g_gate = np.where(sd_all > 0, loose_u[sig_all], loose_d[sig_all])          # script's MA gate
g_byp = g_gate.copy()                                                      # the bypass expression
g_or = g_gate | g_byp
print(f"  ungated signals                 {len(sig_all)}")
print(f"  MA gate 'Fresh cross' keeps     {g_gate.sum()}")
print(f"  the bypass alone keeps          {g_byp.sum()}")
print(f"  their OR keeps                  {g_or.sum()}   (identical: {np.array_equal(g_or, g_gate)})")
print("  So the bypass switch has NO effect at these settings. The shipped panel says so too.")

# the STRICT research mask, for the difference the parity harness cannot see
strict_u = c.st & (c.age_up <= cb); strict_d = (~c.st) & (c.age_dn <= cb)
g_strict = np.where(sd_all > 0, strict_u[sig_all], strict_d[sig_all])
print(f"\n  the RESEARCH (strict) mask keeps {g_strict.sum()}; the script's loose reading admits "
      f"{g_gate.sum()-g_strict.sum()} more "
      f"({100*(g_gate.sum()-g_strict.sum())/max(g_gate.sum(),1):.1f}% of its own population)")
print(f"  subset check (strict is inside loose): {bool((g_strict <= g_gate).all())}")

# =============================================================================== 2  base rates
hd("2  BASE RATES ON THE TRIGGER'S OWN BARS")
br = []
for lab, mu, md in [("fresh 13x48 cross (loose, 7 min)", loose_u, loose_d),
                    ("fresh 13x48 cross (strict)", strict_u, strict_d),
                    ("13>48 state", c.st, ~c.st)]:
    on_sig = float(np.where(sd_all > 0, mu[sig_all], md[sig_all]).mean())
    on_all = float(np.where(sd_all > 0, mu, md).mean()) if False else float((mu.mean() + md.mean()) / 2)
    br.append(dict(cond=lab, on_signal=on_sig, on_all_bars=on_all, lift=on_sig / max(on_all, 1e-9)))
brd = pd.DataFrame(br)
print(brd.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
print("""
  A pass rate near 1.00 would mean the gate is the trigger restated (nine families have died that
  way here); a lift near 1.00 means it carries nothing. Read both columns.""")
brd.to_csv(os.path.join(OUT, "n21_baserates.csv"), index=False)

# =============================================================================== 3  fill model
hd("3  THE FILL-MODEL ARTIFACT, PRICED BEFORE THE RESULT IS QUOTED")
art = []
for be_p, be_o in [(0.0, 0.0), (43.0, 5.0), (43.0, 0.0), (25.0, 5.0), (75.0, 5.0)]:
    q = dict(p, be_pts=be_p, be_off=be_o)
    for fix in (0, 1):
        cc = S.ctx(tf=0.5, fix=fix) if fix != c.fix else c
        cc.fix = fix
        tr = cc.trades(q)
        s = S.summary(tr, len(have), 0.38)
        art.append(dict(be_pts=be_p, be_off=be_o, fix=fix, n=s.get("n", 0),
                        pts=s.get("pts", np.nan), win=s.get("win", np.nan),
                        thru=float(tr["thru"].mean()) if tr is not None else np.nan))
c.fix = 1
ar = pd.DataFrame(art)
piv = ar.pivot_table(index=["be_pts", "be_off"], columns="fix",
                     values=["pts", "win", "thru", "n"])
print(piv.to_string(float_format=lambda v: f"{v:.4f}"))
d0 = ar[(ar.be_pts == 43) & (ar.be_off == 5) & (ar.fix == 0)]["pts"].iloc[0]
d1 = ar[(ar.be_pts == 43) & (ar.be_off == 5) & (ar.fix == 1)]["pts"].iloc[0]
print(f"\n  at the user's 43/5 the artifact is worth {d1-d0:+.3f} points a trade "
      f"({100*(d1-d0)/abs(d0) if d0 else 0:+.1f}%). Everything below uses fix=1.")
ar.to_csv(os.path.join(OUT, "n21_fillmodel.csv"), index=False)

# =============================================================================== 4  IS / OOS
hd("4  IS / OOS -- A CHRONOLOGICAL SPLIT OVER THE SESSIONS THAT CAN TRADE")
tr_all = c.trades(p)
is_d, oos_d = S.split_days(c, p, 0.5)
print(f"  tradeable sessions {len(np.unique(c.day[c.sigs(p)[0]]))}, "
      f"IS {len(is_d)} sessions {DK.from_day(is_d.min()).date()}"
      f"..{DK.from_day(is_d.max()).date()}, "
      f"OOS {len(oos_d)} {DK.from_day(oos_d.min()).date()}"
      f"..{DK.from_day(oos_d.max()).date()}")
rows = []
for lab, dd in [("ALL", None), ("IS", is_d), ("OOS", oos_d)]:
    t = tr_all if dd is None else S.sub(tr_all, dd)
    s = S.summary(t, len(have), 0.38)
    s["block"] = lab
    s["per_mde"] = s.get("pct", np.nan) / s.get("mde", np.nan) if s.get("n", 0) > 1 else np.nan
    rows.append(s)
res = pd.DataFrame(rows)[["block", "n", "pct", "pts", "win", "pf", "tot", "dd", "retdd", "mde", "per_mde"]]
print(res.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
res.to_csv(os.path.join(OUT, "n21_isoos.csv"), index=False)

# the exit mix, because a 70% win rate on a ratchet is a relabelling question
hd("4b  EXIT MIX -- WHERE THE WIN RATE COMES FROM")
WHY = {1: "stop / ratchet", 2: "target", 3: "flatten", 6: "opposite cross"}
mx = tr_all.groupby("why").agg(n=("pts", "size"), pts=("pts", "mean"), tot_pts=("pts", "sum"),
                               pct=("pct", "mean"), tot_pct=("pct", "sum"))
mx.index = [WHY.get(i, str(i)) for i in mx.index]
mx["share"] = mx["n"] / mx["n"].sum()
mx["of_net"] = mx["tot_pct"] / tr_all["pct"].sum()
print(mx.to_string(float_format=lambda v: f"{v:.4f}"))
sec = float(p["be_off"] - c.cost)
k = int((np.abs(tr_all["pts"].to_numpy() - sec) < 1e-6).sum())
print(f"\n  {k} of {len(tr_all)} trades book EXACTLY {sec:+.2f} points -- the secured {p['be_off']:.0f} "
      f"minus the {c.cost:.2f} round turn. A breakeven stop is a LOSING trade by construction; the "
      f"secured offset is what relabels it, and it moves the win rate far more than the money "
      f"(`STUDY_NINE_AM_RANGE` section 8).")
mx.to_csv(os.path.join(OUT, "n21_exitmix.csv"))

# ambiguity -- the one thing only this feed can settle
amb = float(tr_all["amb"].mean())
print(f"\n  intrabar ambiguity at 100/100 points on 30-SECOND bars: {amb:.4f} "
      f"({int(tr_all['amb'].sum())} of {len(tr_all)} trades). "
      f"through-the-market fills: {tr_all['thru'].mean():.4f}")

# =============================================================================== 5  the nulls
hd("5  THE NULLS -- A MATCHED RANDOM ENTRY AND A SAME-SELECTIVITY RANDOM GATE")
rng = np.random.default_rng(7)
sig_g, sd_g = c.sigs(p)
atrf = c.atr_frame(p["atr_n"])
rhi, rlo, _ = c.ranges(p["range_end"])
ok = (c.mod >= p["open_m"]) & (c.mod < p["end_m"]) & np.isfinite(rhi) & np.isfinite(rlo)
elig = np.flatnonzero(ok)
elig_day = c.day[elig]


def control(n_draw=400, seed=0):
    """Random ENTRY: same side mix, same geometry, one per session, bars SORTED (`STUDY_V59`)."""
    r = np.random.default_rng(seed)
    days_with = np.unique(c.day[sig_g])
    pool = {d: elig[elig_day == d] for d in days_with}
    out = []
    for _ in range(n_draw):
        bb, ss = [], []
        for i, b in enumerate(sig_g):
            d = c.day[b]
            cand = pool.get(d)
            if cand is None or not len(cand):
                continue
            bb.append(r.choice(cand)); ss.append(sd_g[i])
        o = np.argsort(np.asarray(bb), kind="stable")
        b2 = np.asarray(bb)[o]; s2 = np.asarray(ss)[o]
        t = c._walk_sig(p, atrf, b2, s2)
        out.append(np.nan if t is None else float(t["pct"].mean()))
    return np.asarray(out, float)


def gate_null(n_draw=400, seed=0):
    """Random GATE of the same selectivity, re-simulated end to end (a veto, not a subset)."""
    r = np.random.default_rng(seed)
    frac = len(sig_g) / max(len(sig_all), 1)
    out = []
    for _ in range(n_draw):
        k = r.random(len(sig_all)) < frac
        if k.sum() < 5:
            out.append(np.nan); continue
        t = c._walk_sig(p, atrf, sig_all[k], sd_all[k])
        out.append(np.nan if t is None else float(t["pct"].mean()))
    return np.asarray(out, float)


rowsn = []
for lab, dd in [("ALL", None), ("IS", is_d), ("OOS", oos_d)]:
    t = tr_all if dd is None else S.sub(tr_all, dd)
    obs = float(t["pct"].mean())
    rowsn.append(dict(block=lab, obs=obs))
ce = control(400, 11); ge = gate_null(400, 12)
print(f"  rule (all)            {tr_all['pct'].mean():+.4f} %/trade on {len(tr_all)} trades")
for lab, nul in [("random ENTRY", ce), ("random GATE", ge)]:
    v = nul[np.isfinite(nul)]
    pv = float((v >= tr_all["pct"].mean()).mean())
    print(f"  {lab:14s} median {np.median(v):+.4f}  p5 {np.percentile(v,5):+.4f}  "
          f"p95 {np.percentile(v,95):+.4f}   p = {pv:.3f}   (n draws {len(v)})")
pd.DataFrame(dict(entry=ce, gate=ge)).to_csv(os.path.join(OUT, "n21_nulls.csv"), index=False)

# day-block bootstrap against ZERO
bo = N.boot_edge(tr_all, n=4000, seed=3, col="pct")
print(f"\n  day-block bootstrap of the edge: mean {tr_all['pct'].mean():+.4f}, "
      f"95% CI [{np.percentile(bo,2.5):+.4f}, {np.percentile(bo,97.5):+.4f}], "
      f"P(mean<=0) = {(np.asarray(bo)<=0).mean():.4f}")
print(f"  MDE at n={len(tr_all)}: {N.mde(tr_all['pct'].std(ddof=1), len(tr_all)):.4f} %/trade, "
      f"delivered {tr_all['pct'].mean():.4f} "
      f"({tr_all['pct'].mean()/N.mde(tr_all['pct'].std(ddof=1), len(tr_all)):.2f}x)")
print("\ndone.")
