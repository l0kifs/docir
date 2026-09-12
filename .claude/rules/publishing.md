---
paths:
  - "src/docir/modules/publishing/**"
---

# Publishing — `docir build`

The site is derived like the index, which is why the build deletes before it writes.

- **`docir build` regenerates its output directory, and that is why it guards it.** The site
  is derived like the index, so every `*.html` is removed before writing — a document deleted
  from the store must not survive as an orphaned page nobody can reach and nobody knows is
  stale. "Delete everything here first" has to be sure it owns "here": a previous build leaves
  `.docir-site`, and anything else non-empty is refused unless `--force`, because `--out` is a
  path a person types. The build does one `query` then one `get` per document — bodies are
  absent from every list path by contract (the skeleton rule), so a build that stopped at
  `query` would report the right count and publish empty pages, which looks exactly like
  success. `test_e2e_build.py::test_bodies_reach_the_pages` pins that.

- **A typed filter token commits on a space or Enter, not on the keystroke that
  completes it.** `extractTokens` skips a `field:value` sitting at the cursor with no
  whitespace after it, so passing through `type:dec` on the way to `type:decision` does
  not filter to nothing. The consequence is the part worth knowing: an uncommitted token
  is still matched as *free text*, and no document body contains a colon-pair, so the
  index reads "0 shown / No documents match" until a space or Enter converts it into a
  facet chip. That intermediate state is indistinguishable from a broken filter, and has
  been reported as one — from a browser session that typed the token and never pressed
  anything else. Before concluding the filter is broken, press Enter. The checkbox
  facets and the URL parameters reach the same state by a different door
  (`?type=decision`), which is the quickest way to tell a parsing bug from this.
