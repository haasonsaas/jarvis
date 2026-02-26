"""Shared tool error taxonomy used across services and telemetry."""

from __future__ import annotations

TOOL_SERVICE_ERROR_CODES: set[str] = {
    "policy",
    "missing_config",
    "missing_fields",
    "invalid_data",
    "timeout",
    "cancelled",
    "network_client_error",
    "invalid_json",
    "api_error",
    "auth",
    "not_found",
    "unexpected",
    "storage_error",
    "missing_store",
    "missing_text",
    "missing_query",
    "missing_entity",
    "missing_plan",
    "invalid_plan",
    "invalid_status",
    "invalid_steps",
    "http_error",
    "summary_unavailable",
    "unknown_error",
}
TOOL_STORAGE_ERROR_DETAILS: set[str] = {
    "storage_error",
    "missing_store",
}


def normalize_service_error_code(code: str) -> str:
    return code if code in TOOL_SERVICE_ERROR_CODES else "unknown_error"
