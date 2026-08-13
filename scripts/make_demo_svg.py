"""Render the captured docir session as a self-contained animated SVG.

Every line below is real output, captured from a four-document store at
COLUMNS=132 from a four-document store. Nothing is retyped or prettied: if the
CLI's rendering changes this asset is wrong, and the fix is to recapture it —

    COLUMNS=132 docir --pretty context "implement a new auth endpoint" --limit 3

— paste the result into ``OUT_1`` below and re-run this script. The lines are
132 characters wide because a terminal's are; ``E501`` is waived for this file
in ``pyproject.toml`` for that reason and no other.

Animation is pure CSS keyframes — no script, because GitHub serves README
images through a proxy that strips JavaScript but keeps stylesheets, and a
static fallback frame would defeat the point of the asset.
"""

from __future__ import annotations

import html
import pathlib

# -- the captured session ----------------------------------------------------

CMD_1 = 'docir context "implement a new auth endpoint" --limit 3'
OUT_1 = """\
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━┓
┃ id                 ┃ type     ┃ status   ┃ title                    ┃ description              ┃ score ┃   sim ┃ matched section ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━┩
│ issue-1ca65f9f25da │ issue    │ open     │ Refresh token race under │ Two tabs refreshing at   │ 0.032 │ 0.531 │ Symptom         │
│                    │          │          │ concurrent logins        │ once revoke each other.  │       │       │                 │
│ adr-db2079b2d42d   │ decision │ proposed │ Short-lived JWTs with    │ How API clients          │ 0.016 │ 0.553 │ Decision        │
│                    │          │          │ refresh rotation         │ authenticate and how     │       │       │                 │
│                    │          │          │                          │ sessions are renewed.    │       │       │                 │
│ adr-8d39326052c8   │ decision │ proposed │ Rate limits are          │ Why throttling keys on   │ 0.016 │ 0.536 │ -               │
│                    │          │          │ per-account, not per-IP  │ the account.             │       │       │                 │
└────────────────────┴──────────┴──────────┴──────────────────────────┴──────────────────────────┴───────┴───────┴─────────────────┘"""

CMD_2 = 'docir get adr-db2079b2d42d --section "Decision"'
OUT_2 = """\
## Decision

Access tokens live 15 minutes. Refresh tokens rotate on every use and are
single-use; replaying one revokes the whole family."""

# -- geometry ----------------------------------------------------------------

CH_W, LINE_H, FONT = 7.8, 19.0, 13.0
PAD_X, TOP = 26.0, 62.0
COLS = max(len(line) for line in (OUT_1 + "\n" + OUT_2).splitlines())
WIDTH = PAD_X * 2 + COLS * CH_W

#: One loop. The holds are long on purpose: a reader arriving mid-cycle should
#: land on a full frame far more often than on a typing one.
DUR = 16.0


def pct(seconds: float) -> float:
    return round(seconds / DUR * 100, 3)


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def line(x: float, y: float, text: str, cls: str) -> str:
    return f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}">{esc(text)}</text>'


def block(y: float, text: str, cls: str, group: str) -> tuple[str, float]:
    """A revealed output block; returns its markup and the y after it."""
    rows = text.splitlines()
    body = "".join(line(PAD_X, y + i * LINE_H, row, cls) for i, row in enumerate(rows))
    return f'<g class="{group}">{body}</g>', y + len(rows) * LINE_H


def typed(y: float, cmd: str, group: str, cursor: str) -> tuple[str, float]:
    """A prompt plus a command revealed left-to-right by an animated clip."""
    prompt_w = 2 * CH_W
    return (
        f'<g class="{group}">'
        f"{line(PAD_X, y, '$', 'prompt')}"
        f'<g clip-path="url(#clip-{group})">'
        f"{line(PAD_X + prompt_w, y, cmd, 'cmd')}</g>"
        f'<rect class="{cursor}" x="{PAD_X + prompt_w:.1f}" y="{y - FONT + 2:.1f}" '
        f'width="{CH_W:.1f}" height="{FONT + 3:.1f}"/>'
        f'<clipPath id="clip-{group}"><rect class="{group}-clip" '
        f'x="{PAD_X + prompt_w:.1f}" y="{y - FONT - 2:.1f}" '
        f'width="0" height="{LINE_H + 4:.1f}"/></clipPath></g>',
        y + LINE_H,
    )


