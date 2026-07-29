"""Runtime settings and the ``~/.docir`` path layout.

Backed by ``pydantic-settings``: the ``home`` and ``idle_timeout`` fields are
populated from ``DOCIR_HOME`` / ``DOCIR_IDLE_TIMEOUT`` (the ``DOCIR_`` env
prefix) or their defaults. Everything the application persists lives under the
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
    use_daemon: bool = False
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
