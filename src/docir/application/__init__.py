# Application layer — use cases orchestrating the domain via its ports.
#
# This layer contains no framework code and no I/O: it depends only on the
# domain (entities, value objects, ports, services) and coordinates them to
# fulfil each CLI command. Infrastructure adapters are injected through the
# domain ports, so the use cases can run against real SQLite/filesystem
# adapters in production and against in-memory fakes in tests unchanged.
#
#   * dto       — request/response data-transfer objects crossing the boundary.
#   * services  — the use-case classes (document, tag, and maintenance flows).
