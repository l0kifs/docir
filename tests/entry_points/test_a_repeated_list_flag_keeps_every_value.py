"""A list flag given twice keeps both values, not the last one.

`--code a/** --code b/**` used to write `code: [b/**]` and say nothing: the
write-side list flags were single-valued, so Click kept the last occurrence,
while every read-side list flag (`query --tag x --tag y`) repeats. An agent
that learned the read form lost globs and edges on the write, and `query --code`
stopped finding the decisions that govern those files.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from docir.config.settings import Settings
from docir.entry_points.cli.app import app

runner = CliRunner()


def run(*args: str):
    return runner.invoke(app, list(args))


def _add(*extra: str) -> dict[str, object]:
    result = run("add", "--type", "decision", "--title", "T", "--description", "d", *extra)
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def _get(doc_id: str) -> dict[str, object]:
    result = run("get", doc_id)
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def _frontmatter(settings: Settings, doc_id: str) -> dict[str, object]:
    (path,) = settings.docs_root.rglob(f"{doc_id}-*.md")
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])


@pytest.fixture(autouse=True)
def _tags(settings: Settings) -> None:
    for key in ("x", "y", "z"):
        assert run("tag", "add", key, "--description", key).exit_code == 0


def test_the_reported_invocation_writes_both_globs(settings: Settings) -> None:
    doc = _add("--code", "a/**", "--code", "b/**", "--body", "b")

    assert _frontmatter(settings, str(doc["id"]))["code"] == ["a/**", "b/**"]


@pytest.mark.parametrize(
    ("flag", "field"),
    [("--tags", "tags"), ("--code", "code")],
)
def test_add_keeps_every_occurrence_in_order_and_either_form(
    settings: Settings, flag: str, field: str
) -> None:
    # Reverse-sorted on purpose: `get` answers from the index, which sorts, so
    # only the file can show that the order given is the order kept.
    values = {"--tags": ("z", "y,x"), "--code": ("c/**", "b/**,a/**")}[flag]
    doc = _add(flag, values[0], flag, values[1])

    expected = {"--tags": ["z", "y", "x"], "--code": ["c/**", "b/**", "a/**"]}[flag]
    assert _frontmatter(settings, str(doc["id"]))[field] == expected


def test_add_keeps_every_repeated_edge() -> None:
    first, second = str(_add()["id"]), str(_add()["id"])
    doc = _add("--related", first, "--related", f"{second}:refines")

    assert _get(str(doc["id"]))["related"] == [
        {"target": first, "kind": "relates_to"},
        {"target": second, "kind": "refines"},
    ]


def test_update_replaces_with_every_occurrence() -> None:
    first, second = str(_add()["id"]), str(_add()["id"])
    doc_id = str(_add("--tags", "x", "--code", "old/**")["id"])

    result = run(
        "update",
        doc_id,
        "--set-tags",
        "y",
        "--set-tags",
        "z",
        "--set-code",
        "a/**",
        "--set-code",
        "b/**",
        "--set-related",
        first,
        "--set-related",
        f"{second}:refines",
    )

    assert result.exit_code == 0, result.output
    doc = _get(doc_id)
    assert doc["tags"] == ["y", "z"]
    assert doc["code"] == ["a/**", "b/**"]
    assert doc["related"] == [
        {"target": first, "kind": "relates_to"},
        {"target": second, "kind": "refines"},
    ]


def test_an_absent_set_flag_leaves_the_list_alone() -> None:
    # The flags became `list[str] | None`, and `update` reads None as "leave it"
    # and an empty list as "clear it". Were Typer to hand back [] for an absent
    # repeatable option, every `update` would clear tags, code and edges.
    target = str(_add()["id"])
    doc_id = str(_add("--tags", "x", "--code", "a/**", "--related", target)["id"])

    assert run("update", doc_id, "--set-title", "Renamed").exit_code == 0

    doc = _get(doc_id)
    assert doc["tags"] == ["x"]
    assert doc["code"] == ["a/**"]
    assert doc["related"] == [{"target": target, "kind": "relates_to"}]


def test_an_empty_value_still_clears() -> None:
    doc_id = str(_add("--tags", "x", "--code", "a/**")["id"])

    assert run("update", doc_id, "--set-tags", "", "--set-code", "").exit_code == 0

    doc = _get(doc_id)
    assert not doc.get("tags")
    assert not doc.get("code")


@pytest.mark.parametrize("form", [("--tags", "x", "--tags", "x"), ("--tags", "x,x")])
def test_a_repeated_value_is_kept_once_and_the_store_still_rebuilds(
    settings: Settings, form: tuple[str, ...]
) -> None:
    # Merging made `--tags x --tags x` arrive as `x, x`, where last-wins had
    # read it as `x`. A repeated tag once failed the write after the file was on
    # disk, and every `reindex` after it (issue-413546da5db7).
    doc = _add(*form)

    assert _frontmatter(settings, str(doc["id"]))["tags"] == ["x"]
    assert run("reindex").exit_code == 0


def test_init_enables_every_repeated_profile(tmp_path: Path) -> None:
    result = run("init", str(tmp_path), "--profiles", "software", "--profiles", "qa")

    assert result.exit_code == 0, result.output
    schema = yaml.safe_load((tmp_path / ".docir" / "docs-schema.yaml").read_text("utf-8"))
    assert schema["profiles"] == ["software", "qa"]
