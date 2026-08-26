---
paths:
  - "src/docir/config/**"
  - "src/docir/entry_points/composition.py"
---

# Store discovery, `docir init` and the composition root

Where the store is, and what creating one may overwrite.

- **`docir init` scopes a repo to a project-local `.docir/` store (adr-20eec6e2e2ca).** It is a bootstrap
  operation in the composition root (`initialize_store`), run in-process by a thin CLI command (no
  daemon/dispatcher). It writes `docs-schema.yaml` + a `.gitignore` for the derived index and runs
  migrations via the normal startup path. `Settings.resolve` discovers the store by walking up for
  `.docir/` (`config/settings.discover_project_home`), so the commit story is `.docir/docs/` +
  `docs-schema.yaml` committed, index gitignored. Do not reach into `documents.infra` for the schema —
  `DEFAULT_SCHEMA_YAML`/`PROFILE_NAMES` are exported from `documents.api`.

- **Both home decisions live in `config/settings.py`.** `Settings.resolve` finds an *existing*
  store (flag → env → discovered `.docir` → global); `new_store_home` picks where `init`
  *creates* one (`--home` names the store directly, a positional directory means
  `<dir>/.docir`, both is an error). They sit side by side and cross-reference each other
  because `init` used to compute its own home in the CLI layer, silently ignored `--home`,
  and so escaped every review that traced `resolve`. Do not move either out.

- **`init --force` treats the two files it writes as unequal.** The `.gitignore` is a constant
  `composition.py` generates, so regenerating it costs nothing; `docs-schema.yaml` holds every
  type, status and cadence a person decided on and **cannot be rebuilt from the documents**.
  So `--force` rewrites the schema only while it is still byte-identical to the generated one;
  a customised schema is *kept* (not refused), reported as `schema_preserved` and warned about
  on stderr, and replacing it needs `--force-schema`. Skipping rather than raising is
  deliberate: an exception aborts before the `.gitignore` is written, which is the thing the
  user ran the command for.
