"""Public surface of the documents module.

The document aggregate and its use cases: the single write path (add / update /
archive / unarchive / delete), the read paths (get / query / search / context),
and index maintenance (reindex / check / lint). Callers depend only on the
services and DTOs re-exported here, never on the module's internals.
"""

from __future__ import annotations

from docir.modules.documents.application.dto import (
    DEFAULT_CONTEXT_EXPAND,
    AddDocumentRequest,
    BenchRequest,
    BenchResult,
    BenchTask,
    ContextRequest,
    DocumentBatch,
    DocumentSummary,
    DocumentView,
    MissingDocument,
    QueryRequest,
    RelatedView,
    SearchRequest,
    UpdateDocumentRequest,
)
from docir.modules.documents.application.services.document_service import DocumentService
from docir.modules.documents.application.services.maintenance_service import (
    MaintenanceService,
    ReindexResult,
    StoreStatus,
)
from docir.modules.documents.application.services.schema_conformance import (
    ConformanceFinding,
    ConformanceReport,
    check_schema_conformance,
)
from docir.modules.documents.infra.default_schema import (
    DEFAULT_ID_STYLE,
    DEFAULT_SCHEMA_YAML,
    ID_STYLES,
    render_schema_yaml,
)
from docir.modules.documents.infra.profiles import PROFILE_NAMES
from docir.modules.documents.infra.schema_loader import describe_schema, load_schema

__all__ = [
    "DEFAULT_CONTEXT_EXPAND",
    "DEFAULT_ID_STYLE",
    "DEFAULT_SCHEMA_YAML",
    "ID_STYLES",
    "PROFILE_NAMES",
    "AddDocumentRequest",
    "BenchRequest",
    "BenchResult",
    "BenchTask",
    "ConformanceFinding",
    "ConformanceReport",
    "ContextRequest",
    "DocumentBatch",
    "DocumentService",
    "DocumentSummary",
    "DocumentView",
    "MaintenanceService",
    "MissingDocument",
    "QueryRequest",
    "ReindexResult",
    "RelatedView",
    "SearchRequest",
    "StoreStatus",
    "UpdateDocumentRequest",
    "check_schema_conformance",
    "describe_schema",
    "load_schema",
    "render_schema_yaml",
]
