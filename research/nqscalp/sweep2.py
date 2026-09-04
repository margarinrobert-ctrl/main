"""Stage 2: the parts of the user's own script that were switched off and never
measured, plus the StochRSI trigger parameters - which are the actual trigger.

Run per instrument (argv[1]); the indicator caches are keyed by period alone, so
one process must not serve two instruments.

Stage A screens on expectancy on both instruments. Stage B runs the matched
control only on what survives, and the survivor must ALSO be positive on the
other instrument - the cross-instrument requirement is a front gate here, not a
final check, because §31 showed NAS-only results reverse sign on US30.
"""
import numpy as np, pandas as pd, sys, itertools, json, warnings
sys.path.insert(0, "/home/user/main/research/donchian"); sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import nqs, cache, data as D

SYM = sys.argv[1]
OUT = "/home/user/main/docs/nqscalp/"
TM, ORD = "barclose", "adverse"
SPEC = {"NAS":  dict(point_value=20.0, tick=0.25, commission=1.24, qty=1),
        "US30": dict(point_value=5.0,  tick=1.00, commission=1.24, qty=1)}[SYM]
BASE = dict(**SPEC, dist_units="atr", pullback_atr=1.15, trail_arm_atr=1.0,
            trail_offset_atr=0.5, sess_start_h=6, sess_start_m=0,
            sess_end_h=11, sess_end_m=30)
df = D.load(SYM); B = cache.build(df); R, H = D.blocks(df)
RT = 2 * 1.0 * SPEC["tick"] + 2 * SPEC["commission"] / SPEC["point_value"]


def run(**kw):
    I, p = cache.indicators(df, B, **{**BASE, **kw})
    (lo, sh), _ = nqs.conditions(df, I, p)
    tr = nqs.simulate(df, I, p, lo & R, sh & R, order=ORD, trail_mode=TM)
    if len(tr) < 60: return None
    yy = pd.DatetimeIndex(tr.ts).year
    ex = tr[(yy != 2020) & (yy != 2022)]
    return dict(n=len(tr), net=float(tr.net_pts.mean()),
                ex_crisis=float(ex.net_pts.mean()) if len(ex) > 20 else np.nan)


print("=" * 118)
print(f"32. THE SWITCHED-OFF FEATURES IN THE SUPPLIED SCRIPT - {SYM}, research, barclose/adverse")
print(f"    round turn {RT:.2f} pts")
print("=" * 118)
FEATURES = [
    ("baseline (all off, as tested)", {}),
    ("early exit: StochRSI fade", dict(exit_stoch_fade=True)),
    ("early exit: slow-EMA break", dict(exit_ema_break=True)),
    ("early exit: trend-EMA break", dict(exit_trend_break=True)),
    ("early exit: fade + EMA break", dict(exit_stoch_fade=True, exit_ema_break=True)),
    ("quick scalp 8 pts / 6 bars", dict(quick_scalp=True, quick_target=8.0, quick_max_bars=6)),
    ("quick scalp 0.5 ATR / 6 bars", dict(quick_scalp=True, quick_target=0.5 * float(np.nanmedian(cache.atr(B, 14)[R])), quick_max_bars=6)),
    ("quick scalp 1.0 ATR / 12 bars", dict(quick_scalp=True, quick_target=1.0 * float(np.nanmedian(cache.atr(B, 14)[R])), quick_max_bars=12)),
    ("volume thrust filter 1.2x", dict(use_volume=True, vol_mult=1.2)),
    ("volume thrust filter 1.5x", dict(use_volume=True, vol_mult=1.5)),
    ("MACD momentum confirm", dict(use_macd=True)),
    ("volume + MACD", dict(use_volume=True, vol_mult=1.2, use_macd=True)),
]
frows = []
for lbl, kw in FEATURES:
    r = run(**kw)
    if r is None:
        print(f"  {lbl:<34} too few trades"); continue
    frows.append(dict(sym=SYM, feature=lbl, **r))
    print(f"  {lbl:<34} n={r['n']:>5}  net {r['net']:>+7.2f}  ex-crisis {r['ex_crisis']:>+7.2f}"
          f"   {'ABOVE RT' if r['net'] > RT else ''}")
pd.DataFrame(frows).to_csv(OUT + f"features_{SYM}.csv", index=False)

print("\n" + "=" * 118)
print(f"33. THE STOCHRSI TRIGGER PARAMETERS - {SYM}. This is the actual trigger, never swept before.")
print("=" * 118)
GRID = list(itertools.product([7, 14, 21], [7, 14, 21], [1, 3, 5], [1, 3],
                              [(10, 90), (20, 80), (30, 70)], [4, 8, 16]))
print(f"  {len(GRID)} configurations")
srows = []
for i, (rl, sl, ks, ds, (osv, obv), rlb) in enumerate(GRID):
    r = run(rsi_len=rl, stoch_len=sl, k_smooth=ks, d_smooth=ds,
            oversold=float(osv), overbought=float(obv), reset_lookback=rlb)
    if r is None: continue
    srows.append(dict(sym=SYM, rsi=rl, stoch=sl, k=ks, d=ds, os=osv, ob=obv,
                      reset=rlb, **r))
    if (i + 1) % 100 == 0: print(f"    {i+1}/{len(GRID)}")
S = pd.DataFrame(srows); S.to_csv(OUT + f"stochrsi_{SYM}.csv", index=False)
print(f"\n  {len(S)} cells with >=60 trades")
print(f"  net expectancy: p5 {S.net.quantile(.05):+.2f}  median {S.net.median():+.2f}  "
      f"p95 {S.net.quantile(.95):+.2f}  max {S.net.max():+.2f}")
print(f"  cells above the round turn ({RT:.2f}): {(S.net > RT).sum()} / {len(S)}")
print(f"  and still above it without 2020+2022: {((S.net > RT) & (S.ex_crisis > RT)).sum()}")
print("\n  MARGINALS")
for col in ("rsi", "stoch", "k", "d", "os", "reset"):
    m = S.groupby(col).agg(net=("net", "mean"), ex=("ex_crisis", "mean"), n=("n", "mean"))
    print(f"    by {col:<6}: " + "   ".join(
        f"{k}: {r.net:+.2f}/{r.ex:+.2f}" for k, r in m.iterrows()))
print("\n  TOP 10 BY NET")
print(f"  {'rsi':>4}{'stoch':>6}{'k':>3}{'d':>3}{'os/ob':>8}{'reset':>6}{'n':>6}{'net':>8}{'ex-crisis':>11}")
for _, x in S.sort_values("net", ascending=False).head(10).iterrows():
    print(f"  {int(x.rsi):>4}{int(x.stoch):>6}{int(x.k):>3}{int(x.d):>3}"
          f"{f'{int(x.os)}/{int(x.ob)}':>8}{int(x.reset):>6}{int(x.n):>6}"
          f"{x.net:>+8.2f}{x.ex_crisis:>+11.2f}")
