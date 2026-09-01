class WorkflowNotFoundError(Exception):
    """Raised when the named workflow has no matching directory under workflows/."""


class RunNotFoundError(Exception):
    """Raised when a requested run id doesn't exist for the given workflow."""
