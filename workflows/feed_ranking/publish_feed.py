"""Export stage: publish the ranked feed out of the system. `path` is a
runtime artifact -- generated here, not checked in (see .gitignore)."""

from .registry import registry

registry.export_stage("publish_feed", depends_on="rank_feed", path="output/feed.json")
