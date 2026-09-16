"""The floor a committed store records, and the floor its contents need.

The second of the two rules in adr-36d6156ffab9. The first — put new meaning in
a new key, which an older loader ignores — costs nothing and reaches builds
already installed, so it is always tried first. This covers what is left: a
change that gives an *existing* key a shape the old rule rejects, which no
amount of later shipping can make readable by a docir someone already has.

Pure, and here rather than beside the loader, because ``check`` has to ask the
same two questions and ``application`` may not import ``infra``. Reading the
file stays the loader's job; deciding what the parsed mapping means is this.
"""

from __future__ import annotations

#: The keys a type block must carry to stand on its own. A block missing any of
#: them cannot be a declaration, which is what makes it readable as an overlay.
REQUIRED_TYPE_KEYS: tuple[str, ...] = ("prefix", "statuses", "default_status")

#: The store format this build understands.
#:
#: An integer rather than the release that introduced it, and the index decided
#: this first: ``_peer_schema_status`` compares a migration revision, not a
#: version, and `index-from-newer-build` reports one. A release number cannot be
#: written here anyway — this repository bumps its version *at* release, so the
#: floor a change needs would name a release that does not exist while the
#: change is being written, and would lock the build writing it out of its own
#: store.
#:
#: 2 is the type overlay (adr-6aa2e2f5f403). 1 is every store a published docir
#: can read, which is why an absent declaration means 1 rather than unknown.
STORE_FORMAT = 2

#: What each format above the first was introduced by, in the words the finding
#: uses. Read by the *newer* build to say why a floor is needed; an older one
#: has no entry for a format it predates, which is why its refusal can only name
#: the number.
FORMAT_FEATURES: dict[int, str] = {
    2: "a partial `types:` block, which overlays a type the package ships",
}


def declared_store_format(raw: object) -> int:
    """The floor a schema file records, or 1 when it records none.

    Absent means *the oldest format*, not unknown — the opposite of every other
    absence in docir, and for a reason: a file written before this key existed
    is, by construction, one every build could already read. There is no third
    state to represent, and treating absence as unknown would make every store
    in the world suspect on the day this shipped.

    Anything unusable is read as absent rather than raised: a hand-typed
    ``store_format: two`` is bookkeeping, and refusing to load the schema over
    it would take the whole store down to report a bad line.
    """
    if not isinstance(raw, dict):
        return 1
    value = raw.get("store_format")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return 1
    return value


def required_store_format(raw: object) -> int:
    """The floor this file's *contents* need, whatever it happens to declare.

    Derived rather than trusted, because the declaration is the half that goes
    missing: a store gains an overlay and nobody remembers to raise the line. A
    floor a human has to remember is a floor that records the release after the
    one that needed it, so nothing here asks anyone to remember.

    One construct needs a floor today. A partial ``types:`` block is a load
    error on every published docir, so a store carrying one is unreadable by
    them — all of it, since the schema resolves before anything opens.
    """
    if not isinstance(raw, dict) or "profiles" not in raw:
        return 1
    types_raw = raw.get("types")
    if not isinstance(types_raw, dict):
        return 1
    overlays = any(
        isinstance(spec, dict) and not all(key in spec for key in REQUIRED_TYPE_KEYS)
        for spec in types_raw.values()
    )
    return 2 if overlays else 1
