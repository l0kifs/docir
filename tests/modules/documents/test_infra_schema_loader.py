"""Tests for the schema YAML loader and default schema."""

from __future__ import annotations

import pytest
import yaml

from docir.modules.documents.infra.default_schema import (
    DEFAULT_SCHEMA_YAML,
    render_schema_yaml,
)
from docir.modules.documents.infra.profiles import PROFILE_NAMES
from docir.modules.documents.infra.schema_loader import (
    describe_schema,
    ensure_schema_file,
    load_schema,
    parse_schema,
)
from docir.platform.errors import SchemaError


def test_default_schema_written_and_loaded(tmp_path) -> None:
    path = tmp_path / "docs-schema.yaml"
    schema = load_schema(path)
    assert path.exists()
    assert set(schema.types) == {"decision", "issue", "architecture", "release_note"}
    assert schema.prefix_for("decision") == "adr"
    assert "resolved" in schema.inactive_statuses()


def test_ensure_schema_file_is_idempotent(tmp_path) -> None:
    path = tmp_path / "s.yaml"
    ensure_schema_file(path)
    path.write_text(
        "types:\n  decision:\n    prefix: adr\n    default_status: a\n    statuses:\n      a: []\n"
    )
    ensure_schema_file(path)  # must not overwrite
    assert "prefix: adr" in path.read_text()


@pytest.mark.parametrize(
    "raw",
    [
        "not a mapping",
        {"types": {}},
        {"types": {"x": "bad"}},
        {"types": {"x": {"statuses": {"a": []}, "default_status": "a"}}},  # no prefix
        {"types": {"x": {"prefix": "x", "default_status": "a"}}},  # no statuses
        {"types": {"x": {"prefix": "x", "statuses": {"a": []}}}},  # no default
        {"types": {"x": {"prefix": "x", "statuses": {"a": "bad"}, "default_status": "a"}}},
    ],
)
def test_parse_schema_rejects_bad_input(raw: object) -> None:
    with pytest.raises(SchemaError):
        parse_schema(raw)


def test_parse_schema_type_field_validation() -> None:
    with pytest.raises(SchemaError):
        parse_schema(
            {
                "types": {
                    "x": {
                        "prefix": "x",
                        "statuses": {"a": []},
                        "default_status": "a",
                        "level": "high",
                    }
                }
            }
        )


def test_parse_schema_id_style() -> None:
    schema = parse_schema(
        {
            "types": {
                "x": {
                    "prefix": "x",
                    "statuses": {"a": []},
                    "default_status": "a",
                    "id_style": "random",
                }
            }
        }
    )
    assert schema.get("x").id_style == "random"


def test_parse_schema_rejects_bad_id_style() -> None:
    with pytest.raises(SchemaError):
        parse_schema(
            {
                "types": {
                    "x": {
                        "prefix": "x",
                        "statuses": {"a": []},
                        "default_status": "a",
                        "id_style": "uuid",
                    }
                }
            }
        )


class TestProfilesAndCore:
    def test_default_includes_core_registry_and_cadence(self, tmp_path) -> None:
        schema = load_schema(tmp_path / "s.yaml")
        assert "supersedes" in schema.relation_types  # from the frozen core
        assert schema.review_days_for("decision") == 365

    def test_named_profile_merges_over_core(self, tmp_path) -> None:
        path = tmp_path / "s.yaml"
        path.write_text("profiles: [research]\n")
        schema = load_schema(path)
        # core `decision` plus the research profile's types.
        assert {"decision", "hypothesis", "experiment", "finding"} <= set(schema.types)

    def test_multiple_profiles_and_allowed_relations(self) -> None:
        schema = parse_schema({"profiles": ["software", "legal"]})
        assert {"issue", "architecture", "policy", "obligation"} <= set(schema.types)
        # allowed_relations from the legal profile parses into the type schema.
        assert schema.get("obligation").allowed_relations["implements"] == ("policy", "contract")

    def test_inline_types_override_profile(self) -> None:
        schema = parse_schema(
            {
                "profiles": ["software"],
                "types": {
                    "issue": {
                        "prefix": "bug",
                        "statuses": {"open": []},
                        "default_status": "open",
                    }
                },
            }
        )
        assert schema.prefix_for("issue") == "bug"  # inline wins over the profile

    def test_unknown_profile_rejected(self) -> None:
        with pytest.raises(SchemaError):
            parse_schema({"profiles": ["nonsense"]})

    def test_profiles_must_be_a_list(self) -> None:
        with pytest.raises(SchemaError):
            parse_schema({"profiles": "software"})


