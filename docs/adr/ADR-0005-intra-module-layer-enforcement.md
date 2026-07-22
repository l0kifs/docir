# ADR-0005: Intra-module layer enforcement — a first-party Roslyn analyzer at build time
Status: accepted
Date: 2026-07-22

## Context

The .NET 10 rework (see [../dotnet-solution-layout.md](../dotnet-solution-layout.md))
is one assembly per bounded context, and that assembly boundary is what makes two of
ARCHITECTURE_RULES §8's gates *compiler-enforced and unbreakable*: only `api.*` is
public because everything else is `internal` (§8.2), and project references can't be
circular so there are no module cycles (§8.4).

That guarantee stops at the **module wall**. Inside a module the layers
(`domain / application / infra`) live as folders/namespaces in the *same* assembly,
so `internal` cannot separate them: nothing at compile time stops a `domain` type
from referencing an `infra` type, or `application` from reaching into `infra`. This
is §8.3 — the Dependency Rule — and it is the one boundary the assembly model does
**not** make free.

Enforcing §8.3 only in an architecture-test project (at `dotnet test`) is the weakest
link in an otherwise compiler-hard design: a test is deletable, so removing one rule
silently disables the check; feedback is late (a test run, not the build); and it is
one gate later than the reliability motive — the whole reason for the port — wants.
So §8.3 should be enforced as *early* and as *un-deletable* as §8.2/§8.4 already are:
at **build time**.

Forces at play:

- **Reliability is the reason for the whole port** — move boundary enforcement onto
  the compiler/analyzers, not conventions or a deletable test.
- **The layer split is already namespace-shaped.** Folders map 1:1 to namespaces
  (`Docir.Catalog.Domain`, `.Application`, `.Infra`), so a namespace-based rule can
  express §8.3 directly, with no new structure.
- **One-assembly-per-module is load-bearing** and must not be traded away — it buys
  §8.2/§8.4 for free and keeps "only `api.*` is public" true.
- **The toolchain should stay permissively licensed.** docir is MIT. The build gate
  is a hard dependency of every contributor and of CI; a copyleft (GPL) tool in it,
  even build-time-only, invites SCA-scanner/policy friction downstream and is worth
  avoiding on principle when an alternative exists.
- **Some §8 rules aren't dependency-graph rules.** §8.1's ratchet, naming
  conventions, and §9's "every `api.*` op has a contract test" are not namespace
  edges and still need a test-based tool.

Options considered:

1. **NsDepCop** — a Roslyn analyzer that validates namespace→namespace rules from a
   per-project `config.nsdepcop` at **build** time. Purpose-built for exactly this,
   and **actively maintained** (3.1.0, 2026-07). *But licensed **GPL-2.0-only**, with
   no linking/build-tool exception.*
2. **`Microsoft.CodeAnalysis.BannedApiAnalyzers`** (MIT) — build-time, can ban a
   namespace via `N:` entries. But its ban list is **per-compilation (per-project)**;
   it cannot say "`Domain` may not use `Infra`" when both namespaces live in the
   *same* project, which is docir's one-project-per-module shape. It only separates
   namespaces across project boundaries.
3. **Test-only (NetArchTest.eNhancedEdition [MIT] / ArchUnitNET [Apache-2.0])** — keep
   §8.3 at `dotnet test`. Permissive, but deletable and one gate late.
4. **A first-party Roslyn analyzer** — write and own a small analyzer for the layer
   graph. Build-time, and under our own (MIT) license.
5. **Sub-assembly split** (`Docir.Catalog.Domain`, …) — let the compiler enforce
   §8.3 via project references.
6. **NDepend** — CQLinq architecture rules. Commercial, per-seat.

## Decision

Enforce §8.3 at **build time with a first-party Roslyn analyzer**, and keep a
permissively-licensed architecture-test suite as the backstop.

- **`Docir.Architecture.Analyzer`** — a small `netstandard2.0` analyzer project under
  `tools/`, depending only on `Microsoft.CodeAnalysis.CSharp` (MIT). It emits
  diagnostic **`DOCIR0001`** from the §8.3 layer matrix, keyed on the namespace of the
  referencing code (`from` layer) and of the referenced symbol (`to` namespace):
  `…Domain` may reference only same-module `…Domain` and the pure-primitive
  `Docir.Platform.Errors` (the one exception ARCHITECTURE_RULES §2 grants — not any
  platform *service*); `…Application` may reference same-module `…Domain`/`…Application`
  and other modules' bare public `api` namespace, never `…Infra`; `…Infra` may
  reference same-module `…Domain`/`…Application`, `Docir.Platform.*`, and `Docir.Config`.
  The matrix is module-agnostic — one analyzer covers all three modules with no
  per-module config file.
- **Wired into module projects only**, via a `src/modules/Directory.Build.props` that
  chains the root gate and adds the analyzer with `OutputItemType="Analyzer"`. Only
  modules have the layered split; `platform/`, `config/`, and `entry_points/` are out
  of scope. The gate can't be skipped per-module because the props applies to all of
  them.
