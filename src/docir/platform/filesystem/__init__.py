"""Filesystem capability: the source-of-truth markdown / YAML file stores.

Git-versioned files under the docs root (documents) and ``tags.yaml`` (the tag
registry) are canonical; the SQLite index is derived from them. This shared
capability abstracts reading and writing those files so every module reaches
the source of truth through one place rather than each other.
"""
