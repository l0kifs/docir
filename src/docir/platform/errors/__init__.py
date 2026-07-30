"""Domain exception hierarchy.

Every error the domain and application layers raise derives from
:class:`DocirError`, so the presentation layer can catch a single base type
and render it as a clean CLI message with an appropriate exit code.
"""

from __future__ import annotations


class DocirError(Exception):
    """Base class for all expected, user-facing errors in the system."""

    #: Process exit code the CLI should return for this error class.
    exit_code: int = 1


# --- Validation (Tier 0, blocks the write) ---------------------------------


class ValidationError(DocirError):
    """A Tier 0 validation rule was violated during a write."""

    exit_code = 2


class SchemaError(DocirError):
    """The docs-schema.yaml configuration itself is invalid or incomplete."""

    exit_code = 3


class TagRegistryError(DocirError):
    """``docs/tags.yaml`` will not parse.

    Separate from :class:`SchemaError` only because it names a different file;
    both are store-level files a human edits by hand, where a syntax slip used
    to escape as a raw ``yaml.ParserError`` traceback.
    """

    exit_code = 3


class MissingRequiredFieldError(ValidationError):
    """A required frontmatter field for the document's type is absent."""


class UnknownDocumentTypeError(ValidationError):
    """The requested document type is not defined in the schema."""


class InvalidStatusError(ValidationError):
    """A status value is not part of the type's status enum."""


class InvalidStatusTransitionError(ValidationError):
    """A status transition is not permitted by the type's schema."""


class UnknownTagError(ValidationError):
    """A referenced tag key is not present in the tag registry."""


class UnknownRelatedError(ValidationError):
    """A ``related`` id does not exist in the index."""


class UnknownRelationKindError(ValidationError):
    """A ``related`` edge names a relation kind not in the schema registry."""


class DisallowedRelationError(ValidationError):
    """A relation kind (or its target type) is not permitted by the source type."""


# --- Lookups ---------------------------------------------------------------


class DocumentNotFoundError(DocirError):
    """No document exists for the requested id."""

    exit_code = 4


class TagNotFoundError(DocirError):
    """No tag exists for the requested key."""

    exit_code = 4


# --- Conflicts / integrity -------------------------------------------------


class TagAlreadyExistsError(DocirError):
    """A tag with the given key is already registered."""

    exit_code = 5


class TagInUseError(DocirError):
    """A tag cannot be removed because documents still reference it."""

    exit_code = 5


class DanglingReferenceError(DocirError):
    """A delete is blocked because other documents link to the target."""

    exit_code = 5


class DuplicateDocumentIdError(DocirError):
    """A freshly allocated id already has a file on disk; the create was refused.

    Means the index's id counter is behind the canonical files — the state a
    rebuild used to leave behind before ``reindex`` restored the counter.
    """

    exit_code = 5


class StaleWriteError(DocirError):
    """The document changed on disk since it was last read; write refused."""

    exit_code = 6


class DaemonError(DocirError):
    """The daemon transport failed in a way the caller must handle."""

    exit_code = 7


class DaemonTimeoutError(DaemonError):
    """The daemon took the request but did not answer within the time allowed.

    Separate from :class:`DaemonError` because the two demand opposite responses.
    A refused connection or a dead peer means the request never landed, so
    respawning the daemon and resending is safe — and is what
    ``SocketExecutor`` does. A reply timeout means the daemon *has* the request
    and may still be executing it; resending would run the command a second
    time, which for a write means a duplicate document. So this one is never
    retried.
    """


# --- Agent instruction setup -----------------------------------------------


class AgentSetupError(DocirError):
    """A ``docir agent install/update`` request is not satisfiable as asked.

    Raised for usage errors such as requesting a global install of a target that
    has no global location (e.g. ``AGENTS.md``).
    """

    exit_code = 2
