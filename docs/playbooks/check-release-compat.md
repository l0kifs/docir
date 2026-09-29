# Check a release candidate against the release people already have

**When:** you are cutting a release, and the newest published build must read a store the candidate wrote, and the other way round (adr-ab4598c6f707).
**Instead of:** typing the `uvx --from docir==<released>` lines by hand — zsh does not word-split `$O`, the scratch store refuses unregistered tags, and each fix costs a rerun.
**Status:** verified
**Last verified:** 2026-09-28

## Do
1. After the version bump and `uv sync` (so `.venv/bin/docir` is the candidate), take the
   released version from `gh release list --limit 1`.
2. `bash docs/playbooks/scripts/release_compat.sh <released>` from anywhere in the repo.
3. Before `gh release create`, list the commits since the last tag that touched a shipped
   surface and check each has a `CHANGELOG.md` entry:
   `git log --format='%h %s' v<released>..HEAD -- src README.md`

## Verify
The script's last line is `PASS: no refusal in either direction` and it exits 0. Any `REFUSED`
line is the break adr-ab4598c6f707 is about; the `findings:` lines are for reading, and a kind
the older build does not know (or `stale-index-build` on this store) is expected, not a failure.
Pointing it at a version that cannot install (`0.0.1`) prints 12 `REFUSED` and exits 1.

## Pitfalls
- After publishing, `https://pypi.org/pypi/docir/<v>/json` answers at once; `uvx` still said
  "no version of docir==<v>" for minutes after 0.30.0's green publish run. Probe the index with
  `curl --compressed` or `uvx -v`: it varies on `Accept-Encoding`, and the uncompressed copy a
  plain `curl` reads was still stale the next day while every installer already had the release.
- A `docs(...)`-prefixed commit can still change the packaged skill or a docstring: 0.30.0's
  `docs(agents)` commit did, and had no changelog entry until step 3 caught it.
- A locally present, gitignored `.claude/rules/managed/*.md` fails
  `test_the_rules_reach_the_code_they_govern.py` locally only; CI's clean checkout passes.
