# docir → C# / .NET 10 solution layout

A port of the existing Python codebase to .NET 10, fully compliant with
[ARCHITECTURE_RULES.md](ARCHITECTURE_RULES.md) (Modular DDD), and chosen so the
**compiler + analyzers + architecture tests become the reliability gate** — the
reason for the port.

> **Structural note.** ARCHITECTURE_RULES §1.3 mandates *vertical before
> horizontal*: slice by business capability first, technical layer second, and
> **layers live inside a module, never at the project root** (§2 forbids
> root-level `domain/`, `application/`, `infrastructure/`). So this is **not** a
> layered `Docir.Domain`/`Docir.Application`/… solution. It is one project per
> **bounded context**, each containing its own `domain/application/infra`.

## Why this shape fits docir naturally

docir's core thesis — *git files are the source of truth; the SQLite index is a
derived, rebuildable projection* — **is** the Modular-DDD read-model pattern
(§5.3): each read-side module maintains its own projection from the owner's
events, reconciled by rebuild. The architecture rules and docir's design already
agree; the rework just makes the boundaries machine-checked.

---

## 1. Module map (bounded contexts)

Three modules, plus the three permitted root buckets (`platform/`, `config/`,
`entry_points/`). Storage ownership is exclusive (§5.3):

| Module | Owns (tables/files) | Owner concept of correctness |
|---|---|---|
| **catalog** | `documents`, `relations`, `document_tags`, `id_sequences`; `docs/*.md` files | A document's frontmatter is valid per schema; transitions legal; relation graph consistent |
| **tags** | `tags`; tag reference-count projection; `tags.yaml` | The tag vocabulary is unique and referentially sound |
| **retrieval** | `documents_fts`, `embeddings` | The relevant-set ranking (lexical + semantic + graph) |

Maps 1:1 onto today's application services: `DocumentService`→catalog,
`TagService`→tags, `MaintenanceService` splits by ownership (`check`/`reindex`
files → catalog; `lint`/`embed flush`/`reindex embeddings` → retrieval).
`documents_fts` + `embeddings` fold into **one** module (retrieval) because
lexical and semantic search share the single invariant "the relevant set" and
are fused by the same scorer — splitting them would create two modules a third
must reach into (§3.3).

### Dependency graph — acyclic by construction

```
entry_points/  ──►  catalog.api, tags.api, retrieval.api, platform, config
retrieval      ──►  catalog.api            (get docs, graph neighbors, bodies)
catalog        ──►  tags.api               (does a tag key exist? — write validation)
tags           ──►  (nothing internal)
```

Direct `api` calls form a line: **retrieval → catalog → tags**. No cycle (§4).
Everything else is a **domain event delivered by a bridge wired in
`entry_points/`**, so no module imports another's event types (which would
re-introduce a cycle):

- **catalog** publishes `DocumentSaved`, `DocumentRemoved` → bridge → retrieval
  (update FTS + mark embedding dirty) and tags (update reference counts).
- **tags** publishes `TagRenamed`, `TagRemoved` → bridge → catalog (rewrite /
  strip the tag on referencing docs).

The bridge (in `entry_points/`) is the only code that imports two modules'
apis at once; each module's `application` handler takes **primitives**, never the
other module's types (§5.1, §5.4).

### The write flow (add a document)

1. `entry_points` CLI `add` → `catalog.api` **AddDocument** command (via the
   executor: in-process or over the daemon socket).
2. catalog validates schema/frontmatter, calls `tags.api.TagExists` per tag,
   checks `related` ids, allocates the id, writes the `.md` file, commits its own
   tables in **its own** unit of work, then publishes `DocumentSaved`.
3. Bridge delivers `DocumentSaved` (synchronously, in-process) →
   `retrieval.IndexDocument` (FTS upsert + mark embedding dirty) and
   `tags.RecordDocumentTags` (ref counts). Each commits **separately** and is
   **idempotent** (§5.1) — no cross-module transaction.
4. `--wait-embeddings` → `entry_points` calls `retrieval.api.FlushEmbeddings`.

FTS stays effectively synchronous (the in-process bus delivers before `add`
returns); embeddings stay deferred behind retrieval's scheduler with `flush` as
the escape hatch — identical observable behavior to today. If a projection write
fails after catalog committed, `reindex` rebuilds it — exactly docir's existing
"index is disposable" guarantee.

---

## 2. Solution tree

