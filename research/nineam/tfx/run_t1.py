"""T1 -- PARAMETER CENSUS and DIAGNOSTICS BEFORE P&L, per timeframe, at the user's TV settings.

Order is the protocol's: what each parameter IS on each chart, then what the trigger and gate do,
then the exit mix -- no control, no grid. Writes t1_census.csv, t1_diag.csv, t1_exitmix.csv.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tfx_core as X   # noqa: E402

pd.set_option("display.width", 230)
P = dict(X.TV)


def hd(t):
    print("\n" + "=" * 100); print(t); print("=" * 100)


c30 = X.ctx(0.5)
alld, is_d, oos_d = X.split(c30, P)
print(f"tradeable sessions (30s reference: 09:00-09:05 range AND a bar in 09:27-10:00): {len(alld)}"
      f"  IS {len(is_d)} / OOS {len(oos_d)}  split at {X.DK.from_day(oos_d.min()).date()}")

# ============================================================ 1  census
hd("1  PARAMETER CENSUS -- what each setting IS on each chart")
rows = []
for tf in X.TFS:
    c = X.ctx(tf)
    mod, day = c.mod, c.day
    sel = np.isin(day, alld)
    # range: bars whose STAMP lies in [540,545)
    rb = sel & (mod >= 540) & (mod < 545)
    rstamps = np.unique(mod[rb])
    r_dur = (rstamps.max() + tf - 540) if len(rstamps) else np.nan
    eb = sel & (mod >= 567) & (mod < 600)
    es = np.unique(mod[eb])
    # coverage in 09:00-11:00 over tradeable sessions: present bars / slots
    cov = (sel & (mod >= 540) & (mod < 660)).sum() / (len(alld) * 120.0 / tf)
    cb = max(1, int(round(7 / tf)))
    sig, sd = c.sigs(P)
    # clock span of the EMA windows and the cross reach, measured at the gated signal bars
    tcl = c.tclose
    def span(nb):
        j = sig[sig >= nb]
        return float(np.median(tcl[j] - tcl[j - nb])) if len(j) else np.nan
    rows.append(dict(tf=tf, range_bars=len(rstamps), range_first=int(rstamps.min()) if len(rstamps) else -1,
                     range_min=r_dur, entry_first=int(es.min()), entry_last=int(es.max()),
                     entry_bars=len(es), flat_bar=660, cov_0900_1100=cov,
                     ema_fast_min=13 * tf, ema_slow_min=48 * tf,
                     ema_fast_clock=span(13), ema_slow_clock=span(48),
                     cross_bars=cb, cross_min_nominal=cb * tf, cross_clock=span(cb)))
cen = pd.DataFrame(rows)
print(cen.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
cen.to_csv(os.path.join(HERE, "t1_census.csv"), index=False)
print("\n  range_min = clock minutes the 'range 09:00-09:05' actually spans: a bar is IN the range")
print("  if its STAMP is in [540,545), so at 15m the whole 09:00-09:15 bar is the range.")
print("  cross_bars = max(1, round(7/tf)) exactly as the script computes it; *_clock columns are the")
print("  MEASURED clock span of that many bars ending at the gated signal bars (omitted bars widen it).")

# ============================================================ 1b ATR inertness, measured
hd("1b IS ATR(14) INERT? -- same signal set and same trades at ATR 7 / 14 / 45")
for tf in X.TFS:
    c = X.ctx(tf)
    out = []
    ref = c.trades(dict(P, atr_n=14))
    for an in (7, 45):
        t = c.trades(dict(P, atr_n=an))
        same = (t is not None and len(t) == len(ref) and np.array_equal(t["eb"].to_numpy(), ref["eb"].to_numpy())
                and np.allclose(t["pts"].to_numpy(), ref["pts"].to_numpy()))
        out.append(f"ATR{an}: {'IDENTICAL' if same else 'DIFFERS'} ({0 if t is None else len(t)} vs {len(ref)})")
    s14, _ = c.sigs(dict(P, atr_n=14)); s45, _ = c.sigs(dict(P, atr_n=45))
    print(f"  {tf:>4}m  signals {len(s14)} vs {len(s45)} equal={np.array_equal(s14, s45)}   " + "   ".join(out))

# ============================================================ 1c the Pine's own crossBars on a 30s chart
hd("1c THE PINE'S tfMin = max(1, seconds/60): ON A 30s CHART crossBars IS 7 BARS = 3.5 MIN, NOT 14")
c = X.ctx(0.5)
for lab, pp in [("research: 14 bars (7 min)", dict(P, ma_mode="xbars", cross_bars=14)),
                ("Pine on 30s: 7 bars (3.5 min)", dict(P, ma_mode="xbars", cross_bars=7)),
                ("clock minutes <= 7", dict(P, ma_mode="xmin", cross_min=7))]:
    s = X.stats(c.trades(pp))
    print(f"  {lab:32s} n {s['n']:3d}  %/tr {s['pct']:+.4f}  PF {s['pf']:.3f}  win {s['win']:.3f}  "
          f"MDE {s['mde']:.4f}")

# ============================================================ 2  diagnostics
hd("2  DIAGNOSTICS BEFORE P&L -- trigger, gate, exits, holds, the relabelled breakeven")
drow, mrow = [], []
sec = P["be_off"] - X.COST
for tf in X.TFS:
    c = X.ctx(tf)
    sig_all, sd_all = X.ungated(c, P)
    sig_g, sd_g = c.sigs(P)
    tr = c.trades(P)
    s = X.stats(tr)
    rhi, rlo, _ = c.ranges(P["range_end"])
    # how far beyond the range edge the FILL is, in points (the latency of detecting at bar close)
    if tr is not None and len(tr):
        sg = tr["sig"].to_numpy(); sd = tr["side"].to_numpy(); ent = tr["ent"].to_numpy()
        lvl = np.where(sd > 0, rhi[sg], rlo[sg])
        beyond = np.median(sd * (ent - lvl))
        hold = c.tclose[tr["xb"].to_numpy()] - (c.tclose[tr["eb"].to_numpy()] - tf)
        relab = int((np.abs(tr["pts"].to_numpy() - sec) < 1e-6).sum())
        rwidth = np.median((rhi - rlo)[sg])
    else:
        beyond = hold = rwidth = np.nan; relab = 0
    # gate firing rate on ALL bars in the entry window vs on the trigger bars (base rate / lift)
    Lm, Sm = c.gate_masks(P, 14)
    win_b = np.isin(c.day, alld) & (c.mod >= 567) & (c.mod < 600)
    base = 0.5 * (Lm[win_b].mean() + Sm[win_b].mean())
    trig = np.where(sd_all > 0, Lm[sig_all], Sm[sig_all]).mean() if len(sig_all) else np.nan
    drow.append(dict(tf=tf, ungated=len(sig_all), ungated_sess=len(np.unique(c.day[sig_all])),
                     kept=len(sig_g), keep_rate=len(sig_g) / max(len(sig_all), 1),
                     gate_base=base, lift=trig / base if base else np.nan,
                     trades=s["n"], sess=s["sess"], pct=s["pct"], pf=s["pf"], win=s["win"],
                     relab_071=relab, relab_share=relab / max(s["n"], 1),
                     hold_med_min=float(np.median(hold)) if s["n"] else np.nan,
                     fill_beyond_edge_pts=beyond, range_width_pts=rwidth,
                     amb=float(tr["amb"].mean()) if s["n"] else np.nan,
                     thru=float(tr["thru"].mean()) if s["n"] else np.nan))
    if tr is not None:
        for w, g in tr.groupby("why"):
            mrow.append(dict(tf=tf, exit=X.WHY.get(int(w), str(w)), n=len(g), share=len(g) / len(tr),
                             pts=g["pts"].mean(), of_net=g["pct"].sum() / tr["pct"].sum()))
dg = pd.DataFrame(drow)
print(dg.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
dg.to_csv(os.path.join(HERE, "t1_diag.csv"), index=False)
mx = pd.DataFrame(mrow)
print("\n  exit mix")
print(mx.pivot(index="tf", columns="exit", values="share").fillna(0).to_string(float_format=lambda v: f"{v:.3f}"))
print("\n  mean points by exit")
print(mx.pivot(index="tf", columns="exit", values="pts").to_string(float_format=lambda v: f"{v:+.2f}"))
mx.to_csv(os.path.join(HERE, "t1_exitmix.csv"), index=False)

# ============================================================ 2b where the 30s sessions go
hd("2b SESSION OVERLAP -- which of the 30s trade sessions survive at each timeframe")
t30 = c30.trades(P)
d30 = set(np.unique(t30["eday"]))
for tf in X.TFS[1:]:
    c = X.ctx(tf)
    t = c.trades(P)
    dd = set() if t is None else set(np.unique(t["eday"]))
    sig_all, _ = X.ungated(c, P)
    da = set(np.unique(c.day[sig_all]))
    print(f"  {tf:>4}m  30s sessions {len(d30)}; with an ungated break here {len(d30 & da)}; "
          f"traded here {len(d30 & dd)}; new sessions not in 30s {len(dd - d30)}")
print("\ndone.")
