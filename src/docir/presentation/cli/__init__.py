# CLI adapter — the Typer application and its rendering helpers.
#
#   * app          — the Typer command tree and process entry point.
#   * runner       — builds the executor and runs one request per command.
#   * rendering    — Rich formatting of responses (tables, panels, JSON).
#   * daemon_cmds  — the `docir daemon serve/start/status/stop` subcommands.
#   * body_input   — resolves body text from --body / --body-file / --stdin.
