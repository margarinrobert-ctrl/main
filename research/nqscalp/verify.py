"""Causality and correctness checks that gate every number downstream.

1. TRUNCATION. Recompute every indicator on data[:i+1] and require the value at
   bar i to equal the full-sample value. Any look-ahead - a centred window, a
   backfill, a global normalisation - shows up here and nowhere else.
2. EXECUTION ALIGNMENT. Every fill bar must be strictly after its signal bar,
   and no exit may precede its fill. Same-bar execution is the single most
   productive way to manufacture alpha and is invisible to a feature audit.
3. INDICATOR CROSS-CHECK. Wilder RMA/ATR/RSI against a literal transcription of
   the textbook recursions, independent of the vectorised code.
4. FUTURE-BAR PROBE. Shift the whole price series forward one bar inside the
   simulator; a strategy reading its own fill bar gets better, not worse.
"""
import numpy as np, pandas as pd, sys
sys.path.insert(0, "/home/user/main/research/donchian"); sys.path.insert(0, ".")
import nqs, data as D

df = D.load("NAS")
I, p = nqs.indicators(df)
(lo, sh), in_sess = nqs.conditions(df, I, p)
fails = []

print("=" * 96); print("1. TRUNCATION - indicators recomputed on data[:i+1] must match"); print("=" * 96)
rng = np.random.default_rng(7)
probe = rng.choice(np.arange(5000, len(df)), size=40, replace=False)
maxerr = {k: 0.0 for k in ("trend", "fast", "slow", "atr", "k", "d", "swing_hi", "swing_lo")}
for i in sorted(probe):
    sub = df.iloc[: i + 1]
    J, _ = nqs.indicators(sub)
    for k in maxerr:
        a, b = J[k][-1], I[k][i]
        if np.isfinite(a) and np.isfinite(b):
            maxerr[k] = max(maxerr[k], abs(a - b) / max(abs(b), 1e-9))
for k, v in maxerr.items():
    ok = v < 1e-9
    print(f"  {k:<10} max relative deviation {v:.3e}   {'OK' if ok else 'LOOK-AHEAD'}")
    if not ok: fails.append(f"truncation {k}")

print("\n" + "=" * 96); print("2. EXECUTION ALIGNMENT"); print("=" * 96)
tr = nqs.simulate(df, I, p, lo, sh)
bad_fill = int((tr.fill_bar <= tr.sig_bar).sum())
bad_exit = int((tr.exit_bar < tr.fill_bar).sum())
overlap = int((tr.sig_bar.values[1:] < tr.exit_bar.values[:-1]).sum())
fill_is_open = float(np.abs(tr.fill.values - (I["o"][tr.fill_bar.values] + tr.side.values * p["slippage_ticks"] * nqs.TICK)).max())
print(f"  fills at or before their signal bar : {bad_fill}   {'OK' if not bad_fill else 'LEAK'}")
print(f"  exits before their fill bar         : {bad_exit}   {'OK' if not bad_exit else 'LEAK'}")
print(f"  overlapping positions               : {overlap}   {'OK' if not overlap else 'BUG'}")
print(f"  fill price != next open + slippage  : {fill_is_open:.2e}   {'OK' if fill_is_open < 1e-9 else 'BUG'}")
print(f"  signal->fill gap, unique values     : {sorted(set((tr.fill_bar - tr.sig_bar).tolist()))}")
for nm, v in (("bad_fill", bad_fill), ("bad_exit", bad_exit), ("overlap", overlap)):
    if v: fails.append(nm)

print("\n" + "=" * 96); print("3. INDICATOR CROSS-CHECK vs literal textbook recursions"); print("=" * 96)
c = df.close.values.astype(float); h = df.high.values.astype(float); l = df.low.values.astype(float)
def lit_rma(x, n):
    out = np.full(len(x), np.nan); s = np.nanmean(x[:n]); out[n-1] = s
    for i in range(n, len(x)):
        s = (s * (n - 1) + x[i]) / n; out[i] = s
    return out
tr_lit = np.empty(len(c)); tr_lit[0] = h[0] - l[0]
for i in range(1, len(c)):
    tr_lit[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
atr_lit = lit_rma(tr_lit, 14)
d_atr = np.nanmax(np.abs(atr_lit - I["atr"]))
g = np.maximum(np.diff(c, prepend=c[0]), 0.0); g[0] = np.nan
ls = np.maximum(-np.diff(c, prepend=c[0]), 0.0); ls[0] = np.nan
rsi_lit = 100 - 100 / (1 + lit_rma(g[1:], 14) / lit_rma(ls[1:], 14))
rsi_mine = nqs.rsi(c, 14)[1:]
d_rsi = np.nanmax(np.abs(rsi_lit - rsi_mine))
print(f"  ATR(14) Wilder  max abs deviation : {d_atr:.3e}   {'OK' if d_atr < 1e-8 else 'MISMATCH'}")
print(f"  RSI(14) Wilder  max abs deviation : {d_rsi:.3e}   {'OK' if d_rsi < 1e-8 else 'MISMATCH'}")
if d_atr >= 1e-8: fails.append("atr")
if d_rsi >= 1e-8: fails.append("rsi")

print("\n" + "=" * 96); print("4. FUTURE-BAR PROBE - a leaky engine improves when fed the future"); print("=" * 96)
base = nqs.stats(tr)["exp_pts"]
fut = df.copy()
for col in ("open", "high", "low", "close"):
    fut[col] = fut[col].shift(-1)
fut = fut.iloc[:-1].reset_index(drop=True)
Jf, pf_ = nqs.indicators(fut)
(lof, shf), _ = nqs.conditions(fut, Jf, pf_)
trf = nqs.simulate(fut, Jf, pf_, lof, shf)
print(f"  as written                : {base:+.3f} pts/trade")
print(f"  prices shifted one forward : {nqs.stats(trf)['exp_pts']:+.3f} pts/trade")
print("  (a big JUMP here would mean the engine already reads the fill bar)")

print("\n" + "=" * 96)
print("VERIFICATION: " + ("ALL CHECKS PASS" if not fails else f"FAILURES: {fails}"))
print("=" * 96)
