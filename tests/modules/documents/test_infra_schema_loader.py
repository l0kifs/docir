"""Tests for the schema YAML loader and default schema."""

from __future__ import annotations

import pytest
import yaml

from docir.modules.documents.domain.services import schema_shape
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


class TestDisableTypes:
    """Subtracting a merged type (adr-f8cce745d0d5, issue-ab138501abfd).

    Merging is additive and the core is injected whenever a `profiles:` key is
    present, so before this the `decision` name and its `adr` prefix existed in
    every store and could not be given up.
    """

    def test_a_core_type_can_be_removed(self) -> None:
        schema = parse_schema({"profiles": ["software"], "disable_types": ["decision"]})
        assert "decision" not in schema.types
        # The profile's own types are untouched by the subtraction.
        assert {"issue", "architecture", "release_note"} <= set(schema.types)

    def test_removing_the_type_frees_its_prefix(self) -> None:
        # The whole point: `product_decision` claims `adr` and the corpus keeps
        # the `adr-...` ids it already has. This raised
        # "prefix 'adr' used by both 'decision' and 'product_decision'".
        schema = parse_schema(
            {
                "profiles": ["software"],
                "disable_types": ["decision"],
                "types": {
                    "product_decision": {
                        "prefix": "adr",
                        "statuses": {"draft": ["active"], "active": []},
                        "default_status": "draft",
                    }
                },
            }
        )
        assert schema.prefix_for("product_decision") == "adr"
        assert "decision" not in schema.types

    def test_a_profile_type_can_be_removed_too(self) -> None:
        schema = parse_schema({"profiles": ["software"], "disable_types": ["release_note"]})
        assert "release_note" not in schema.types
        assert "decision" in schema.types

    def test_a_name_nothing_declares_is_refused(self) -> None:
        # A typo that silently did nothing forever is the failure mode the
        # `required:` and status-target checks already exist to prevent.
        with pytest.raises(SchemaError) as excinfo:
            parse_schema({"profiles": ["software"], "disable_types": ["decisions"]})
        message = str(excinfo.value)
        assert "'decisions'" in message
        assert "decision" in message  # names what would have worked

    def test_declaring_and_disabling_one_name_is_refused(self) -> None:
        with pytest.raises(SchemaError) as excinfo:
            parse_schema(
                {
                    "profiles": ["software"],
                    "disable_types": ["decision"],
                    "types": {
                        "decision": {
                            "prefix": "dec",
                            "statuses": {"draft": []},
                            "default_status": "draft",
                        }
                    },
                }
            )
        assert "delete the block" in str(excinfo.value)

    def test_disabling_everything_is_refused(self) -> None:
        with pytest.raises(SchemaError) as excinfo:
            parse_schema({"profiles": [], "disable_types": ["decision"]})
        assert "no types" in str(excinfo.value)

    def test_it_must_be_a_list(self) -> None:
        with pytest.raises(SchemaError):
            parse_schema({"profiles": ["software"], "disable_types": "decision"})

    def test_it_applies_to_an_inline_only_schema(self) -> None:
        # Nothing is merged into an inline-only file, so every name it could
        # disable is one it declares -- which is the contradiction, reported the
        # same way rather than as a key that works only in the other mode.
        with pytest.raises(SchemaError) as excinfo:
            parse_schema(
                {
                    "types": {
                        "note": {
                            "prefix": "n",
                            "statuses": {"draft": []},
                            "default_status": "draft",
                        }
                    },
                    "disable_types": ["note"],
                }
            )
        assert "delete the block" in str(excinfo.value)

    def test_the_removal_reads_as_schema_drift(self, tmp_path) -> None:
        # `check` has to be able to explain why a corpus went unknown-type.
        before = describe_schema(parse_schema({"profiles": ["software"]}))
        after = describe_schema(
            parse_schema({"profiles": ["software"], "disable_types": ["decision"]})
        )
        assert "-type decision" in schema_shape.diff(before, after)


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
        # The only core kind carrying both: it says the source sits above the
        # target *and* waits for it (adr-716c2eeb4e51).
        assert kinds["depends_on"]["blocking"] is True
        assert kinds["refines"]["dependency"] is True
        assert kinds["refines"]["blocking"] is False
        # Exhaustive rather than per-key: a new property must be *decided* for
        # every kind, not silently defaulted for the ones nobody thought about.
        assert kinds["implements"] == {
            "name": "implements",
            "symmetric": False,
            "dependency": False,
            "successor": False,
            "blocking": False,
        }


