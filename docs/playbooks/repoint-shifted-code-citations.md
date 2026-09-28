# Re-point code citations an edit shifted

**When:** `test_code_citations.py` fails with "names `X`, but line N is in `Y`" after you added or removed lines in a cited source file.
**Instead of:** reading the failure, grepping each symbol by hand, then fetching the document to find the exact citation text.
**Status:** verified
**Last verified:** 2026-09-28

## Do
1. `uv run pytest -q -p no:tach tests/entry_points/test_code_citations.py 2>&1 | grep "names \`"` — each line gives the document, `file:N` and the symbol it should name.
2. For each symbol: `grep -n "def <symbol>(" <file>` gives its new line.
3. Write `pairs.json` as `[["<file>:<old> (\`<symbol>\`)", "<file>:<new> (\`<symbol>\`)"], ...]` and run `python3 docs/playbooks/scripts/patch_docir_text.py <doc-id> pairs.json` (whole-body mode; the citations usually sit in a table).

## Verify
`uv run pytest -q -p no:tach tests/entry_points/test_code_citations.py` passes.

## Pitfalls
- The document id is the prefix of the file name the failure prints (`arch-0a3c2d6d54a6-…md` → `arch-0a3c2d6d54a6`).
- One inserted method shifts every citation below it by the same amount; check each symbol anyway, since a citation may sit above the edit.
- A citation is often truncated mid-cell in `docir get` output; match on `file:N (\`symbol` without the closing backtick if the cell wraps.
- Editing the document withdraws its `verified` stamp; do not re-stamp it inside the task that moved the code.
