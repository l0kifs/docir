---
code:
- src/docir/modules/indexing/domain/scoring.py
- src/docir/modules/documents/application/services/document_service.py
created: '2026-08-16'
description: What score and similarity each mean on a context or search hit, which
  one --min-score filters, and the two hits it never drops.
id: ref-0e14d7c32dbf
owner: maintainer
related:
- adr-927aa43d9635
status: active
tags:
- retrieval
- cli
title: How to read a ranked result
type: reference
updated: '2026-08-25'
---

Every read path that ranks — `context` and `search` — returns two numbers per hit, and
they answer different questions. Confusing them is how "the top result scored 0.03, so
nothing matched" and "the top result came back, so it is relevant" both happen.

## score orders; it does not measure

`score` is rank fusion. The full-text ranking and the vector ranking are combined by
reciprocal rank fusion, which reads *positions* rather than strengths — so the number
says where a document placed against the others and nothing about how good the match was.

A nonsense query against a one-document store scores that document about 0.0328, which is
what a perfect match in the same store scores. Read `score` as an ordering and never as a
quality, and never threshold on it.

## similarity is the number with absolute meaning

`similarity` is the raw cosine between the query and the winning vector, from 0.0 to 1.0.
It is comparable across queries and across stores, which is what makes "nothing here is
relevant" expressible at all.

As rough guidance rather than thresholds:

| similarity | read it as |
|---|---|
| above 0.7 | on topic |
| 0.4 – 0.7 | related; read the description before trusting it |
| below 0.4 | probably noise |

## --min-score filters similarity

Despite the name, `--min-score` is applied to `similarity`, not to `score`:

```bash
docir context "implement a new auth endpoint" --min-score 0.5
```

An empty result is then a real answer — nothing in the corpus is close enough — rather
than the top of a list that had to return something. That is the whole point of the flag,
and it only works because the number it reads means something absolutely.

## Two hits it never drops

**Graph neighbours.** A hit marked `via_graph` is present because a selected document
links to it, not because it scored. Filtering it on relevance would remove exactly the
context the expansion exists to add.

**Hits with no `similarity` at all.** An absent value means *no current vector* — the
document changed and the embedding queue has not caught up — not a score of zero.
Dropping those would filter on queue staleness rather than on relevance. Run
`docir embed --flush` if you need the floor to cover everything.

This is also why a 0.0 is rounded rather than omitted from the output: absent has to keep
meaning "not scored".

## matched_section names where the hit came from

Each `##` section is embedded separately, so a hit usually means one section matched.
`matched_section` carries the heading whose vector earned the rank — pass it straight to
`docir get <id> --section "<heading>"` instead of pulling the whole body.

Absent means the match is not addressable as a section: the document's own vector won, the
hit was lexical, or it arrived through the graph. It never means nothing matched.

## An absent field means its default

Captured output is trimmed — fields holding no value are dropped, and `score` and
`similarity` are rounded. So no `owner` key means no owner, no `stale` key means not
stale, and an empty `tags` list is simply not there.

Pass `--no-trim` for the full, unrounded payload when you are comparing numbers rather
than reading results.

## Or ask the ranking directly

Everything above explains two numbers because the numbers were all there was. Since 0.18.0 they
are not: `docir context "<task>" --explain` returns the terms behind each rank —

```
lexical_rank=7 lexical_rrf=0.0149 semantic_rank=1 semantic_rrf=0.0164
similarity=0.813 matched_section="Switching embedders re-embeds…"
```

— and a graph-reached hit carries `via_graph_from` and `via_graph_route` instead, naming the
seed it came from and whether that edge was a successor, an ordinary relation or a mention.

It answers the question `--min-score` cannot. `--min-score` tells you whether anything relevant
exists; this tells you **why this outranked that**. A hit with a `semantic_rank` and no
`lexical_rank` shares no vocabulary with your wording and was found by meaning alone; the
reverse means the embedder contributed nothing to it.

Keys are omitted rather than nulled, so an absent `lexical_rank` is the finding, not a gap in
the payload. `docir search --explain` gives the thinner version: rank and raw BM25.
