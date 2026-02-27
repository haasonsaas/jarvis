"""Service tool schemas and runtime required-field contracts."""

from __future__ import annotations

from typing import Any

from jarvis.tools.service_schemas_advanced import SERVICE_TOOL_SCHEMAS_ADVANCED
from jarvis.tools.service_schemas_comms import SERVICE_TOOL_SCHEMAS_COMMS
from jarvis.tools.service_schemas_home import SERVICE_TOOL_SCHEMAS_HOME
from jarvis.tools.service_schemas_memory import SERVICE_TOOL_SCHEMAS_MEMORY

SERVICE_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    **SERVICE_TOOL_SCHEMAS_HOME,
    **SERVICE_TOOL_SCHEMAS_COMMS,
    **SERVICE_TOOL_SCHEMAS_MEMORY,
    **SERVICE_TOOL_SCHEMAS_ADVANCED,
}


def _schema_required_fields(schema: dict[str, Any]) -> set[str]:
    required = schema.get("required")
    if not isinstance(required, list):
        return set()
    fields: set[str] = set()
    for item in required:
        text = str(item).strip()
        if text:
            fields.add(text)
    return fields


SERVICE_RUNTIME_REQUIRED_FIELDS: dict[str, set[str]] = {
    name: _schema_required_fields(schema)
    for name, schema in SERVICE_TOOL_SCHEMAS.items()
}
