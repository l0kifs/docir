"""The real :class:`FileSink` — reads and writes instruction files on disk."""

from __future__ import annotations

from pathlib import Path


class FilesystemSink:
    """Reads/writes UTF-8 files, creating parent directories on write."""

    def read(self, path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
