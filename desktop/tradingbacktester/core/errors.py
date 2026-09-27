"""Exception hierarchy for the application.

Every error that can reasonably be produced by user input derives from
:class:`BacktesterError` and carries a *user message* that is safe to show in a
dialog, plus optional *detail* that goes to the log file only.  The UI layer
never shows a raw traceback: it catches :class:`BacktesterError`, shows
``err.user_message``, and logs ``err.detail`` together with the traceback.
"""

from __future__ import annotations


class BacktesterError(Exception):
    """Base class for all application errors.

    Parameters
    ----------
    user_message:
        Short, plain-language description shown to the user.
    detail:
        Optional technical detail written to the log file.
    """

    #: Title used by the UI when showing this error in a message box.
    title: str = "Error"

    def __init__(self, user_message: str, detail: str | None = None) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.user_message


class DataError(BacktesterError):
    """Raised for problems with market data files or datasets."""

    title = "Data Error"


class CsvImportError(DataError):
    """Raised when a CSV file cannot be parsed or mapped."""

    title = "CSV Import Error"


class InsufficientDataError(DataError):
    """Raised when there are not enough bars to do what was asked."""

    title = "Not Enough Data"


class TimeframeError(DataError):
    """Raised for an unknown timeframe or an impossible resample."""

    title = "Timeframe Error"


class IndicatorError(BacktesterError):
    """Raised for an unknown indicator or invalid indicator parameters."""

    title = "Indicator Error"


class StrategyError(BacktesterError):
    """Raised for an invalid strategy definition."""

    title = "Strategy Error"


class StrategyStorageError(StrategyError):
    """Raised when a strategy file cannot be read or written."""

    title = "Strategy Storage Error"


class ParameterError(StrategyError):
    """Raised when a strategy parameter value is outside its allowed range."""

    title = "Invalid Parameter"


class OrderError(BacktesterError):
    """Raised when an order cannot be created or is internally inconsistent."""

    title = "Invalid Order"


class RiskError(BacktesterError):
    """Raised when risk settings are contradictory or impossible to satisfy."""

    title = "Risk Configuration Error"


class BacktestError(BacktesterError):
    """Raised when a backtest cannot start or cannot continue."""

    title = "Backtest Error"


class CancelledError(BacktesterError):
    """Raised inside a worker when the user cancels a long-running task."""

    title = "Cancelled"


class StorageError(BacktesterError):
    """Raised when a workspace file cannot be read or written."""

    title = "Storage Error"


class ReportError(BacktesterError):
    """Raised when a report cannot be produced."""

    title = "Report Error"
