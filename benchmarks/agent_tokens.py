"""What an agent spends to search and to audit the docs, with docir and without, as a store grows.

``tokens.py`` prices both read paths in Python, and its grep side is modelled: it lists
every matching path and opens the five best-matching files, which no agent does. This runs
the real thing, on this repository's own store as it is now and as it stood earlier in git
history, so the curve is a real store at real sizes rather than a generated one. Two jobs:

- **search** — Claude Code answers the judged questions in ``example_fixture.yaml`` once
  with only Grep, Glob and Read over the markdown, once with only the docir CLI. Recall is
  scored on the ids the answer names, against the fixture. A question is asked of a store
  only if every document it needs already existed there.
- **audit** — Claude Code audits a copy of the store with five defects planted in it (a
  dangling edge, a duplicate id, a relation cycle, an overdue review, a file that does not
  parse), once with Grep, Glob, Read and Bash, once with all of those and docir — told in
  the prompt that ``check`` is the answer — and once with docir's packaged skill installed
  instead of being told. The answer
  key is what ``docir check`` reports on that copy, and the run refuses to start unless it
  reports every planted defect: an answer key that misses one would score a blind arm
  perfect. Both arms get the same definition of each defect, cadences included, so the
  baseline is not failing for want of a rule docir knows and it does not.

Each session is read back from its transcript: the context held at the answer (the last
turn's whole prompt plus its output, minus a fixed-overhead probe — the same arm asked only
to reply "OK" — which removes the system prompt and tool definitions), every token
processed across all turns, turns, tool calls, wall clock and cost. A run is *correct* when
it names every expected document — and, in the audit, nothing else — and ``$/ok`` divides
an arm's spend by its correct runs, so a cheap wrong answer does not read as a saving.

Run::

    uv run python benchmarks/agent_tokens.py --sizes 93,175                 # prints the plan
    uv run python benchmarks/agent_tokens.py --sizes 93,175 --yes           # both jobs
    uv run python benchmarks/agent_tokens.py --suite audit --reps 1 --yes   # a smoke run

Every run is one ``claude -p`` session and spends money, so without ``--yes`` it prints the
plan and exits. Transcripts are kept under ``--out``; a rerun with the same ``--out`` resumes
instead of repeating. Needs the ``claude`` CLI signed in. The audit's baseline arm runs
Bash unattended inside its copy of the store. This is a measurement, not a test: it prints
numbers and exits 0.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "benchmarks" / "example_fixture.yaml"
STORE = ".docir"
ID = re.compile(r"\b[a-z]+-[0-9a-f]{12}\b")

#: The model every published row was measured with. Another model is another row, not a
#: correction: a bigger one may grep more narrowly or read fewer files.
MODEL = "claude-sonnet-5"
#: Resolved once, here: the baseline arm's PATH drops every directory holding a docir, and
#: the one holding claude may be among them.
CLAUDE = shutil.which("claude") or "claude"

#: Mean spend per session, only for the plan's estimate. search: 2026-09-25, 76 sessions,
#: $3.54. audit: 2026-09-28, 27 sessions over its three arms, $3.67.
USD_PER_RUN = {"search": 0.047, "audit": 0.14}

AUDIT_HINT = (
    "The project's documentation is in a docir store, the markdown files under ./.docir/docs. "
    "Use the docir CLI through Bash: docir check reports structural findings as JSON, each "
    "with a kind and the doc_ids it names; docir get <id> reads a document. Grep, Glob, Read "
    "and Bash are there too."
)

#: In the search each arm gets one way to read the docs. The grep arm cannot run a shell,
#: so it cannot reach docir. The docir arm is pre-approved only `docir`, which is a
#: permission, not a fence: Claude Code still runs a read-only command (find, grep, head,
#: sed) unasked and refuses the rest. No search run used one (38 of 38, 2026-09-28).
#:
#: The audit compares an agent without docir to the same agent with it. Its baseline arm
#: gets a shell, because checking every file against five rules is the job a real agent
#: writes a script for — and no docir: it is off its PATH (`_env`), refused by permission,
#: and any attempt is reported as a leak. Its docir arm gets that shell too, and is told
#: that `check`'s findings are the answer. Measured 2026-09-28: fenced to docir like the
#: search's, half its runs re-verified `check` through the gaps and spent up to a third of
#: their calls on refused commands; given the shell but not told, every run re-verified by
#: hand and docir saved nothing below 259 documents; told, none did. The skill arm is the
#: same agent with no such line, and docir's packaged skill installed in its copy instead:
#: what an adopter's agent is told, as against what this prompt tells it.
SUITES = {
    "search": {
        "grep": {
            "tools": ["--tools", "Grep,Glob,Read", "--allowedTools", "Grep,Glob,Read"],
            "hint": "The project's documentation is the markdown files under ./docs; each "
            "file name starts with the document's id. Search them with Grep, Glob and Read.",
        },
        "docir": {
            "tools": ["--tools", "Bash", "--allowedTools", "Bash(docir:*)"],
            "hint": "The project's documentation is in a docir store. Use the docir CLI "
            'through Bash: docir context "<question>" returns ranked summaries (no bodies); '
            'docir get <id> --section "<heading>" reads one section, docir get <id> a whole '
            "document.",
        },
    },
    "audit": {
        "shell": {
            "tools": [
                "--tools",
                "Grep,Glob,Read,Bash",
                "--allowedTools",
                "Grep,Glob,Read,Bash",
                "--disallowedTools",
                "Bash(docir:*),Bash(uvx:*),Bash(pipx:*)",
            ],
            "hint": "The project's documentation is the markdown files under ./docs, one "
            "document per file with YAML frontmatter; each file name starts with the "
            "document's id. Read them with Grep, Glob, Read and Bash.",
        },
        "docir": {
            "docir": True,
            "tools": [
                "--tools",
                "Grep,Glob,Read,Bash",
                "--allowedTools",
                "Grep,Glob,Read,Bash",
            ],
            "hint": AUDIT_HINT + " docir check applies exactly the rules below to every file, "
            "so its findings for them are the answer and need no second pass by hand.",
        },
        "skill": {
            "docir": True,
            "skill": True,
            "isolation": ["--setting-sources", "project,local"],
            "tools": [
                "--tools",
                "Grep,Glob,Read,Bash,Skill",
                "--allowedTools",
                "Grep,Glob,Read,Bash,Skill",
            ],
            "hint": AUDIT_HINT,
        },
    },
}
DOCIR = "docir"

#: Nothing from the user's own setup: no settings, MCP servers or skills. An arm that tests
#: a skill loads the project's settings instead, where it installed that skill — and only it.
ISOLATION = ["--setting-sources", "local", "--disable-slash-commands"]

ASK = (
    'Question from a teammate: "{question}"\n'
    "Find the project documents that answer it. Reply with only the ids of the documents "
    "that answer it, most relevant first, at most 5, one per line (an id looks like "
    "adr-27c63ad02695)."
)
AUDIT = (
    "Audit the project's documentation for these five defects, and only these:\n"
    "- dangling: a document's `related:` names an id that no document has\n"
    "- duplicate-id: two files carry the same `id:`\n"
    "- cycle: documents that lead back to themselves through directed relations ({directed}; "
    "a bare id in `related:` is relates_to, which is not directed)\n"
    "- stale: a document past its type's review cadence ({cadence}), counted in days from "
    "`verified`, else `revoked`, else `created`; archived documents are never stale. "
    "Today is {today}.\n"
    "- malformed: a file whose YAML frontmatter does not parse\n"
    "Reply with only the documents that have one, one per line as `<id> <defect>` (for a "
    "malformed file, the id its file name starts with), or NONE if there are none."
)
AUDIT_KINDS = ("dangling", "duplicate-id", "cycle", "stale", "malformed")
PROBE = "Reply with the single word OK."


@dataclass(frozen=True)
class Store:
    rev: str | None  # None: the working tree
    docs: int
    ids: frozenset[str]

    @property
    def label(self) -> str:
        return str(self.docs)


@dataclass(frozen=True)
class Task:
    id: str
    prompt: str
    expected: frozenset[str]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, check=True, capture_output=True, text=True
    ).stdout


def _doc_ids(names: list[str]) -> frozenset[str]:
    """Ids of the markdown documents among *names*; a document's file name starts with it."""
    return frozenset(
        m.group(0) for n in names if n.endswith(".md") and (m := ID.match(Path(n).name))
    )


