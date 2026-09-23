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
#: How long a client waits for the daemon to say *anything* before giving up
#: (seconds). Deliberately generous, and deliberately not the connect timeout:
#: connecting to a local Unix socket either succeeds at once or not at all, while
#: the reply arrives only after the daemon has done the work. Sizing this like a
#: connect budget is what made ``reindex`` fail on a 65-document store while the
#: daemon completed it.
#:
#: It bounds *silence*, not work: a running command sends a keepalive frame every
#: few seconds, and each frame re-arms the socket. So this is the answer to "has
#: the daemon died?", and there is no corpus size it has to be raised for — the
#: reason it once had to be is exactly the bug the keepalive removed.
DEFAULT_REQUEST_TIMEOUT = 300.0
#: The per-project store directory name, discovered by walking up from the CWD
#: (the ``.git`` model). ``docir init`` creates one; commands then scope to it.
PROJECT_STORE_DIRNAME = ".docir"

#: Opts the ambient release notice (and the daemon's daily fetch) in or out for
#: this shell. Read directly rather than through the ``DOCIR_`` prefix because it
#: has to be distinguishable from *unset*: set to anything it is the final word,
#: over the store's own preference and over ``CI``, in both directions.
UPDATE_CHECK_ENV = "DOCIR_UPDATE_CHECK"

#: The variable every CI provider sets. A build server is the one reader that
#: cannot act on an upgrade notice and the one place acting on it would do harm:
#: an agent that follows "run `docir self upgrade`" inside a job makes that job's
#: docir version depend on the day it ran. Suppressing here is the convention
#: npm's update-notifier and its imitators already established.
CI_ENV = "CI"

#: The store's own settings, committed beside ``docs-schema.yaml``. It holds what
#: a *team* decides once rather than what a machine decides — today, only whether
#: this store's agents are told about a newer docir.
#:
#: **A new file, never a new key in an existing one.** A store is read by whatever
#: docir each teammate installed (adr-ab4598c6f707), and a build that has never
#: heard of this file cannot fail on it, while a new key in ``stores.yaml`` is
#: exactly how 0.20.0 came to refuse every read of a store written by 0.21.0.
STORE_CONFIG_FILENAME = "config.yaml"

#: fastembed's own variable for where it keeps a downloaded model. docir honours
#: it rather than overriding it: a CI image that pins it is naming a directory it
#: also caches, and two sides naming different directories is how this repo's own
#: workflow came to re-download the model on every run.
MODEL_CACHE_ENV = "FASTEMBED_CACHE_PATH"

#: How many CPU threads the ONNX embedding model may use. docir's own variable
#: rather than one of fastembed's, because fastembed takes this as a constructor
#: argument and has no variable for it.
#:
#: **Per-machine, so an environment variable and never a schema key.** A store is
#: a committed artifact read by whoever clones it, so a core count inside it
#: would impose one laptop's hardware on the whole team — the same argument that
#: keeps the model out of the store (adr-78090be868ec), one field over.
EMBED_THREADS_ENV = "DOCIR_EMBED_THREADS"


