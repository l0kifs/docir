"""Public surface of the release module.

Answers two questions about the docir *installation* rather than about any
store: how it was installed (and therefore whether it may upgrade itself), and
whether a newer version has been published. Like ``agents``, it owns no index or
database state and runs in-process — it is the tool looking at itself.

The network call is opt-in and daily; see :class:`ReleaseService`.
"""

from __future__ import annotations

from pathlib import Path

from docir.modules.release.application.service import ReleaseService
from docir.modules.release.domain.installation import PACKAGE, Installation, detect
from docir.modules.release.domain.results import ReleaseStatus, UpgradeOutcome, is_newer
from docir.modules.release.infra.adapters import (
    JsonFileReleaseCache,
    PyPIReleaseIndex,
    SubprocessRunner,
)
from docir.modules.release.infra.probe import gather_evidence
from docir.platform.clock import Clock, SystemClock


def current_installation() -> Installation:
    """Classify the running docir installation (no I/O beyond a few stat calls)."""
    return detect(gather_evidence())


def build_release_service(
    version: str, cache_path: Path, clock: Clock | None = None
) -> ReleaseService:
    """Wire the release service for one process."""
    return ReleaseService(
        installation=current_installation(),
        runner=SubprocessRunner(),
        index=PyPIReleaseIndex(),
        cache=JsonFileReleaseCache(cache_path),
        clock=clock or SystemClock(),
        version=version,
    )


__all__ = [
    "PACKAGE",
    "Installation",
    "ReleaseService",
    "ReleaseStatus",
    "UpgradeOutcome",
    "build_release_service",
    "current_installation",
    "is_newer",
]
