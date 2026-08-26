"""The real :class:`FileSink` — reads and writes instruction files on disk."""

from __future__ import annotations

import contextlib
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

    def markdown_files(self, directory: Path) -> tuple[Path, ...]:
        if not directory.is_dir():
            return ()
        return tuple(sorted(path for path in directory.rglob("*.md") if path.is_file()))

    def remove(self, path: Path) -> None:
        path.unlink(missing_ok=True)
        parent = path.parent
        # `rmdir` refuses a non-empty directory, which is exactly the condition
        # to stop on — so the check and the delete are one atomic call rather
        # than a listing somebody could race.
        with contextlib.suppress(OSError):
            parent.rmdir()
