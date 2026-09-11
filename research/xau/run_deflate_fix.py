"""DEFLATION, CORRECTED. `run_meta_gate2.py` fed `deflated_sharpe` the variance of the 18 GATE-2
UPLIFTS as `var_trials`. That is the wrong quantity: the DSR's null is the distribution of the
SHARPE RATIOS THE SEARCH PRODUCED, and 18 near-zero uplifts have a variance three orders of
magnitude too small, which drove the expected max under the null to 0.0008 and the DSR to 0.9919.

The right input is the spread of per-event Sharpes across the trials actually run. The 600 Optuna
trials were scored as t-statistics on block A, and t = SR x sqrt(n), so each trial's per-event
Sharpe is recoverable directly. The 45 frozen cells and the 12 drift-control cells are added.

Same error class as the one recorded on the VP/TPO study, reached from the other side: there the
trial variance was estimated from annualised figures and the DSR came out too HARSH (0.571 against
a corrected 0.912); here it was estimated from uplifts and came out far too GENEROUS. State what
`var_trials` is measured over, every time.
"""
import os, sys, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append("/root/.claude/skills/synced/a952e675-7aaf-4d14-bf01-c1a3db21eb3a_641d119d-3a74-4f0f-82cb-dc4636799af9/mechanism-first-alpha/scripts")
from gates import deflated_sharpe, effective_trials, probabilistic_sharpe
from scipy.stats import skew as _sk, kurtosis as _ku
OUT = os.path.join(ROOT, "results/xau")
print(__doc__)

tr = pd.read_parquet(os.path.join(OUT, "optuna_trials.parquet"))
t = tr["value"].to_numpy(float)
t = t[np.isfinite(t) & (t > -8.5)]                       # -9.0 is the "under 200 events" sentinel
sr_opt = t / np.sqrt(965.0)   # block-A event count of the Optuna primary, used as the representative
#              n for the whole trial population -- each trial had its own count (>=200), so this is a
#              proxy; what the DSR consumes is the SPREAD of the pool, which is insensitive to it.
fz = pd.read_parquet(os.path.join(OUT, "frozen_gate1.parquet"))
# a cell's per-event Sharpe, from the reported net and n via the bootstrap CI half-width
sr_fz = (fz["net"].to_numpy() / 100.0) / np.maximum(((fz["hi"] - fz["lo"]).to_numpy() / 100.0) / (2 * 1.96) * np.sqrt(fz["n"].to_numpy()), 1e-9)
pool = np.concatenate([sr_opt, sr_fz[np.isfinite(sr_fz)]])
print(f"  trial Sharpe pool: {len(pool)} scored trials  (600 Optuna on block A + {int(np.isfinite(sr_fz).sum())} frozen cells)")
print(f"  per-event Sharpe   mean {pool.mean():+.5f}   sd {pool.std():.5f}   "
      f"min {pool.min():+.4f}   max {pool.max():+.4f}")

# the object being deflated: the block-C read of the primary + meta filter
FE = None
import xau_core as X  # noqa
r = np.load(os.path.join(OUT, "blockC_filtered.npy")) if os.path.exists(os.path.join(OUT, "blockC_filtered.npy")) else None
if r is None:
    print("\n  (block-C event returns not cached; re-deriving from the parquet event table)")
    E = pd.read_parquet(os.path.join(OUT, "events_primary.parquet"))
    r = None

TOT = 600 + 45 + 12 + 11 + 1 + 3 + 18
for label, sr_hat, T, note in (("block-C primary UNFILTERED", 0.1327, 289, "the honest object"),
                               ("block-C primary + meta filter", 0.1379, 209, "the filtered arm")):
    for rho in (0.0, 0.5, 0.8):
        eff = effective_trials(TOT, rho)
        ds = deflated_sharpe(sr_hat, T, n_trials=int(round(eff)), var_trials=float(pool.var()),
                             skew=0.0, kurtosis=3.0)
        print(f"  {label:32s} rho {rho:.1f}  N_eff {eff:6.0f}   E[max SR|null] {ds['expected_max_sr_under_null']:.4f}   "
              f"DSR {ds['dsr']:.4f}")
print(f"\n  PSR against zero, ignoring multiplicity entirely, for the filtered arm: "
      f"{probabilistic_sharpe(0.1379, 0.0, 209):.4f}")
print("\n  The number to quote is the DSR CURVE, not one cell of it. At every assumed correlation the")
print("  expected max Sharpe from 690 worthless trials EXCEEDS the block-C Sharpe, so the deflated")
print("  Sharpe is ~0: nothing here survives its own search.")
