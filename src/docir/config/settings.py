"""Runtime settings and the ``~/.docir`` path layout.

Backed by ``pydantic-settings``: the ``home``, ``idle_timeout`` and
``request_timeout`` fields are populated from ``DOCIR_HOME`` /
``DOCIR_IDLE_TIMEOUT`` / ``DOCIR_REQUEST_TIMEOUT`` (the ``DOCIR_`` env prefix) or
their defaults. Everything the application persists lives under the
single home directory; pointing ``DOCIR_HOME`` at a temp dir is what makes the
whole system hermetic and testable — no global state leaks between runs.

The derived paths are plain ``@property`` computations over ``home``; the
settings object is frozen (immutable), which those read-only properties are
unaffected by.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Environment variable naming the root data directory (``DOCIR_`` + ``HOME``).
HOME_ENV = "DOCIR_HOME"
#: Force in-process execution (bypass the daemon) — used by tests and CI.
NO_DAEMON_ENV = "DOCIR_NO_DAEMON"
#: Idle timeout (seconds) before the daemon shuts itself down.
DEFAULT_IDLE_TIMEOUT = 900.0
#: How long a client waits for the daemon's *reply* before giving up (seconds).
#: Deliberately generous, and deliberately not the connect timeout: connecting to
#: a local Unix socket either succeeds at once or not at all, while the reply
#: arrives only after the daemon has done the work — a ``reindex`` over a large
#: corpus is one request that legitimately runs for minutes. Sizing this like a
#: connect budget is what made ``reindex`` fail on a 65-document store while the
#: daemon completed it. Raise ``DOCIR_REQUEST_TIMEOUT`` for a slower corpus.
DEFAULT_REQUEST_TIMEOUT = 300.0
#: The per-project store directory name, discovered by walking up from the CWD
#: (the ``.git`` model). ``docir init`` creates one; commands then scope to it.
PROJECT_STORE_DIRNAME = ".docir"


def discover_project_home(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` (default CWD) for a ``.docir`` store directory.

    Returns the first ``.docir`` directory found on the path to the filesystem
    root, or ``None`` if there is none — mirroring how git locates ``.git``. This
    is what makes a project-local store (created by ``docir init``) take effect
    without setting ``DOCIR_HOME`` in every shell.
    """
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        candidate = directory / PROJECT_STORE_DIRNAME
        if candidate.is_dir():
            return candidate
    return None


def enclosing_project_home(home: Path) -> Path | None:
    """The nearest project store *above* ``home``, if one exists.

    The third home decision, kept beside the other two for the reason recorded
    on :func:`new_store_home`: a rule about which store is in play that lives
    anywhere else escapes the review that reads these.

    ``init`` deliberately does not reuse an enclosing store — reusing a parent
    is the wrong answer when the caller asked for a new one (adr-20eec6e2e2ca) — but
    "do not reuse it" and "do not mention it" are different decisions, and only
    the first was made. Discovery walks *up*, so a store created beneath another
    captures every command run under it, silently, and the outer store's
    ``check`` never sees those documents: they are not orphaned or dangling,
    they are in a different corpus (issue-e10cde8c5085).

    Starts at ``home``'s own directory so an explicitly-named store (``--home
    /srv/docs``) still notices a sibling ``.docir``, and skips a candidate that
    *is* ``home`` so re-initialising a store does not report itself.
    """
    home = Path(home).expanduser().resolve()
    start = home.parent
    for directory in (start, *start.parents):
        candidate = directory / PROJECT_STORE_DIRNAME
        if candidate.is_dir() and candidate != home:
            return candidate
    return None


def new_store_home(directory: Path | None, explicit_home: Path | None) -> Path:
    """Where ``docir init`` should create a store — the counterpart to :meth:`Settings.resolve`.

    Kept in this module deliberately. ``init`` used to compute its home in the
    CLI layer and so drifted out of sync with every other command, silently
    ignoring ``--home`` and creating the store in whatever directory the shell
    happened to be in (issue-638068ed09a6). A review that traced ``resolve`` never saw it,
    because it did not use it. Both home decisions now sit here and are read
    together.

    ``init`` *creates* where ``resolve`` *discovers*, so this deliberately does
    not walk up for an existing ``.docir``: reusing a parent store is the wrong
    answer when the caller has asked for a new one.

    ``explicit_home`` (the ``--home`` flag) names a store path directly; the
    positional ``directory`` names the project whose ``.docir`` is the store.
    They disagree, so asking for both raises rather than resolving by
    precedence — silently preferring one was the original defect.

    Raises :class:`ValueError`: this module is a dependency leaf and cannot
    import the error taxonomy, so the caller translates it into a domain error.
    """
    if explicit_home is not None and directory is not None:
        intended = Path(directory).resolve() / PROJECT_STORE_DIRNAME
        raise ValueError(
            "--home and a project directory both name where the store goes; pass one. "
            f"--home would create it at {Path(explicit_home).expanduser().resolve()}; "
            f"the directory argument would create it at {intended}."
        )
    if explicit_home is not None:
        return Path(explicit_home).expanduser().resolve()
    return (directory or Path()).resolve() / PROJECT_STORE_DIRNAME


#: The marker `enclosing_repository` walks up for. Deliberately the same walk as
#: :func:`discover_project_home`, one directory name over.
_GIT_DIRNAME = ".git"


def enclosing_repository(start: Path | None = None) -> Path | None:
    """The git repository containing ``start``, or ``None``.

    Used for one narrow purpose: telling apart "no store here, and no repo
    either" — where the global ``~/.docir`` is exactly what the user meant —
    from "inside a repo that was never ``docir init``-ed", where it almost
    certainly is not. Warning on both would fire on correct usage.
    """
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        if (directory / _GIT_DIRNAME).exists():
            return directory
    return None