class TestBundledProfileIntegrity:
    """Guards the one global namespace every bundled profile shares (adr-c0ce6f347f3e)."""

    def test_every_profile_combination_has_unique_prefixes(self) -> None:
        # Prefix uniqueness is enforced across the *merged* schema, so a new
        # bundled type can collide with a profile it is never used beside.
        # Enabling all of them at once is the strictest check available.
        schema = parse_schema({"profiles": list(PROFILE_NAMES)})
        prefixes = [type_schema.prefix for type_schema in schema.types.values()]
        assert len(prefixes) == len(set(prefixes)), "bundled profiles share an id prefix"

    def test_qa_profile_layers_over_core(self) -> None:
        schema = parse_schema({"profiles": ["qa"]})
        assert {"decision", "test_plan", "test_case"} <= set(schema.types)
        assert schema.prefix_for("test_plan") == "tp"
        assert schema.review_days_for("test_case") == 180

    def test_software_profile_carries_release_note(self) -> None:
        schema = parse_schema({"profiles": ["software"]})
        release_note = schema.get("release_note")
        assert release_note.prefix == "rel"
        assert release_note.default_status == "draft"
        # A published release note is a historical fact — it never goes stale.
        assert release_note.review_days == 0


class TestDescribeSchema:
    def test_reports_the_merged_result(self) -> None:
        described = describe_schema(parse_schema({"profiles": ["qa"]}))
        assert "supersedes" in described["relation_types"]  # from the frozen core
        names = [entry["name"] for entry in described["types"]]
        assert names == sorted(names), "types must render in a stable order"
        assert {"decision", "test_plan", "test_case"} <= set(names)

    def test_exposes_the_fields_an_author_needs(self) -> None:
        described = describe_schema(parse_schema({"profiles": ["software"]}))
        entry = next(e for e in described["types"] if e["name"] == "architecture")
        assert entry["prefix"] == "arch"
        assert entry["default_status"] == "draft"
        assert entry["transitions"]["draft"] == ["active"]
        assert entry["inactive_statuses"] == ["deprecated"]
        assert entry["review_days"] == 365
        assert entry["id_style"] == "sequential"


class TestRenderSchemaYaml:
    def test_default_selects_the_software_profile(self) -> None:
        assert "profiles: [software]" in render_schema_yaml()
        assert render_schema_yaml() == DEFAULT_SCHEMA_YAML

    def test_named_profiles_are_generated_not_substituted(self) -> None:
        # Regression guard (adr-c0ce6f347f3e): the body used to be built by replacing the
        # literal "profiles: [software]" in DEFAULT_SCHEMA_YAML. If that sentinel
        # ever drifted the replace silently no-opped, so `init --profiles X`
        # wrote the *default* profiles while reporting X. Generating the line
        # makes that divergence unrepresentable.
        body = render_schema_yaml(("research", "ops"))
        assert "profiles: [research, ops]" in body
        assert "profiles: [software]" not in body

    def test_rendered_body_round_trips_through_the_loader(self) -> None:
        for profiles in ((), ("qa",), ("research", "ops", "legal")):
            schema = parse_schema(yaml.safe_load(render_schema_yaml(profiles)))
            assert schema.types, f"rendered body for {profiles} resolved to no types"

    def test_carries_the_commented_authoring_example(self) -> None:
        # The worked example is the only place an agent can learn the inline
        # grammar from the file itself, so its presence is part of the contract.
        body = render_schema_yaml()
        assert "# types:" in body
        assert "#     prefix: tp" in body
        assert "allowed_relations" in body
        # It must stay inert: commenting it out is what keeps the default schema
        # exactly the software profile.
        assert set(parse_schema(yaml.safe_load(body)).types) == {
            "decision",
            "issue",
            "architecture",
            "release_note",
        }


class TestRelationAndStalenessFields:
    def test_inline_relation_types_parsed(self) -> None:
        schema = parse_schema(
            {
                "types": {"x": {"prefix": "x", "statuses": {"a": []}, "default_status": "a"}},
                "relation_types": ["relates_to", "blocks"],
            }
        )
        assert schema.relation_types == frozenset({"relates_to", "blocks"})

    def test_review_days_parsed(self) -> None:
        schema = parse_schema(
            {
                "types": {
                    "x": {
                        "prefix": "x",
                        "statuses": {"a": []},
                        "default_status": "a",
                        "review_days": 42,
                    }
                }
            }
        )
        assert schema.review_days_for("x") == 42

    @pytest.mark.parametrize(
        "spec",
        [
            {"prefix": "x", "statuses": {"a": []}, "default_status": "a", "review_days": "soon"},
            {
                "prefix": "x",
                "statuses": {"a": []},
                "default_status": "a",
                "allowed_relations": "no",
            },
            {
                "prefix": "x",
                "statuses": {"a": []},
                "default_status": "a",
                "allowed_relations": {"implements": "not-a-list"},
            },
        ],
    )
    def test_bad_relation_or_staleness_fields_rejected(self, spec: dict) -> None:
        with pytest.raises(SchemaError):
            parse_schema({"types": {"x": spec}})

    def test_bad_relation_types_rejected(self) -> None:
        with pytest.raises(SchemaError):
            parse_schema(
                {
                    "types": {"x": {"prefix": "x", "statuses": {"a": []}, "default_status": "a"}},
                    "relation_types": "not-a-list",
                }
            )


