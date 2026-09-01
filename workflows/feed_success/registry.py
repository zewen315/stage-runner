"""The one StageRegistry every stage file in this workflow registers into.
Kept in its own module so every stage file can `from .registry import
registry` without importing each other."""

from stages import StageRegistry

registry = StageRegistry()
