"""StrategyDocument — domain entity for a persisted JSON strategy."""

from dataclasses import dataclass, field


@dataclass
class StrategyDocument:
    """A saved v2 JSON strategy definition with metadata."""

    name: str
    schema_version: str
    definition_json: str
    normalized_json: str = ""
    description: str = ""
    created_at: str = ""
    updated_at: str = ""
    id: int | None = None
    tags: list[str] = field(default_factory=list)