def current_store() -> Store:
    names = [str(p) for p in (REPO / STORE / "docs").rglob("*.md")]
    return Store(rev=None, docs=len(names), ids=_doc_ids(names))


def history_store(size: int) -> Store:
    """The first commit on the first-parent line whose store held at least *size* documents."""
    for rev in _git(
        "rev-list", "--reverse", "--first-parent", "HEAD", "--", f"{STORE}/docs"
    ).split():
        names = _git("ls-tree", "-r", "--name-only", rev, "--", f"{STORE}/docs").split()
        ids = _doc_ids(names)
        if len(ids) >= size:
            return Store(rev=rev, docs=len(ids), ids=ids)
    raise SystemExit(f"the store never held {size} documents")


def _env(docir: bool) -> dict[str, str]:
    """The docir arm: this checkout's docir first on PATH, in-process, silent, found by
    walking up. Every other arm: no directory that holds a docir, and no virtualenv whose
    Python could ``-m docir``."""
    env = dict(os.environ)
    env.update(DOCIR_NO_DAEMON="1", DOCIR_UPDATE_CHECK="0")
    env.pop("DOCIR_HOME", None)
    if docir:
        env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"
    else:
        env.pop("VIRTUAL_ENV", None)
        env["PATH"] = os.pathsep.join(
            d for d in env.get("PATH", "").split(os.pathsep) if d and not (Path(d) / DOCIR).exists()
        )
    return env


