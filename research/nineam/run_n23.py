"""30-second US30, the advanced battery: is the result the RULE or the BAR SIZE?

`run_n22` section 6c found the same configuration is +0.0358 %/trade at 30 seconds, -0.0450 at
one minute and -0.0137 at five, on bars resampled from the SAME file. That is the question this
runner settles, and the candidate explanation is `STUDY_V57`'s: the script converts the fresh-cross
reach from MINUTES and does NOT convert the EMA lengths, so `EMA 13 / 48` spans 6.5 and 24 minutes
on a 30-second chart against 13 and 48 minutes on a one-minute one. Same numbers, different
indicator, different strategy.

Then the accounting a result this size needs: the driftless break-even the geometry implies, the
component drop-one, the cost ladder, Sharpe and Sortino on the DAILY ZERO-FILLED series, the
deflation over the counted looks, and the trades it would take to verify.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, "/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_"
                   "641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
import na_core as N    # noqa: E402
import na_opt as O     # noqa: E402
import na_s30 as S     # noqa: E402

try:
    import gates as G
except Exception:
    G = None

OUT = HERE
pd.set_option("display.width", 220)


def hd(t):
    print("\n" + "=" * 96); print(t); print("=" * 96)


c = S.ctx(tf=0.5, fix=1)
P = dict(S.CFG)
tr = c.trades(P)
r = tr["pct"].to_numpy()
tdays = np.unique(c.day[c.sigs(P)[0]])
yrs = (tdays.max() - tdays.min()) / 365.25

# ====================================================== 1  is it the rule or the bar size?
hd("1  THE RESOLUTION QUESTION -- EMA LENGTHS ARE BAR COUNTS AND THE SCRIPT DOES NOT CONVERT THEM")
rows = []
for tf, lab in [(0.5, "30s"), (1.0, "1m"), (5.0, "5m")]:
    for fast, slow, how in [(13, 48, "as configured (13/48 bars)"),
                            (max(1, int(round(13 * 0.5 / tf))), max(1, int(round(48 * 0.5 / tf))),
                             "matched to 6.5 / 24 MINUTES")]:
        cc = S.ctx(tf=tf, fix=1) if (fast, slow) == (13, 48) else None
        if cc is None:
            import na_30s as T
            cc = S.Ctx30(name="US30L", tf=tf, fix=1, frame=T.frame(tf=tf, atr_n=14),
                         block_name="ALL", fast=fast, slow=slow)
        t = cc.trades(P)
        rows.append(dict(tf=lab, fast=fast, slow=slow, how=how,
                         fast_min=fast * tf, slow_min=slow * tf,
                         n=0 if t is None else len(t),
                         pct=np.nan if t is None else float(t["pct"].mean()),
                         tot=np.nan if t is None else float(t["pct"].sum()),
                         win=np.nan if t is None else float((t["pct"] > 0).mean())))
rr = pd.DataFrame(rows)
print(rr.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
print("""
  The top row of each pair is what the user runs. The second holds the EMAs' reach in MINUTES
  fixed and lets the bar size change -- if the sign follows the bar size in BOTH readings, the
  result is the resolution; if it follows the minutes, it is the rule.""")
rr.to_csv(os.path.join(OUT, "n23_resolution.csv"), index=False)

# ====================================================== 2  the geometry's own break-even
hd("2  THE WIN RATE AGAINST ITS OWN DRIFTLESS BREAK-EVEN")
sp, tp, cost = P["stop_pts"], P["tgt_pts"], c.cost
be_drift = (sp + cost) / (sp + tp)
w = float((r > 0).mean())
hit = float((tr["why"] == 2).mean())
print(f"  stop {sp:.0f} pts, target {tp:.0f} pts, round turn {cost:.2f} pts")
print(f"  a driftless barrier pair needs (S+C)/(T+S) = {be_drift:.4f} to break even")
print(f"  the rule's TARGET-HIT rate is {hit:.4f} -- that is the number the bound applies to")
print(f"  its overall WIN rate is {w:.4f}, inflated by the breakeven ratchet booking "
      f"{int((np.abs(tr['pts'].to_numpy() - (P['be_off']-cost)) < 1e-6).sum())} trades at "
      f"{P['be_off']-cost:+.2f} pts")
print(f"  shortfall of the target-hit rate against its bound: {hit - be_drift:+.4f}")
print("""
  The ratchet and the cross exit break the two-outcome algebra (24.6% of trades exit on the cross,
  29.8% on the secured level), so the bound is a diagnostic here and not a verdict -- but it is
  the reason a 70% win rate is not by itself evidence.""")

# ====================================================== 3  drop-one
hd("3  DROP-ONE -- WHAT EACH COMPONENT CONTRIBUTES")
VAR = [("as configured", {}),
       ("- the MA gate", dict(ma_mode="off")),
       ("- the breakeven", dict(be_pts=0.0, be_off=0.0)),
       ("- the cross exit", dict(x_mode="off")),
       ("- the target", dict(tgt_mode="none", tgt_pts=0.0)),
       ("- the 568 arm (09:30 instead)", dict(open_m=570)),
       ("- the 5-min range (full half hour)", dict(range_end=570)),
       ("long only", dict(side="long")),
       ("short only", dict(side="short"))]
rows = []
for lab, q in VAR:
    t = c.trades(dict(P, **q))
    if t is None or len(t) == 0:
        rows.append(dict(arm=lab, n=0)); continue
    x = t["pct"].to_numpy()
    rows.append(dict(arm=lab, n=len(x), pct=float(x.mean()), tot=float(x.sum()),
                     win=float((x > 0).mean()),
                     pf=float(x[x > 0].sum() / -x[x < 0].sum()) if (x < 0).any() else np.nan,
                     mde=float(N.mde(x.std(ddof=1), len(x))),
                     d_vs_full=float(x.mean() - r.mean())))
do = pd.DataFrame(rows)
print(do.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
do.to_csv(os.path.join(OUT, "n23_dropone.csv"), index=False)

# ====================================================== 4  cost ladder
hd("4  COST LADDER -- WHERE THE RESULT DIES")
rows = []
for m in (0.0, 0.5, 1.0, 2.0, 4.0, 8.0):
    t = c.trades(dict(P, cost_mult=m))
    x = t["pct"].to_numpy()
    rows.append(dict(cost_mult=m, round_turn=c.cost * m, pct=float(x.mean()),
                     tot=float(x.sum()), win=float((x > 0).mean())))
cs = pd.DataFrame(rows)
print(cs.to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
cs.to_csv(os.path.join(OUT, "n23_cost.csv"), index=False)

# ====================================================== 5  daily Sharpe / Sortino
hd("5  SHARPE AND SORTINO ON THE DAILY ZERO-FILLED SERIES (the account's, not the trades')")
alld = np.unique(c.day[(c.mod >= 540) & (c.mod < 545)])


def daily(t, days):
    if t is None or len(t) == 0:
        return pd.Series(0.0, index=days)
    return pd.Series(t["pct"].to_numpy()).groupby(t["eday"].to_numpy()).sum() \
             .reindex(days).fillna(0.0)


is_d, oos_d = S.split_days(c, P, 0.5)
rows = []
for lab, dd in [("ALL", alld), ("IS", is_d), ("OOS", oos_d)]:
    d = daily(S.sub(tr, dd) if lab != "ALL" else tr, dd)
    v = d.to_numpy()
    dn = v[v < 0]
    rows.append(dict(block=lab, days=len(v), traded=int((v != 0).sum()),
                     mean=float(v.mean()), sd=float(v.std(ddof=1)),
                     sharpe=float(v.mean() / v.std(ddof=1) * np.sqrt(252)) if v.std(ddof=1) > 0 else np.nan,
                     sortino=float(v.mean() / dn.std(ddof=1) * np.sqrt(252)) if len(dn) > 1 else np.nan,
                     tot=float(v.sum())))
sh = pd.DataFrame(rows)
print(sh.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
print("  Zero-filled over every session that CAN trade. Over traded days only a filter is paid for "
      "trading less (`CLAUDE.md`), and here 57 trades sit on 54 of 92 sessions.")
sh.to_csv(os.path.join(OUT, "n23_sharpe.csv"), index=False)

# ====================================================== 6  stability
hd("6  MONTH BY MONTH -- 4.5 MONTHS IS THE WHOLE SAMPLE")
mo = pd.DataFrame({"m": pd.to_datetime(tr["eday"].to_numpy() * 86_400_000_000_000)
                        .to_period("M").astype(str), "pct": r})
g = mo.groupby("m")["pct"].agg(["size", "mean", "sum"])
print(g.to_string(float_format=lambda v: f"{v:+.4f}"))
g.to_csv(os.path.join(OUT, "n23_months.csv"))

# ====================================================== 7  power and deflation
hd("7  POWER AND DEFLATION")
sd = float(r.std(ddof=1))
mde = N.mde(sd, len(r))
print(f"  per-trade sd {sd:.4f}, n {len(r)}, MDE {mde:.4f}, delivered {r.mean():.4f} "
      f"({r.mean()/mde:.2f}x)")
need = int(np.ceil((2.802 * sd / r.mean()) ** 2)) if r.mean() > 0 else -1
rate = len(r) / max(yrs, 1e-9)
print(f"  trades to detect the observed effect: {need:,} against {len(r)} in hand "
      f"= {need/max(rate,1e-9):.1f} YEARS at this feed's {rate:.0f}/yr")
print(f"  (and the feed only carries the 09:00 range on 92 of 293 sessions, so that rate is "
      f"itself a property of the export and not of the market)")
LOOKS = 72 + 9 + 6 + 3 + 3 + 5      # walk-forward grid, drop-one, cost, resolutions, jitter, ratchet
print(f"\n  counted looks in this study: {LOOKS}; E[max t | pure noise] = "
      f"{N.e_max_normal(LOOKS):.3f} against the 2.802 detection needs")
if G is not None:
    per = float(r.mean() / sd)
    vt = (0.2 * per) ** 2          # dispersion of the trial Sharpes, taken from the walk-forward grid
    dsr = G.deflated_sharpe(per, len(r), LOOKS, var_trials=vt,
                            skew=float(pd.Series(r).skew()),
                            kurtosis=float(pd.Series(r).kurtosis() + 3.0))
    emx = G.expected_max_sharpe(vt, LOOKS)
    dv = dsr["dsr"] if isinstance(dsr, dict) else float(dsr)
    ev = emx["expected_max"] if isinstance(emx, dict) else float(emx)
    print(f"  per-trade Sharpe {per:.4f}; E[max | noise] over {LOOKS} looks {ev:.4f}; "
          f"deflated Sharpe {dv:.4f}")
    print(f"  verdict: {'PASS' if dv > 0.95 else 'FAIL'} at the 0.95 bar; the Sharpe is "
          f"{per/max(ev,1e-9):.2f}x its own noise floor")

print("\ndone.")
