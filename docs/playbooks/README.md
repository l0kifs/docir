# Execution playbooks

One file per recurring task step: the fastest verified way to do it in this repo, with a
deterministic check. Written and read by agents following the `execution-playbooks` skill.

The index below is generated from each playbook's `**When:**` line by that skill's
`scripts/sync_index.py`. Never edit it by hand.

<!-- index:start -->
- [Check a release candidate against the release people already have](check-release-compat.md) — you are cutting a release, and the newest published build must read a store the candidate wrote, and the other way round (adr-ab4598c6f707).
- [Exercise a feature whose behaviour depends on the install kind](exercise-an-install-kind-feature.md) — a change reads `Installation.method` and you must see it work against this repo's real store, which a checkout cannot show you.
- [Inspect what an agent benchmark session did](inspect-agent-benchmark-session.md) — a `benchmarks/agent_tokens.py` row surprises you — too costly, too many calls, a false positive — and you need to see what the session ran.
- [Patch a sentence in a docir document](patch-docir-text.md) — a docir document is wrong in one place and the fix is `--replace-section` or `--replace-body`, which take the whole text back.
- [Prove a guard by injecting the bug it claims to catch](prove-guard-by-injection.md) — you wrote or changed a test that guards a behaviour or a piece of prose and CLAUDE.md's rule applies: a test that has never failed has not been shown to work.
- [Re-point code citations an edit shifted](repoint-shifted-code-citations.md) — `test_code_citations.py` fails with "names `X`, but line N is in `Y`" after you added or removed lines in a cited source file.
<!-- index:end -->
