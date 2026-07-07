# Examples

Two runnable, self-contained examples. Both create a throwaway workspace, so
they never touch your real `~/.docir`.

## 1. CLI walkthrough — `quickstart.sh`

A complete end-to-end tour of the `docir` command line, reproducing the
architecture's agent flow: register tags → record a decision and a related
issue → discover context → read a decision → add a new decision → resolve the
issue → query, search, and run a graph health check. Each command is echoed
before it runs, and the generated markdown files are printed at the end.

```bash
./examples/quickstart.sh
```

It writes to `examples/.workspace/` (reset on every run) and runs in-process
(`DOCIR_NO_DAEMON=1`) for deterministic output.

## 2. Library usage — `library_usage.py`

Drives docir programmatically through the application dispatcher instead of the
CLI — useful for embedding it in another Python tool. Shows tag registration,
document creation, hybrid `context` retrieval, and a validated status update.

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
- `docs/doc-index-architecture.md` explains the full design.
