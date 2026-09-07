"""A model layer for this repository's intraday futures research.

The libraries here (LightGBM, XGBoost, CatBoost, PyTorch, scikit-learn, Optuna, MLflow, Ray) all
make it cheaper to search. Everything this repository has measured says that is the dangerous
direction: on 225,792 initial-balance configurations a RANDOM pick landed at the 51.5th percentile
of locked-holdout P&L and the best-of-143,536 landed at the 13.4th, with in-sample/out-of-sample
rank correlation of -0.079. Optuna with 500 trials is that experiment with a better UI.

So the discipline is inside the API rather than beside it, and the parts that are easy to skip are
the parts that are not optional:

  * every split is PURGED and EMBARGOED, because triple-barrier labels overlap;
  * every fit is scored in DOLLARS after costs, not in AUC alone;
  * every experiment runs a SHUFFLED-LABEL control automatically, so the reader always sees what
    the same pipeline produces on noise;
  * every t-statistic is DAY-CLUSTERED, because bars inside a session are not independent;
  * every tuned result is reported next to the hurdle its own trial count implies;
  * the LOCKED HOLDOUT is a separate call you make once, and it refuses to run twice on one object.

Modules
-------
  dataset  causal feature assembly and triple-barrier labels
  splits   purged + embargoed K-fold, session-aware
  zoo      one interface over LightGBM / XGBoost / CatBoost / sklearn / PyTorch
  metrics  cost-aware, day-clustered evaluation
  tune     Optuna search with the search cost priced in
  track    MLflow logging to a local file store
  runner   Ray-parallel experiment driver
"""

__all__ = ["dataset", "splits", "zoo", "metrics", "tune", "track", "runner"]
