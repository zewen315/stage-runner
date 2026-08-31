class ResourceNotFoundError(Exception):
    """Raised when a requested resource or resource version does not exist."""


class ResourceAlreadyExistsError(Exception):
    """Raised when creating a resource whose name is already taken."""