- **Severity via the existing gate.** `DOCIR0001` is declared `Warning`; the layout's
  `TreatWarningsAsErrors` + blanket `WarningsAsErrors` promotes it to a **red build**,
  so there is no per-project severity to forget (a `.editorconfig`
  `dotnet_diagnostic.DOCIR0001.severity` can still tune it if ever needed).
- **Folder ⇒ namespace is pinned**, because the analyzer keys off namespaces:
  `.editorconfig` sets `dotnet_style_namespace_match_folder = true` and raises
  `IDE0130`, so a type filed under `Domain/` but declared in another namespace is
  itself a build error. IDE0130 guarantees the mapping; `DOCIR0001` enforces the layer
  edges over it — together they enforce §8.3 on the real layout.
- **`NetArchTest.eNhancedEdition`** (MIT; the original `NetArchTest` is inactive since
  2023) remains the `Docir.Architecture.Tests` suite for what is *not* a layer edge:
  §8.1's boundary ratchet (baseline empty from day one), naming/structure conventions,
  and the §9 "every `api.*` op has a contract test" assertion.
- The analyzer itself is covered by unit tests (`Microsoft.CodeAnalysis.Testing`), and
  a tiny fixture module with a deliberate `domain → infra` edge asserts the build goes
  red — the analyzer is load-bearing, so it is tested like production code.

### Rejected

- **NsDepCop (option 1)** — it does exactly this job and is well maintained, so
  maintenance is *not* the objection: the objection is the **GPL-2.0** license. Using
  it as a build-time, non-distributed analyzer is very likely legally compatible with
  an MIT project (the tool's output is not a derivative of the tool, and we would not
  redistribute it). But keeping GPL out of the toolchain avoids downstream
  SCA-scanner/corporate-policy friction and matches the "permissive toolchain"
  preference above, and a first-party analyzer is only ~a page of code. Reconsider if
  writing/owning the analyzer proves more costly than expected and the GPL concern is
  judged moot for docir's distribution context.
- **BannedApiAnalyzers (option 2)** — MIT and build-time, but cannot express
  namespace-to-namespace rules *within* one project, which is precisely docir's
  layout. Usable only as optional defense-in-depth (e.g. banning framework namespaces
  from `…Domain` for §2 framework-freeness), not as the §8.3 mechanism.
- **Test-only (option 3)** — deletable and one gate too late; kept only as the
  backstop for non-edge rules.
- **Sub-assembly split (option 5)** — would triple the assembly count and force layer
  types to become `public` across the sub-assembly seams (or thread
  `InternalsVisibleTo` everywhere), eroding the "only `api.*` is public" guarantee
  (§8.2) that the one-assembly-per-module model exists to provide. Buys compiler
  enforcement of §8.3 at the cost of the property the design values most.
- **NDepend (option 6)** — per-seat commercial licensing, disproportionate for a
  single-maintainer CLI.

## Consequences

**Easier**
- §8.3 joins §8.2/§8.4 as a **build-time** guarantee — un-deletable-by-accident,
  reported while building, closing the design's weakest link.
- **Fully permissive toolchain**: no GPL (or any third-party) dependency in the layer
  check; the analyzer is ours under MIT.
- The rule speaks the codebase's own vocabulary (modules, layers) and is module-
  agnostic, so no per-module config to maintain.
- Architecture tests get smaller and clearer — only the non-edge rules remain there.

**Harder**
- **We build and maintain an analyzer.** ~a page of `DiagnosticAnalyzer` plus its unit
  tests, and it must track Roslyn API and any future layer-rule changes. This is the
  accepted cost of the license/permissiveness choice; the code is small, well-trodden
  (a namespace-graph analyzer), and pinned by its own tests.
- Two enforcement tools: a §8.3 violation is a *build* error (`DOCIR0001`) while
  §8.1/§9 violations are *test* failures. Documented in §5 and §7 of the layout.
- The analyzer keys off **namespaces**, not folders — the `Domain/Application/Infra`
  folders must map to `…Domain/.Application/.Infra` namespaces, made machine-checked
  via `IDE0130` / `dotnet_style_namespace_match_folder`.

**Now forbidden**
- Making §8.3 test-only again, or removing the analyzer from the module build.
- Adding a GPL-licensed package to the build/tooling dependency graph without a
  superseding ADR.
- Splitting a module's layers into separate assemblies to enforce layering (would
  breach §8.2's public-surface guarantee — see Rejected).
- Suppressing `DOCIR0001` at project or file level to land a layer violation; fix the
  dependency or revise the analyzer's matrix (and record why) instead.

Reconsider this decision if the layer namespaces stop mirroring the folders, if the
maintenance cost of the analyzer outweighs the license benefit (→ revisit NsDepCop
with a documented GPL assessment), or if the codebase grows enough to justify NDepend.
