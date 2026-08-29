<!-- docir:v0.22.0 — generated file, do not edit by hand; refresh with `docir agent update` after upgrading docir -->
# Publishing the corpus for humans

`docir build --out site/` renders the whole store as a self-contained static
site — one page per document, no external requests, publishable to GitHub Pages
unchanged. Reach for it when someone asks for the decisions in a reviewable
form; it shows the relation graph in both directions and flags stale documents.

```bash
docir build --out site/ --title "<project> — design docs"   # heading, tab, wordmark
docir build --out site/ --logo assets/logo.svg              # mark + favicon
docir build --out site/ --mermaid vendor/mermaid.min.js     # draw mermaid fences
docir build --out site/ --include-archived                  # archived docs too
```

Always pass `--title`: it is what the site calls itself, and the default is the
word "Documentation" on every page. `--logo` sets the top-left mark *and* the
favicon — pass it when the repo has its own logo, otherwise the site carries
docir's. Archived documents are left out unless you ask for them. `--out` is
regenerated each build, and a directory docir did not build is refused unless
you pass `--force`.

A ` ```mermaid ` fence in a body publishes as its own source unless you pass
`--mermaid` pointing at mermaid's **classic-script** bundle — docir loads the runtime with a
plain `<script src>`, so it needs the file that sets `window.mermaid` rather than the ESM
entry. That is `dist/mermaid.min.js`, which mermaid still ships on the 11 line even though its
package `exports` name only the `.mjs` module. Fetch it once:

```bash
curl -o mermaid.min.js https://cdn.jsdelivr.net/npm/mermaid@11.16.1/dist/mermaid.min.js
docir build --out site/ --title "<project>" --mermaid mermaid.min.js
```

An `.mjs` runtime is refused with that URL in the error; docir writes it beside the
pages and loads it from there, so the site still opens from `file://`. docir
does not ship the bundle — it is megabytes — and writes it only when a document
actually draws something.

