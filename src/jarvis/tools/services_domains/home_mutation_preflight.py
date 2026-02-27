"""Smart-home mutation preflight and policy checks."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_domains.home_mutation_policy import home_mutation_prepare_policy
from jarvis.tools.services_domains.home_mutation_state_checks import home_mutation_prepare_state


async def home_mutation_prepare(args: dict[str, Any], *, start_time: float) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    context, early_response = await home_mutation_prepare_policy(args, start_time=start_time)
    if early_response is not None:
        return None, early_response
    if context is None:
        return None, None

    return await home_mutation_prepare_state(context, start_time=start_time)
