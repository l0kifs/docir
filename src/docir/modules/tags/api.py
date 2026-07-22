"""Public surface of the tags module.

The tag registry: the source of truth for which tags exist. Callers depend only
on :class:`TagService` and :class:`TagView`, never on the module's internals.
"""

from __future__ import annotations

from docir.modules.tags.application.dto import TagView
from docir.modules.tags.application.services.tag_service import TagService

__all__ = ["TagService", "TagView"]
