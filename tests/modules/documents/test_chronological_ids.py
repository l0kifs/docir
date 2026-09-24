"""``id_style: chronological`` — collision-resistant ids that sort by creation time."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest

from docir.config.settings import Settings
from docir.entry_points.composition import Container, build_container
from docir.modules.documents.domain.value_objects import identifiers
from docir.modules.documents.domain.value_objects.identifiers import DocId
from docir.platform.clock import Clock
from docir.platform.errors import ValidationError

CHRONOLOGICAL_SCHEMA = """\
store_format: 3
types:
  decision:
    prefix: adr
    default_status: proposed
    id_style: chronological
    statuses:
      proposed: [accepted]
      accepted: []
"""

# 0x68251190: a real creation second (May 2025) whose hex is all decimal digits.
ALL_DIGIT_SECONDS = 0x68251190


class _InstantClock(Clock):
    """A clock pinned to one unix second, moved only by the test."""

    def __init__(self, seconds: int) -> None:
        self.seconds = seconds

    def today(self) -> date:
        return self.now().date()

    def now(self) -> datetime:
        return datetime.fromtimestamp(self.seconds, UTC)


@pytest.fixture
def instant() -> _InstantClock:
    return _InstantClock(0x6AB51E14)


def _open(settings: Settings, schema: str, clock: Clock) -> Container:
    settings.ensure_directories()
    settings.schema_path.write_text(schema, encoding="utf-8")
    return build_container(settings, background_embeddings=False, clock=clock)


@pytest.fixture
def store(settings: Settings, instant: _InstantClock) -> Iterator[Container]:
    container = _open(settings, CHRONOLOGICAL_SCHEMA, instant)
    try:
        yield container
    finally:
        container.close()


def _add(container: Container, title: str, **extra: object) -> str:
    payload = {"type": "decision", "title": title, "description": "d", **extra}
    return container.dispatcher.dispatch("add", payload)["id"]


class TestTheDomainBuilder:
    def test_the_suffix_is_the_second_then_four_random_hex(self) -> None:
        doc_id = DocId.build_chronological("adr", 0x6AB51E14)
        assert re.fullmatch(r"adr-6ab51e14[0-9a-f]{4}", doc_id.value)
        # Same length as a random token, so every guard keyed on that shape
        # treats it as a token and never as a counter.
        assert doc_id.looks_random

    def test_an_early_second_is_zero_padded(self) -> None:
        # Without the fixed width, second 0x10 would print as "10" and sort
        # after second 0x0fffffff's "fffffff".
        assert DocId.build_chronological("adr", 0x10).suffix.startswith("00000010")

    def test_ids_sort_in_the_order_of_their_seconds(self) -> None:
        # Seconds chosen to cross hex-digit boundaries (9 -> a, f -> 10, the
        # width of the leading digit), where a non-padded or uppercase rendering
        # would break lexicographic order.
        seconds = [0x0FFFFFFF, 0x10000000, 0x6AB51E19, 0x6AB51E1A, 0x6AB51F00, 0xFFFFFFFF]
        ids = [DocId.build_chronological("adr", s).value for s in seconds]
        assert sorted(ids) == ids

    @pytest.mark.parametrize("seconds", [-1, 0x100000000])
    def test_a_second_outside_eight_hex_digits_is_refused(self, seconds: int) -> None:
        with pytest.raises(ValidationError):
            DocId.build_chronological("adr", seconds)


class TestMintingThroughTheCli:
    def test_the_id_carries_the_clock_second(
        self, store: Container, instant: _InstantClock
    ) -> None:
        assert re.fullmatch(r"adr-6ab51e14[0-9a-f]{4}", _add(store, "First"))

    def test_ids_minted_later_sort_later_and_so_do_their_files(
        self, store: Container, instant: _InstantClock, settings: Settings
    ) -> None:
        minted = []
        for step, seconds in enumerate([0x6AB51E19, 0x6AB51E1A, 0x6AB51F00, 0x6AB60000]):
            instant.seconds = seconds
            # Titles descend alphabetically, so a filename sort that ignored the
            # id would come out reversed.
            minted.append(_add(store, f"{'zyxw'[step]} title"))
        assert sorted(minted) == minted
        files = sorted(p.name for p in (settings.docs_root / "decisions").glob("*.md"))
        assert [name[: len(minted[0])] for name in files] == minted

    def test_ids_minted_in_one_second_stay_unique(self, store: Container) -> None:
        minted = {_add(store, f"T{i}") for i in range(20)}
        assert len(minted) == 20
        assert all(doc_id.startswith("adr-6ab51e14") for doc_id in minted)

    def test_a_local_collision_is_retried(
        self, store: Container, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tails = iter(["beef", "beef", "cafe"])
        monkeypatch.setattr(identifiers.secrets, "token_hex", lambda _n: next(tails))
        assert _add(store, "First") == "adr-6ab51e14beef"
        assert _add(store, "Second") == "adr-6ab51e14cafe"

    def test_a_type_can_opt_in_under_a_schema_wide_random_style(
        self, settings: Settings, instant: _InstantClock
    ) -> None:
        container = _open(
            settings,
            "store_format: 3\nprofiles: [software]\nid_style: random\n"
            "types:\n  decision:\n    id_style: chronological\n",
            instant,
        )
        try:
            decision = _add(container, "D")
            issue = container.dispatcher.dispatch(
                "add", {"type": "issue", "title": "I", "description": "d"}
            )["id"]
        finally:
            container.close()
        assert decision.startswith("adr-6ab51e14")
        assert re.fullmatch(r"issue-[0-9a-f]{12}", issue)
        assert not issue.startswith("issue-6ab51e14")


class TestAnAllDigitSuffixIsNeverACounter:
    """A chronological suffix is all digits whenever its second and tail are.

    Read as a sequential number it is ~682 billion, so a counter raised from it
    would make the type's next sequential id twelve digits long the day the store
    switched styles. Each test switches the type to `sequential` afterwards, which
    is the moment such a counter would surface.
    """

    SEQUENTIAL = CHRONOLOGICAL_SCHEMA.replace("chronological", "sequential")

    def _next_sequential(self, settings: Settings) -> str:
        container = _open(settings, self.SEQUENTIAL, _InstantClock(ALL_DIGIT_SECONDS))
        try:
            return _add(container, "Next")
        finally:
            container.close()

    def test_minting_one(self, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(identifiers.secrets, "token_hex", lambda _n: "0123")
        container = _open(settings, CHRONOLOGICAL_SCHEMA, _InstantClock(ALL_DIGIT_SECONDS))
        try:
            assert _add(container, "Digits") == "adr-682511900123"
            container.dispatcher.dispatch("reindex", {})
        finally:
            container.close()
        assert self._next_sequential(settings) == "adr-0001"

    def test_adopting_one_with_add_id(self, settings: Settings) -> None:
        container = _open(settings, CHRONOLOGICAL_SCHEMA, _InstantClock(ALL_DIGIT_SECONDS))
        try:
            assert _add(container, "Adopted", id="adr-682511900123") == "adr-682511900123"
        finally:
            container.close()
        assert self._next_sequential(settings) == "adr-0001"


def _doc_file(doc_id: str, title: str) -> str:
    return (
        "---\n"
        "created: '2026-07-07'\n"
        "description: d\n"
        f"id: {doc_id}\n"
        "related: []\n"
        "status: proposed\n"
        "tags: []\n"
        f"title: {title}\n"
        "type: decision\n"
        "updated: '2026-07-07'\n"
        "---\n\nbody\n"
    )


class TestARepairedDuplicateKeepsItsPlace:
    def test_the_reissued_id_keeps_the_leading_second(
        self, store: Container, instant: _InstantClock, settings: Settings
    ) -> None:
        # Two branches minted one id in one second; the repair runs a month on.
        # Stamping the repair's second would move the file past everything
        # created in between, which is the order this style promises.
        decisions = settings.docs_root / "decisions"
        decisions.mkdir(parents=True, exist_ok=True)
        for title in ("alpha", "beta"):
            (decisions / f"adr-6ab51e14beef-{title}.md").write_text(
                _doc_file("adr-6ab51e14beef", title), encoding="utf-8"
            )
        instant.seconds = 0x6AD30000
        actions = store.dispatcher.dispatch("repair", {})["actions"]
        reissued = [a for a in actions if a["kind"] == "duplicate-id"]
        assert len(reissued) == 1
        ids = {p.name[:16] for p in decisions.glob("*.md")}
        assert len(ids) == 2
        assert "adr-6ab51e14beef" in ids
        assert all(doc_id.startswith("adr-6ab51e14") for doc_id in ids)

    def test_a_counter_id_has_no_leading_second(self) -> None:
        assert DocId("adr-0007").leading_second is None
        assert DocId("adr-6ab51e14beef").leading_second == 0x6AB51E14
