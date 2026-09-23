# Execution playbooks

One file per recurring task step: the fastest verified way to do it in this repo, with a
deterministic check. Written and read by agents following the `execution-playbooks` skill.

The index below is generated from each playbook's `**When:**` line by that skill's
`scripts/sync_index.py`. Never edit it by hand.

<!-- index:start -->
- [Exercise a feature whose behaviour depends on the install kind](exercise-an-install-kind-feature.md) — a change reads `Installation.method` and you must see it work against this repo's real store, which a checkout cannot show you.
- [Patch a sentence in a docir document](patch-docir-text.md) — a docir document is wrong in one place and the fix is `--replace-section` or `--replace-body`, which take the whole text back.
- [Prove a guard by injecting the bug it claims to catch](prove-guard-by-injection.md) — you wrote or changed a test that guards a behaviour or a piece of prose and CLAUDE.md's rule applies: a test that has never failed has not been shown to work.
<!-- index:end -->
