"""Reading the environment for install evidence — the only place that guesses.

Every marker here is one an installer writes for its own use, so detection is
reading a fact rather than inferring one: ``uv tool`` leaves ``uv-receipt.toml``
at the root of the environment it created, pipx leaves ``pipx_metadata.json``,
and anything installed from a path leaves ``direct_url.json`` in its dist-info
(PEP 610). The uvx case is the exception — an ephemeral environment is
recognised by living under uv's cache.
"""

from __future__ import annotations

import json
import os
import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from docir.modules.release.domain.installation import PACKAGE, Evidence


def gather_evidence() -> Evidence:
    """Describe the running interpreter, without deciding what it means."""
    prefix = Path(sys.prefix)
    direct_url, editable = _direct_url()
    return Evidence(
        prefix=prefix,
        executable=Path(sys.executable),
        has_uv_receipt=(prefix / "uv-receipt.toml").exists(),
        has_pipx_metadata=(prefix / "pipx_metadata.json").exists(),
        direct_url=direct_url,
        editable=editable,
        ephemeral=_under_uv_cache(prefix),
    )


def _direct_url() -> tuple[str | None, bool]:
    """``(url, editable)`` from the installed distribution's ``direct_url.json``."""
    try:
        text = distribution(PACKAGE).read_text("direct_url.json")
    except (PackageNotFoundError, OSError):
        return None, False
    if not text:
        return None, False
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None, False
    if not isinstance(data, dict):
        return None, False
    url = data.get("url")
    dir_info = data.get("dir_info")
    editable = bool(dir_info.get("editable")) if isinstance(dir_info, dict) else False
    return (str(url) if url else None), editable


def _under_uv_cache(prefix: Path) -> bool:
    """Whether ``prefix`` sits inside uv's cache — where ``uvx`` builds its envs."""
    cache = os.environ.get("UV_CACHE_DIR")
    roots = [Path(cache)] if cache else [Path.home() / ".cache" / "uv"]
    return any(_is_within(prefix, root) for root in roots)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