**One assembly per module.** This is deliberate: C#'s `internal` access modifier
makes "only `api.*` is public" a **compile-time** guarantee (§3.2, §8.2) — a
foreign assembly literally cannot name a module's internal types. Circular
project references are a compiler error, so **no-module-cycles (§8.4) is
compiler-enforced too.**

```
Docir.sln
Directory.Build.props            # the reliability gate — every project inherits it
Directory.Packages.props         # central package versions
.editorconfig                    # analyzer/style severities (many = error)
global.json                      # pin the .NET 10 SDK

src/
  config/
    Docir.Config/                # Settings + derived path layout; depends on third-party only

  platform/                      # shared, business-free technical capability (LEAF)
    Docir.Platform.Errors/       #   DocirException base + ExitCode; DaemonException
    Docir.Platform.Persistence/  #   SQLite connection factory, UnitOfWork base, migration runner
    Docir.Platform.Transport/    #   length-prefixed JSON, UDS server/client, Request/Response,
                                 #     IRequestExecutor (in-process + socket), in-process event bus
    Docir.Platform.Observability/#   logging setup (daemon.log)

  modules/
    Directory.Build.props        # modules-only: chains root gate + wires the layer analyzer (§8.3)
    Docir.Catalog/               # PUBLIC: Api + DTOs + events; INTERNAL: everything below
      Api.cs  CONTRACT.md
      Domain/                    #   Document, DocId, Relation, Schema, validation, graph checks,
                                 #     id generator, markdown sections, slugify
      Application/               #   Add/Update/Get/Query/Archive/Delete/Reindex/Check handlers;
                                 #     ports: IDocumentRepository, IDocumentFileStore, IClock
      Infra/                     #   SQLite repos, markdown file store, catalog UoW, migration
    Docir.Tags/
      Api.cs  CONTRACT.md
      Domain/                    #   Tag, vocabulary invariants
      Application/               #   Add/List/Rename/Remove, TagExists query, RecordDocumentTags;
                                 #     ports: ITagRepository, ITagFileStore
      Infra/                     #   tags repo, tags.yaml store, ref-count projection, UoW, migration
    Docir.Retrieval/
      Api.cs  CONTRACT.md
      Domain/                    #   Embedding + cosine, scoring/fusion, similarity-lint, SearchHit
      Application/               #   Search/Context/Lint/Flush/ReindexEmbeddings; projection handlers;
                                 #     ports: ISearchIndex, IEmbeddingRepository, IEmbedder, IEmbeddingScheduler
      Infra/                     #   FTS5 repo, embeddings repo, deterministic + ONNX embedders,
                                 #     Channels scheduler, retrieval UoW, migration

  entry_points/
    Docir.Cli/                   # THE executable (client + daemon host); no business logic
      Program.cs                 #   dispatch `daemon serve` vs client/in-process
      Composition.cs             #   DI wiring: build modules, mount surface descriptors, wire the bridge
      EventBridge.cs             #   map publisher events → consumer commands (primitives only)
      Commands/                  #   Spectre.Console.Cli command classes (one per verb)
      Rendering.cs               #   Spectre tables/panels + --json

tools/
  Docir.Architecture.Analyzer/   # first-party Roslyn analyzer (netstandard2.0); DOCIR0001 = §8.3
                                 #   layer check at build. MIT (ours) — no GPL toolchain dep (ADR-5)

tests/                           # per user directive: central tests/, SPLIT PER MODULE (see §9)
  catalog/    { domain/ application/ infra/ contract/ }
  tags/       { domain/ application/ infra/ contract/ }
  retrieval/  { domain/ application/ infra/ contract/ }
  platform/   { transport/ persistence/ }
  entry_points/  { e2e/ }        # spawn the built binary, incl. daemon
  Docir.Architecture.Tests/      # NetArchTest.eNhancedEdition: §8.1 ratchet + boundary asserts
                                 #   (§8.3 layers enforced earlier by the DOCIR0001 analyzer at build — ADR-5)
```

The `Docir.Cli` assembly is emitted as `docir` (`<AssemblyName>docir</AssemblyName>`
or `<ToolCommandName>docir</ToolCommandName>`). The **same binary** is CLI client
and daemon server (`docir daemon serve`), as `python -m docir …` is today.

---

## 3. Inside a module — the public surface

`api.*` in .NET = **one public facade type + public DTO/event records; everything
else `internal`** (§3.2). Example:

