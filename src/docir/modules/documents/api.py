"""Public surface of the documents module.

The document aggregate and its use cases: the single write path (add / update /
archive / unarchive / delete), the read paths (get / query / search / context),
and index maintenance (reindex / check / lint). Callers depend only on the
services and DTOs re-exported here, never on the module's internals.
"""

from __future__ import annotations

from docir.modules.documents.application.dto import (
    AddDocumentRequest,
    ContextRequest,
    DocumentView,
    QueryRequest,
    SearchRequest,
    UpdateDocumentRequest,
)
from docir.modules.documents.application.services.document_service import DocumentService
from docir.modules.documents.application.services.maintenance_service import (
    MaintenanceService,
    ReindexResult,
)
from docir.modules.documents.infra.schema_loader import load_schema

__all__ = [
    "AddDocumentRequest",
    "ContextRequest",
    "DocumentService",
    "DocumentView",
    "MaintenanceService",
    "QueryRequest",
    "ReindexResult",
    "SearchRequest",
    "UpdateDocumentRequest",
    "load_schema",
]
