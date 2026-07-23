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
        explicit ``use_daemon=False``) forces in-process execution. Passing
        ``home`` overrides the ``DOCIR_HOME`` env var for that call.
        """
        if use_daemon is None:
            use_daemon = os.environ.get(NO_DAEMON_ENV, "") == ""
        # Omitting ``home`` lets pydantic read DOCIR_HOME / the default factory;
        # passing it takes precedence over the env var for this call.
        if home is None:
            return cls(use_daemon=use_daemon)
        return cls(home=Path(home), use_daemon=use_daemon)

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
