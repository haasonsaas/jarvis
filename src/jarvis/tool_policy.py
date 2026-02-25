from __future__ import annotations

import fnmatch


def _normalize(name: str) -> str:
    return name.strip().lower()


def _matches(name: str, patterns: list[str]) -> bool:
    if not patterns:
        return False
    normalized = _normalize(name)
    for pattern in patterns:
        if fnmatch.fnmatchcase(normalized, _normalize(pattern)):
            return True
    return False


def is_tool_allowed(name: str, allow: list[str], deny: list[str]) -> bool:
    if _matches(name, deny):
        return False
    if not allow:
        return True
    return _matches(name, allow)


def filter_allowed_tools(tools: list[str], allow: list[str], deny: list[str]) -> list[str]:
    return [tool for tool in tools if is_tool_allowed(tool, allow, deny)]
