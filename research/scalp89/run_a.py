"""A. What each piece of the configured script is worth. NQ 5m unless stated, research block."""
from __future__ import annotations
import os, sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s89_core as M
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)

def line(t): print("\n" + "=" * 124 + f"\n{t}\n" + "=" * 124)
def row(nm, s, extra=""):
    print(f"  {nm:44s}{s['n']:>6d}{s['pct']:>10.4f}{s['pf']:>8.3f}{s['win']:>7.1f}"
          f"{s['R']:>8.3f}{s['usd_tot']:>11,.0f}{s['hold']:>7.0f}{extra}")
def hdr(): print(f"  {'variant':44s}{'n':>6s}{'%/trade':>10s}{'PF':>8s}{'win':>7s}{'R':>8s}{'$ 5 MNQ':>11s}{'hold':>7s}")
def R(t): return t[t.block == "research"]

D = M.build("NQ", 5)
base = M.run(D)
line("1. THE EXIT MACHINE -- the configured 15/8-point trail against the alternatives")
hdr()
for nm, kw in (("as configured: trail fixed 15/8, stop 1.5 / tgt 2.5 ATR", dict()),
               ("trail OFF: plain 1.5 / 2.5 ATR bracket", dict(cfg=dict(M.CFG, trail_on=0))),
               ("trail in ATR (code default 1.0 arm / 0.5 off)", dict(cfg=dict(M.CFG, trail_arm=np.nan, trail_off=np.nan))),
               ("trail fixed 30 / 15 points", dict(cfg=dict(M.CFG, trail_arm=30.0, trail_off=15.0))),
               ("trail fixed 60 / 30 points", dict(cfg=dict(M.CFG, trail_arm=60.0, trail_off=30.0))),
               ("no target (stop + trail only)", dict(cfg=dict(M.CFG, tgt_mult=99.0))),
               ("no target, no trail (stop only)", dict(cfg=dict(M.CFG, tgt_mult=99.0, trail_on=0)))):
    cfg = kw.get("cfg", M.CFG)
    if np.isnan(cfg.get("trail_arm", 0.0)):
        # ATR-scaled trail: arm 1.0 ATR / offset 0.5 ATR, using the median ATR as a proxy
        # (a per-trade ATR trail needs the kernel to take arrays -- done in run_c)
        a = float(np.nanmedian(D["atr"][D["blocks"]["research"]]))
        cfg = dict(cfg, trail_arm=1.0 * a, trail_off=0.5 * a)
        nm += f"  [~{a:.0f}pt ATR proxy]"
    t = M.run(D, cfg=cfg); r = R(t)
    mix = r["exit"].value_counts(normalize=True).mul(100).round(0).to_dict()
    row(nm, M.stats(r), "   " + " ".join(f"{k}{int(v)}%" for k, v in mix.items()))
print(f"\n  median ATR(14) on research 5m bars: {np.nanmedian(D['atr'][D['blocks']['research']]):.1f} points,"
      f" so the 1.5x stop is ~{1.5*np.nanmedian(D['atr'][D['blocks']['research']]):.0f} pts and the trail arms at 15.")

line("2. THE ORDER-MODEL GAPS -- naked fill bar, and Pine's intrabar path")
hdr()
for nm, kw in (("script: naked fill bar, Pine path", dict(protect_fill=0, path=1)),
               ("bracket live on the fill bar, Pine path", dict(protect_fill=1, path=1)),
               ("naked fill bar, STOP-FIRST (conservative)", dict(protect_fill=0, path=0)),
               ("bracket on fill bar, stop-first", dict(protect_fill=1, path=0))):
    row(nm, M.stats(R(M.run(D, **kw))))

line("3. ENTRY ABLATION -- drop one condition at a time (trail OFF so the entry is readable)")
hdr()
C0 = dict(M.CFG, trail_on=0)
t0 = R(M.run(D, cfg=C0)); row("all conditions (trail off)", M.stats(t0))
for nm, cfg in (("no EMA89 trend gate", None), ("no 15-pt pullback depth", dict(C0, min_pb=0.0)),
                ("no EMA touch (any low)", None), ("no StochRSI reset", dict(C0, os_lvl=101.0, ob_lvl=-1.0)),
                ("no session window (all hours)", dict(C0, sess_start=0, sess_end=24*60))):
    if cfg is None:
        D2 = dict(D)
        if nm.startswith("no EMA89"):
            D2["e_tr"] = np.where(np.isfinite(D["e_tr"]), -1e18, np.nan)   # up always true...
            # ...but that kills shorts; handle both by scoring long-only + short-only sum below
            sig_l = M.signals(dict(D, e_tr=np.full(D["n"], -1e18)), C0)
            sig_s = M.signals(dict(D, e_tr=np.full(D["n"], 1e18)), C0)
            sig = np.where(sig_l == 1, 1, np.where(sig_s == -1, -1, 0))
            t = M.run(D, cfg=C0, side_override=sig)
        else:
            D2["e_f"] = np.full(D["n"], 1e18); D2["e_s"] = np.full(D["n"], 1e18)
            # touch always true for longs; for shorts need -1e18 -- run both and merge
            sig_l = M.signals(dict(D, e_f=np.full(D["n"], 1e18), e_s=np.full(D["n"], 1e18)), C0)
            sig_s = M.signals(dict(D, e_f=np.full(D["n"], -1e18), e_s=np.full(D["n"], -1e18)), C0)
            sig = np.where(sig_l == 1, 1, np.where(sig_s == -1, -1, 0))
            t = M.run(D, cfg=C0, side_override=sig)
    else:
        t = M.run(D, cfg=cfg)
    row(nm, M.stats(R(t)))
row("longs only (trail off)", M.stats(R(M.run(D, cfg=C0, side_override=np.where(M.signals(D, C0) == 1, 1, 0)))))
row("shorts only (trail off)", M.stats(R(M.run(D, cfg=C0, side_override=np.where(M.signals(D, C0) == -1, -1, 0)))))

line("4. SESSION -- the window includes the pre-open block this branch has measured as worst four times")
hdr()
for nm, ss, se, fl in (("as configured 07:01-12:30 NY (06:01-11:30 Chicago), no flatten", 7*60+1, 12*60+30, 0),
                       ("09:30-12:30 NY, no flatten", 9*60+30, 12*60+30, 0),
                       ("09:30-16:00 NY, no flatten", 9*60+30, 16*60, 0),
                       ("as configured + flatten 15:55", 7*60+1, 12*60+30, 1),
                       ("09:30-12:30 + flatten 15:55", 9*60+30, 12*60+30, 1),
                       ("all hours, no flatten", 0, 24*60, 0)):
    t = M.run(D, cfg=dict(C0, sess_start=ss, sess_end=se), use_flat=fl)
    r = R(t); ov = 100 * (r["exit"] == "eod").mean()
    row(nm, M.stats(r))
