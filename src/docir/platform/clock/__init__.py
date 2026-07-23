"""Clock capability: the :class:`Clock` port and its system implementation."""

from docir.platform.clock.port import Clock
from docir.platform.clock.system import SystemClock

__all__ = ["Clock", "SystemClock"]
