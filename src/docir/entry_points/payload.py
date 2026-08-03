"""Token-shaping for machine-readable responses.

Every payload docir hands to a machine — the CLI's piped JSON and the MCP
server's tool results — passes through :func:`trim`. It lives here rather than
in ``cli/rendering.py`` because it is not a rendering concern: it is the wire
shape of an agent-facing response, and two transports now depend on it being
the same one.
"""

from __future__ import annotations

from collections.abc import Mapping

_SCORE_DECIMALS = 4

#: Rounded rather than dropped, so a real 0.0 similarity survives trimming — an
#: absent `similarity` must mean "not scored", never "scored zero".
_SCORE_KEYS = frozenset({"score", "similarity"})


def trim(value: object) -> object:
    """Drop information-free fields (empty str/list/map, null) and round scores.

    Never drops ``False`` or a numeric ``0`` — only genuinely empty values — so an
    omitted key always means "the default", never a real zero. Recurses into
    nested lists and maps.
    """
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if key in _SCORE_KEYS and isinstance(item, float):
                result[str(key)] = round(item, _SCORE_DECIMALS)
                continue
            trimmed = trim(item)
            if trimmed is None or trimmed == "" or trimmed == [] or trimmed == {}:
                continue
            result[str(key)] = trimmed
        return result
    if isinstance(value, list | tuple):
        return [trim(item) for item in value]
    return value
