"""The one StageRegistry every stage file in this workflow registers into.
Kept in its own module so every stage file can `from .registry import
registry` without importing each other.

on_failure="fallback": when a stage here fails, the Scheduler doesn't halt
the run -- it treats the failed stage as if it had produced its
currently-promoted resource version instead, and keeps going."""

from stages import StageRegistry

registry = StageRegistry(on_failure="fallback")
