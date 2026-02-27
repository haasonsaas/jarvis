"""Compatibility exports for trust memory domain handlers."""

from __future__ import annotations

from jarvis.tools.services_domains.trust_memory_governance import memory_governance
from jarvis.tools.services_domains.trust_memory_ops import (
    memory_add,
    memory_forget,
    memory_update,
)
from jarvis.tools.services_domains.trust_memory_query import (
    memory_recent,
    memory_search,
    memory_status,
)
from jarvis.tools.services_domains.trust_memory_summary import (
    memory_summary_add,
    memory_summary_list,
)

__all__ = [
    "memory_add",
    "memory_update",
    "memory_forget",
    "memory_search",
    "memory_status",
    "memory_recent",
    "memory_summary_add",
    "memory_summary_list",
    "memory_governance",
]
