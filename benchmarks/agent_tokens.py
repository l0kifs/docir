"""What an agent holds in context to answer, with docir and with grep, as a real store grows.

``tokens.py`` prices both read paths in Python, and its grep side is modelled: it lists
every matching path and opens the five best-matching files, which no agent does. This runs
the real thing. Claude Code answers the judged questions in ``example_fixture.yaml`` twice
over — once with only Grep, Glob and Read over the markdown, once with only the docir CLI —
on this repository's own store as it is now and as it stood earlier in git history, so the
curve is a real store at real sizes rather than a generated one.

What is measured is the context the agent held when it answered: the last turn's whole
prompt plus its output, minus a fixed-overhead probe (the same arm asked only to reply
"OK"), which removes the system prompt and tool definitions. Recall is scored on the ids the
answer names, against the fixture. A question is asked of a store only if every document it
needs already existed there.

Run::

    uv run python benchmarks/agent_tokens.py --sizes 93,175 --yes          # ~80 sessions
    uv run python benchmarks/agent_tokens.py --task E06 --reps 1 --yes     # a smoke run

Every run is one ``claude -p`` session and spends money, so without ``--yes`` it prints the
plan and exits. Transcripts are kept under ``--out``; a rerun with the same ``--out`` resumes
instead of repeating. Needs the ``claude`` CLI signed in. This is a measurement, not a test:
it prints numbers and exits 0.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
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

#: Mean spend per session on 2026-09-25 (76 sessions, $3.54). Only for the plan's estimate.
USD_PER_RUN = 0.047

#: Each arm gets exactly one way to read the docs. The grep arm cannot run a shell, so it
#: cannot reach docir; the docir arm can run only `docir`, so it cannot grep the files.
ARMS = {
    "grep": {
        "tools": ["--tools", "Grep,Glob,Read", "--allowedTools", "Grep,Glob,Read"],
        "hint": "The project's documentation is the markdown files under ./docs; each file "
        "name starts with the document's id. Search them with Grep, Glob and Read.",
    },
    "docir": {
        "tools": ["--tools", "Bash", "--allowedTools", "Bash(docir:*)"],
        "hint": "The project's documentation is in a docir store. Use the docir CLI through "
        'Bash: docir context "<question>" returns ranked summaries (no bodies); docir get '
        '<id> --section "<heading>" reads one section, docir get <id> a whole document.',
    },
}

ASK = (
    'Question from a teammate: "{question}"\n'
    "Find the project documents that answer it. Reply with only the ids of the documents "
    "that answer it, most relevant first, at most 5, one per line (an id looks like "
    "adr-27c63ad02695)."
)
PROBE = "Reply with the single word OK."


@dataclass(frozen=True)
class Store:
    rev: str | None  # None: the working tree
    docs: int
    ids: frozenset[str]

    @property
    def label(self) -> str:
        return str(self.docs)


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


def _env() -> dict[str, str]:
    """This checkout's docir first on PATH, in-process, silent, and found by walking up."""
    env = dict(os.environ)
    env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"
    env.update(DOCIR_NO_DAEMON="1", DOCIR_UPDATE_CHECK="0")
    env.pop("DOCIR_HOME", None)
    return env


def materialise(store: Store, dest: Path) -> None:
    """Two copies of the store: a docir home with a fresh index, and the bare docs for grep."""
    home = dest / "docir" / STORE
    if (home / "index.db").exists():
        return
    shutil.rmtree(dest, ignore_errors=True)
    if store.rev is None:
        skip = shutil.ignore_patterns("index.db*", "daemon.log", "release-check.json")
        shutil.copytree(REPO / STORE, home, ignore=skip)
    else:
        archive = subprocess.run(
            ["git", "archive", store.rev, STORE], cwd=REPO, check=True, capture_output=True
        ).stdout
        with tarfile.open(fileobj=BytesIO(archive)) as tar:
            tar.extractall(dest / "docir", filter="data")
    shutil.copytree(home / "docs", dest / "grep" / "docs")
    subprocess.run(
        ["docir", "reindex"], cwd=dest / "docir", env=_env(), check=True, capture_output=True
    )


def run(arm: str, cwd: Path, prompt: str, out: Path, model: str) -> None:
    if out.exists() and out.stat().st_size:
        return
    tmp = out.with_suffix(".tmp")
    with tmp.open("wb") as stdout, out.with_suffix(".err").open("wb") as stderr:
        done = subprocess.run(
            [
                "claude",
                "-p",
                f"{ARMS[arm]['hint']}\n\n{prompt}",
                "--model",
                model,
                "--output-format",
                "stream-json",
                "--verbose",
                # Nothing from the user's own setup: no settings, MCP servers or skills.
                "--setting-sources",
                "local",
                "--strict-mcp-config",
                "--disable-slash-commands",
                "--no-session-persistence",
                *ARMS[arm]["tools"],
            ],
            cwd=cwd,
            env=_env(),
            stdout=stdout,
            stderr=stderr,
            check=False,
            timeout=900,
        )
    if done.returncode == 0:
        tmp.rename(out)


