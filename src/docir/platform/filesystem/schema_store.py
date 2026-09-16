"""Reading ``docs-schema.yaml`` as bytes, and recording one line back into it.

Beside :mod:`tag_store` and for the same reason: the file is a store artifact,
so the layer that touches it is ``platform``, where ``application`` may reach it.
What the parsed mapping *means* is decided in
``documents.domain.services.store_format`` — this only moves bytes.

Writes here are deliberately textual, never a re-dump. ``docs-schema.yaml`` is
the one file docir tells a human to edit, and it ships eighty lines of comments
explaining what the keys do; round-tripping it through a YAML dumper would
silently delete every one of them. A repair that costs the reader the
documentation is not a repair.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

#: An existing declaration, at the top level (no leading whitespace).
_DECLARED = re.compile(r"^store_format\s*:.*$", re.MULTILINE)


class YamlSchemaFileStore:
    """The schema file, read raw and amended a line at a time."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def read_raw(self) -> object:
        """The file as parsed YAML, or ``{}`` when it is missing or unreadable.

        Never raises. Both callers — `check` and `doctor` — run *because*
        something may be wrong with this file, and a reporter that dies on its
        subject reports nothing.
        """
        try:
            return yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return {}

    def record_store_format(self, value: int) -> bool:
        """Write ``store_format: <value>``, replacing any line already there.

        Returns whether the file changed, so a repair reports only what it did.

        Placed at the very top when there is none. The alternative — after the
        leading comment block — reads better and is wrong: that block explains
        the keys below it, and slipping a key into the middle of the explanation
        makes the file look like it was edited by something that had not read
        it. A floor is machine bookkeeping and says so by sitting above the
        prose.
        """
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError:
            return False
        line = f"store_format: {value}"
        if _DECLARED.search(text):
            updated = _DECLARED.sub(line, text, count=1)
        else:
            updated = f"{line}\n{text}"
        if updated == text:
            return False
        self._path.write_text(updated, encoding="utf-8")
        return True
