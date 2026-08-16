---
code:
- src/docir/modules/publishing/infra/rendering.py
created: '2026-08-16'
description: docir build parses bodies with the CommonMark preset, which passes raw
  HTML through, so a script tag in a contributed document runs on the published site.
id: issue-6e9005dda3a3
owner: maintainer
related:
- adr-a343140d72e2
status: open
tags:
- cli
- docs
- material
title: A published page executes raw HTML from a document body
type: issue
updated: '2026-08-16'
---

`docir build` renders each document body with a CommonMark parser that passes raw HTML
through unchanged. A `<script>` tag written into a body therefore executes on the published
page, under the site's own origin.

## What the renderer does

The parser is built as `MarkdownIt("commonmark", {"linkify": False})`. The `commonmark`
preset sets `html: True`, because raw HTML is part of the CommonMark specification, so the
body is emitted verbatim:

```
>>> parser.render("Body text <script>alert(1)</script> end")
'<p>Body text <script>alert(1)</script> end</p>'
```

Everything docir interpolates *around* the body is escaped — titles, descriptions, tags,
owners, filter values, the graph payload. The body is the only opening, and fenced and
inline code inside it are escaped normally, so quoting HTML in a document is safe.

## Why it is usually fine

The corpus is the repository's own: committed, reviewed like code, and written through the
CLI rather than dropped in. HTML in a body is also genuinely useful — a `<details>` block
that folds a long table, an `<img>` with a width, a centred header. Turning raw HTML off
wholesale would break documents that legitimately use it, and would make docir's renderer
less capable than every other markdown tool the author has.

## When it is not fine

A repository that accepts documentation pull requests and publishes with `docir build` in
CI. A contributed document is then executable content on the project's site, and the
reviewer approving the prose is not necessarily reading it as code — the diff looks like
documentation.

The corpus stops being trusted input at the moment someone outside the project can add to
it, and nothing in docir marks that transition. A store cannot currently say "this corpus
is not mine".

## What this issue does not decide

Three shapes are plausible and they are not equivalent:

- **Leave it and keep documenting it.** Correct if the trust assumption always holds, and
  the assumption is at least stated.
- **A flag on `docir build`** that strips or escapes raw HTML, for the untrusted-corpus
  case. Puts the choice at publish time, where the person knows whose documents they are.
- **Switch the default and let documents opt in.** Safe by default, at the cost of breaking
  existing bodies on upgrade and of diverging from CommonMark.

The choice trades specification conformance against a default that is safe for a corpus
docir cannot inspect. That is a decision, not a fix.

## Where it is written down today

`.github/SECURITY.md` describes the behaviour under "Published sites", which is the honest
thing to do until this is decided. A policy file is not where a renderer's trust boundary
belongs, though — nothing in the publishing module's own documents says it.