class TestRequiredNamesRealFields:
    """issue-e3c4dfad4f7b: `required:` accepted names nothing could satisfy.

    The loader checked only that it was a list, while Tier 0 reads the field off
    the document — so `required: [commit]` loaded fine and then rejected every
    write of that type forever, with a message naming the write rather than the
    schema. The same class of defect as an undeclared status target, which this
    loader already catches, and fixed the same way: refuse at load, naming what
    would have worked.
    """

    def _spec(self, required: list[str]) -> dict[str, object]:
        return {
            "types": {
                "probe": {
                    "prefix": "pr",
                    "statuses": {"active": []},
                    "default_status": "active",
                    "required": required,
                }
            }
        }

    def test_a_field_no_document_can_carry_is_refused(self) -> None:
        with pytest.raises(SchemaError) as exc:
            parse_schema(self._spec(["commit"]))
        message = str(exc.value)
        assert "'commit'" in message
        # And it names the ones that would have worked, so the fix needs no
        # second round trip through the source.
        assert "owner" in message and "tags" in message

    def test_a_real_optional_field_is_accepted(self) -> None:
        schema = parse_schema(self._spec(["owner"]))
        assert schema.get("probe").required_fields == ("owner",)

    def test_path_is_refused_because_it_is_assigned_after_validation(self) -> None:
        # It *is* a Document field, and requiring it would reject every create:
        # the file store assigns the path after Tier 0 has run.
        with pytest.raises(SchemaError):
            parse_schema(self._spec(["path"]))


class TestEmbedModel:
    """The store's ``embed_model:`` key — shape here, existence elsewhere.

    The loader deliberately does *not* check that the name is a model anyone
    supports: answering costs a ``fastembed`` import, and the schema loads on
    every command. That half is
    ``entry_points.composition.verify_embed_model``, and
    ``TestVerifyEmbedModel`` covers it.
    """

    def _spec(self, embed_model: object) -> dict[str, object]:
        return {
            "profiles": ["software"],
            "embed_model": embed_model,
        }

    def test_absent_means_the_default_rather_than_a_name(self) -> None:
        # None, not the default string: "nobody chose" and "somebody chose the
        # default" differ once a future release moves the default.
        assert parse_schema({"profiles": ["software"]}).embed_model is None

    def test_a_name_is_carried_through_the_profile_merge(self) -> None:
        schema = parse_schema(self._spec("BAAI/bge-small-en-v1.5"))
        assert schema.embed_model == "BAAI/bge-small-en-v1.5"

    def test_an_inline_schema_carries_it_too(self) -> None:
        schema = parse_schema(
            {
                "embed_model": "BAAI/bge-small-en-v1.5",
                "types": {
                    "probe": {
                        "prefix": "pr",
                        "statuses": {"active": []},
                        "default_status": "active",
                    }
                },
            }
        )
        assert schema.embed_model == "BAAI/bge-small-en-v1.5"

    @pytest.mark.parametrize("value", [42, [], {}, "", "   "])
    def test_a_non_string_or_blank_name_is_refused_at_load(self, value: object) -> None:
        # Injected bug: a schema whose key is a list would otherwise reach the
        # embedder as an unusable value and fail on first embed, in the
        # scheduler thread where the exception is swallowed.
        with pytest.raises(SchemaError) as exc:
            parse_schema(self._spec(value))
        assert "embed_model" in str(exc.value)

    def test_surrounding_whitespace_is_stripped(self) -> None:
        # A hand-edited YAML value picks these up, and the name is compared by
        # equality against the verified set and written into `model_id`.
        assert parse_schema(self._spec("  BAAI/bge-small-en-v1.5 ")).embed_model == (
            "BAAI/bge-small-en-v1.5"
        )

    def test_it_stays_out_of_the_drift_payload(self) -> None:
        # Drift reports what `git diff` cannot show — a type or cadence the
        # *package* moved. This key only changes when somebody edits the file,
        # so reporting it would make every deliberate switch look like drift.
        described = describe_schema(parse_schema(self._spec("BAAI/bge-small-en-v1.5")))
        assert "embed_model" not in described