```csharp
namespace Docir.Catalog;                       // the ONLY public namespace of this assembly

public sealed class CatalogApi                 // commands + queries facade
{
    public DocumentView Add(AddDocumentCommand cmd);
    public DocumentView Update(UpdateDocumentCommand cmd);
    public DocumentView Get(string id);
    public IReadOnlyList<DocumentView> Query(DocumentQuery q);
    public void Delete(string id, bool force);
    public IReadOnlyList<CheckFinding> Check();          // Tier-1 graph health
    public ReindexResult Reindex(bool changedOnly);
    // …≤15 operations (§3.3)
}

public sealed record AddDocumentCommand(/* primitives + DTOs only */);   // owned DTO
public sealed record DocumentView(/* primitives only */);                // owned DTO
public sealed record DocumentSaved(string Id, ImmutableArray<string> Tags /*…*/); // event
public static class CatalogSurface { public static IEnumerable<CommandDescriptor> Descriptors {…} }

// Domain/, Application/, Infra/ types are all `internal` — invisible to other assemblies.
```

`api.*` **exports only** commands, queries, owned DTOs, events, and surface
descriptors — never entities, repositories, ports, UoW handles, or another
module's types (§3.2). retrieval returns its **own** `ScoredDocumentView` (not
catalog's `DocumentView`) — structurally similar DTOs are duplicated per module
by rule (§5.4), not shared.

### Where each existing type lands

| Python source | Module / layer | C# construct |
|---|---|---|
| `entities/document.py`, `value_objects/identifiers.py`, `entities/relation.py` | catalog/domain | `sealed record Document`, `readonly record struct DocId`/`Relation` |
| `schema.py`, `services/{validation,graph_checks,id_generator,markdown_sections,slugify}.py` | catalog/domain | records + pure services; `Schema.Create` factory validates invariants |
| `services/document_service.py` (add/update/get/query/archive/delete), `reindex`, `check` | catalog/application | one handler per op; ports `IDocumentRepository`, `IDocumentFileStore`, `IClock` |
| `filesystem/markdown_store.py`, `persistence/{models,repositories,unit_of_work}.py` (docs/relations/tags-link/seq) | catalog/infra | `Dapper.AOT` repos + `MarkdownDocumentFileStore` + catalog UoW |
| `errors.py`: `Validation*`, `Schema*`, `DocumentNotFound`, `StaleWrite`, `DanglingReference`, `Unknown*` | catalog/domain | derive from `Docir.Platform.Errors.DocirException` |
| `entities/tag.py` | tags/domain | `sealed record Tag` |
| `services/tag_service.py`, `filesystem/tag_file_store.py`, tags rows | tags/{application,infra} | Add/List/Rename/Remove + `TagExists` + ref-count projection |
| `errors.py`: `TagNotFound`, `TagAlreadyExists`, `TagInUse` | tags/domain | |
| `value_objects/{embedding,results}.py`, `services/{scoring,similarity_lint}.py` | retrieval/domain | `Embedding` (SIMD cosine), scorer, `SearchHit`/`ScoredDocument` |
| `services/document_service.py` (search/context), `maintenance_service.py` (lint/flush) | retrieval/application | Search/Context/Lint/Flush handlers + projection handlers |
| `persistence` FTS5 + embeddings, `embedding/*`, `embedding/scheduler.py` | retrieval/infra | FTS5 repo, embeddings repo, embedders, Channels scheduler |
| `daemon/*`, `application/executor.py`, `application/dispatcher.py` (mechanism) | platform/transport + entry_points | transport = platform; command→module routing = entry_points wiring |
| `config/settings.py` | config | `sealed record Settings` bound from `DOCIR_*` |
| `presentation/cli/*`, `composition.py` | entry_points | Spectre commands + DI wiring + event bridge |

---

## 4. platform / config / entry_points

- **`config/`** — `Settings` bound from `DOCIR_*` env (via
  `Microsoft.Extensions.Configuration`), with derived path properties
  (`docs_root`, `db_path`, `schema_path`, `tags_path`, `socket_path` [keeps the
  `sha1(home)[:12]` short name under the AF_UNIX ~104-char limit], `pid_path`,
  `log_path`, `idle_timeout`). Depends on third-party only (§4).
