"""Public surface of the indexing module.

The relevance/ranking engine over the derived index: hybrid (lexical + semantic)
scoring for ``docs context`` and the deferred embedding-recompute scheduler.
Consumers construct a scheduler through :func:`build_scheduler` and rank with
:class:`HybridScorer`; the concrete scheduler implementations stay private.
"""

from __future__ import annotations

from collections.abc import Callable

from docir.modules.indexing.application.ports.scheduler import EmbeddingScheduler
from docir.modules.indexing.domain.scoring import HybridScorer
from docir.modules.indexing.infra.scheduler import (
    InlineEmbeddingScheduler,
    ThreadedEmbeddingScheduler,
)
from docir.platform.embedding import Embedder
from docir.platform.persistence.unit_of_work import UnitOfWork

UnitOfWorkFactory = Callable[[], UnitOfWork]


def build_scheduler(
    uow_factory: UnitOfWorkFactory,
    embedder: Embedder,
    *,
    background: bool,
) -> EmbeddingScheduler:
    """Construct the embedding scheduler for one process.

    ``background=True`` returns a started, debounced background scheduler (used
    by the daemon); ``False`` returns an inline, synchronous one (in-process /
    tests).
    """
    if background:
        scheduler: EmbeddingScheduler = ThreadedEmbeddingScheduler(uow_factory, embedder)
        scheduler.start()
        return scheduler
    return InlineEmbeddingScheduler(uow_factory, embedder)


__all__ = ["EmbeddingScheduler", "HybridScorer", "build_scheduler"]