def read(path: Path) -> dict:
    """Context held at the answer, turns, cost and the answer text, from one transcript."""
    turns: list[tuple[str, int, int]] = []
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
        elif event.get("type") == "result":
            result = event
    text = result.get("result", "")
    return {
        "held": turns[-1][1] + turns[-1][2] if turns else 0,
        "turns": len(turns),
        "cost": result.get("total_cost_usd", 0.0),
        "text": text,
        "error": bool(result.get("is_error")) or text.startswith("API Error"),
    }


def report(rows: list[dict], stores: list[Store], tasks: set[str] | None, title: str) -> None:
    print(f"\n{title}")
    print(
        f"{'docs':>5} {'arm':6} {'n':>3} {'held (net)':>11} {'turns':>6} {'$/run':>7} "
        f"{'recall':>7} {'errors':>7}"
    )
    for store in stores:
        medians = {}
        for arm in ARMS:
            sel = [
                r
                for r in rows
                if r["store"] == store.label
                and r["arm"] == arm
                and (tasks is None or r["task"] in tasks)
            ]
            if not sel:
                continue
            medians[arm] = statistics.median(r["held_net"] for r in sel)
            print(
                f"{store.docs:>5} {arm:6} {len(sel):>3} {medians[arm]:>11,.0f} "
                f"{statistics.median(r['turns'] for r in sel):>6.1f} "
                f"{statistics.mean(r['cost'] for r in sel):>7.3f} "
                f"{statistics.mean(r['recall'] for r in sel):>7.2f} "
                f"{sum(r['error'] for r in sel):>7}"
            )
        if medians.get("docir"):
            print(f"{'':>5} grep / docir = {medians['grep'] / medians['docir']:.1f}x")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--sizes",
        default="",
        help="Earlier store sizes from git history, e.g. 93,175 (default: none)",
    )
    parser.add_argument("--reps", type=int, default=2, help="Runs per question (default: 2)")
    parser.add_argument("--task", action="append", help="Only this fixture id (repeatable)")
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

    fixture = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    fixture = [e for e in fixture if not args.task or e["id"] in args.task]
    stores = [history_store(int(s)) for s in args.sizes.split(",") if s] + [current_store()]
    plan = {s.label: [e for e in fixture if set(e["relevant"]) <= s.ids] for s in stores}
    runs = sum(len(ARMS) * (1 + len(plan[s.label]) * args.reps) for s in stores)
    for s in stores:
        where = s.rev[:7] if s.rev else "working tree"
        print(
            f"{s.docs:>4} docs ({where}): {len(plan[s.label])} answerable of {len(fixture)} "
            f"questions: {' '.join(e['id'] for e in plan[s.label])}"
        )
    print(f"{runs} sessions on {args.model}, about ${runs * USD_PER_RUN:.2f}; out: {args.out}")
    if not args.yes:
        print("dry run: pass --yes to run them")
        return 0

    jobs = []
    for s in stores:
        root = args.out / "stores" / s.label
        materialise(s, root)
        for arm in ARMS:
            jobs.append((arm, root / arm, PROBE, args.out / f"{s.label}-{arm}-OK-1.jsonl"))
            for e in plan[s.label]:
                for rep in range(1, args.reps + 1):
                    out = args.out / f"{s.label}-{arm}-{e['id']}-{rep}.jsonl"
                    jobs.append((arm, root / arm, ASK.format(question=e["task"]), out))
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        list(pool.map(lambda j: run(*j, model=args.model), jobs))

    relevant = {e["id"]: set(e["relevant"]) for e in fixture}
    rows = []
    for s in stores:
        for arm in ARMS:
            probe = args.out / f"{s.label}-{arm}-OK-1.jsonl"
            if not probe.exists():
                print(f"no probe for {s.label}/{arm}: see {probe.with_suffix('.err')}")
                continue
            base = read(probe)["held"]
            for e in plan[s.label]:
                for rep in range(1, args.reps + 1):
                    path = args.out / f"{s.label}-{arm}-{e['id']}-{rep}.jsonl"
                    if not path.exists():
                        continue
                    r = read(path)
                    found = ID.findall(r["text"])[:5]
                    rows.append(
                        {
                            **r,
                            "store": s.label,
                            "arm": arm,
                            "task": e["id"],
                            "held_net": r["held"] - base,
                            "recall": len(set(found) & relevant[e["id"]]) / len(relevant[e["id"]]),
                        }
                    )
    print(
        f"\n{len(rows)} of {runs - len(stores) * len(ARMS)} question runs read; "
        f"total ${sum(r['cost'] for r in rows):.2f}"
    )
    report(rows, stores, None, "Every answerable question, per store")
    common = set.intersection(*({e["id"] for e in plan[s.label]} for s in stores))
    if len(stores) > 1 and common:
        report(rows, stores, common, f"Only the questions every store can answer: {sorted(common)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
