"""Notes capture and Notion bridge helpers for services domains."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import aiohttp

def capture_note(
    services_module: Any,
    *,
    backend: str,
    title: str,
    content: str,
    path_hint: str = "",
) -> dict[str, Any]:
    normalized_backend = str(backend or "local_markdown").strip().lower()
    clean_title = str(title or "jarvis-note").strip() or "jarvis-note"
    clean_content = str(content or "").strip()
    slug = re.sub(r"[^a-z0-9_-]+", "-", clean_title.lower()).strip("-") or "jarvis-note"
    if normalized_backend in {"obsidian", "local_markdown"}:
        base = Path(path_hint).expanduser() if path_hint else services_module._notes_capture_dir
        base.mkdir(parents=True, exist_ok=True)
        file_path = base / f"{slug}.md"
        body = f"# {clean_title}\n\n{clean_content}\n"
        file_path.write_text(body)
        return {
            "backend": normalized_backend,
            "stored": True,
            "path": str(file_path),
        }
    if normalized_backend == "notion":
        return {
            "backend": normalized_backend,
            "stored": False,
            "status": "draft_only",
            "detail": "Notion API bridge is not configured; returning structured draft payload.",
            "title": clean_title,
            "content": clean_content,
        }
    return {
        "backend": normalized_backend,
        "stored": False,
        "status": "unsupported_backend",
    }


def notion_configured(services_module: Any) -> bool:
    return bool(services_module._notion_api_token and services_module._notion_database_id)


async def capture_note_notion(
    services_module: Any,
    *,
    title: str,
    content: str,
) -> tuple[dict[str, Any] | None, str | None]:
    if not notion_configured(services_module):
        return None, "missing_config"
    payload = {
        "parent": {"database_id": services_module._notion_database_id},
        "properties": {
            "title": {
                "title": [
                    {
                        "type": "text",
                        "text": {"content": title[:200]},
                    }
                ]
            }
        },
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": content[:2000]},
                        }
                    ]
                },
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {services_module._notion_api_token}",
        "Notion-Version": services_module.NOTION_API_VERSION,
        "Content-Type": "application/json",
    }
    timeout = aiohttp.ClientTimeout(
        total=services_module._effective_act_timeout(
            services_module._webhook_timeout_sec,
            minimum=1.0,
            maximum=30.0,
        )
    )
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post("https://api.notion.com/v1/pages", headers=headers, json=payload) as resp:
                if resp.status in {200, 201}:
                    try:
                        body = await resp.json()
                    except Exception:
                        return None, "invalid_json"
                    if not isinstance(body, dict):
                        return None, "invalid_json"
                    page_id = str(body.get("id", "")).strip()
                    url = str(body.get("url", "")).strip()
                    if not page_id:
                        return None, "invalid_json"
                    return {
                        "backend": "notion",
                        "stored": True,
                        "status": "created",
                        "page_id": page_id,
                        "url": url,
                    }, None
                if resp.status in {401, 403}:
                    return None, "auth"
                return None, "http_error"
    except asyncio.TimeoutError:
        return None, "timeout"
    except asyncio.CancelledError:
        return None, "cancelled"
    except aiohttp.ClientError:
        return None, "network_client_error"
    except Exception:
        return None, "unexpected"