def materialise(
    store: Store, dest: Path, baseline: str, plant: Callable[[Path], None] | None = None
) -> None:
    """Two copies of the store: a docir home with a fresh index, and the bare files for the
    *baseline* arm — the docs alone for a search, the whole store for an audit, which needs
    the schema. *plant* edits the docs first, so both arms read the same damage."""
    home = dest / DOCIR / STORE
    if (home / "index.db").exists():
        return
    shutil.rmtree(dest, ignore_errors=True)
    skip = shutil.ignore_patterns("index.db*", "daemon.log", "release-check.json")
    if store.rev is None:
        shutil.copytree(REPO / STORE, home, ignore=skip)
    else:
        archive = subprocess.run(
            ["git", "archive", store.rev, STORE], cwd=REPO, check=True, capture_output=True
        ).stdout
        with tarfile.open(fileobj=BytesIO(archive)) as tar:
            tar.extractall(dest / DOCIR, filter="data")
    if plant is None:
        shutil.copytree(home / "docs", dest / baseline / "docs")
    else:
        plant(home / "docs")
        shutil.copytree(home, dest / baseline, ignore=skip)
    subprocess.run(
        [DOCIR, "reindex"], cwd=dest / DOCIR, env=_env(True), check=True, capture_output=True
    )


# --- the audit's planted defects -------------------------------------------------------


def _front(path: Path) -> tuple[dict, str] | None:
    """A document's frontmatter and body, or None when it does not parse."""
    head, sep, body = path.read_text(encoding="utf-8").removeprefix("---\n").partition("\n---\n")
    if not sep:
        return None
    try:
        meta = yaml.safe_load(head)
    except yaml.YAMLError:
        return None
    return (meta, body) if isinstance(meta, dict) else None