def main() -> None:
    parts: list[str] = []
    y = TOP
    frag, y = typed(y, CMD_1, "c1", "cur1")
    parts.append(frag)
    y += 6
    frag, y = block(y, OUT_1, "out", "o1")
    parts.append(frag)
    y += LINE_H
    frag, y = typed(y, CMD_2, "c2", "cur2")
    parts.append(frag)
    y += 6
    frag, y = block(y, OUT_2, "body", "o2")
    parts.append(frag)
    height = y + 22

    css = f"""
    .term-bg {{ fill: #0d1117; }}
    .term-bar {{ fill: #161b22; }}
    .term-edge {{ fill: none; stroke: #30363d; stroke-width: 1; }}
    text {{ font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas,
            "DejaVu Sans Mono", monospace; font-size: {FONT}px;
            white-space: pre; dominant-baseline: alphabetic; }}
    .prompt {{ fill: #3fb950; }}
    .cmd    {{ fill: #e6edf3; }}
    .out    {{ fill: #9198a1; }}
    .body   {{ fill: #e6edf3; }}
    .title  {{ fill: #6e7783; font-size: 11.5px; }}
    /* Amber is only ever the caret — the brand's one fixed rule. */
    .cur1, .cur2 {{ fill: #E0932C; }}
    .o1, .o2 {{ opacity: 0; }}

    @keyframes type1 {{
      0%             {{ width: 0; }}
      {pct(1.6)}%    {{ width: {len(CMD_1) * CH_W:.1f}px; }}
      {pct(15.4)}%   {{ width: {len(CMD_1) * CH_W:.1f}px; }}
      {pct(15.6)}%   {{ width: 0; }}
      100%           {{ width: 0; }}
    }}
    @keyframes type2 {{
      0%, {pct(6.2)}%  {{ width: 0; }}
      {pct(7.5)}%      {{ width: {len(CMD_2) * CH_W:.1f}px; }}
      {pct(15.4)}%     {{ width: {len(CMD_2) * CH_W:.1f}px; }}
      {pct(15.6)}%     {{ width: 0; }}
      100%             {{ width: 0; }}
    }}
    @keyframes reveal1 {{
      0%, {pct(1.7)}%  {{ opacity: 0; }}
      {pct(2.1)}%      {{ opacity: 1; }}
      {pct(15.4)}%     {{ opacity: 1; }}
      {pct(15.6)}%     {{ opacity: 0; }}
      100%             {{ opacity: 0; }}
    }}
    @keyframes reveal2 {{
      0%, {pct(7.6)}%  {{ opacity: 0; }}
      {pct(8.0)}%      {{ opacity: 1; }}
      {pct(15.4)}%     {{ opacity: 1; }}
      {pct(15.6)}%     {{ opacity: 0; }}
      100%             {{ opacity: 0; }}
    }}
    /* The caret sits at the end of what has been typed, then stops blinking
       while the reader is meant to be looking at the output. */
    @keyframes caret1 {{
      0%             {{ transform: translateX(0); opacity: 1; }}
      {pct(1.6)}%    {{ transform: translateX({len(CMD_1) * CH_W:.1f}px); opacity: 1; }}
      {pct(1.7)}%    {{ transform: translateX({len(CMD_1) * CH_W:.1f}px); opacity: 0; }}
      100%           {{ opacity: 0; }}
    }}
    @keyframes caret2 {{
      0%, {pct(6.2)}%  {{ transform: translateX(0); opacity: 0; }}
      {pct(6.3)}%      {{ transform: translateX(0); opacity: 1; }}
      {pct(7.5)}%      {{ transform: translateX({len(CMD_2) * CH_W:.1f}px); opacity: 1; }}
      {pct(7.6)}%      {{ opacity: 0; }}
      100%             {{ opacity: 0; }}
    }}
    .c1-clip {{ animation: type1 {DUR}s steps({len(CMD_1)}, end) infinite; }}
    .c2-clip {{ animation: type2 {DUR}s steps({len(CMD_2)}, end) infinite; }}
    .o1 {{ animation: reveal1 {DUR}s linear infinite; }}
    .o2 {{ animation: reveal2 {DUR}s linear infinite; }}
    .cur1 {{ animation: caret1 {DUR}s steps({len(CMD_1)}, end) infinite; }}
    .cur2 {{ animation: caret2 {DUR}s steps({len(CMD_2)}, end) infinite; }}

    @media (prefers-reduced-motion: reduce) {{
      .c1-clip {{ animation: none; width: {len(CMD_1) * CH_W:.1f}px; }}
      .c2-clip {{ animation: none; width: {len(CMD_2) * CH_W:.1f}px; }}
      .o1, .o2 {{ animation: none; opacity: 1; }}
      .cur1, .cur2 {{ animation: none; opacity: 0; }}
    }}
    """

    dots = "".join(
        f'<circle cx="{22 + i * 18}" cy="21" r="5.5" fill="{c}"/>'
        for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840"))
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH:.0f} {height:.0f}" '
        f'width="{WIDTH:.0f}" height="{height:.0f}" role="img" '
        f'aria-label="A terminal running docir context, which returns three ranked '
        f'documents with no bodies, then docir get --section, which returns one section.">'
        f"<style>{css}</style>"
        f'<rect class="term-bg" width="{WIDTH:.0f}" height="{height:.0f}" rx="10"/>'
        f'<path class="term-bar" d="M0 10a10 10 0 0 1 10-10h{WIDTH - 20:.0f}'
        f'a10 10 0 0 1 10 10v32H0z"/>'
        f"{dots}"
        f'<text class="title" x="{WIDTH / 2:.0f}" y="25" text-anchor="middle">'
        f"~/acme-payments — docir</text>"
        f'<rect class="term-edge" x="0.5" y="0.5" width="{WIDTH - 1:.0f}" '
        f'height="{height - 1:.0f}" rx="10"/>'
        f"{''.join(parts)}</svg>"
    )
    out = pathlib.Path(__file__).resolve().parent.parent / "assets" / "docir-demo.svg"
    out.write_text(svg, encoding="utf-8")
    print(f"{out} — {WIDTH:.0f}x{height:.0f}, {len(svg) / 1024:.1f} KiB")


if __name__ == "__main__":
    main()
