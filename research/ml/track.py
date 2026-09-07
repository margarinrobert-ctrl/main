"""MLflow logging to a local file store.

What is worth tracking here is not the metric -- it is the DENOMINATOR. The failure mode this
repository keeps measuring is a good number selected out of many, and the only defence is a record
of how many were looked at. So every run logs its trial count, and `log_result` refuses to record a
tuned metric without one.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

# MLflow 3 put the filesystem store into maintenance mode and raises on it, so the default is the
# SQLite backend it recommends. Local file, no server, nothing to run -- but it is a real database,
# so `mlflow ui --backend-store-uri sqlite:///research/mlruns.db` works against it directly.
DEFAULT_URI = f"sqlite:///{Path('research/mlruns.db').resolve()}"


def _mlflow():
    import mlflow
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", DEFAULT_URI))
    return mlflow


@contextmanager
def run(experiment: str, name: str, params: dict | None = None, enabled: bool = True):
    """Context manager yielding a logger. A no-op object when disabled, so callers stay clean."""
    if not enabled:
        class _Null:
            def metric(self, *a, **k): pass
            def param(self, *a, **k): pass
            def text(self, *a, **k): pass
        yield _Null()
        return

    mlflow = _mlflow()
    mlflow.set_experiment(experiment)
    with mlflow.start_run(run_name=name):
        if params:
            mlflow.log_params({k: str(v)[:250] for k, v in params.items()})

        class _Log:
            def metric(self, k, v):
                import math
                if v is not None and isinstance(v, (int, float)) and math.isfinite(v):
                    mlflow.log_metric(k, float(v))

            def param(self, k, v):
                mlflow.log_param(k, str(v)[:250])

            def text(self, body, path):
                mlflow.log_text(body, path)

        yield _Log()


def log_result(logger, score, prefix: str, n_trials: int | None = None) -> None:
    """Log a Score. A tuned result MUST carry its trial count or this raises.

    That is deliberate: a Sharpe with no denominator is the thing this whole protocol exists to
    stop, and making it an error is cheaper than making it a convention.
    """
    from .metrics import deflate
    logger.metric(f"{prefix}_auc", score.auc)
    logger.metric(f"{prefix}_take_all", score.take_all)
    logger.metric(f"{prefix}_lift", score.best_lift)
    logger.metric(f"{prefix}_t_day", score.t_day)
    logger.metric(f"{prefix}_n", score.n)
    if n_trials is not None:
        d = deflate(score.t_day, n_trials)
        logger.metric(f"{prefix}_hurdle", d["hurdle"])
        logger.metric(f"{prefix}_clears_hurdle", float(d["clears"]))
        logger.param(f"{prefix}_n_trials", n_trials)
    elif prefix.startswith("tuned"):
        raise ValueError("a tuned result must be logged with n_trials -- see module docstring")
