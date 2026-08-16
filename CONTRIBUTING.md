# Contributing to docir

Issues and pull requests are welcome. This file covers the mechanics; the design
rationale lives in docir's own store, which is the point of the project.

## Where to ask

- **[Q&A](https://github.com/l0kifs/docir/discussions/categories/q-a)** — how do I, why does
  it behave that way, is this the right approach. No reproduction needed.
- **[Ideas](https://github.com/l0kifs/docir/discussions/categories/ideas)** — a change you
  are weighing, before it is a proposal.
- **[Issues](https://github.com/l0kifs/docir/issues)** — a reproducible bug, or work that has
  already been agreed on.

If you are unsure, start a discussion; it is easy to promote once there is a reproduction.

Paste the command you ran and its output either way. Every command prints JSON when its
output is captured, so `docir check | cat` is already a complete report.

## Requirements

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** — the project is one uv-managed package
- Linux, macOS or Windows. Everything runs locally; only the first-run model download
  needs network.

```bash
git clone https://github.com/l0kifs/docir && cd docir
uv sync                                    # create the environment
uv run docir --help                        # the CLI, from your checkout
```

A checkout detects as a `project` install, so `docir self upgrade` will not replace the
environment you are working in — it says so and resyncs the store instead.

## Orient with docir before you change anything

docir dogfoods itself. Its ADRs, architecture documents, runbooks and gap register are
documents in `.docir/docs/`, so read them through the CLI rather than by path:

```bash
docir context "what you are about to change"   # ranked skeletons, no bodies
docir query --type decision                    # every ADR
docir get arch-1cfb1b212237                    # the architecture
docir get arch-322e5f992ad2                    # the module rules
```

Most "why is it like this?" questions are answered by a decision that already exists.
Reading it first is cheaper than rediscovering the constraint in review.

## Never edit the documents by hand

Every write to `.docir/docs/` goes through the CLI — that is what keeps frontmatter,
schema and id allocation consistent. Record a design deviation as a decision:

```bash
docir add --type decision --title "..." --description "..." --stdin < draft.md
```

`docs-schema.yaml` and `docs/tags.yaml` are the exceptions: they have no CLI write path
and are meant to be edited directly. Run `docir reindex && docir check` afterwards.

## The gate suite

CI runs all of these. Run them before opening a PR:

```bash
uv run ruff check . && uv run ruff format --check .   # lint + format
uv run ty check                                       # type check
uv run vulture                                        # dead-code scan
uv run tach check                                     # module boundaries
uv run python scripts/check_contract_sync.py          # api.py <-> CONTRACT.md
uv run pytest --cov=docir --cov-fail-under=90         # tests + coverage
```

`tach check` prints `[WARN] ... deprecated` lines and still exits 0 — those are the
recorded baseline of shared-index edges, which may shrink but never grow. A real boundary
break exits non-zero.

`uv run pytest -m "not slow"` skips the end-to-end tests that spawn a real daemon
subprocess and load the real embedding model.

## Module boundaries

The codebase is vertical bounded-context modules over a shared platform, wired by thin
entry points. Two rules cause most review comments:

- **Each module exposes exactly one public file, `api.py`.** Code outside a module may
  import only that, never its `domain`/`application`/`infra`.
- **A change to an `api.py` and its `CONTRACT.md` must land in the same commit** —
  `scripts/check_contract_sync.py` fails the build otherwise.

The sanctioned responses to a boundary error are: route through the module's `api`, move
the shared thing into `platform`, or merge the modules. Never widen the baseline in
`tach.toml`, and never add a `tach-ignore`.

## Benchmarks

Ranking and chunking changes are measured, not argued. Run the relevant harness before and
after:

```bash
uv run python benchmarks/run.py         # retrieval quality (recall@5, MRR) + token cost
uv run python benchmarks/chunking.py    # section structure — the one that moves on a splitter change
uv run python benchmarks/latency.py     # read latency by corpus size and daemon mode
uv run python benchmarks/tokens.py      # token cost by corpus size, against a grep baseline
```

Quote the numbers in the PR. `run.py` is the wrong instrument for a chunking change — its
corpus has no section over the ceiling, so a broken splitter scores what a working one does.

## Tests

- New behaviour needs a test through the seam its layer prescribes: pure unit tests for
  `domain/`, the `dispatcher`/`container` fixtures for use cases, real SQLite for `infra/`,
  and the `slow` subprocess tests for end-to-end.
- **Verify a new guard by injecting the bug it claims to catch.** A test that has never
  failed has not been shown to work. Where a guard scans a corpus, assert *which* items it
  found — a count cannot distinguish "nothing is wrong" from "nothing is checked".
- When a test pins a subtle bug, name the bug in a comment.

## License

By contributing you agree that your contributions are licensed under the
[MIT License](LICENSE).
