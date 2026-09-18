<!-- docir:v0.28.0 — generated file, do not edit by hand; refresh with `docir agent update` after upgrading docir -->
# Editing `docs-schema.yaml`

The one file you edit by hand — there is no CLI write path for it. Read
[`SKILL.md`](../SKILL.md) for the default types and statuses; this file is what
to do when they do not fit.

## Contents

- Required keys on every type — `prefix`, `statuses`, `default_status`
- Optional keys — `required`, `inactive_statuses`, `level`, `review_days`, `id_style`
- `max_body_chars` — the one schema key that can refuse a write
- `relation_types` — declaring what a relation kind means
- Changing one key of a type a profile ships — write a *partial* block
- `disable_types` — giving up a type to free its prefix, and moving the documents
- `checks:` — a store's own rules, as JMESPath expressions
- `allowed_relations` — the whitelist trap

## Editing the schema

`docs-schema.yaml` is the one file you edit by hand (no CLI write path). Prefer
adding a **profile** over inline types; add inline `types:` only for something
no profile covers. Run `docir schema validate` after every edit.

`schema validate` answers two questions: whether the file loads, and **what it
costs the corpus** — how many documents carry a type, status, required field or
relation kind the schema no longer accepts, with a sample of their ids. Check
that number before you commit a schema edit; it is the one thing `git diff`
cannot show you, since the core and profiles merge in at load. It never changes
the exit code — the schema is valid, and the documents are what moved.

Three keys are **required** on every type — omitting any is a `SchemaError`:

| key | type | notes |
|---|---|---|
| `prefix` | str | mints ids (`tp` → `tp-0001`). **Unique across the whole merged schema**, so check `docir schema show` first. |
| `statuses` | **mapping** | `status: [targets it may transition to]`, *not* a list. Terminal status → `[]`. |
| `default_status` | str | must be a key in `statuses`. |

**Every status name you write must be a key in that type's `statuses`** — a
transition target, `default_status`, and each `inactive_statuses` entry. A typo
(`open: [closd]`) is rejected at load with the declared names listed, so it fails
on the next command rather than surviving until a write. That check runs on
*every* command, not only `schema validate`: a broken schema stops the store.

Optional: `required` (extra frontmatter fields), `inactive_statuses` (hidden from
default reads), `level` (int; see below), `review_days` (staleness cadence; 0 =
never stale), `id_style` (`sequential` | `random`), `allowed_relations`,
`max_body_chars` (see below).

`level` only bites on **dependency** edges: a `depends_on` or `refines` edge from
a higher-level type to a lower-level one is a Tier 1 `layering` warning. Ordinary
`relates_to` links never are — linking a decision to the issue that motivated it
is normal and silent.

```yaml
relation_types: [governs, blocks]   # extra kinds on top of the core six
types:
  test_plan:
    prefix: tp
    default_status: draft
    statuses:
      draft: [active]
      active: [deprecated]
      deprecated: []
    inactive_statuses: [deprecated]
    level: 3
    review_days: 180
```

## Changing one key of a type a profile ships

`types:` entries are usually *new* types. To adjust one the core or a profile
already declares, write a block that leaves out `prefix` / `statuses` /
`default_status` — docir reads that as an overlay and keeps everything you did
not name:

```yaml
profiles: [software]
types:
  decision:
    max_body_chars: 8000      # statuses, level, review_days all still the core's
```

**Do not paste the whole type in to change one key.** With all three required
keys present the block is a *declaration*, and it takes the type over: from then
on your copy is the definition, and upgrades to docir stop reaching it. Write it
out only when you want to own the grammar.

Check which you got with `docir schema show`, which prints the resolved type —
an overlay that landed shows your key beside the ones you did not write.

Two limits. `statuses:` inside an overlay swaps the mapping out entirely (there
is no way to add a single status), and an overlay of a name nothing else
declares is an error that lists the available names for you — nine times in ten
it is a `profiles:` entry you meant to add.

## `max_body_chars` — the one schema key that can refuse a write

Every other key here shapes what a document may *say*. This one caps how long it
may get, and it is the only Tier 0 rule that reads the body:

```yaml
types:
  test_plan:
    max_body_chars: 8000            # absent and 0 both mean no ceiling
    max_body_chars_enforce: false   # optional: warn instead of refusing
```

**No type ships with a ceiling.** Until you set one, nothing is refused for
length — so turning this on is a deliberate act, and the number is yours.

`docir add`, and any `docir update` that leaves the body over the ceiling **and
longer than it already was**, exits **9**:

