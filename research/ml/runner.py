"""The experiment driver: every model family, fitted the same way, against the same controls.

Ray parallelises across model families. It is used for exactly that -- the folds inside a family
are sequential because the boosters already use every core, and nesting the two makes both slower.

The shuffled-label control is not optional and not a flag. It runs beside every real fit, on the
same folds, with the same model, so the reader never has to take "AUC 0.508" on trust: the number
next to it says what this pipeline produces on noise.
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from ml import track
from ml.dataset import build
from ml.metrics import HEADER, deflate, evaluate
from ml.splits import PurgedKFold, locked_split
from ml.zoo import REGISTRY, predict_proba


def fit_oof(model_name, params, X, y_dollars, sess, horizon, n_splits=5, shuffle_labels=False,
            seed=20250822, n_threads=None):
    """Out-of-fold probabilities on purged, embargoed folds."""
    from ml.zoo import thread_kwargs
    spec = REGISTRY[model_name]
    params = dict(params or {})
    params.update(thread_kwargs(model_name, n_threads))
    cv = PurgedKFold(n_splits=n_splits, horizon=horizon, embargo=0.01)
    Xv = np.asarray(X, float)
    lab = (y_dollars > 0).astype(int)
    if shuffle_labels:
        lab = np.random.default_rng(seed).permutation(lab)
    oof = np.full(len(Xv), np.nan)
    for tr, te in cv.split(len(Xv)):
        m = spec.build(**params)
        m.fit(Xv[tr], lab[tr])
        oof[te] = predict_proba(m, Xv[te])
    return oof


def _one_family(model_name, Xr, yr, sr, horizon, n_splits, n_threads=None):
    """Real fit + shuffled control for one family. Returns a dict, picklable for Ray."""
    t0 = time.time()
    oof = fit_oof(model_name, None, Xr, yr, sr, horizon, n_splits, n_threads=n_threads)
    s_real = evaluate(oof, yr, sr)
    oof_s = fit_oof(model_name, None, Xr, yr, sr, horizon, n_splits, shuffle_labels=True,
                    n_threads=n_threads)
    s_ctrl = evaluate(oof_s, yr, sr)
    return dict(model=model_name, real=s_real, control=s_ctrl, secs=time.time() - t0)


def run_families(models, Xr, yr, sr, horizon, n_splits=5, use_ray=True):
    """Fit every family. Ray when available, sequential otherwise -- identical results."""
    import os
    n_cpu = max(1, os.cpu_count() or 1)
    if not use_ray:
        # Sequential: give each family every core.
        return [_one_family(m, Xr, yr, sr, horizon, n_splits, n_cpu) for m in models]
    # Parallel: divide the cores among concurrently running families so the machine sees n_cpu
    # threads in total rather than n_families x n_cpu.
    per = max(1, n_cpu // min(len(models), n_cpu))
    import os
    import ray
    if not ray.is_initialized():
        # Ray workers are fresh interpreters: they do not inherit the driver's sys.path, so
        # `import ml.runner` fails on them unless research/ is on PYTHONPATH explicitly. Absolute,
        # because the worker's cwd is not guaranteed to be the repo root.
        research_dir = str((__import__("pathlib").Path(__file__).resolve().parent.parent))
        ray.init(ignore_reinit_error=True, log_to_driver=False, include_dashboard=False,
                 num_cpus=n_cpu,
                 runtime_env={"env_vars": {
                     "PYTHONPATH": research_dir + os.pathsep + os.environ.get("PYTHONPATH", ""),
                     "OMP_NUM_THREADS": "1",     # families run in parallel; don't oversubscribe
                 }})
    remote = ray.remote(_one_family)
    Xr_ref = ray.put(Xr); yr_ref = ray.put(yr); sr_ref = ray.put(sr)
    futures = [remote.remote(m, Xr_ref, yr_ref, sr_ref, horizon, n_splits, per) for m in models]
    return ray.get(futures)


def main(models=None, n_splits=5, tune_model="lightgbm", n_trials=25, use_ray=True,
         mlflow_on=True) -> None:
    models = models or ["logistic", "random_forest", "hist_gb", "lightgbm", "xgboost",
                        "catboost", "torch_mlp"]
    X, y, meta = build()
    sess = meta.sess.to_numpy()
    horizon = int(np.nanpercentile(meta.bars_held, 95))

    res_m, hold_m = locked_split(sess, holdout_frac=0.2)
    Xr, yr, sr = X[res_m], y[res_m], sess[res_m]
    Xh, yh, sh = X[hold_m], y[hold_m], sess[hold_m]

    print("=" * 104)
    print("MODEL LAYER — every family, purged folds, shuffled control, locked holdout")
    print("=" * 104)
    print(f"\n  {len(X):,} rows x {X.shape[1]} features over {meta.sess.nunique()} sessions")
    print(f"  label: $900 stop / $1,500 target / 16:00 flat, ${19.00:.2f} round turn charged")
    print(f"  purge horizon {horizon} bars (95th pct of holding time), embargo 1%")
    print(f"  research {res_m.sum():,} rows / LOCKED holdout {hold_m.sum():,} rows (split on sessions)")
    print(f"\n  BENCHMARK — take every bar long: research ${yr.mean():.2f}/trade, "
          f"holdout ${yh.mean():.2f}/trade")
    print("  A model has to beat that number, not zero.\n")

    with track.run("nq-intraday", "families", {"n_splits": n_splits, "horizon": horizon},
                   enabled=mlflow_on) as log:
        out = run_families(models, Xr, yr, sr, horizon, n_splits, use_ray=use_ray)
        print(HEADER)
        for r in sorted(out, key=lambda d: -(d["real"].best_lift if np.isfinite(d["real"].best_lift) else -1e9)):
            print(r["real"].line(r["model"]))
            print(r["control"].line(f"  ^ shuffled control"))
            track.log_result(log, r["real"], f"{r['model']}_real")
            track.log_result(log, r["control"], f"{r['model']}_control")

    best = max(out, key=lambda d: d["real"].best_lift if np.isfinite(d["real"].best_lift) else -1e9)
    print(f"\n  best family on research: {best['model']} "
          f"(lift ${best['real'].best_lift:.2f}/trade, t(day) {best['real'].t_day:.2f})")
    print(f"  its shuffled control:    lift ${best['control'].best_lift:.2f}/trade, "
          f"t(day) {best['control'].t_day:.2f}")

    # ---- tuning, with the search priced ----
    from ml.tune import search
    print("\n" + "=" * 104)
    print(f"OPTUNA — {n_trials} trials on {tune_model}, and what {n_trials} trials cost")
    print("=" * 104 + "\n")
    with track.run("nq-intraday", f"tune-{tune_model}", {"n_trials": n_trials},
                   enabled=mlflow_on) as log:
        best_params, s_tuned, report, _ = search(tune_model, Xr, yr, sr, horizon,
                                                 n_trials=n_trials, n_splits=n_splits, logger=log)
        track.log_result(log, s_tuned, "tuned", n_trials=report["n_trials"])
    print(f"  best lift on research      ${report['best_lift']:.2f}/trade, t(day) {report['t_day']:.2f}")
    print(f"  spread across {report['n_trials']} trials  ${report['spread_across_trials']:.2f} "
          f"(worst trial ${report['worst_trial']:.2f})")
    print(f"  hurdle for {report['n_trials']} trials     t > {report['hurdle']:.2f}  "
          f"-> {'CLEARS' if report['clears'] else 'DOES NOT CLEAR'}")
    print(f"  params: {best_params}")

    # ---- the locked holdout, opened once ----
    print("\n" + "=" * 104)
    print("LOCKED HOLDOUT — opened once, with the tuned model and the untuned best family")
    print("=" * 104 + "\n")
    print(HEADER)
    lab_r = (yr > 0).astype(int)
    for label, name, params in (("untuned " + best["model"], best["model"], None),
                                (f"tuned {tune_model}", tune_model, best_params)):
        m = REGISTRY[name].build(**(params or {}))
        m.fit(np.asarray(Xr, float), lab_r)
        p = predict_proba(m, np.asarray(Xh, float))
        s = evaluate(p, yh, sh)
        print(s.line(label))
    print(f"\n  take-every-bar on the holdout: ${yh.mean():.2f}/trade — the number to beat")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=None)
    ap.add_argument("--trials", type=int, default=25)
    ap.add_argument("--splits", type=int, default=5)
    ap.add_argument("--tune-model", default="lightgbm")
    ap.add_argument("--no-ray", action="store_true")
    ap.add_argument("--no-mlflow", action="store_true")
    a = ap.parse_args()
    main(models=a.models, n_splits=a.splits, tune_model=a.tune_model, n_trials=a.trials,
         use_ray=not a.no_ray, mlflow_on=not a.no_mlflow)
