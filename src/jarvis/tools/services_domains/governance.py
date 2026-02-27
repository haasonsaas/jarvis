"""Compatibility exports for governance domain handlers."""

from __future__ import annotations

from jarvis.tools.services_domains.governance_quality import (
    embodiment_presence,
    quality_evaluator,
)
from jarvis.tools.services_domains.governance_skills import (
    skills_disable,
    skills_enable,
    skills_governance,
    skills_list,
    skills_version,
)
from jarvis.tools.services_domains.governance_status import (
    jarvis_scorecard,
    system_status,
    system_status_contract,
)
from jarvis.tools.services_domains.governance_tool_summary import (
    tool_summary,
    tool_summary_text,
)

__all__ = [
    "tool_summary",
    "tool_summary_text",
    "skills_governance",
    "quality_evaluator",
    "embodiment_presence",
    "skills_list",
    "skills_enable",
    "skills_disable",
    "skills_version",
    "system_status",
    "system_status_contract",
    "jarvis_scorecard",
]
