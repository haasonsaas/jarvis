from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    ("module_name", "blocked_module"),
    [
        ("jarvis.tools.services_domains.planner_runtime", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.integrations_runtime", "jarvis.tools.services"),
        ("jarvis.runtime_telemetry", "jarvis.__main__"),
        ("jarvis.runtime_state", "jarvis.__main__"),
        ("jarvis.runtime_startup", "jarvis.__main__"),
        ("jarvis.runtime_voice_profile", "jarvis.__main__"),
        ("jarvis.runtime_operator_status", "jarvis.__main__"),
        ("jarvis.runtime_conversation", "jarvis.__main__"),
        ("jarvis.runtime_preferences", "jarvis.__main__"),
        ("jarvis.runtime_multimodal", "jarvis.__main__"),
        ("jarvis.tools.services_proactive_runtime", "jarvis.tools.services"),
        ("jarvis.tools.services_governance_runtime", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.trust_memory", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.trust_identity", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.home_state", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.home_orchestrator", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.home_orch_plan_exec", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.home_orch_automation", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.home_orch_tasks", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.home_control", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.home_mutation", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.home_mutation_preflight", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.home_mutation_execute", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.home_ha_tools", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.home_ha_conversation", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.home_ha_todo", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.home_ha_timer", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.home_ha_area_media", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.home_area_entities_tool", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.home_media_control_tool", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.comms_notifications", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.comms_notify_webhooks", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.comms_notify_pushover", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.comms_email", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.comms_todoist", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.comms_todoist_add", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.comms_todoist_list", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.governance_tool_summary", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.governance_skills", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.governance_skills_governance", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.governance_skills_registry", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.governance_quality", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.governance_status", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.integrations_hub", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.integrations_hub_calendar_notes", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.integrations_hub_messaging", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.integrations_hub_release_channels", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.integrations_ops", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.integrations_weather", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.integrations_webhook", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.integrations_calendar", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.integrations_deadletter", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.planner_engine_domain", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.planner_engine_plan_graph", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.planner_engine_deferred", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.planner_engine_autonomy", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.planner_schedule", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.planner_timers", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.planner_reminders", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.planner_reminders_crud", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.planner_reminders_notify", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.planner_taskplan", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.trust_memory_ops", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.trust_memory_query", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.trust_memory_summary", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.trust_memory_governance", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.trust_proactive_briefing", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.trust_proactive_nudges", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.trust_proactive_anomaly", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.trust_proactive_nudge_decision", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.trust_proactive_followthrough", "jarvis.tools.services"),
    ],
)
def test_runtime_module_import_boundary(module_name: str, blocked_module: str) -> None:
    code = (
        "import importlib, sys;"
        f"importlib.import_module('{module_name}');"
        f"print('loaded=' + str('{blocked_module}' in sys.modules))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "loaded=False" in proc.stdout.strip()
