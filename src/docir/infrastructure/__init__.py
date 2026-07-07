# Infrastructure layer — concrete adapters implementing the domain ports.
#
# This is the only layer allowed to touch frameworks, the filesystem, SQLite,
# ONNX models, sockets, and threads. Everything here is hidden behind a domain
# port, so the application never imports it directly; the composition root in
# the presentation layer wires these adapters into the use cases.
#
#   * config     — runtime settings and the ~/.docir path layout.
#   * schema     — load docs-schema.yaml into the domain Schema object.
#   * filesystem — markdown/frontmatter document store and tags.yaml store.
#   * persistence— SQLAlchemy models, repositories, unit of work, migrations.
#   * embedding  — deterministic + fastembed embedders and the async scheduler.
#   * daemon     — Unix-socket server/client, lifecycle, and request executor.
#   * clock      — the system clock adapter.
