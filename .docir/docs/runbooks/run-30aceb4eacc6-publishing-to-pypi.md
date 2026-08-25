---
code:
- pyproject.toml
- .github/workflows/**
created: '2026-07-30'
description: How to publish docir to PyPI with uv and GitHub Actions trusted publishing.
id: run-30aceb4eacc6
owner: maintainer
related:
- run-f4a756206fe0
- rel-0c8d261640f6
status: active
tags:
- release
title: Publishing to PyPI
type: runbook
updated: '2026-08-25'
---

This project uses [UV](https://docs.astral.sh/uv/) as the package manager and GitHub Actions for automated publishing to PyPI.

## Prerequisites

1. **PyPI Account**: Create an account at [https://pypi.org/](https://pypi.org/)
2. **Trusted Publishing**: Configure trusted publishing (no API tokens needed!) at [https://pypi.org/manage/account/publishing/](https://pypi.org/manage/account/publishing/)
   - Add a new publisher with:
     - PyPI Project Name: `docir`
     - Owner: `l0kifs`
     - Repository name: `docir`
     - Workflow name: `publish-to-pypi.yml`
     - Environment name: (leave blank)

## Automated Publishing (Recommended)

The project is configured to automatically publish to PyPI when a new GitHub release is created.

**Check current release version** before starting:
```bash
gh release list --limit 10 2>&1 | cat
```

1. **Update version** in `pyproject.toml` (the single source of truth for the version):
   ```toml
   version = "0.2.0"  # Update to your new version
   ```

2. **Update CHANGELOG.md** (required): move entries from `[Unreleased]` into a new version section and update the compare links at the bottom. A section per Keep-a-Changelog heading, plus **Measured and rejected** for anything built and removed — the measurement is the artifact, not the code.

3. **Refresh the generated agent instructions** (required): `docir agent update`
   stamps the files from the *running* `__version__`, so it has to run after the bump
   in step 1 and before the commit in step 4. Nothing detects a stale stamp later —
   0.11.0 shipped with docir's own `.claude/skills/docir/SKILL.md` still claiming
   v0.10.0. See run-f4a756206fe0 for what a *consumer* of the release then has to run.
   ```bash
   uv run docir agent update   # the workspace build, not the installed tool
   ```

4. **Commit and push** your changes:
   ```bash
   git add pyproject.toml CHANGELOG.md .claude/skills/docir/SKILL.md
   git commit -m "Bump version to 0.2.0"
   git push
   ```

5. **Create a GitHub release**:

   Using GitHub CLI with inline notes:
   ```bash
   # Create the release
   gh release create v0.2.0 \
     --title "v0.2.0 - Release Title" \
     --notes "## 🎯 New Features
   - Feature 1 description
   - Feature 2 description

   ## 🐛 Bug Fixes
   - Fix 1 description

   ## 📚 Documentation
   - Doc updates

   ## 🔗 Full Changelog
   See [CHANGELOG.md](https://github.com/l0kifs/docir/blob/v0.2.0/CHANGELOG.md)"
   ```

   Or using the GitHub web interface:
   - Go to [https://github.com/l0kifs/docir/releases/new](https://github.com/l0kifs/docir/releases/new)
   - Create a new tag (e.g., `v0.2.0`)
   - Add release title and description
   - Click "Publish release"

   To verify the release:
   ```bash
   gh release view v0.2.0
   ```

6. **GitHub Actions will automatically**:
   - Build the package using UV
   - Publish to PyPI using trusted publishing
   - You can monitor the progress in the Actions tab

7. **Record the release in the store** (required): a `release_note` document, linked to the
   decisions the release is made of.

   ```bash
   docir add --type release_note --status published \
     --title "0.X.0 — <the thesis, same as the release title>" \
     --description "<one sentence: what the release made possible>" \
     --related adr-...,adr-...,ref-... \
     --stdin < notes.md
   ```

   **Not a second changelog.** `CHANGELOG.md` and the GitHub release carry the full text; this
   carries what neither can — the edges. Link every decision the release contains, especially
   the ones recording work that was *built and thrown away*: those are what a later reader most
   needs, because they are what somebody will otherwise propose again, and a changelog has
   nowhere to put them.

   Carry the upgrade note too. It is the actionable half, and `docir context "what shipped in
   0.X.0"` is where somebody will look for it.

   Status `published`, since the release is. Commit it separately from `chore(release)`: the
   version bump is the release, and this describes it.

## Manual Publishing

If you need to publish manually:

1. **Install UV** (if not already installed):
   ```bash
   pip install uv
   ```

2. **Build the package**:
   ```bash
   uv build
   ```
   This creates distribution files in the `dist/` directory.

3. **Publish using UV** (requires PyPI API token):
   ```bash
   uv publish
   ```
   Or use `twine`:
   ```bash
   pip install twine
   twine upload dist/*
   ```

## Testing on TestPyPI

Before publishing to the main PyPI, you can test on TestPyPI:

1. Configure trusted publishing for TestPyPI at [https://test.pypi.org/manage/account/publishing/](https://test.pypi.org/manage/account/publishing/)

2. Manually trigger the workflow or publish directly to TestPyPI:
   ```bash
   uv publish --index-url https://test.pypi.org/legacy/
   ```

3. Test installation:
   ```bash
   pip install --index-url https://test.pypi.org/simple/ docir
   ```

## Best Practices

1. **Always create tags on the `main` branch** - Never tag on `develop` or feature branches
2. **Merge develop to main before tagging** - Ensure all changes are in main
3. **Test on TestPyPI first** (optional but recommended for major releases)
4. **Use semantic versioning** (MAJOR.MINOR.PATCH)
5. **Analyze changes** in the repository between the last release and current state
6. **Update CHANGELOG.md** with all changes before release (required)
7. **Test build locally** before pushing tags
8. **Keep credentials secure** - use project-specific tokens
9. **Test installation** from PyPI after publishing
10. **Create a GitHub Release** after a successful publish
11. **Monitor PyPI stats** and user feedback
