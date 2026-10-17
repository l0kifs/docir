"""What the CLI must not import at startup (issue-9509f9fa3631).

A warm-daemon read is mostly interpreter start and imports, so every module the
client loads for a command it is not running is paid by every command. Each
package below arrives through one command's code path; a module-scope import of
it breaks no behaviour any other test checks and only shows up as latency.

`fastmcp` has its own guard in `test_mcp_cmds.py`; this covers the rest.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

# package -> the one place allowed to import it, which is what to fix when it leaks.
_DEFERRED = {
    "watchfiles": "daemon/cmds.py `_run_server` — only the daemon watches docs/",
    "anyio": "arrives with watchfiles; same deferral",
    "markdown_it": "cli/app.py `build` — only a site build renders markdown",
    "docir.modules.publishing.api": "cli/app.py `build`",
}


@pytest.mark.slow
@pytest.mark.parametrize("module", sorted(_DEFERRED))
def test_importing_the_cli_does_not_import(module: str) -> None:
    """Checked in a subprocess: this session has imported all of them already."""
    probe = (
        "import sys; import docir.entry_points.cli.app; "
        f"sys.exit(1 if {module!r} in sys.modules else 0)"
    )
    assert subprocess.run([sys.executable, "-c", probe], check=False).returncode == 0, (
        f"importing the CLI pulled in {module} — keep the import inside {_DEFERRED[module]}"
    )
