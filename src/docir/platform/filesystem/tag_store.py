"""YAML tag-registry store (implements ``TagFileStore``).

``docs/tags.yaml`` is a simple ``key: description`` mapping — the canonical,
git-versioned source of truth for what tags exist.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from docir.modules.tags.domain.entities.tag import Tag
from docir.platform.filesystem.ports import TagFileStore


class YamlTagFileStore(TagFileStore):
    """Reads and writes ``docs/tags.yaml``."""

    def __init__(self, tags_path: Path) -> None:
        self._path = tags_path

    def load(self) -> list[Tag]:
        if not self._path.exists():
            return []
        raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            return []
        return [Tag(key=str(key), description=str(description)) for key, description in raw.items()]

    def write(self, tags: list[Tag]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        mapping = {tag.key: tag.description for tag in tags}
        text = yaml.safe_dump(mapping, sort_keys=True, allow_unicode=True)
        self._path.write_text(text, encoding="utf-8")
