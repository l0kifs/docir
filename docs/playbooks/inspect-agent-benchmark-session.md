# Inspect what an agent benchmark session did

**When:** a `benchmarks/agent_tokens.py` row surprises you — too costly, too many calls, a false positive — and you need to see what the session ran.
**Instead of:** writing a fresh `python -c` over the `.jsonl` transcripts each time, once for commands, again for refused calls, again for the answer text.
**Status:** verified
**Last verified:** 2026-09-28

## Do
1. Find the transcripts under the run's `--out` directory; they are named `<docs>-<suite>-<arm>-<task>-<rep>.jsonl`, and `-OK-1` is the probe.
2. `python3 docs/playbooks/scripts/agent_session.py <out>/259-audit-docir-A01-*.jsonl`
3. Read the call list for the pattern — re-verification by hand, a run of `REFUSED` lines, a tool the arm should not have — and the `ANSWER` line for prose the scorer may have counted.

## Verify
Each session prints one `==` header whose tool-call count and `$` match that run's `tools` and cost in the benchmark's report, then one line per call; a refused call has a `REFUSED` line under it.

## Pitfalls
- A permission is not a fence: `--allowedTools Bash(docir:*)` pre-approves docir, and Claude Code still runs a read-only `find`/`grep`/`head`/`sed` unasked. Look for those in a docir arm before trusting its numbers.
- Refusals cost turns without failing the run; a session with many `REFUSED` lines is measuring the harness, not the tool.
- Move superseded transcripts out of `--out` before rerunning an arm whose flags or prompt changed: the harness resumes by file name and would reuse them.
