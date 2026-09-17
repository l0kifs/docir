"""Every surface that tells an adopter which mermaid runtime to fetch names the same one.

issue-28e5dc0191cd: the packaged skill and the README said 11.16.1 while
`docir build --help` and the `.mjs` refusal still sent adopters to 10.9.3 on
the grounds that mermaid 11 is ESM-only. That is false — `dist/mermaid.min.js`
is still published on the 11 line, only absent from the package's `exports` —
and docir's own Pages workflow disproves it on every deploy: it publishes with
11.16.1 and asserts in a real browser that the diagrams draw. The surfaces are
edited on different days for different reasons, and nothing but this test
notices when one is left behind.

Five surfaces. The `build` docstring is introspected from the Typer tree, the
same object `--help` renders from; the refusal is *raised*, not read from
source; the packaged `reference/publishing.md` is what an adopter's agent
reads; `README.md` is what the adopter reads; `pages.yml` is what actually
runs. Each must yield a version — an extractor that finds nothing would
otherwise report agreement — and they must all yield the same one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import typer.main

from docir.entry_points.cli.app import app
from docir.modules.agents.infra.template_provider import PackagedTemplateProvider
from docir.modules.publishing.infra import diagrams
from docir.platform.errors import ValidationError

_REPO = Path(__file__).resolve().parents[2]

#: `mermaid@11.16.1` in a URL, or the `MERMAID_VERSION: 11.16.1` the workflow pins.
_VERSION = re.compile(r"(?:mermaid@|MERMAID_VERSION:\s*)(\d+\.\d+\.\d+)")


def _refusal() -> str:
    with pytest.raises(ValidationError) as exc:
        diagrams.resolve_runtime(Path("mermaid.core.mjs"))
    return str(exc.value)


def _surfaces() -> dict[str, str]:
    build = typer.main.get_command(app).commands["build"]
    return {
        "build --help": build.help or "",
        "the .mjs refusal": _refusal(),
        "reference/publishing.md": PackagedTemplateProvider().template("skill")[
            "reference/publishing.md"
        ],
        "README.md": (_REPO / "README.md").read_text(encoding="utf-8"),
        "pages.yml": (_REPO / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8"),
    }


def test_every_surface_names_the_same_mermaid_version() -> None:
    versions = {name: set(_VERSION.findall(text)) for name, text in _surfaces().items()}
    silent = [name for name, found in versions.items() if not found]
    assert not silent, f"no mermaid version found in {silent} — the extractor is not checking them"
    distinct = {v for found in versions.values() for v in found}
    assert len(distinct) == 1, f"the guidance disagrees about the runtime: {versions}"
    assert diagrams.MERMAID_RUNTIME_URL.split("mermaid@")[1].split("/")[0] in distinct


def test_no_surface_calls_the_bundle_umd() -> None:
    """The operative requirement is *classic script*, and "UMD" was the framing
    under which the wrong version survived: it made 10.x "the last line that
    has one" sound like a fact about mermaid rather than about the word."""
    offenders = [name for name, text in _surfaces().items() if "UMD" in text]
    assert not offenders, offenders
