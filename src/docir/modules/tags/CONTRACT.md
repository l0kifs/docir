# tags

## Purpose
Owns the registry of tags — the controlled vocabulary that classifies
documents. It is the single source of truth for which tags exist and keeps that
vocabulary consistent everywhere a tag is used.

## Public operations
- `TagService.add(key, description) -> TagView` — register a new tag. The key must match the
  shared grammar (`platform.naming.TAG_KEY_PATTERN`: lowercase letters, digits and hyphens,
  starting with a letter) or the call raises `ValidationError`. Keys already in the registry
  are never rewritten — a pre-existing one that fails the grammar is a `tag-key-format`
  *warning* from `docir check`, fixed by renaming.
- `TagService.list_all(limit=DEFAULT_TAG_PAGE, offset=0) -> [TagView]` — one key-ordered page of
  the registry. Paged because listing grows with the vocabulary; the write paths still read it
  whole, since a rename rewrites every referencing document. Each `TagView` carries `usage`,
  the number of indexed documents (archived included) that hold the tag, so a dead tag is
  visible; `0` means `remove` will not need `--force`.
- `TagService.rename(old, new, merge=False) -> tuple[str, ...]` — rename a tag across the
  registry and every document that uses it, returning the ids rewritten. Only `new` is
  validated against the key grammar: renaming *away* from a legacy key is the migration path. Renaming onto an
  existing key is refused unless `merge`, which folds `old` into `new`: documents carrying
  both end with one, and `new`'s description survives.
- `TagService.remove(key, force) -> None` — remove a tag; blocked while in use
  unless forced (then stripped from referencing documents)

Neither `rename` nor `remove` advances a rewritten document's `updated`: a bulk
classification edit is not a human re-verification (see the staleness invariant).

## Events published
- none (no event bus; see ADR-0002)

## Events consumed
- none

## Owns
- data: the tag registry (`docs/tags.yaml` and its index projection).
  Physically stored in the shared index/filesystem owned by `platform`
  (grandfathered; see ADR-0002).

## Depends on
- modules: none
- platform: persistence, filesystem, errors, naming (the tag-key grammar)

## Policy
- permissions: none (single-user local CLI; see ADR-0003)
