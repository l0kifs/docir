# Examples

Two runnable, self-contained examples. Both create a throwaway workspace, so
they never touch your real `~/.docir`.

## 1. CLI walkthrough — `quickstart.sh`

A complete end-to-end tour of the `docir` command line, reproducing the
architecture's agent flow: register tags → record a decision (with an `owner`)
and an issue linked by a **typed edge** → discover context as a body-less
**skeleton** → read the full decision → record a successor that **supersedes**
the original → retire it and resolve the issue → re-**verify** a doc's freshness
→ query, search, and run a Tier 1 graph health check → inspect the **core +
profiles** schema. Each command is echoed before it runs, and the generated
markdown (typed `related`, `owner`/`verified`) is printed at the end.

```bash
./examples/quickstart.sh
```

It writes to `examples/.workspace/` (reset on every run) and runs in-process
(`DOCIR_NO_DAEMON=1`) for deterministic output.

## 2. Library usage — `library_usage.py`

Drives docir programmatically through the application dispatcher instead of the
CLI — useful for embedding it in another Python tool. Shows tag registration,
document creation with a typed `depends_on` edge and an `owner`, skeleton
`context` retrieval (no body) vs. `get` (full body), a validated status
transition, and stamping `verified` to reset the staleness clock.

```bash
uv run python examples/library_usage.py
```

## 3. Real semantic embeddings — `fastembed_semantic.py`

Contrasts the two `Embedder` backends behind the same port. The deterministic
default ranks by shared words; the real `fastembed` (ONNX) backend ranks by
meaning, so it links a query about "refresh token rotation" to a document about
"session renewal strategy" that shares almost no vocabulary.

Requires the optional extra and a one-time model download:

```bash
uv sync --extra embeddings
uv run python examples/fastembed_semantic.py
```

Setting `DOCIR_EMBEDDER=fastembed` makes the whole CLI (and `docir context`)
use this backend instead of the default. The other two examples above use the
deterministic embedder, so they stay offline and reproducible.

## What to look at next

- The generated files under the workspace `docs/` directory are the source of
  truth — plain markdown with YAML frontmatter, ready to commit to git.
- `uv run docir --help` lists every command.
- The full design is a docir document in docir's own store: `docir get arch-1cfb1b212237`.
