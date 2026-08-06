---
code:
- src/docir/modules/publishing/infra/rendering.py
created: '2026-08-05'
description: Why the published index shows applied filters as removable chips, accepts
  tracker-style tokens (type:x, is:stale, -status:y), records each facet step in history,
  and dims zero-count options instead of dropping selections.
id: adr-6afdbace7a45
owner: maintainer
related:
- kind: refines
  to: adr-a343140d72e2
- adr-307ba1f1a820
status: accepted
tags:
- cli
- docs
title: The index filter is chip-displayed state with a token grammar
type: decision
updated: '2026-08-06'
---

## Context

adr-a343140d72e2 gave the published index faceted filters: type/status/updated
checkbox popovers with live counts, OR-within/AND-across semantics, and the
combined state mirrored into the URL. A research pass against that bar
(2026-08-05; Baymard/NN/g faceted-search research plus the filter models of
GitHub Issues, Linear, Jira, Datadog and Pagefind) found five gaps, each a
documented failure mode rather than a taste call:

- **Applied state was invisible.** The facet summaries showed counts
  ("type · 2"), the pattern Baymard names as the anti-pattern: the reader must
  reopen every popover to learn what is filtering the list. Removable chips
  above the results are the ~72% desktop convention.
- **Narrowed options vanished, and selections were silently dropped.** The
  status facet hid options the type selection excluded and unchecked a
  selected status that became unavailable — the "where did it go?" confusion,
  solved in the wild by dimming at count zero and never dropping a selection
  (its chip stays visible as the cause of an empty list).
- **Back ignored filtering.** Every change wrote `replaceState`, but users
  perceive each facet change as a view; Baymard measures 27% of sites
  mishandling exactly this. A step must be a history entry; a keystroke not.
- **Rows displayed facts the filter could not reach.** Owner and staleness
  were visible on rows and views but not filterable — and the review queue
  (`query --stale`) had no shareable URL equivalent on the site.
- **Zero results dead-ended.** No recovery action, the failure Baymard finds
  on 68% of no-results pages.

Tracker muscle memory was the second input: GitHub's dropdowns write
`key:value` tokens into one input, Linear renders filters as operator-editable
chips. Engineers try that grammar in any filter box.

## Decision

One state object with a single mutation door per fact, displayed as chips:

- **Chips are the canonical display.** Every applied filter — facet value,
  exclusion, stale flag, date window — is a removable chip above the list, in
  the order applied; "remove last filter" pops that order.
- **The text box doubles as a token bar.** `type:x`, `status:x`, `owner:x`,
  `is:stale`, `updated:30d` and `-` negations convert to chips, but only when
  the value exists in the corpus; anything else stays free text and searches
  as words. The GUI and the grammar share one state, so neither can drift.
- **Facets follow the corpus.** The owner facet renders only when a document
  has an owner; the stale toggle only when something is stale; the stale
  banner links to `?is=stale`, which makes the review queue a copyable URL.
- **Zero-count options ghost.** Dimmed and disabled, never removed; a
  selection is never silently dropped.
- **Each facet step is `pushState`; typing is `replaceState`.** Back undoes
  filtering. Load, Back/Forward and preset views all funnel through one
  params reader that drops unknown values instead of filtering to zero.
- **Preset views at browsing scale.** Corpora big enough for the recent strip
  get one-click views (all / stale / open issues / updated·7d), each carrying
  its target query string verbatim (`data-sig`), so a preset lights up when
  the reader assembles the same state by hand.
- **Zero results offer recovery**: remove the last filter, or clear all.

The URL schema is extended backward-compatibly: existing `type=`, `status=`,
`updated=`, `from=`/`to=`, `q=` links keep restoring; `owner=`, `is=stale`
and `-`-prefixed exclusion values are new.

## Consequences

- **A behaviour change, not just an addition**: a selected status that stops
  matching now stays selected (ghosted, chip visible) where it used to be
  dropped. The old rationale — "filtering to zero with no visible cause" —
  is answered by the chips row plus the recovery buttons.
- The filter script roughly doubles, but remains dependency-free, inline and
  offline-complete; nothing about adr-a343140d72e2's self-containment moves.
- The engine was designed against the portal redesign concept (concept 1 in
  `design-concepts/`) and is intended to carry over unchanged when that skin
  lands; this ADR covers the behaviour, not the visual redesign.
- Pinned by markup tests in `tests/modules/publishing/test_site_rendering.py`
  (chips, tokens, ghosting, pushState, conditional facets, presets,
  recovery); the interactive behaviour was verified in a browser against
  docir's own 106-document corpus.
