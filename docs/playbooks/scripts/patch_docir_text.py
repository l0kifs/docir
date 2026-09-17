#!/usr/bin/env python3
"""Replace exact text in a docir document through the CLI, without retyping the section.

usage: patch_docir_text.py <id> <pairs.json> [--section "<heading>"] [-- <docir update args>]

pairs.json is [[old, new], ...]. Each `old` must occur exactly once in the target text
(the section body without its heading line, or the whole body); otherwise nothing is
written and the script exits 1 naming the pair. With --section the write is
`--replace-section`; without it, `--replace-body --force` (the body is re-read right
before the write, so the disk_diverged guard still protects it). Everything after `--`
is passed to `docir update` unchanged, e.g. `-- --set-code "a,b" --set-description "..."`.
"""

import json
import subprocess
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    extra: list[str] = []
    if "--" in argv:
        cut = argv.index("--")
        argv, extra = argv[:cut], argv[cut + 1 :]
    section = None
    if "--section" in argv:
        i = argv.index("--section")
        section = argv[i + 1]
        argv = argv[:i] + argv[i + 2 :]
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    doc_id, pairs_path = argv
    pairs = json.loads(Path(pairs_path).read_text())

    read = ["uv", "run", "docir", "get", doc_id] + (["--section", section] if section else [])
    got = subprocess.run(read, capture_output=True, text=True, check=True)
    body = json.loads(got.stdout)["body"]
    if section:
        first, _, body = body.partition("\n")
        if first.strip() != f"## {section}":
            print(f"unexpected first line {first!r}", file=sys.stderr)
            return 1
        body = body.strip("\n")
    for old, new in pairs:
        n = body.count(old)
        if n != 1:
            print(f"old text occurs {n} times, nothing written: {old[:80]!r}", file=sys.stderr)
            return 1
        body = body.replace(old, new)

    mode = ["--replace-section", section] if section else ["--replace-body", "--force"]
    write = ["uv", "run", "docir", "update", doc_id, *mode, "--stdin", *extra]
    res = subprocess.run(write, input=body, capture_output=True, text=True)
    if res.returncode:
        print(res.stdout, res.stderr, file=sys.stderr)
        return res.returncode
    out = json.loads(res.stdout)
    print(json.dumps({k: out.get(k) for k in ("id", "updated", "verified", "revoked")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
