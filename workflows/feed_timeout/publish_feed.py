"""Export stage: publish the ranked feed out of the system. `path` is
relative to the run's *output* directory, not the workflow's own directory
-- the workflow directory is checked-in, read-only content; this is a
generated run artifact and lives somewhere else entirely."""

from .registry import registry

registry.export_stage("publish_feed", depends_on="rank_feed", path="feed.json")