class TestStatusNamesMustBeDeclared:
    """A status name the type does not declare is rejected at load (issue-b47a1203baa2).

    `statuses: {open: [closd]}` used to load happily. The typo surfaced much
    later, on the first write, as `invalid transition 'open' -> 'closed'` — a
    message naming a status that IS declared, which sends the reader to their
    command instead of to the schema. `docir schema validate` exists to catch an
    edit before it reaches a write, and it passed the most likely edit error.
    """

    def test_undeclared_transition_target_rejected(self) -> None:
        with pytest.raises(SchemaError, match="undeclared status"):
            parse_schema(
                {
                    "types": {
                        "ticket": {
                            "prefix": "tkt",
                            "statuses": {"open": ["closd"], "closed": []},
                            "default_status": "open",
                        }
                    }
                }
            )

    def test_undeclared_inactive_status_rejected(self) -> None:
        with pytest.raises(SchemaError, match="inactive_statuses"):
            parse_schema(
                {
                    "types": {
                        "ticket": {
                            "prefix": "tkt",
                            "statuses": {"open": ["closed"], "closed": []},
                            "default_status": "open",
                            "inactive_statuses": ["done"],
                        }
                    }
                }
            )

    def test_undeclared_default_status_rejected(self) -> None:
        # Every `add` of this type would have failed; the schema declared a
        # starting state the type does not have.
        with pytest.raises(SchemaError, match="default_status"):
            parse_schema(
                {
                    "types": {
                        "ticket": {
                            "prefix": "tkt",
                            "statuses": {"open": ["closed"], "closed": []},
                            "default_status": "new",
                        }
                    }
                }
            )

    def test_the_error_names_the_declared_statuses(self) -> None:
        # The old failure misdirected; this one has to point at the schema.
        with pytest.raises(SchemaError) as excinfo:
            parse_schema(
                {
                    "types": {
                        "ticket": {
                            "prefix": "tkt",
                            "statuses": {"open": ["closd"], "closed": []},
                            "default_status": "open",
                        }
                    }
                }
            )
        message = str(excinfo.value)
        assert "'closd'" in message and "closed, open" in message

    def test_a_healthy_schema_still_loads(self) -> None:
        schema = parse_schema(
            {
                "types": {
                    "ticket": {
                        "prefix": "tkt",
                        "statuses": {"open": ["closed"], "closed": []},
                        "default_status": "open",
                        "inactive_statuses": ["closed"],
                    }
                }
            }
        )
        assert schema.types["ticket"].default_status == "open"


@pytest.mark.parametrize("profile", PROFILE_NAMES)
def test_every_bundled_profile_still_loads(profile: str) -> None:
    # The new rejections run on the shipped profiles too, so a typo in one of
    # them fails here rather than in an adopting repo.
    schema = parse_schema({"profiles": [profile]})
    assert schema.types