def model_cache_home() -> Path:
    """Where the embedding model is downloaded and kept.

    **Not derived from a store's ``home``, and it must not be.** The model is
    ~67 MB and identical for every store on the machine, while a project store
    is one per repository and a committed artifact — a copy inside each would
    be downloaded per repository and would need gitignoring to stay out of
    everyone's working tree. So this is the *user-level* ``~/.docir``, which is
    the only docir directory that is per-machine rather than per-project.

    It replaces fastembed's default of ``tempfile.gettempdir()/fastembed_cache``,
    which is wrong in two ways that are the same way: a downloaded model is
    durable state, and a temp directory is where the system puts state it is
    entitled to delete. So the download is re-paid whenever the OS sweeps, and
    where there is no temp directory at all the call raises before docir runs
    (issue-c5c089bcc1b2).

    The override is read here and passed as fastembed's ``cache_dir`` argument
    rather than left to fastembed, because ``define_cache_dir`` computes its
    default *before* it reads the variable — so in a sandbox with no temp
    directory, setting ``FASTEMBED_CACHE_PATH`` does not help and passing
    ``cache_dir`` is the only thing that does.
    """
    override = os.environ.get(MODEL_CACHE_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / PROJECT_STORE_DIRNAME / "models"


def embed_threads() -> int | None:
    """How many threads the embedding model may use, or ``None`` for its default.

    ``None`` means *unset*, and unset means fastembed's own behaviour: ONNX
    takes every core it can see. That is a fine default on a build machine and a
    poor one on a laptop, where warming the model, a reindex and every `context`
    query all saturate the CPU (GitHub #23). The variable is the cap, and it
    reaches ONNX as both ``intra_op_num_threads`` and ``inter_op_num_threads``.

    A value that is not a positive integer is ignored rather than raising. This
    is read while a container is built, on every command including the ones run
    to diagnose the problem, and a typo in a shell profile that made `docir
    doctor` refuse to run would be the worst possible failure here — `doctor`
    reports the effective value instead, which is where somebody looks.
    """
    raw = os.environ.get(EMBED_THREADS_ENV, "").strip()
    if not raw:
        return None
    try:
        threads = int(raw)
    except ValueError:
        return None
    return threads if threads > 0 else None


def store_update_check(home: Path) -> bool | None:
    """What ``<home>/config.yaml`` says about the release notice, if anything.

    ``None`` means the store expressed no preference — no file, an unreadable
    one, or one that does not carry the key — and the caller keeps its default.

    **Every failure is ``None`` rather than an exception.** This is read on every
    command, before anything the user asked for happens, from a file a person
    may hand-edit. A typo in it must cost the notice, never the command; and an
    older docir reading a key a newer one wrote takes the same path, which is
    what makes the file safe to add to a committed store at all.
    """
    import yaml

    try:
        document = yaml.safe_load((home / STORE_CONFIG_FILENAME).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(document, dict):
        return None
    value = document.get("update_check")
    return value if isinstance(value, bool) else None


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
    #: Whether every command prints schema drift to stderr after it runs.
    #: Off by default: `docir check` reports the same thing as a finding, and a
    #: notice on *every* command repeats until someone reindexes, which is how a
    #: warning stops being read. ``DOCIR_SCHEMA_NOTICE=1`` opts in, for the case
    #: the finding cannot cover — a change nobody will run `check` to discover.
    schema_notice: bool = False
    #: Whether to check PyPI for a newer docir and say so on stderr.
    #:
    #: Three inputs, highest first: ``DOCIR_UPDATE_CHECK`` (set to anything, it
    #: decides, in both directions) → ``CI`` being set, which forces it off →
    #: ``update_check:`` in the store's ``config.yaml``, which ``docir init``
    #: writes as ``true``. The default with none of them is ``False``.
    #:
    #: **The default stays off, and the opt-in stays an act somebody performed.**
    #: This is the only network call docir makes in its life, and a documentation
    #: tool that phones home unasked is not one people keep installed
    #: (adr-a555ee6bc484). Creating a store is that act: it is deliberate, it is
    #: the moment a team decides how this repository's docs are kept, and the
    #: answer it records is committed, so one decision covers everyone who clones
    #: it. Nobody who never ran `docir init` is ever contacted.
    #:
    #: The repetition argument ``schema_notice`` makes above is answered instead
    #: by the throttle — `ReleaseService.announce` says it once per version per
    #: day — and by `notice_for`, which says nothing at all where the upgrade
    #: cannot be performed.
    #:
    #: When it is on the daemon does the fetching, at most once a day, and the
    #: CLI only reads the answer it left behind.
    update_check: bool = False
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
        return _with_store_preferences(cls._for_home(home, use_daemon=use_daemon))

    @classmethod
    def _for_home(cls, home: str | os.PathLike[str] | None, *, use_daemon: bool) -> Settings:
        """The home rule alone, before the store gets a say about anything."""
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
    def store_config_path(self) -> Path:
        """The store's committed settings file (see ``STORE_CONFIG_FILENAME``)."""
        return self.home / STORE_CONFIG_FILENAME

    @property
    def release_cache_path(self) -> Path:
        """Where the last "is there a newer docir" answer is remembered.

        In the store rather than the index: it is a fact about the installation,
        not about the documents, and `reindex` must not be able to lose it.
        """
        return self.home / "release-check.json"

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


def _with_store_preferences(settings: Settings) -> Settings:
    """Layer the store's own ``config.yaml`` under the environment.

    Separate from :meth:`Settings._for_home` and applied after it, because the
    file lives *inside* the home the home rule just decided: there is no order in
    which one pass could do both. It is the same shape as the home rule itself —
    one function, every input to one decision visible side by side — and it is
    here for the same reason, which is that ``--home`` was once silently ignored
    by a second copy of a decision living somewhere else.

    Precedence, highest first:

    * ``DOCIR_UPDATE_CHECK`` set to anything at all. An explicit variable is a
      person answering the question for this shell, and it wins in *both*
      directions: ``=0`` silences a store that opted in, ``=1`` overrides ``CI``.
    * ``CI`` set. A build server cannot act on the notice, and an agent that
      acts on it there makes the job's docir version depend on the day it ran.
    * ``update_check:`` in the store's ``config.yaml``.
    """
    if os.environ.get(UPDATE_CHECK_ENV, "").strip():
        return settings
    if os.environ.get(CI_ENV, "").strip():
        return settings.model_copy(update={"update_check": False})
    stored = store_update_check(settings.home)
    if stored is None:
        return settings
    return settings.model_copy(update={"update_check": stored})
