# Filesystem adapters — the canonical, git-versioned source of truth.
#
#   * markdown_store — read/write docs/<type>s/<id>-<slug>.md as frontmatter
#                      + markdown body (implements DocumentFileStore).
#   * tag_file_store — read/write docs/tags.yaml (implements TagFileStore).
