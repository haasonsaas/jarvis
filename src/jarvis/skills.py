from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_VALID_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


@dataclass
class SkillRecord:
    name: str
    version: str
    description: str
    namespace: str
    capabilities: list[str]
    allowed_network_domains: list[str]
    allowed_paths: list[str]
    signed: bool
    signature_valid: bool
    enabled: bool
    status: str
    source_path: str
    load_error: str | None = None
    loaded_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "namespace": self.namespace,
            "capabilities": list(self.capabilities),
            "allowed_network_domains": list(self.allowed_network_domains),
            "allowed_paths": list(self.allowed_paths),
            "signed": self.signed,
            "signature_valid": self.signature_valid,
            "enabled": self.enabled,
            "status": self.status,
            "source_path": self.source_path,
            "load_error": self.load_error,
            "loaded_at": self.loaded_at,
        }


class SkillRegistry:
    """Discovers and governs local skill manifests.

    Manifests are expected at <skills_dir>/<skill_name>/skill.json.
    """

    def __init__(
        self,
        *,
        skills_dir: str,
        allowlist: list[str] | None = None,
        require_signature: bool = False,
        signature_key: str = "",
        enabled: bool = True,
        state_path: str | None = None,
    ) -> None:
        self._skills_dir = Path(skills_dir).expanduser()
        self._allowlist = {
            item.strip().lower()
            for item in (allowlist or [])
            if item and item.strip()
        }
        self._require_signature = bool(require_signature)
        self._signature_key = str(signature_key)
        self._enabled = bool(enabled)
        self._records: dict[str, SkillRecord] = {}
        self._errors: list[dict[str, Any]] = []
        self._state_path = Path(state_path).expanduser() if state_path else self._skills_dir / ".state.json"
        self._enabled_overrides: dict[str, bool] = {}
        self._load_state()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def discover(self) -> dict[str, Any]:
        self._records.clear()
        self._errors.clear()

        if not self._enabled:
            return self.status_snapshot()

        self._skills_dir.mkdir(parents=True, exist_ok=True)
        names_seen: set[str] = set()

        for entry in sorted(self._skills_dir.iterdir(), key=lambda p: p.name.lower()):
            if not entry.is_dir():
                continue
            manifest_path = entry / "skill.json"
            if not manifest_path.exists():
                continue
            record = self._load_manifest(manifest_path)
            if record.name in names_seen:
                self._errors.append({
                    "path": str(manifest_path),
                    "error": "duplicate_skill_name",
                    "name": record.name,
                })
                continue
            names_seen.add(record.name)
            self._records[record.name] = record

        self._persist_state()
        return self.status_snapshot()

    def _load_manifest(self, manifest_path: Path) -> SkillRecord:
        loaded_at = time.time()
        try:
            raw = json.loads(manifest_path.read_text())
            if not isinstance(raw, dict):
                raise ValueError("manifest must be an object")
        except Exception as exc:
            return SkillRecord(
                name=manifest_path.parent.name.lower(),
                version="0.0.0",
                description="",
                namespace=f"skill.{manifest_path.parent.name.lower()}",
                capabilities=[],
                allowed_network_domains=[],
                allowed_paths=[],
                signed=False,
                signature_valid=False,
                enabled=False,
                status="error",
                source_path=str(manifest_path),
                load_error=f"invalid_manifest:{exc}",
                loaded_at=loaded_at,
            )

        name = str(raw.get("name", manifest_path.parent.name)).strip().lower()
        version = str(raw.get("version", "0.0.0")).strip() or "0.0.0"
        description = str(raw.get("description", "")).strip()
        namespace = str(raw.get("namespace", f"skill.{name}")).strip().lower()
        capabilities = self._normalize_str_list(raw.get("capabilities"))
        allowed_network_domains = self._normalize_str_list(raw.get("allowed_network_domains"))
        allowed_paths = self._normalize_str_list(raw.get("allowed_paths"))
        signature = str(raw.get("signature", "")).strip()

        valid_name = bool(_VALID_NAME_RE.match(name))
        namespace_ok = namespace.startswith("skill.") and len(namespace.split(".")) >= 2
        namespace_owner_ok = namespace.split(".")[1] == name if namespace_ok else False

        signature_valid = self._verify_signature(
            name=name,
            version=version,
            namespace=namespace,
            capabilities=capabilities,
            signature=signature,
        )

        status = "loaded"
        load_error = None

        if not valid_name:
            status = "error"
            load_error = "invalid_name"
        elif not namespace_ok:
            status = "error"
            load_error = "invalid_namespace"
        elif not namespace_owner_ok:
            status = "error"
            load_error = "namespace_mismatch"
        elif self._allowlist and name not in self._allowlist:
            status = "blocked"
            load_error = "not_allowlisted"
        elif self._require_signature and not signature_valid:
            status = "blocked"
            load_error = "invalid_signature"

        enabled = self._enabled_overrides.get(name, status == "loaded")
        if status != "loaded":
            enabled = False

        return SkillRecord(
            name=name,
            version=version,
            description=description,
            namespace=namespace,
            capabilities=capabilities,
            allowed_network_domains=allowed_network_domains,
            allowed_paths=allowed_paths,
            signed=bool(signature),
            signature_valid=signature_valid,
            enabled=enabled,
            status=status,
            source_path=str(manifest_path),
            load_error=load_error,
            loaded_at=loaded_at,
        )

    def _verify_signature(
        self,
        *,
        name: str,
        version: str,
        namespace: str,
        capabilities: list[str],
        signature: str,
    ) -> bool:
        if not signature:
            return False
        if not self._signature_key:
            return False
        payload = "|".join([
            name,
            version,
            namespace,
            ",".join(capabilities),
        ]).encode("utf-8")
        expected = hmac.new(self._signature_key.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    @staticmethod
    def _normalize_str_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        items: list[str] = []
        for item in value:
            text = str(item).strip()
            if not text:
                continue
            items.append(text)
        return items

    def list_records(self) -> list[dict[str, Any]]:
        return [record.as_dict() for _, record in sorted(self._records.items(), key=lambda kv: kv[0])]

    def enable_skill(self, name: str) -> tuple[bool, str]:
        key = str(name).strip().lower()
        record = self._records.get(key)
        if record is None:
            return False, "skill_not_found"
        if record.status != "loaded":
            return False, record.load_error or "skill_not_loadable"
        record.enabled = True
        self._enabled_overrides[key] = True
        self._persist_state()
        return True, "enabled"

    def disable_skill(self, name: str) -> tuple[bool, str]:
        key = str(name).strip().lower()
        record = self._records.get(key)
        if record is None:
            return False, "skill_not_found"
        record.enabled = False
        self._enabled_overrides[key] = False
        self._persist_state()
        return True, "disabled"

    def skill_version(self, name: str) -> str | None:
        key = str(name).strip().lower()
        record = self._records.get(key)
        if record is None:
            return None
        return record.version

    def status_snapshot(self) -> dict[str, Any]:
        records = self.list_records()
        loaded = [item for item in records if item.get("status") == "loaded"]
        enabled = [item for item in loaded if item.get("enabled")]
        blocked = [item for item in records if item.get("status") == "blocked"]
        errored = [item for item in records if item.get("status") == "error"]
        return {
            "enabled": self._enabled,
            "skills_dir": str(self._skills_dir),
            "loaded_count": len(loaded),
            "enabled_count": len(enabled),
            "blocked_count": len(blocked),
            "error_count": len(errored),
            "require_signature": self._require_signature,
            "allowlist_count": len(self._allowlist),
            "skills": records,
            "load_errors": list(self._errors),
        }

    def _load_state(self) -> None:
        path = self._state_path
        if not path.exists():
            self._enabled_overrides = {}
            return
        try:
            payload = json.loads(path.read_text())
        except Exception:
            self._enabled_overrides = {}
            return
        raw = payload.get("enabled") if isinstance(payload, dict) else None
        if not isinstance(raw, dict):
            self._enabled_overrides = {}
            return
        parsed: dict[str, bool] = {}
        for key, value in raw.items():
            name = str(key).strip().lower()
            if not name:
                continue
            parsed[name] = bool(value)
        self._enabled_overrides = parsed

    def _persist_state(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "enabled": {name: enabled for name, enabled in sorted(self._enabled_overrides.items())},
        }
        self._state_path.write_text(json.dumps(payload, indent=2))