def _write(path: Path, meta: dict, body: str) -> None:
    head = yaml.safe_dump(meta, sort_keys=True, allow_unicode=True, width=10_000)
    path.write_text(f"---\n{head}---\n{body}", encoding="utf-8")


def _targets(meta: dict) -> list[str]:
    return [e if isinstance(e, str) else str(e.get("to")) for e in meta.get("related") or []]


def plant_defects(docs: Path, cadence: dict[str, int], today: date) -> dict[str, set[str]]:
    """Plant one defect of every audited kind in *docs* and return the ids each one names.

    Targets are the first live documents, by id, that can carry the defect cleanly, so a
    store plants the same damage on every run. The file that stops parsing is one nothing
    links to: an edge to it would dangle once the index drops it, and that finding is
    docir's reading of the damage, not a second defect the baseline could see in the files.
    """
    live = sorted(
        (meta["id"], p, meta, body)
        for p in docs.rglob("*.md")
        if (front := _front(p))
        for meta, body in [front]
        if meta.get("id") and not meta.get("archived")
    )
    ids = {d[0] for d in live}
    linked = {t for _, _, meta, _ in live for t in _targets(meta)}
    taken: set[str] = set()

    def pick(ok: Callable[[str, Path, dict], bool]) -> tuple[str, Path, dict, str]:
        doc = next(d for d in live if d[0] not in taken and ok(d[0], d[1], d[2]))
        taken.add(doc[0])
        return doc

    doc_id, path, meta, _ = pick(
        lambda i, p, m: (
            i not in linked and f"\ntitle: {m.get('title')}\n" in p.read_text(encoding="utf-8")
        )
    )
    # An unquoted colon in a title: the commonest way a hand edit breaks YAML.
    text = path.read_text(encoding="utf-8")
    broken = text.replace(f"\ntitle: {meta['title']}\n", f"\ntitle: {meta['title']}: draft\n")
    path.write_text(broken, encoding="utf-8")
    planted = {"malformed": {doc_id}}

    ghost = "adr-" + hashlib.sha256(b"docir audit ghost").hexdigest()[:12]
    assert ghost not in ids, ghost
    doc_id, path, meta, body = pick(lambda i, p, m: m.get("type") == "decision")
    _write(path, {**meta, "related": [*(meta.get("related") or []), ghost]}, body)
    planted["dangling"] = {doc_id}

    # The file a retype left behind: the same document, under another type's directory.
    doc_id, path, _, _ = pick(lambda i, p, m: m.get("type") == "issue")
    other = next(d for d in sorted(docs.iterdir()) if d.is_dir() and d != path.parent)
    shutil.copy2(path, other / path.name)
    planted["duplicate-id"] = {doc_id}

    doc_id, path, meta, body = pick(lambda i, p, m: cadence.get(str(m.get("type")), 0) > 0)
    overdue = today - timedelta(days=cadence[meta["type"]] + 60)
    _write(path, {**meta, "verified": overdue.isoformat()}, body)
    planted["stale"] = {doc_id}

    a = pick(lambda i, p, m: m.get("type") == "issue")
    b = pick(lambda i, p, m: m.get("type") == "issue")
    for (_, path, meta, body), (to, *_) in ((a, b), (b, a)):
        edge = {"to": to, "kind": "depends_on"}
        _write(path, {**meta, "related": [*(meta.get("related") or []), edge]}, body)
    planted["cycle"] = {a[0], b[0]}
    return planted


def _docir_json(cwd: Path, *args: str) -> object:
    done = subprocess.run(
        [DOCIR, *args], cwd=cwd, env=_env(True), check=False, capture_output=True, text=True
    )
    return json.loads(done.stdout)


def _schema_rules(cwd: Path) -> tuple[dict[str, int], list[str]]:
    """Each type's review cadence and the directed relation kinds, as the store declares them."""
    schema = _docir_json(cwd, "schema", "show")
    assert isinstance(schema, dict)
    cadence = {t["name"]: t["review_days"] for t in schema["types"] if t.get("review_days")}
    directed = [k["name"] for k in schema["relation_kinds"] if not k["symmetric"]]
    return cadence, directed


