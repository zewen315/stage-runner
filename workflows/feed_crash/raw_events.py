"""Import stage: raw engagement events, standing in for an external source
(a real system would read this from an event stream, not a checked-in file)."""

from .registry import registry

registry.import_stage("raw_events", path="data/raw_events.json")
