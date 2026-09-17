# Patch a sentence in a docir document

**When:** a docir document is wrong in one place and the fix is `--replace-section` or `--replace-body`, which take the whole text back.
**Instead of:** `docir get --section`, pasting the section back by hand with the edit in it, then re-reading the result to see whether the edit landed and nothing else moved.
**Status:** verified
**Last verified:** 2026-09-17

## Do
1. Write `pairs.json` as `[["<exact old text>", "<new text>"], ...]`. Copy each `old` from `docir get <id>` output verbatim, line breaks included; a paraphrase will not match.
2. One section: `python3 docs/playbooks/scripts/patch_docir_text.py <id> pairs.json --section "<heading text>"` (the text after `## `, nothing else).
   Whole body (a heading rename, or edits across several sections): omit `--section`; the script uses `--replace-body --force`.
3. Anything else the same write needs goes after `--`: `-- --set-description "..." --set-code "a,b"`. Add `--verified` there only when you re-read the whole document against the code.

## Verify
Exit 0 prints `{"id": ..., "updated": ..., "verified": ..., "revoked": ...}`; an `old` that occurs zero or more than once exits 1 and writes nothing, naming the pair. Then `docir get <id> --section "<heading>"` shows the new text and `docir check` reports no `malformed` or `unresolved-link` for the document.

## Pitfalls
- In section mode the heading line is stripped before matching, so never put `## Heading` in a pair; in body mode you may, which is how a heading is renamed.
- Section mode resolves a repeated heading to the first one; use body mode for the second.
- Editing a verified document withdraws its stamp and records `revoked` — intended, the review covered the old text. A `--set-code`, `--verified` or any other flag on the same write also moves `updated`, so expect two frontmatter lines in the diff.
- `old` in a table row is safest as the cell plus its `|` delimiters, since a bare number or path may occur elsewhere.
- Runs `uv run docir`, so it needs the repo environment (`uv sync`) and the store the CWD resolves to.
