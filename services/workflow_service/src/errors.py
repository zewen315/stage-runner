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


class RunNotCancellableError(Exception):
    """Raised when trying to cancel a run that's already terminal
    (completed, failed, or already cancelled)."""
