"""The schema-overlay warning must stay where an agent on an old build reads it.

A store using a partial `types:` block is refused by any docir predating that
form, with `type '<name>' must define a string 'prefix'` — a message that names
the wrong cause and implies the one repair that silently breaks the store
(writing the missing keys turns the overlay into a declaration, taking the type
over). Nothing this build ships can change what an installed older docir prints,
so the remedy lives in the files an agent still reaches from there: the store's
own `docs-schema.yaml`, the packaged template every new store gets, and the
skill an adopter installs (adr-ab4598c6f707, adr-6aa2e2f5f403).

These assert the *warning*, not the loader — which is the half no other test can
cover, since the loader under test is the one that understands the syntax.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from docir.modules.documents.infra.default_schema import DEFAULT_SCHEMA_YAML

#: The literal an older docir prints. It is the string an agent will paste into
#: a search or hand back to a human, so every warning has to carry it verbatim
#: rather than paraphrasing the failure.
OLD_BUILD_ERROR = "must define a string 'prefix'"

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "src/docir/modules/agents/infra/templates/skill"
STORE_SCHEMA = REPO / ".docir/docs-schema.yaml"


def _overlay_types(text: str) -> list[str]:
    """Type names declared as overlays — a `types:` child with no `prefix:`."""
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.rstrip() == "types:")
    except StopIteration:
        return []
    names: list[str] = []
    current: str | None = None
    has_prefix = False
    for line in lines[start + 1 :]:
        if line and not line.startswith(" "):
            break
        stripped = line.strip()
        if line.startswith("  ") and not line.startswith("   ") and stripped.endswith(":"):
            if current is not None and not has_prefix:
                names.append(current)
            current, has_prefix = stripped[:-1], False
        elif stripped.startswith("prefix:"):
            has_prefix = True
    if current is not None and not has_prefix:
        names.append(current)
    return names


class TestThisStoreWarnsBesideItsOverlays:
    def test_the_store_actually_uses_overlays(self) -> None:
        # The guard below is vacuous if it does not — assert which types, not a
        # count, so "nothing is wrong" cannot pass for "nothing is checked".
        assert _overlay_types(STORE_SCHEMA.read_text(encoding="utf-8")) == ["decision", "issue"]

    def test_the_error_an_older_docir_prints_is_named_in_the_file(self) -> None:
        # An agent that hits the failure opens this file next; it has to find
        # the diagnosis here, because its installed skill may predate it too.
        assert OLD_BUILD_ERROR in STORE_SCHEMA.read_text(encoding="utf-8")

    def test_the_file_forbids_the_repair_the_message_implies(self) -> None:
        text = STORE_SCHEMA.read_text(encoding="utf-8").lower()
        assert "do not" in text
        assert "upgrade" in text


class TestTheShippedGuidanceCarriesIt:
    @pytest.mark.parametrize(
        "path",
        [SKILL / "reference/troubleshooting.md", SKILL / "reference/schema.md"],
        ids=["troubleshooting", "schema"],
    )
    def test_the_reference_an_adopter_installs_covers_overlays(self, path: Path) -> None:
        assert "overlay" in path.read_text(encoding="utf-8").lower()

    def test_troubleshooting_names_the_exact_error(self) -> None:
        # Verbatim: an agent matches on the string it was given, and a
        # paraphrase is a page it will not find.
        assert OLD_BUILD_ERROR in (SKILL / "reference/troubleshooting.md").read_text(
            encoding="utf-8"
        )

    def test_troubleshooting_sends_the_reader_to_doctor(self) -> None:
        # The one command that still runs when the schema will not load, and so
        # the only way to see the installed version beside the failure.
        text = (SKILL / "reference/troubleshooting.md").read_text(encoding="utf-8")
        assert "docir doctor" in text
        assert "schema-unreadable" in text

    def test_the_packaged_template_warns_before_a_store_adopts_one(self) -> None:
        # Every new store gets this file, so the cost is stated where the
        # decision is made rather than after it has been committed.
        assert OLD_BUILD_ERROR in DEFAULT_SCHEMA_YAML
