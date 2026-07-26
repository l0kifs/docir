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
    DocumentSummary,
    DocumentView,
    QueryRequest,
    RelatedView,
    SearchRequest,
    UpdateDocumentRequest,
)
from docir.modules.documents.application.services.document_service import DocumentService
from docir.modules.documents.application.services.maintenance_service import (
    MaintenanceService,
    ReindexResult,
)
from docir.modules.documents.infra.default_schema import (
    DEFAULT_SCHEMA_YAML,
    render_schema_yaml,
)
from docir.modules.documents.infra.profiles import PROFILE_NAMES
from docir.modules.documents.infra.schema_loader import describe_schema, load_schema

__all__ = [
    "DEFAULT_SCHEMA_YAML",
    "PROFILE_NAMES",
    "AddDocumentRequest",
    "ContextRequest",
    "DocumentService",
    "DocumentSummary",
    "DocumentView",
    "MaintenanceService",
    "QueryRequest",
    "ReindexResult",
    "RelatedView",
    "SearchRequest",
    "UpdateDocumentRequest",
    "describe_schema",
    "load_schema",
    "render_schema_yaml",
]
