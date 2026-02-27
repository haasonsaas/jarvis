"""System status contract field definitions and payload helper."""

from __future__ import annotations

import copy
from typing import Any

from jarvis.tools.services_governance_contract_core_fields import (
    SYSTEM_STATUS_CONTRACT_CORE_FIELDS,
)
from jarvis.tools.services_governance_contract_expansion_fields import (
    SYSTEM_STATUS_CONTRACT_EXPANSION_FIELDS,
)
from jarvis.tools.services_governance_contract_operational_fields import (
    SYSTEM_STATUS_CONTRACT_OPERATIONAL_FIELDS,
)

_SYSTEM_STATUS_CONTRACT_FIELDS: dict[str, Any] = {
    **SYSTEM_STATUS_CONTRACT_CORE_FIELDS,
    **SYSTEM_STATUS_CONTRACT_OPERATIONAL_FIELDS,
    **SYSTEM_STATUS_CONTRACT_EXPANSION_FIELDS,
}


def system_status_contract_payload(*, schema_version: str) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        **copy.deepcopy(_SYSTEM_STATUS_CONTRACT_FIELDS),
    }
