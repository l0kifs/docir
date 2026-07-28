# tags

## Purpose
Owns the registry of tags — the controlled vocabulary that classifies
documents. It is the single source of truth for which tags exist and keeps that
vocabulary consistent everywhere a tag is used.

## Public operations
- `TagService.add(key, description) -> TagView` — register a new tag
- `TagService.list_all() -> [TagView]` — every registered tag
- `TagService.rename(old, new) -> None` — rename a tag across the registry and
  every document that uses it
- `TagService.remove(key, force) -> None` — remove a tag; blocked while in use
  unless forced (then stripped from referencing documents)

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
- platform: persistence, filesystem, errors

## Policy
- permissions: none (single-user local CLI; see ADR-0003)
