"""Print what one or more ``claude -p --output-format stream-json`` sessions did.

Usage::

    python3 docs/playbooks/scripts/agent_session.py <transcript.jsonl>...

Per session: tool calls, cost, wall clock, then every tool call in order — Bash's command,
otherwise the pattern or path — with ``REFUSED`` and the reason beside any call the
permission layer turned down, and the final answer. A benchmark's summary row says what a
session cost; this says why, which is the question a surprising row always raises next.

Needs no dependency beyond the standard library, so it runs outside the project's venv.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

#: How much of each command and each refusal to print. A heredoc'd Python script is
#: hundreds of characters; its first line says what it was for.
WIDTH = 110


def _one_line(text: str) -> str:
    return " ".join(text.split())[:WIDTH]


def describe(path: Path) -> None:
    calls: dict[str, str] = {}
    refused: dict[str, str] = {}
    result: dict = {}
    for line in path.read_text().splitlines():
        event = json.loads(line)
        message = event.get("message")
        # Only assistant and user events carry a message object; the content of a plain user
        # turn is a string, not a list of blocks.
        content = message.get("content") if isinstance(message, dict) else None
        content = content if isinstance(content, list) else []
        if event.get("type") == "assistant":
            for block in content:
                if block.get("type") == "tool_use":
                    args = block.get("input") or {}
                    what = args.get("command") or args.get("pattern") or args.get("file_path")
                    calls[block["id"]] = f"{block['name']:5} {_one_line(str(what or ''))}"
        elif event.get("type") == "user":
            for block in content:
                if isinstance(block, dict) and block.get("is_error"):
                    reason = block.get("content")
                    reason = reason if isinstance(reason, str) else json.dumps(reason)
                    refused[block["tool_use_id"]] = _one_line(reason)
        elif event.get("type") == "result":
            result = event
    print(
        f"== {path.name}: {len(calls)} tool calls, {len(refused)} refused, "
        f"${result.get('total_cost_usd', 0):.3f}, {result.get('duration_ms', 0) / 1000:.0f}s"
    )
    for tool_id, call in calls.items():
        print(f"   {call}")
        if tool_id in refused:
            print(f"     REFUSED {refused[tool_id]}")
    print(f"   ANSWER {_one_line(result.get('result', '(none)'))}")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    for arg in sys.argv[1:]:
        describe(Path(arg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