class TestMaxBodyChars:
    """issue-5d6a5e854d11: the Tier 2 size threshold is per type, not one constant."""

    def _schema(self, tmp_path, body: str):
        path = tmp_path / "s.yaml"
        path.write_text(body)
        return load_schema(path)

    def test_absent_leaves_it_unset_so_the_linter_default_applies(self, tmp_path) -> None:
        schema = self._schema(tmp_path, "profiles: [software]\n")
        assert schema.types["issue"].max_body_chars is None

    def test_zero_is_kept_and_is_not_confused_with_absent(self, tmp_path) -> None:
        # 0 means "never too long"; None means "use the default". A loader that
        # collapsed them would silently re-enable the check on a register.
        schema = self._schema(
            tmp_path,
            "types:\n  register:\n    prefix: reg\n    default_status: active\n"
            "    statuses:\n      active: []\n    max_body_chars: 0\n",
        )
        assert schema.types["register"].max_body_chars == 0

    def test_a_custom_limit_is_read(self, tmp_path) -> None:
        schema = self._schema(
            tmp_path,
            "types:\n  note:\n    prefix: nt\n    default_status: active\n"
            "    statuses:\n      active: []\n    max_body_chars: 1200\n",
        )
        assert schema.types["note"].max_body_chars == 1200

    def test_a_non_integer_is_refused(self, tmp_path) -> None:
        with pytest.raises(SchemaError, match="max_body_chars"):
            self._schema(
                tmp_path,
                "types:\n  note:\n    prefix: nt\n    default_status: active\n"
                "    statuses:\n      active: []\n    max_body_chars: lots\n",
            )

    def test_schema_show_reports_it(self, tmp_path) -> None:
        schema = self._schema(
            tmp_path,
            "types:\n  note:\n    prefix: nt\n    default_status: active\n"
            "    statuses:\n      active: []\n    max_body_chars: 0\n",
        )
        described = describe_schema(schema)
        note = next(t for t in described["types"] if t["name"] == "note")
        assert note["max_body_chars"] == 0


def _minimal_type(prefix: str) -> dict[str, object]:
    return {"prefix": prefix, "statuses": {"a": []}, "default_status": "a"}


class TestRelationKindMappingForm:
    """`relation_types:` accepts a mapping of kind -> properties.

    The list form is what every schema written before this says, so it has to
    keep parsing and keep meaning "defaults". The mapping form is the `types:`
    shape — a named thing that carries configuration is keyed by its name.
    """

    def test_the_list_form_still_parses_and_means_defaults(self) -> None:
        schema = parse_schema(
            {
                "types": {"note": _minimal_type("nt")},
                "relation_types": ["relates_to", "blocks"],
            }
        )
        assert schema.relation_types == frozenset({"relates_to", "blocks"})
        assert schema.is_symmetric_relation("relates_to"), "core default survives"
        assert not schema.is_symmetric_relation("blocks")

    def test_the_mapping_form_registers_kinds_and_their_properties(self) -> None:
        schema = parse_schema(
            {
                "types": {"note": _minimal_type("nt")},
                "relation_types": {
                    "relates_to": None,
                    "duplicates": {"symmetric": True},
                    "revokes": {"successor": True},
                    "governs": {"dependency": True},
                },
            }
        )
        assert schema.relation_types == frozenset(
            {"relates_to", "duplicates", "revokes", "governs"}
        )
        assert schema.is_symmetric_relation("duplicates")
        assert schema.is_dependency_relation("governs")
        assert "revokes" in schema.successor_relation_kinds()

    def test_naming_a_core_kind_to_set_one_flag_keeps_the_others(self) -> None:
        """Partial declaration must not silently reset what it did not mention."""
        schema = parse_schema(
            {
                "types": {"note": _minimal_type("nt")},
                "relation_types": {"contradicts": {"dependency": True}},
            }
        )
        kind = schema.relation_kind("contradicts")
        assert kind.dependency, "the declared flag"
        assert kind.symmetric and kind.successor, "the core's, not reset to False"

    def test_an_unknown_property_is_rejected(self) -> None:
        with pytest.raises(SchemaError, match="unknown property 'directed'"):
            parse_schema(
                {
                    "types": {"note": _minimal_type("nt")},
                    "relation_types": {"blocks": {"directed": True}},
                }
            )

    def test_non_mapping_properties_are_rejected(self) -> None:
        with pytest.raises(SchemaError, match="properties must be a mapping"):
            parse_schema(
                {
                    "types": {"note": _minimal_type("nt")},
                    "relation_types": {"blocks": ["symmetric"]},
                }
            )

    def test_a_profiled_schema_may_add_a_kind_without_resetting_the_core(self) -> None:
        """Merge is per key: the fragments each contribute, none replaces."""
        schema = parse_schema({"profiles": ["software"], "relation_types": {"blocks": None}})
        assert "blocks" in schema.relation_types
        assert "supersedes" in schema.relation_types, "still registered by the core"
        assert schema.is_symmetric_relation("relates_to"), "core properties intact"

    def test_schema_show_reports_the_resolved_properties(self) -> None:
        """The file shows the ingredients; only this shows what a kind means."""
        described = describe_schema(parse_schema({"profiles": ["software"]}))
        kinds = {k["name"]: k for k in described["relation_kinds"]}
        assert kinds["relates_to"]["symmetric"] is True
        assert kinds["supersedes"]["successor"] is True
        assert kinds["depends_on"]["dependency"] is True
        assert kinds["implements"] == {
            "name": "implements",
            "symmetric": False,
            "dependency": False,
            "successor": False,
        }