def audit_task(root: Path, store: Store, today: date) -> Task:
    """Plant the defects, and read the answer key back from ``docir check``."""
    planted_file = root / "planted.json"
    if not planted_file.exists():
        shutil.rmtree(root, ignore_errors=True)
        rules: dict = {}

        def plant(docs: Path) -> None:
            cadence, directed = _schema_rules(docs.parent.parent)
            rules.update(cadence=cadence, directed=directed)
            planted = plant_defects(docs, cadence, today)
            rules["planted"] = {k: sorted(v) for k, v in planted.items()}

        materialise(store, root, "shell", plant)
        planted_file.write_text(json.dumps(rules, indent=1))
    rules = json.loads(planted_file.read_text())

    findings = _docir_json(root / DOCIR, "check")
    assert isinstance(findings, list)
    # A document is something a file carries: `dangling` also names the id that is missing,
    # and `malformed` names no id at all, only the file ("malformed frontmatter in <path>: ...").
    files = _doc_ids([str(p) for p in (root / DOCIR / STORE / "docs").rglob("*.md")])
    reported: dict[str, set[str]] = {}
    for f in findings:
        if f["kind"] in AUDIT_KINDS:
            names = f.get("doc_ids") or ID.findall(f["message"].partition(": ")[0])
            reported.setdefault(f["kind"], set()).update(set(names) & files)
    missed = {
        kind: sorted(set(ids) - reported.get(kind, set()))
        for kind, ids in rules["planted"].items()
        if set(ids) - reported.get(kind, set())
    }
    if missed:
        raise SystemExit(f"{store.docs} docs: docir check does not report {missed}; {root}")
    planted = {i for ids in rules["planted"].values() for i in ids}
    expected = frozenset().union(*reported.values())
    if extra := sorted(expected - planted):
        print(f"{store.docs} docs: also expected, already in the store: {' '.join(extra)}")
    cadence = ", ".join(f"{t} {d} days" for t, d in sorted(rules["cadence"].items()))
    prompt = AUDIT.format(
        directed=", ".join(rules["directed"]),
        cadence=f"{cadence}; other types have none",
        today=today.isoformat(),
    )
    return Task("A01", prompt, expected)


def install_skill(root: Path, arm: str) -> None:
    """A copy of the planted docir store with docir's packaged skill installed beside it.

    Its own copy, so the arm told in its prompt never finds the skill in its tree, and its
    own reindex rather than a copied index, which may hold the path it was built at.
    """
    dest = root / arm
    if (dest / ".claude" / "skills" / DOCIR / "SKILL.md").exists():
        return
    shutil.rmtree(dest, ignore_errors=True)
    skip = shutil.ignore_patterns("index.db*", "daemon.log", "release-check.json")
    shutil.copytree(root / DOCIR, dest, ignore=skip)
    for args in (["reindex"], ["agent", "install", "."]):
        subprocess.run([DOCIR, *args], cwd=dest, env=_env(True), check=True, capture_output=True)


# --- sessions and transcripts ----------------------------------------------------------


def run(suite: str, arm: str, cwd: Path, prompt: str, out: Path, model: str) -> None:
    if out.exists() and out.stat().st_size:
        return
    tmp = out.with_suffix(".tmp")
    spec = SUITES[suite][arm]
    with tmp.open("wb") as stdout, out.with_suffix(".err").open("wb") as stderr:
        done = subprocess.run(
            [
                CLAUDE,
                "-p",
                f"{spec['hint']}\n\n{prompt}",
                "--model",
                model,
                "--output-format",
                "stream-json",
                "--verbose",
                *spec.get("isolation", ISOLATION),
                "--strict-mcp-config",
                "--no-session-persistence",
                *spec["tools"],
            ],
            cwd=cwd,
            env=_env(spec.get("docir", False)),
            stdout=stdout,
            stderr=stderr,
            check=False,
            timeout=900,
        )
    if done.returncode == 0:
        tmp.rename(out)


