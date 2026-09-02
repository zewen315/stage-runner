class WorkflowNotFoundError(Exception):
    """Raised when the named workflow has no matching directory under workflows/."""


class RunNotFoundError(Exception):
    """Raised when a requested workflow run id doesn't exist for the given workflow."""


class StageRunNotFoundError(Exception):
    """Raised when a requested stage run id doesn't exist for the given workflow."""


class ScheduleNotFoundError(Exception):
    """Raised when a requested schedule id doesn't exist for the given workflow."""


class RecurringScheduleNotFoundError(Exception):
    """Raised when a requested recurring schedule id doesn't exist for the given workflow."""


class InvalidCronExpressionError(Exception):
    """Raised when a recurring schedule's cron_expression can't be parsed."""


class InvalidRecurrenceError(Exception):
    """Raised when a recurring schedule's recurrence isn't exactly one of
    cron_expression/interval_seconds, or interval_seconds isn't a positive
    integer."""


class RunNotCancellableError(Exception):
    """Raised when trying to cancel a run that's already terminal
    (completed, failed, or already cancelled)."""


class ScheduleNotCancellableError(Exception):
    """Raised when trying to cancel a schedule that's already been
    dispatched to a WorkflowRun -- cancel that run instead."""


class InvalidOnFailureError(Exception):
    """Raised when on_failure isn't one of "halt" or "fallback"."""
