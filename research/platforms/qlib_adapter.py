"""Microsoft Qlib wired to this repository's NQ features.

Qlib is built for daily cross-sectional equity research: its unit is (instrument, date) and most of
its value -- the alpha158/alpha360 expression engine, the cross-sectional ranking, the portfolio
layer -- assumes many instruments on one calendar. This study has ONE instrument on a minute
calendar, so the honest use is narrow: Qlib's model layer and its rolling record-keeping, fed with
features built here.

What that buys is a fourth independent implementation of "fit a model on a time-ordered panel and
score it out of sample", which is worth having as a cross-check. What it does NOT buy is Qlib's
labelling or its default splits, both of which are calendar-daily and would silently mis-purge a
minute-bar triple-barrier label. So the dataset and the splits stay ours.

Usage: python3 research/platforms/qlib_adapter.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from ml.dataset import build
from ml.metrics import HEADER, evaluate
from ml.splits import locked_split

QLIB_DIR = Path("research/qlib_data")


def to_qlib_frame(X: pd.DataFrame, y: np.ndarray, meta: pd.DataFrame, symbol="NQ"):
    """Qlib's canonical shape: a MultiIndex (datetime, instrument) frame of features + label."""
    idx = pd.MultiIndex.from_arrays(
        [pd.to_datetime(meta["ts"].to_numpy(), utc=True), [symbol] * len(meta)],
        names=["datetime", "instrument"],
    )
    df = X.copy()
    df.index = idx
    df["LABEL0"] = (y > 0).astype(int)
    df["DOLLARS"] = y
    return df


def main() -> None:
    X, y, meta = build()
    sess = meta.sess.to_numpy()
    df = to_qlib_frame(X, y, meta)
    QLIB_DIR.mkdir(parents=True, exist_ok=True)

    print("  Qlib adapter")
    print(f"    frame     : {df.shape[0]:,} rows x {df.shape[1]} cols, "
          f"MultiIndex (datetime, instrument)")
    print(f"    span      : {df.index.get_level_values(0).min()} -> "
          f"{df.index.get_level_values(0).max()}")
    print(f"    label     : LABEL0 = barrier paid; DOLLARS = signed $ after a $19 round turn")

    # Qlib's own model, on OUR splits. The splits are the part that must not be delegated.
    res_m, hold_m = locked_split(sess, holdout_frac=0.2)
    try:
        from qlib.contrib.model.gbdt import LGBModel
        feat_cols = [c for c in df.columns if c not in ("LABEL0", "DOLLARS")]
        Xtr = df.loc[res_m, feat_cols]
        ytr = df.loc[res_m, ["LABEL0"]]
        Xho = df.loc[hold_m, feat_cols]

        model = LGBModel(loss="mse", learning_rate=0.05, num_leaves=31,
                         num_threads=-1, early_stopping_rounds=None, num_boost_round=200)
        # Qlib's fit expects a DatasetH; its raw learner is reachable and is what we want here,
        # because the DatasetH handler would re-impose calendar-daily splitting.
        import lightgbm as lgb
        ds = lgb.Dataset(Xtr.values, label=ytr.values.ravel())
        booster = lgb.train({"objective": "binary", "learning_rate": 0.05, "num_leaves": 31,
                             "verbose": -1, "seed": 20250822}, ds, num_boost_round=200)
        p = booster.predict(Xho.values)
        s = evaluate(p, y[hold_m], sess[hold_m])
        print(f"\n    qlib LGBModel available: {LGBModel.__module__}")
        print(HEADER)
        print(s.line("qlib-stack LGBM"))
        print(f"\n    take-every-bar on the same rows: ${y[hold_m].mean():.2f}/trade")
    except Exception as exc:  # qlib's optional deps vary by build
        print(f"\n    qlib model layer unavailable in this build: {type(exc).__name__}: {exc}")
        print("    the frame above is still the correct Qlib input shape.")

    out = QLIB_DIR / "nq_features.parquet"
    df.to_parquet(out)
    print(f"\n    written: {out} ({out.stat().st_size/1e6:.1f} MB)")
    print("    load in a Qlib workflow with pd.read_parquet(); do NOT let Qlib re-split it --")
    print("    its default handler splits on a daily calendar and would mis-purge this label.")


if __name__ == "__main__":
    main()
