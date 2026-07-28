"""Maps command names + payloads onto the use-case services.

The dispatcher is the single place that knows the command vocabulary and how to
(de)serialize DTOs. Both the in-process executor and the daemon server run
requests through it, so the wire contract and the local contract can never
drift apart.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict

from docir.modules.documents.api import (
    DEFAULT_CONTEXT_EXPAND,
    AddDocumentRequest,
    ContextRequest,
    DocumentService,
    MaintenanceService,
    QueryRequest,
    SearchRequest,
    UpdateDocumentRequest,
)
from docir.modules.tags.api import TagService
from docir.platform.errors import DocirError

Payload = dict[str, object]
Handler = Callable[[Payload], object]


class Dispatcher:
    """Routes a ``(command, payload)`` pair to the matching use case."""

    def __init__(
        self,
        documents: DocumentService,
        tags: TagService,
        maintenance: MaintenanceService,
    ) -> None:
        self._documents = documents
        self._tags = tags
        self._maintenance = maintenance
        self._handlers: dict[str, Handler] = {
            "ping": self._ping,
            "add": self._add,
            "update": self._update,
            "get": self._get,
            "query": self._query,
            "search": self._search,
            "context": self._context,
            "archive": self._archive,
            "unarchive": self._unarchive,
            "delete": self._delete,
            "tag_add": self._tag_add,
            "tag_list": self._tag_list,
            "tag_rename": self._tag_rename,
            "tag_remove": self._tag_remove,
            "reindex": self._reindex,
            "check": self._check,
            "repair": self._repair,
            "lint": self._lint,
            "embed_flush": self._embed_flush,
        }

    def dispatch(self, command: str, payload: Payload) -> object:
        handler = self._handlers.get(command)
        if handler is None:
            raise DocirError(f"unknown command {command!r}")
        return handler(payload)

    # -- handlers -----------------------------------------------------------

    def _ping(self, _payload: Payload) -> object:
        return {"pong": True}

    def _add(self, payload: Payload) -> object:
        request = AddDocumentRequest(
            type=_str(payload, "type"),
            title=_str(payload, "title"),
            description=_str(payload, "description"),
            tags=_tuple(payload, "tags"),
            related=_tuple(payload, "related"),
            body=_str(payload, "body", default=""),
            status=_opt_str(payload, "status"),
            owner=_opt_str(payload, "owner"),
            wait_embeddings=_bool(payload, "wait_embeddings"),
        )
        return asdict(self._documents.add(request))

    def _update(self, payload: Payload) -> object:
        request = UpdateDocumentRequest(
            doc_id=_str(payload, "doc_id"),
            status=_opt_str(payload, "status"),
            set_title=_opt_str(payload, "set_title"),
            set_description=_opt_str(payload, "set_description"),
            set_tags=_opt_tuple(payload, "set_tags"),
            set_related=_opt_tuple(payload, "set_related"),
            set_owner=_opt_str(payload, "set_owner"),
            mark_verified=_bool(payload, "mark_verified"),
            append_section=_opt_pair(payload, "append_section"),
            replace_section=_opt_pair(payload, "replace_section"),
            replace_body=_opt_str(payload, "replace_body"),
            force=_bool(payload, "force"),
            allow_transition_override=_bool(payload, "allow_transition_override"),
            wait_embeddings=_bool(payload, "wait_embeddings"),
        )
        return asdict(self._documents.update(request))

    def _get(self, payload: Payload) -> object:
        return asdict(self._documents.get(_str(payload, "doc_id")))

    def _query(self, payload: Payload) -> object:
        request = QueryRequest(
            types=_tuple(payload, "types"),
            statuses=_tuple(payload, "statuses"),
            tags=_tuple(payload, "tags"),
            include_archived=_bool(payload, "include_archived"),
            include_inactive=_bool(payload, "include_inactive"),
            limit=_int(payload, "limit", default=50),
        )
        return [asdict(view) for view in self._documents.query(request)]

    def _search(self, payload: Payload) -> object:
        request = SearchRequest(
            text=_str(payload, "text"),
            limit=_int(payload, "limit", default=20),
            include_inactive=_bool(payload, "include_inactive"),
        )
        return [asdict(view) for view in self._documents.search(request)]

    def _context(self, payload: Payload) -> object:
        request = ContextRequest(
            task=_str(payload, "task"),
            limit=_int(payload, "limit", default=5),
            include_inactive=_bool(payload, "include_inactive"),
            expand=_int(payload, "expand", default=DEFAULT_CONTEXT_EXPAND),
        )
        return [asdict(view) for view in self._documents.context(request)]

    def _archive(self, payload: Payload) -> object:
        return asdict(self._documents.archive(_str(payload, "doc_id")))

    def _unarchive(self, payload: Payload) -> object:
        return asdict(self._documents.unarchive(_str(payload, "doc_id")))

    def _delete(self, payload: Payload) -> object:
        doc_id = _str(payload, "doc_id")
        unlinked = self._documents.delete(doc_id, force=_bool(payload, "force"))
        return {"deleted": doc_id, "unlinked": list(unlinked)}

    def _tag_add(self, payload: Payload) -> object:
        view = self._tags.add(_str(payload, "key"), _str(payload, "description"))
        return asdict(view)

    def _tag_list(self, _payload: Payload) -> object:
        return [asdict(view) for view in self._tags.list_all()]

    def _tag_rename(self, payload: Payload) -> object:
        self._tags.rename(_str(payload, "old"), _str(payload, "new"))
        return {"renamed": [_str(payload, "old"), _str(payload, "new")]}

    def _tag_remove(self, payload: Payload) -> object:
        self._tags.remove(_str(payload, "key"), force=_bool(payload, "force"))
        return {"removed": _str(payload, "key")}

    def _reindex(self, payload: Payload) -> object:
        if _bool(payload, "embeddings"):
            return {"embedded": self._maintenance.reindex_embeddings()}
        result = self._maintenance.reindex(changed_only=_bool(payload, "changed_only"))
        return asdict(result)

    def _check(self, _payload: Payload) -> object:
        return [asdict(issue) for issue in self._maintenance.check()]

    def _repair(self, _payload: Payload) -> object:
        return asdict(self._maintenance.repair())

    def _lint(self, _payload: Payload) -> object:
        return [asdict(finding) for finding in self._maintenance.lint_deep()]

    def _embed_flush(self, _payload: Payload) -> object:
        return {"embedded": self._maintenance.flush_embeddings()}


# -- payload coercion helpers ----------------------------------------------


def _str(payload: Payload, key: str, *, default: str | None = None) -> str:
    value = payload.get(key, default)
    if value is None:
        raise DocirError(f"missing required field {key!r}")
    return str(value)


def _opt_str(payload: Payload, key: str) -> str | None:
    value = payload.get(key)
    return None if value is None else str(value)


def _bool(payload: Payload, key: str) -> bool:
    return bool(payload.get(key, False))


def _int(payload: Payload, key: str, *, default: int) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return default
    return int(value)


def _tuple(payload: Payload, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list | tuple):
        return tuple(str(item) for item in value)
    return ()


def _opt_tuple(payload: Payload, key: str) -> tuple[str, ...] | None:
    if key not in payload or payload[key] is None:
        return None
    return _tuple(payload, key)


def _opt_pair(payload: Payload, key: str) -> tuple[str, str] | None:
    value = payload.get(key)
    if not isinstance(value, list | tuple) or len(value) < 2:
        return None
    items = list(value)
    return (str(items[0]), str(items[1]))
