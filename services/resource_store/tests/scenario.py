"""A tiny DSL for writing a test as an ordered list of operations and their
expected behavior, instead of free-form imperative code.

Each Step calls one method on the service under test. `args`/`kwargs` may be
plain values, or callables of the form `lambda results: ...` to reference an
earlier named step's result -- this is what lets a test read as a script:
"upload this (call it v1), then promote v1, then expect get() to return it."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pytest


@dataclass
class Step:
    op: str
    args: list = field(default_factory=list)
    kwargs: dict = field(default_factory=dict)
    name: str | None = None
    expect: Callable[[Any], None] | None = None
    raises: type[Exception] | None = None


def run(service, steps: list[Step]) -> dict:
    """Execute `steps` in order against `service`. Returns a dict of named
    step results, so later steps (or the caller, after run() returns) can
    reference earlier ones."""
    results: dict = {}

    def resolve(value):
        return value(results) if callable(value) else value

    for step in steps:
        args = [resolve(a) for a in step.args]
        kwargs = {key: resolve(value) for key, value in step.kwargs.items()}
        method = getattr(service, step.op)

        if step.raises is not None:
            with pytest.raises(step.raises):
                method(*args, **kwargs)
            continue

        result = method(*args, **kwargs)
        if step.expect is not None:
            assert step.expect(result), f"expect failed for {step.op}({args!r}, {kwargs!r}) -> {result!r}"
        if step.name is not None:
            results[step.name] = result

    return results