```
error: body is 9120 chars, over the 8000-char limit for type 'test_plan'
— split it into linked documents, or raise `max_body_chars` for 'test_plan'
in docs-schema.yaml
```

Growth is the trigger, not size. A document already over its ceiling still takes
`--set-title`, `--status`, `--set-tags`, `--type` and a *shorter*
`--replace-body`, so you are never locked out of the edit that fixes it. When
you hit this, the move is to split — lift a section into its own document and
link the two — not to raise the number:

```bash
docir get tp-0001 --section "Rollback"                  # read the section out
docir add --type test_plan --title "Rollback" \
  --description "..." --related tp-0001 --body "..."    # ...into its own doc
docir update tp-0001 --remove-section "Rollback"        # ...and out of this one
```

`max_body_chars_enforce: false` keeps the ceiling and reports instead of
refusing: the write succeeds, the warning goes to stderr, and the JSON carries
`body_limit_notice`. Setting it without a `max_body_chars` to relax is a
`SchemaError` — there would be nothing to make advisory.

The same number is what `docir lint --deep` reports as `scope-creep`, which is
all this key did before it gained a tier. Absent, the lint falls back to 8000;
`0` turns off both halves, the right answer for a type that holds a register (a
glossary split in half is two half-glossaries). So `max_body_chars_enforce:
false` is the way to keep the old advisory behaviour exactly — one line, no
renaming.

`relation_types` also takes a **mapping**, which is how you declare what a kind
*means*. Three optional properties, all defaulting to false:

| property | effect |
|---|---|
| `symmetric` | the edge says the same thing both ways, so a mutually-referencing pair is not a `cycle` finding |
| `dependency` | the source sits *above* the target in the type hierarchy — the only claim `layering` reads |
| `blocking` | the source *waits for* the target, so a source whose blockers have all closed is `unblocked`. Separate from `dependency`: `refines` is a dependency and not a blocker |
| `successor` | the *incoming* direction answers "is this still current?", so `docir context` follows it backwards |

```yaml
relation_types:
  governs:     {dependency: true}
  duplicates:  {symmetric: true}
  replaced_by: {successor: true}
  blocks:      {}                  # registered, all defaults
```

Defaults are asymmetric on purpose: a kind you do not describe is still
cycle-checked (so a `blocks` loop is reported) but adds no layering warning and
changes no traversal. The core six carry their meaning without being listed —
`relates_to` and `contradicts` are symmetric, `supersedes`/`contradicts` are
successors, `depends_on`/`refines` are dependencies. `docir schema show` prints
the resolved properties of every kind.

Merging only **adds** types: the core is always merged, and an inline block can
only override a type by its own name. `disable_types:` is how you give one up —
and it is what frees that type's `prefix`, so your own type can claim it and the
corpus keeps the ids it already has.

```yaml
profiles: [software]
disable_types: [decision]        # the name stops resolving, and `adr` is free
types:
  product_decision:
    prefix: adr                  # every existing adr-... id stays valid
    default_status: draft
    statuses: {draft: [active], active: []}
```

Then move the documents over — one at a time, because only you know what each old
status becomes:

```bash
docir query --type decision --limit 500 | jq -r '.[].id' \
  | xargs -I{} docir update {} --type product_decision --status active
```

Until they are moved, `docir check` reports them as `unknown-type` (a warning, so
nothing is blocked) beside the `schema-drift` finding naming the change. Disabling
a name nothing declares, or one the same file declares inline, is refused.

`checks:` is how a store states a rule about **its own** corpus. Each is a JMESPath expression
over the same projection `query --expr` uses, so write it as a query first and declare it once
it finds what you meant. A truthy result *is* the finding — the expression describes documents
that are wrong.

```yaml
checks:
  superseded-still-live:
    expr: "length(related_by[?kind=='supersedes']) > `0` && status != 'superseded'"
    message: something supersedes this and it is still in a live status
```

The name becomes the finding's kind and may not collide with one docir defines. Always a
warning, never an error — `--strict` gates on docir's own error kinds and must mean the same
thing in every repository; `--strict-all` is what makes a store's rules fatal.

`allowed_relations` is a **whitelist trap**: absent/empty means permissive (any
kind, any target), but listing one kind restricts the type to *only* the listed
kinds — re-list every kind you still want, including `relates_to`.

```yaml
    allowed_relations:
      relates_to: []                  # [] = any target type
      depends_on: [runbook, decision] # only these target types
```

