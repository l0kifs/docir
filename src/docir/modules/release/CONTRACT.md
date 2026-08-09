# release

## Purpose
Answers two questions about the docir *installation* rather than about a store:
how docir was installed — and therefore whether it may upgrade itself — and
whether a newer version has been published. Backs `docir self status` and the
package step of `docir self upgrade`.

## Public operations
- `current_installation() -> Installation` — classify the running install
  (`uv-tool` | `pipx` | `pip` | `project` | `uvx` | `unknown`), carrying the
  `upgrade_command` to run and an `explanation` of why there is none
- `build_release_service(version, cache_path, clock=None) -> ReleaseService` —
  wire the service for one process
- `ReleaseService.status(refresh=False) -> ReleaseStatus` — installed against
  newest known; a file read unless `refresh`
- `ReleaseService.upgrade_package() -> UpgradeOutcome` — run the installer where
  there is one; otherwise report why not
- `is_newer(candidate, than=...) -> bool` — PEP 440 comparison, the one place
  version ordering is decided

`ReleaseStatus` carries `installed`, `latest`, `checked_on`, `method`,
`upgrade_command`, `explanation`, and the derived `update_available`.
`UpgradeOutcome` carries `ran`, `ok`, `command`, `message`.

## Behavioural guarantees
- **An installer runs only where docir owns its environment** (uv tool, pipx, a
  virtualenv pip install). A checkout, a lockfile-managed project, an ephemeral
  `uvx` run and an unrecognised layout all return an empty command and a reason.
- **`latest` is three-valued.** `None` means *unknown* — never checked, or the
  check failed — never "up to date".
- **The network is opt-in and daily.** `status()` reads the cache; only
  `refresh=True` may fetch, and it skips the fetch when the cache was already
  written today. Every network failure collapses to `None`.
- Nothing here decides *when* to check: the caller does (`DOCIR_UPDATE_CHECK`).

## Events published
- none (no event bus; see adr-d3e3616400bf)

## Events consumed
- none

## Owns
- data: one small JSON file in the store (`release-check.json`) holding the last
  answer and the date it was fetched. No index/database state; it does not
  participate in the shared unit-of-work.

## Depends on
- modules: none
- platform: clock

## Policy
- permissions: none (single-user local CLI; see adr-90e994d931cc)
- transport: runs in-process only; not routed through the daemon/dispatcher
  (same argument as adr-3a2d5ee7bc84, and see adr-31aa7aa60d11 for why the
  package step re-execs rather than continuing in the replaced process)
