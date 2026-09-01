class ResourceNotFoundError(Exception):
    """Raised when a requested resource or resource version does not exist."""


class ResourceValidationError(Exception):
    """Raised when a resource has no declared contract (no matching
    resources/<name>.py), or a value fails that contract's validate()."""
