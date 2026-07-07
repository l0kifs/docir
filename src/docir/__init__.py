# docir — Doc-Index CLI.
#
# A git-backed markdown document system with a derived, read-optimized index.
# The markdown files under the docs root are the source of truth; the SQLite
# index (metadata + FTS5 + relation graph + semantic embeddings) is a
# rebuildable projection on top of them.
#
# The package is split into four Clean Architecture layers, each in its own
# sub-package with dependencies pointing strictly inward:
#
#   presentation  -> application -> domain
#   infrastructure ------------^  (implements domain ports)
#
#   * domain          — enterprise rules: entities, value objects, ports
#                       (interfaces), domain services, errors. Depends on
#                       nothing else in the package.
#   * application     — use cases orchestrating the domain via its ports,
#                       plus the DTOs that cross the boundary.
#   * infrastructure  — concrete adapters implementing the domain ports
#                       (SQLAlchemy index, filesystem store, embedder,
#                       scheduler, daemon transport).
#   * presentation    — the Typer/Rich CLI and the composition root that
#                       wires infrastructure adapters into the use cases.

__version__ = "0.1.0"
