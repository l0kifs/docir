---
paths:
  - "src/docir/modules/documents/application/services/document_service.py"
  - "src/docir/modules/documents/domain/services/markdown_sections.py"
  - "src/docir/modules/documents/domain/services/markdown_headings.py"
  - "src/docir/modules/documents/domain/services/code_globs.py"
  - "src/docir/platform/filesystem/code_matcher.py"
  - "src/docir/entry_points/payload.py"
---

# The document read path

Read paths exist to save the caller's context, which is why they return less than they could. Adding to what they return is a change to the contract, not an improvement.

- **Read paths return skeletons (two-tier retrieval).** `query`/`search`/`context` return
  `DocumentSummary` (frontmatter + typed edges + staleness, **no body**); only `get` returns the full
  `DocumentView` with the body. Do not add the body back to the list paths — the skeleton is the
  context-saving contract. `get --section "<heading>"` narrows the body to one section and is the
  paired read for chunked ranking (adr-927aa43d9635): it returns exactly the span `--replace-section` would
  overwrite (`extract_section` and `replace_section` share one end boundary — do not let them
  diverge, or an agent can read one span and overwrite another), and an unknown heading raises
  *listing the real ones*, because discovering them by fetching the whole body is the cost the flag
  removes.
  **All three — read, write and chunk — take their headings from one scanner,
  `markdown_headings.scan_headings`, and a heading inside a fenced block is not one**
  (issue-af046a467575). `markdown_sections` used to scan lines naively while `chunking` tracked
  fences, so a document quoting a markdown template read as sections the embedder never saw:
  `--section` returned a fragment ending in an *unclosed* fence, and `--replace-section` ended the
  span at the phantom boundary and stranded the rest of the quote at top level — a corrupted body,
  reported as success. Do not give any of the three its own heading regex; the two agreeing is the
  invariant, and `test_markdown_headings.py` asserts set **equality** against the shared scanner
  because an earlier subset assertion passed with the divergence reintroduced.
  **Read and write agree on the span and differ by one line inside it**: the read returns the
  heading, `--replace-section` and `--append-section` write their own. Handing the read's
  output straight to the write therefore spelled the heading twice, and nothing could take the
  second one out — `replace_section` matches the first occurrence and keeps its line,
  `append_section` adds a sibling, so the exit was `--replace-body --force`
  (issue-9d4db5cd5f29). Text *opening* with the heading it is written under is now refused at
  Tier 0, narrowly: a sub-heading first, the heading named further down and the heading quoted
  in a fence are all ordinary content, and all three are pinned. `--remove-section` deletes a
  heading and its span — first-match like everything else here, no `#`-marker guard (a body
  already spelling `## ## X` has to be nameable to be repairable), and it is the only body edit
  that takes a heading and no text.

- **A document's `code` globs are validated for shape on write and for reality only in Tier 1.**
  Optional `code:` frontmatter names the code a document governs (issue-90aea6d1b891). Tier 0
  refuses an absolute path, a `..` segment, a backslash separator and an empty entry — patterns
  that can never match — but *accepts* one that matches nothing today, because a decision is
  routinely written before the code it decides. `docir check` then reports `unmatched-code` as a
  warning, and only when `Settings.code_root` finds a `.git` above the store: a global
  `~/.docir` has no tree to resolve a repo-relative pattern against, and an unresolved pattern
  (absent from the map handed to `GraphChecker`) means *unknown*, not missing — the same rule
  `similarity` follows. `content_hash` sorts the globs, like tags: the file keeps the author's
  order and the index returns them sorted, and without the sort every reindexed document read as
  hand-edited and `--replace-body` refused a write that loses nothing.
  **`query --code <path>` matches the patterns as text** (`domain/services/code_globs.py`), not
  by walking the tree — the branch that *deletes* a file is exactly when its decisions must be
  re-read, and a filesystem match answers "nothing" there. It is a post-SQL predicate applied
  **before the limit**, sharing one scan loop with `--stale` (`_post_sql_predicate` /
  `_scanned_page`); a document governing a directory governs the files in it, since a miss costs
  an unread decision and a false hit costs a glance. The forward check (`RepositoryCodeMatcher`,
  "does this pattern still name anything") stays `Path.glob`; the two answer different questions
  and only their *grammar* has to agree.
