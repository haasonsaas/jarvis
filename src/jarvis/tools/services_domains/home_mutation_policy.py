"""Policy and validation checks for smart-home mutation preflight."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_domains.home_mutation_policy_guardrails import (
    home_mutation_policy_apply_guardrails,
)
from jarvis.tools.services_domains.home_mutation_policy_validate_identity import (
    home_mutation_policy_validate_identity,
)


async def home_mutation_prepare_policy(
    args: dict[str, Any],
    *,
    start_time: float,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    context, early_response = home_mutation_policy_validate_identity(args, start_time=start_time)
    if early_response is not None:
        return None, early_response
    if context is None:
        return None, None

    return await home_mutation_policy_apply_guardrails(context, start_time=start_time)