- **`platform/persistence`** — `Microsoft.Data.Sqlite` connection factory +
  `UnitOfWork` base + a small hand-written migration runner (applies each
  module's ordered embedded SQL scripts in a transaction, recording them in a
  `schema_migrations` table). Data access is **`Dapper.AOT`** (compile-time,
  source-generated row mapping — AOT-safe and reflection-free; see ADR-4). The
  **one** SQLite file (`index.db`) is shared physical infra, but **each module
  declares and owns its own tables + migration scripts**, and each module scopes
  its UoW to its own tables — no cross-module transaction (§5.1, §5.3).
  `Microsoft.Data.Sqlite` bundles `e_sqlite3` with **FTS5 compiled in** (more
  deterministic than the host Python's SQLite).
- **`platform/transport`** — length-prefixed JSON framing
  (`BinaryPrimitives`+`System.Text.Json`), `UnixDomainSocketEndPoint` server &
  client, `Request`/`Response`, `IRequestExecutor` (`InProcess` + `Socket`,
  respawn-once-on-stale), and the **in-process event bus**. All business-free
  (§5.4).
- **`platform/errors`** — `abstract class DocirException : Exception { virtual int
  ExitCode => 1; }` + `DaemonException`. Module-specific exceptions live in their
  owning module and derive from this base.
- **`entry_points/Docir.Cli`** — thin (§2): parse args, mount each module's
  surface descriptors into the transport's command registry, wire the event
  bridge, render. `Program.cs` runs the daemon `BackgroundService` for `daemon
  serve` (hosting retrieval's warm embedder + scheduler) or the Spectre client
  otherwise. **No handler bodies, no validation beyond transport parsing.**

---

## 5. The reliability gate

`Directory.Build.props` — inherited by every project, so guarantees can't be
skipped per-project:

```xml
<Project>
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <LangVersion>latest</LangVersion>
    <ImplicitUsings>enable</ImplicitUsings>

    <Nullable>enable</Nullable>
    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
    <WarningsAsErrors />                          <!-- promote ALL warnings, incl. CS86xx nullable -->

    <AnalysisLevel>latest-all</AnalysisLevel>
    <EnableNETAnalyzers>true</EnableNETAnalyzers>
    <EnforceCodeStyleInBuild>true</EnforceCodeStyleInBuild>   <!-- IDE0051 dead-code, etc. -->
    <Deterministic>true</Deterministic>
  </PropertyGroup>

  <ItemGroup>                                     <!-- analyzers every project inherits (all MIT/Apache) -->
    <PackageReference Include="Roslynator.Analyzers" PrivateAssets="all" />
    <PackageReference Include="Meziantou.Analyzer" PrivateAssets="all" />
    <PackageReference Include="SonarAnalyzer.CSharp" PrivateAssets="all" />
  </ItemGroup>
  <!-- §8.3 layer check runs a first-party analyzer wired into MODULE projects only
       (they alone have the domain/application/infra split) — see the §8.3 subsection. -->
</Project>
```

### ARCHITECTURE_RULES §8 enforcement, mapped to .NET

The whole point of §8 is *machine-checked boundaries*. The assembly-per-module
model makes several of them **free at compile time** — stronger than the Python
original could offer:

| §8 gate | .NET mechanism | When |
|---|---|---|
| §8.2 public-surface (only `api.*` importable) | assembly boundary + `internal` default | **compiler** |
| §8.4 no module cycles | project references can't be circular | **compiler** |
| §8.3 layer check (`domain`↛`infra`, `application`; `domain`→platform *pure primitives only* [`errors`], not services; `application`↛`infra`) | **first-party Roslyn analyzer** (`DOCIR0001`), namespace-based — see ADR-5 | **`dotnet build`** |
| §8.1 boundary linter + ratchet | `NetArchTest.eNhancedEdition` suite; greenfield ⇒ baseline empty from day one (§15) | `dotnet test` |
| §8.7 dead code | `IDE0051`/`CS0169` (+ `internal` unused) | **`dotnet build`** |
| §8.6 contract sync (`api.*` ⇄ `CONTRACT.md`) | CI step: `git diff --name-only` assertion | CI |
| §9 every `api.*` op has a contract test | `tests/<module>/contract/` | `dotnet test` |

**Intra-module layering (§8.3) is enforced at *build* time, not test time.** Since
`domain/application/infra` share one assembly, `internal` cannot separate them and
the compiler alone can't stop a domain type referencing an infra type. A **small
first-party Roslyn analyzer** (`Docir.Architecture.Analyzer`, diagnostic `DOCIR0001`)
closes that gap: it runs inside the C# compiler and, from a type's namespace, applies
the §8.3 layer matrix — `…Domain` may reference nothing internal but the pure-primitive
`Docir.Platform.Errors`; `…Application` may reference `…Domain` and other modules'
public `api`, never `…Infra`; `…Infra` may reference `…Domain`, `…Application`, and
`platform/*`. A violation is a **red build**, not a red test that could be deleted.
Off-the-shelf tools were considered and rejected (ADR-5): **NsDepCop** does exactly
this but is **GPL-2.0-licensed**, which we keep out of an MIT project's toolchain on
principle and to avoid SCA-policy friction; **BannedApiAnalyzers** (MIT) can't
separate namespaces *within* one project; a sub-assembly split would breach §8.2. The
first-party analyzer is ~a page of code we own outright under our own license, and it
lets the layer rule share the codebase's exact vocabulary. `NetArchTest.eNhancedEdition`
(MIT; the original `NetArchTest` is unmaintained since 2023) stays as the `dotnet test`
backstop for what an analyzer can't cheaply phrase — §8.1's ratchet, naming
conventions, and §9's "every `api.*` op has a contract test".

#### Layer rules ride on namespaces — so pin folder ⇒ namespace

The analyzer keys off **namespaces**, not folders. For its rule to actually mean
"`domain/` may not use `infra/`", each layer folder **MUST** map to the matching
namespace suffix: `Domain/` → `Docir.Catalog.Domain`, `Application/` →
`…Application`, `Infra/` → `…Infra` (the public facade + DTOs + events stay in the
bare `Docir.Catalog`, §3). That mapping is itself made machine-checked in
`.editorconfig`, so a misfiled type can't silently escape a layer rule:

```ini
# folder ⇒ namespace, enforced at build (promoted to error by the gate's WarningsAsErrors)
dotnet_style_namespace_match_folder = true
dotnet_diagnostic.IDE0130.severity = warning
```

IDE0130 guarantees the folders equal the namespaces; `DOCIR0001` enforces the layer
edges on those namespaces — together they enforce §8.3 on the real layout, at build.

#### The layer analyzer — the §8.3 matrix as code

The analyzer is one small `netstandard2.0` project, `tools/Docir.Architecture.Analyzer`
(depends on `Microsoft.CodeAnalysis.CSharp`, MIT). It is wired **only into module
projects** — they alone have the layered split — via a `src/modules/Directory.Build.props`
that chains the root props and adds the analyzer as an analyzer reference:

```xml
<!-- src/modules/Directory.Build.props — modules only; chain the root gate first -->
<Project>
  <Import Project="$([MSBuild]::GetPathOfFileAbove('Directory.Build.props', '$(MSBuildThisFileDirectory)../'))" />
  <ItemGroup>
    <ProjectReference Include="$(MSBuildThisFileDirectory)../../tools/Docir.Architecture.Analyzer/Docir.Architecture.Analyzer.csproj"
                      OutputItemType="Analyzer" ReferenceOutputAssembly="false" />
  </ItemGroup>
</Project>
```

The whole §8.3 rule is one data-driven switch — it reads like the allowlist NsDepCop
would have used, but lives in our repo under our license and speaks the codebase's own
vocabulary. Violations report as `Warning`; the gate's `WarningsAsErrors` promotes them
to a red build, so there is no per-project severity to forget. The load-bearing arm is
`Layer.Domain`: it permits only same-module domain and the pure-primitive
`Docir.Platform.Errors` (ARCHITECTURE_RULES §2), so any other internal edge out of
domain is a build error.

```csharp
// tools/Docir.Architecture.Analyzer/LayerDependencyAnalyzer.cs  (skeleton)
[DiagnosticAnalyzer(LanguageNames.CSharp)]
public sealed class LayerDependencyAnalyzer : DiagnosticAnalyzer
{
    static readonly DiagnosticDescriptor Rule = new(
        "DOCIR0001", "Illegal cross-layer dependency",
        "{0} ({1}) must not reference {2} ({3}) — ARCHITECTURE_RULES §8.3",
        "Architecture", DiagnosticSeverity.Warning, isEnabledByDefault: true);

    public override ImmutableArray<DiagnosticDescriptor> SupportedDiagnostics => ImmutableArray.Create(Rule);

    public override void Initialize(AnalysisContext ctx)
    {
        ctx.EnableConcurrentExecution();
        ctx.ConfigureGeneratedCodeAnalysis(GeneratedCodeAnalysisFlags.None);
        // walk every referenced symbol: usages, base types, signatures, attributes
        ctx.RegisterOperationAction(Check, OperationKind.Invocation, OperationKind.ObjectCreation,
            OperationKind.FieldReference, OperationKind.PropertyReference, OperationKind.TypeOf);
        ctx.RegisterSymbolAction(CheckSignatures, SymbolKind.NamedType, SymbolKind.Method, SymbolKind.Property);
    }

    // `from` = layer of the referencing code; `to` = namespace of the referenced symbol.
    // Only Docir.* targets are in scope; System/third-party are ignored here (domain
    // framework-freeness, ARCH §2, is a separate BannedApiAnalyzers list if wanted).
    static bool Allows(Layer from, Ns to) => from switch
    {
        Layer.Domain      => to.SameModule(Layer.Domain) || to.Is("Docir.Platform.Errors"),
        Layer.Application => to.SameModule(Layer.Domain, Layer.Application)
                             || to.IsOtherModuleApi()               // Docir.<X> exactly (public facade)
                             || to.Is("Docir.Platform.Errors"),
        Layer.Infra       => to.SameModule(Layer.Domain, Layer.Application)
                             || to.Under("Docir.Platform") || to.Is("Docir.Config"),
        Layer.Api         => to.SameModule(Layer.Application, Layer.Domain)
                             || to.Is("Docir.Platform.Transport"),  // CommandDescriptor for the surface
        _                 => true,   // platform/config/entry_points: not layered, out of scope
    };
    // Check / CheckSignatures: resolve from-layer + to-namespace, and if !Allows -> ReportDiagnostic.
}
```

The matrix is module-agnostic (`SameModule`/`IsOtherModuleApi` derive the module from
the namespace), so one analyzer covers all three modules with no per-module config. It
also encodes the direct-call line **retrieval → catalog → tags**: `IsOtherModuleApi`
lets `retrieval.Application` reference `Docir.Catalog` (the bare api namespace) but
never `Docir.Catalog.Infra`. Each of these would be a red build (`DOCIR0001`):
`…Domain → …Infra`, `…Application → …Infra`, `…Domain → Docir.Platform.Persistence`.

Plus the tool-consolidation that motivated the port: `ty`→compiler+`Nullable`,
`vulture`→`IDE0051`, `ruff`→Roslyn+`Roslynator.Analyzers`+`Meziantou.Analyzer`,
`ruff format`→`dotnet format`, `pytest`+cov→xUnit+coverlet. CI is:
`dotnet build -warnaserror` · `dotnet format --verify-no-changes` · `dotnet test`
(the last also runs the architecture + contract suites).

> **Cross-cutting concerns (§6):** docir has no auth/tenancy/feature-flags. Its
> only cross-cutting mechanisms are the **error→exit-code mapping** (one point:
> `platform/errors` + the executor) and the **daemon-vs-in-process transport**
> (one point: `platform/transport`). Both already satisfy "one declaration, one
> enforcement" — no per-feature branching. Note this explicitly so a reviewer
> doesn't look for an authz registry that shouldn't exist.

---

## 6. CONTRACT.md per module (§7 — MUST)

Each module ships a `CONTRACT.md` (<40 lines) next to `api.*`; a change to
`api.*` and to `CONTRACT.md` must land in the **same commit** (§8.6). Skeletons:

```markdown
# catalog
## Purpose
Records and maintains the project's decisions, issues, and architecture notes as
validated documents, and the links between them.
## Public operations
- Add/Update/Get/Query/Archive/Unarchive/Delete(command|query) -> DocumentView
- Check() -> CheckFinding[]        # graph health
- Reindex(changedOnly) -> ReindexResult
- TagReferences(key) query used by tags   # or via event — see Depends on
## Events published
- DocumentSaved — a document's content/metadata changed
- DocumentRemoved — a document was deleted
## Events consumed
- TagRenamed, TagRemoved (from tags) — rewrite/strip the tag on referencing docs
## Owns
- storage: documents, relations, document_tags, id_sequences; docs/*.md files
## Depends on
- modules: tags (TagExists)
- platform: persistence, errors, transport
## Policy
- permissions: none (local single-user CLI)
```

```markdown
# tags
## Purpose
Keeps a single, unambiguous vocabulary of tags so documents classify consistently.
## Public operations
- Add/List/Rename/Remove
- TagExists(key) -> bool          # used by catalog write validation
## Events published
- TagRenamed, TagRemoved
## Events consumed
- DocumentSaved, DocumentRemoved (from catalog) — maintain per-tag reference counts
## Owns
- storage: tags; tag reference-count projection; tags.yaml
## Depends on / Policy
- platform: persistence, errors; permissions: none
```

```markdown
# retrieval
## Purpose
Finds the documents most relevant to a task, combining word-match, meaning, and
document links.
## Public operations
- Search(text) -> SearchResultView[]
- Context(task) -> ScoredDocumentView[]
- Lint() -> LintFinding[]         # duplicate content, oversized
- FlushEmbeddings() / ReindexEmbeddings()
## Events consumed
- DocumentSaved, DocumentRemoved (from catalog) — maintain FTS + embedding projections
## Owns
- storage: documents_fts, embeddings
## Depends on / Policy
- modules: catalog (Get, graph neighbors, bodies); platform; permissions: none
```

Also update the root **README** to list exactly these three modules + one-line
purpose and nothing about internals (§7 MUST).

---

## 7. Tests — central `tests/`, split per module

Per your directive, tests live under `tests/` **split per bounded context**
(mirroring each module's internal structure), not inside the modules. This
**deviates from §9's MUST** ("tests live inside the module they cover") — a
deliberate deviation that requires an ADR (§14; see §11 below). Everything else
about §9 is honored:

```
tests/<module>/
  domain/       # pure unit — no I/O, no mocks (§9)
  application/  # use-case tests — ports replaced by in-memory fakes (§9 SHOULD: fakes over mocks)
  infra/        # integration — real SQLite temp DB / filesystem
  contract/     # every api.* operation has a contract test (§9 MUST), incl. negative cases
tests/entry_points/e2e/   # full stack; spawn the built binary, incl. the daemon
tests/Docir.Architecture.Tests/   # NetArchTest.eNhancedEdition — §8.1 ratchet + boundary asserts
                                  #   (§8.3 layers: DOCIR0001 analyzer at build — ADR-5)
```

Frameworks: **xUnit** + **coverlet** (gate at 90% via
`/p:Threshold=90`) + **NetArchTest.eNhancedEdition** for the boundary suite (the
original `NetArchTest` is unmaintained since 2023); intra-module layering (§8.3) is
enforced earlier, at build time, by the first-party `DOCIR0001` analyzer (see §5 and
ADR-5). Port the
existing pytest assertions per layer first — they are the executable spec that
keeps a from-scratch rewrite from silently changing behavior.

---

## 8. NuGet summary

| Concern | Package(s) |
|---|---|
| Persistence (data access + migrations) | `Dapper.AOT` + `Microsoft.Data.Sqlite`; hand-written per-module migration runner (decided — ADR-4, §10.1) |
| SQLite native (FTS5 bundled) | `SQLitePCLRaw.bundle_e_sqlite3` (transitive) |
| YAML / frontmatter | `YamlDotNet` (fence-split + deserialize the block) |
| ONNX embeddings | `Microsoft.ML.OnnxRuntime`, `Microsoft.ML.Tokenizers` |
| Vector math (SIMD cosine) | `System.Numerics.Tensors` |
| CLI + rendering | `Spectre.Console.Cli`, `Spectre.Console` |
| Config / DI / hosting / clock | `Microsoft.Extensions.{Configuration,DependencyInjection,Hosting}`, `TimeProvider` (BCL) |
| Tests | `xunit`, `coverlet.collector`, `NetArchTest.eNhancedEdition`, `Microsoft.Extensions.TimeProvider.Testing` |
| Analyzers | `Roslynator.Analyzers`, `Meziantou.Analyzer`, `SonarAnalyzer.CSharp` (all MIT/Apache) |
| Architecture analyzer (§8.3) | first-party `Docir.Architecture.Analyzer`, built on `Microsoft.CodeAnalysis.CSharp` (MIT); no third-party layer-check package — ADR-5 |

---

## 9. Idiom cheat-sheet

| Python | C# |
|---|---|
| `@dataclass` | `record` (`with` = `dataclasses.replace`) |
| frozen `slots=True` dataclass | `readonly record struct` |
| `ABC` + `@abstractmethod` (a port) | `interface` (in the module's `application`, `internal`) |
| context-manager UoW (`__enter__/__exit__`) | `IUnitOfWork : IDisposable` + `using`; `Dispose` rolls back if not committed |
| `date` | `DateOnly` |
| `tuple[str, ...]` | `ImmutableArray<string>` |
| `re.compile` | `[GeneratedRegex]` (source-generated, AOT-safe) |
| `secrets.token_hex(6)` | `Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(6))` |
| `hashlib.sha256` / `struct.pack("<f")` | `SHA256.HashData` / `BinaryPrimitives` (float32 LE, byte-compatible) |
| `Embedding.cosine_similarity` (pure loop) | `TensorPrimitives.CosineSimilarity` (SIMD — free speed win) |
| `threading.Thread`+`Event` (scheduler) | `System.Threading.Channels` + a debounced consumer |
| `json.dumps/loads` | `System.Text.Json` (source-gen context) |
| dispatcher `_str/_int/_tuple` coercion | typed `JsonElement.Deserialize<TCommand>` — the whole coercion layer disappears |

---

## 10. Decisions

### 10.1 Persistence stack — **decided: `Dapper.AOT` + `Microsoft.Data.Sqlite`** (ADR-4)

Not EF Core. docir's schema is small and stable (six tables, edge-list
relations, no navigation graphs or ad-hoc LINQ), and FTS5 + float32 embedding
BLOBs are raw SQL under any ORM — so an ORM is mostly bypassed already. Raw,
explicit SQL is **one** consistent data-access model with no query-translation
layer to surprise you at runtime (aligned with the reliability motive), fits the
per-module table+migration ownership (§5.3) better than juggling multiple EF
`DbContext`s and migration histories in one SQLite file, and — because
`Dapper.AOT` is a compile-time source generator — is **NativeAOT-clean without
forcing AOT**, keeping the single-binary distribution path open for later rather
than foreclosing it (EF would foreclose it). Accepted cost: SQL is hand-written
(parameterized) with no change-tracking — a fit for docir's explicit-upsert
style, and the SQL is already specified in the existing SQLAlchemy repos. Full
rationale and consequences: [adr/ADR-0004-persistence-stack.md](adr/ADR-0004-persistence-stack.md).

### 10.2 ONNX under AOT — still to validate

`Microsoft.ML.OnnxRuntime` is native interop; validate it in the chosen publish
mode with an early spike but implement it **last** — the deterministic embedder
(retrieval/infra) keeps the whole system shippable and all tests hermetic
meanwhile.

---

## 11. Decision records to write (§14 — MUST)

§14 requires an ADR when a module is created, a `platform/` capability is added,
or a **SHOULD/MUST** is deliberately violated. Create, at minimum:

- **ADR-1: Module map** — catalog / tags / retrieval, with the data-ownership
  table and the retrieval = FTS+embeddings merge rationale. *(to write)*
- **ADR-2: Cross-module events via an `entry_points` bridge** — why event types
  are not shared and handlers take primitives (avoids the §4 cycle). *(to write)*
- **ADR-3: Central `tests/` split per module** — the deliberate deviation from §9
  (tests-inside-module) per your directive. *(to write)*
- **ADR-4: Persistence stack** — `Dapper.AOT` + `Microsoft.Data.Sqlite` (§10.1).
  ✅ written: [adr/ADR-0004-persistence-stack.md](adr/ADR-0004-persistence-stack.md).
- **ADR-5: Intra-module layer enforcement** — a first-party `DOCIR0001` Roslyn
  analyzer (build-time §8.3) + `NetArchTest.eNhancedEdition` backstop; why not
  NsDepCop (GPL-2.0), BannedApiAnalyzers, test-only, a sub-assembly split, or NDepend.
  ✅ written: [adr/ADR-0005-intra-module-layer-enforcement.md](adr/ADR-0005-intra-module-layer-enforcement.md).

Use the §14 format (`# ADR-<n>` · Status · Context · Decision · Consequences),
one append-only file each, under `docs/adr/`.

---

## 12. Recommended build order

Front-loads the gate and the safe pure code; defers the two risk items. Each step
is independently testable.

1. **Skeleton + gate** — solution, `Directory.Build.props`, analyzers,
   `.editorconfig`, the `Docir.Architecture.Analyzer` (`DOCIR0001`) + its
   `src/modules/Directory.Build.props` wiring, and the `Docir.Architecture.Tests`
   project. Boundaries red from day one (§8.1 baseline empty). A tiny fixture module
   with a deliberate `domain → infra` edge proves `DOCIR0001` fails the build.
2. **platform + config** — errors base, persistence primitives + migration runner,
   transport (protocol, UDS, executor, event bus), Settings.
3. **tags** (leaf module) — domain → application → infra + contract tests. Smallest,
   validates the module template end-to-end.
4. **catalog** — the core; depends on `tags.api`. Port the pytest suite per layer.
5. **retrieval** on the deterministic embedder — depends on `catalog.api`; wire the
   projection event handlers.
6. **entry_points** — Spectre commands, composition, event bridge; e2e tests.
7. **daemon** path in transport/entry_points + e2e daemon tests.
8. **ONNX embedder** — behind `IEmbedder`, de-risked by everything above passing on
   the deterministic backend.
9. **Packaging + CI** — publish profile (§10.1) + the three-command gate.