def read(path: Path) -> dict:
    """What one session held, processed, called, took and cost, and its answer text."""
    turns: list[tuple[str, int, int]] = []
    tools: dict[str, str] = {}
    skill = False
    result: dict = {}
    for line in path.read_text().splitlines():
        event = json.loads(line)
        if event.get("type") == "assistant":
            usage = event["message"].get("usage") or {}
            prompt = sum(
                usage.get(k, 0)
                for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
            )
            turn = (event["message"].get("id"), prompt, usage.get("output_tokens", 0))
            # One API message streams as several events that repeat its usage.
            if turns and turns[-1][0] == turn[0]:
                turns[-1] = turn
            else:
                turns.append(turn)
            for block in event["message"].get("content") or []:
                if block.get("type") == "tool_use":
                    tools[block["id"]] = (block.get("input") or {}).get("command", "")
                    skill = skill or block.get("name") == "Skill"
        elif event.get("type") == "result":
            result = event
    text = result.get("result", "")
    return {
        "held": turns[-1][1] + turns[-1][2] if turns else 0,
        "tokens": sum(p + o for _, p, o in turns),
        "turns": len(turns),
        "tools": len(tools),
        "secs": result.get("duration_ms", 0) / 1000,
        "cost": result.get("total_cost_usd", 0.0),
        "text": text,
        "commands": [c for c in tools.values() if c],
        "skill": skill,
        "error": bool(result.get("is_error")) or text.startswith("API Error"),
    }


def invokes_docir(command: str) -> bool:
    """Whether a shell command runs docir — directly, through a tool runner, or as a module.

    Reading about docir (``grep -r docir docs``) is not running it, so a word is matched
    only where a command starts.
    """
    for segment in re.split(r"&&|\|\||[;|\n]|\$\(|`", command):
        words = [w for w in segment.split() if not re.fullmatch(r"\w+=\S*", w)]
        if not words:
            continue
        head = Path(words[0]).name
        if head == DOCIR or (head in {"uv", "uvx", "pipx"} and DOCIR in words):
            return True
        if head.startswith("python") and words[1:3] == ["-m", DOCIR]:
            return True
    return False


#: An audit's accusation: a line that opens with an id, bulleted or quoted or not, and names
#: a defect. Prose around the list is not one — "confirmed: `adr-…` does not exist" names
#: the missing target of a dangling edge, and scoring every line's first id counted that.
ACCUSATION = re.compile(rf"^[\s*`>•-]*({ID.pattern})\b.*\b(?:{'|'.join(AUDIT_KINDS)})\b")


def score(suite: str, text: str, expected: frozenset[str]) -> tuple[float, int]:
    """Recall against *expected*, and the number of ids named that are not in it.

    A search names at most five, ranked; its extras are only noise and are not counted. An
    audit counts the documents its accusations name.
    """
    if suite == "search":
        return len(set(ID.findall(text)[:5]) & expected) / len(expected), 0
    named = {m.group(1) for line in text.splitlines() if (m := ACCUSATION.match(line))}
    return len(named & expected) / len(expected), len(named - expected)


# --- the report ------------------------------------------------------------------------

COLUMNS = (
    ("held", "held", ",.0f", 7),
    ("tokens", "tokens", ",.0f", 9),
    ("turns", "turns", ".1f", 6),
    ("tools", "tools", ".1f", 6),
    ("secs", "secs", ".0f", 5),
)


