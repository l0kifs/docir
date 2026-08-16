# Security Policy

## Supported versions

docir is pre-1.0 and ships from a single line of releases. Fixes land in the newest
release on PyPI; older versions are not patched.

| Version | Supported |
|---|---|
| latest release | ✅ |
| anything older | ❌ — upgrade with `docir self upgrade` |

## Reporting a vulnerability

Report privately through
[GitHub Security Advisories](https://github.com/l0kifs/docir/security/advisories/new).
Please do not open a public issue for something exploitable.

If that page is unavailable to you, open a normal
[issue](https://github.com/l0kifs/docir/issues) saying only that you have a security
report and asking for a private channel — no details, no reproduction — and you will
get one.

Expect an acknowledgement within a week. There is no bounty programme.

## What docir's attack surface actually is

docir is a single-user local CLI with no server, no accounts and no authorization model
(a recorded design decision, not an oversight). That makes the surface small and specific,
and these are the parts worth attention in a report:

**The daemon socket.** The daemon listens on a Unix socket in the system temp directory,
named from a hash of the store path. Filesystem permissions are the only boundary: anyone
who can write to that path can issue commands against your store as you. On a shared host,
that is the thing to look at.

**Published sites.** `docir build` renders each document body with a CommonMark parser,
which passes raw HTML through by design — so a `<script>` tag in a document body reaches
the published page. Everything docir interpolates *around* the body is HTML-escaped. This
is safe for the intended use (your own committed corpus, reviewed like code) and is worth
knowing if you publish a store that accepts documentation from outside: a contributed
document is executable content on your site.

**Network.** Two calls, both narrow: the embedding model downloads once from Hugging Face
on first use (`DOCIR_EMBEDDER=deterministic` skips it entirely), and an opt-in release
check queries PyPI at most once a day when `DOCIR_UPDATE_CHECK=1` is set. Nothing else
leaves the machine — no document content is ever sent anywhere.

**The index.** SQLite, derived and gitignored. It holds nothing the markdown files do not
already hold, so it is exactly as sensitive as your repository.

## What is not a vulnerability

- **No authorization between users of the same machine.** docir has no actors; a local
  user with your filesystem permissions is you.
- **Documents are trusted input.** Frontmatter and bodies come from your own repository.
  Malformed input should produce a clean error, and a crash on it is a bug worth
  reporting — but content from your own corpus doing what it says is not a boundary
  crossing.
- **Hand-edited files that fail validation.** `docir check` reporting a broken corpus is
  the system working.