class Settings(BaseSettings):
    """Resolved paths and tunables for one docir installation.

    Field sources, highest precedence first: constructor kwargs → ``DOCIR_*``
    environment variables → field defaults.
    """

    model_config = SettingsConfigDict(
        env_prefix="DOCIR_",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
        validate_default=True,
    )

    home: Path = Field(default_factory=lambda: Path.home() / ".docir")
    idle_timeout: float = DEFAULT_IDLE_TIMEOUT
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT
    use_daemon: bool = False
    #: Whether the daemon watches ``docs/`` and reindexes what changes. On by
    #: default: the files are canonical and the index is derived, so an
    #: automatic reindex can only make the two agree and can never lose work.
    #: ``DOCIR_WATCH=0`` opts out.
    watch: bool = True
    #: How ``home`` was chosen: ``flag`` | ``env`` | ``project`` | ``global``.
    #: Carried so callers can tell a deliberate store from a fallback — a write
    #: that lands in the global store because someone forgot ``docir init`` is
    #: indistinguishable from one that was meant to.
    home_origin: str = "global"

    @field_validator("home")
    @classmethod
    def _normalize_home(cls, value: Path) -> Path:
        """Expand ``~`` and resolve to an absolute path however home was set."""
        return Path(value).expanduser().resolve()

    @classmethod
    def resolve(
        cls,
        home: str | os.PathLike[str] | None = None,
        *,
        use_daemon: bool | None = None,
    ) -> Settings:
        """Build settings, applying the inverted ``DOCIR_NO_DAEMON`` semantics.

        The daemon is used by default; a set ``DOCIR_NO_DAEMON`` env var (or an
        explicit ``use_daemon=False``) forces in-process execution.

        Home precedence, highest first: an explicit ``home`` argument (the
        ``--home`` flag) → the ``DOCIR_HOME`` env var → a project-local
        ``.docir`` discovered by walking up from the CWD → the global
        ``~/.docir`` default. The discovery step is what lets ``docir init``
        scope a repo's docs to the repo without exporting ``DOCIR_HOME``.

        This resolves a store that already exists. ``docir init``, which creates
        one, uses :func:`new_store_home` — the two rules live side by side here
        so neither can drift out of sync with the other again.
        """
        if use_daemon is None:
            use_daemon = os.environ.get(NO_DAEMON_ENV, "") == ""
        if home is not None:
            return cls(home=Path(home), use_daemon=use_daemon, home_origin="flag")
        if os.environ.get(HOME_ENV):
            # Let pydantic read DOCIR_HOME (env_prefix DOCIR_ + field ``home``).
            return cls(use_daemon=use_daemon, home_origin="env")
        discovered = discover_project_home()
        if discovered is not None:
            return cls(home=discovered, use_daemon=use_daemon, home_origin="project")
        return cls(use_daemon=use_daemon, home_origin="global")

    def is_unintended_global_fallback(self) -> bool:
        """Whether this store is the global default reached from inside a repo.

        The global store is a real feature (personal notes), so falling back to
        it is not an error — but doing so from inside a git repository that was
        never ``docir init``-ed means the documents land in the user's home
        directory, ungitted and invisible to teammates, while the reported path
        reads as repo-relative. Setting ``DOCIR_HOME`` explicitly takes the
        ``env`` branch, which is how someone who *does* mean the global store
        from inside a repo says so without a new flag.
        """
        return self.home_origin == "global" and enclosing_repository() is not None

    # -- derived paths ------------------------------------------------------

    @property
    def docs_root(self) -> Path:
        """Where the canonical markdown files live."""
        return self.home / "docs"

    @property
    def code_root(self) -> Path | None:
        """The repository a document's ``code`` globs are relative to, if any.

        The same walk `is_unintended_global_fallback` uses, started at the store
        instead of the CWD: a project store lives at ``<repo>/.docir``, so the
        repository above it is the tree the patterns were written against. A
        store with no repository above it (the plain global ``~/.docir``) has
        none, and ``None`` is what makes `check` skip the code finding there
        rather than report every pattern as missing.
        """
        return enclosing_repository(self.home)

    @property
    def db_path(self) -> Path:
        """The derived SQLite index file."""
        return self.home / "index.db"

    @property
    def schema_path(self) -> Path:
        """The per-type schema config."""
        return self.home / "docs-schema.yaml"

    @property
    def tags_path(self) -> Path:
        """The canonical tag registry file."""
        return self.docs_root / "tags.yaml"

    @property
    def socket_path(self) -> Path:
        """The daemon's Unix domain socket.

        Placed under the system temp dir with a short, home-derived name rather
        than inside ``home`` — a deep home path would blow past the platform's
        ~104-char ``AF_UNIX`` limit. The name is stable per home, so every
        client for the same installation targets the same socket.
        """
        digest = hashlib.sha1(str(self.home).encode("utf-8")).hexdigest()[:12]
        return Path(tempfile.gettempdir()) / f"docir-{digest}.sock"

    @property
    def pid_path(self) -> Path:
        """The daemon's PID file."""
        return self.home / "daemon.pid"

    @property
    def log_path(self) -> Path:
        """The daemon's log file."""
        return self.home / "daemon.log"

    @property
    def database_url(self) -> str:
        """The SQLAlchemy URL for the index database."""
        return f"sqlite:///{self.db_path}"

    def ensure_directories(self) -> None:
        """Create the home and docs directories if they do not yet exist."""
        self.docs_root.mkdir(parents=True, exist_ok=True)