def report(
    rows: list[dict], suite: str, stores: list[Store], tasks: set[str] | None, title: str
) -> None:
    arms = list(SUITES[suite])
    print(f"\n{title}")
    print(
        f"{'docs':>5} {'arm':6} {'n':>3} "
        + " ".join(f"{h:>{w}}" for _, h, _, w in COLUMNS)
        + f" {'$/run':>6} {'recall':>6} {'fp':>4} {'ok':>5} {'$/ok':>6} {'err':>4} {'leak':>4}"
        + f" {'skill':>5}"
    )
    for store in stores:
        medians: dict[str, dict[str, float]] = {}
        for arm in arms:
            sel = [
                r
                for r in rows
                if r["suite"] == suite
                and r["store"] == store.label
                and r["arm"] == arm
                and (tasks is None or r["task"] in tasks)
            ]
            if not sel:
                continue
            medians[arm] = {k: statistics.median(r[k] for r in sel) for k, *_ in COLUMNS}
            medians[arm]["cost"] = statistics.mean(r["cost"] for r in sel)
            ok = sum(r["ok"] for r in sel)
            per_ok = f"{sum(r['cost'] for r in sel) / ok:>6.3f}" if ok else f"{'-':>6}"
            print(
                f"{store.docs:>5} {arm:6} {len(sel):>3} "
                + " ".join(f"{medians[arm][k]:>{w}{fmt}}" for k, _, fmt, w in COLUMNS)
                + f" {medians[arm]['cost']:>6.3f}"
                f" {statistics.mean(r['recall'] for r in sel):>6.2f}"
                f" {statistics.mean(r['fp'] for r in sel):>4.1f}"
                f" {ok:>2}/{len(sel):<2} {per_ok}"
                f" {sum(r['error'] for r in sel):>4} {sum(r['leak'] for r in sel):>4}"
                f" {sum(r['skill'] for r in sel):>5}"
            )
        base = medians.get(arms[0])
        for arm in arms[1:]:
            if base and (ours := medians.get(arm)):
                ratios = [
                    f"{k} {base[k] / ours[k]:.1f}x"
                    for k in (*(c[0] for c in COLUMNS), "cost")
                    if ours[k]
                ]
                print(f"{'':>5} {arms[0]} / {arm}: {', '.join(ratios)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--sizes",
        default="",
        help="Earlier store sizes from git history, e.g. 93,175 (default: none)",
    )
    parser.add_argument(
        "--suite",
        action="append",
        choices=list(SUITES),
        help="Only this job (repeatable; default: every job)",
    )
    parser.add_argument("--reps", type=int, default=2, help="Runs per question (default: 2)")
    parser.add_argument("--task", action="append", help="Only this fixture id (repeatable)")
    parser.add_argument(
        "--arm",
        action="append",
        help="Run only this arm (repeatable); the report still reads every arm's transcripts",
    )
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--jobs", type=int, default=4, help="Sessions at once (default: 4)")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(tempfile.gettempdir()) / "docir-agent-tokens",
        help="Transcripts and store copies; reused to resume",
    )
    parser.add_argument("--yes", action="store_true", help="Spend the money and run")
    args = parser.parse_args()
    suites = args.suite or list(SUITES)

    def asked_arms(suite: str) -> list[str]:
        return [a for a in SUITES[suite] if not args.arm or a in args.arm]

    fixture = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    fixture = [e for e in fixture if not args.task or e["id"] in args.task]
    stores = [history_store(int(s)) for s in args.sizes.split(",") if s] + [current_store()]
    plan = {s.label: [e for e in fixture if set(e["relevant"]) <= s.ids] for s in stores}
    per_suite = {
        "search": {s.label: len(plan[s.label]) for s in stores},
        "audit": {s.label: 1 for s in stores},
    }
    runs = {
        suite: sum(
            len(asked_arms(suite)) * (1 + per_suite[suite][s.label] * args.reps) for s in stores
        )
        for suite in suites
    }
    for s in stores:
        where = s.rev[:7] if s.rev else "working tree"
        line = f"{s.docs:>4} docs ({where}):"
        if "search" in suites:
            line += (
                f" {len(plan[s.label])} answerable of {len(fixture)} questions:"
                f" {' '.join(e['id'] for e in plan[s.label])};"
            )
        if "audit" in suites:
            line += f" an audit of {len(AUDIT_KINDS)} planted defects;"
        print(line.rstrip(";"))
    usd = sum(n * USD_PER_RUN[suite] for suite, n in runs.items())
    print(f"{sum(runs.values())} sessions on {args.model}, about ${usd:.2f}; out: {args.out}")
    if not args.yes:
        print("dry run: pass --yes to run them")
        return 0

    today = date.today()
    tasks: dict[tuple[str, str], list[Task]] = {}
    for s in stores:
        root = args.out / "stores" / s.label
        if "search" in suites:
            materialise(s, root, "grep")
            tasks["search", s.label] = [
                Task(e["id"], ASK.format(question=e["task"]), frozenset(e["relevant"]))
                for e in plan[s.label]
            ]
        if "audit" in suites:
            audit_root = args.out / "stores" / f"{s.label}-audit"
            tasks["audit", s.label] = [audit_task(audit_root, s, today)]
            for arm, spec in SUITES["audit"].items():
                if spec.get("skill"):
                    install_skill(audit_root, arm)

    def cwd(suite: str, store: Store, arm: str) -> Path:
        return (
            args.out
            / "stores"
            / (store.label if suite == "search" else f"{store.label}-audit")
            / arm
        )

    def transcript(suite: str, store: Store, arm: str, task: str, rep: int) -> Path:
        return args.out / f"{store.label}-{suite}-{arm}-{task}-{rep}.jsonl"

    jobs = []
    for suite in suites:
        for s in stores:
            for arm in asked_arms(suite):
                jobs.append(
                    (suite, arm, cwd(suite, s, arm), PROBE, transcript(suite, s, arm, "OK", 1))
                )
                for t in tasks[suite, s.label]:
                    for rep in range(1, args.reps + 1):
                        out = transcript(suite, s, arm, t.id, rep)
                        jobs.append((suite, arm, cwd(suite, s, arm), t.prompt, out))
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        list(pool.map(lambda j: run(*j, model=args.model), jobs))

    rows = []
    asked = 0
    for suite in suites:
        for s in stores:
            for arm in SUITES[suite]:
                probe = transcript(suite, s, arm, "OK", 1)
                if not probe.exists():
                    print(f"no probe for {s.label}/{suite}/{arm}: see {probe.with_suffix('.err')}")
                    continue
                base = read(probe)["held"]
                for t in tasks[suite, s.label]:
                    for rep in range(1, args.reps + 1):
                        path = transcript(suite, s, arm, t.id, rep)
                        asked += arm in asked_arms(suite)
                        if not path.exists():
                            continue
                        r = read(path)
                        recall, fp = score(suite, r["text"], t.expected)
                        leak = not SUITES[suite][arm].get("docir") and any(
                            invokes_docir(c) for c in r["commands"]
                        )
                        rows.append(
                            {
                                **r,
                                "suite": suite,
                                "store": s.label,
                                "arm": arm,
                                "task": t.id,
                                "held": r["held"] - base,
                                "recall": recall,
                                "fp": fp,
                                "ok": recall == 1 and fp == 0 and not leak,
                                "leak": leak,
                            }
                        )
    print(f"\n{len(rows)} runs read, {asked} asked for; total ${sum(r['cost'] for r in rows):.2f}")
    print("held: context at the answer, net of the probe. medians; $/run, recall, fp: means")
    if "search" in suites:
        report(rows, "search", stores, None, "search: every answerable question, per store")
        common = set.intersection(*({e["id"] for e in plan[s.label]} for s in stores))
        if len(stores) > 1 and common:
            report(
                rows,
                "search",
                stores,
                common,
                f"search: only the questions every store can answer: {sorted(common)}",
            )
    if "audit" in suites:
        report(rows, "audit", stores, None, "audit: five planted defects, per store")
    return 0


if __name__ == "__main__":
    sys.exit(main())
