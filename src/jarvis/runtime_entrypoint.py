"""Entrypoint orchestration helpers for Jarvis CLI runtime."""

from __future__ import annotations

import asyncio
import json
import signal
from contextlib import suppress
from typing import Any, Callable


def maybe_run_backup_or_restore(
    args: Any,
    *,
    config_class: Callable[[], Any],
    create_backup_bundle_fn: Callable[[Any, str], dict[str, Any]],
    restore_backup_bundle_fn: Callable[[Any, str], dict[str, Any]],
) -> bool:
    if not (args.backup or args.restore):
        return False
    config = config_class()
    try:
        if args.backup:
            result = create_backup_bundle_fn(config, args.backup)
        else:
            result = restore_backup_bundle_fn(config, args.restore, overwrite=bool(args.force))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        raise SystemExit(1) from exc
    print(json.dumps(result, indent=2))
    return True


def run_jarvis_event_loop(jarvis: Any) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task = loop.create_task(jarvis.run())

    def shutdown(sig, frame):
        task.cancel()

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)

    try:
        loop.run_until_complete(task)
    finally:
        with suppress(Exception):
            loop.run_until_complete(loop.shutdown_asyncgens())
        with suppress(Exception):
            loop.run_until_complete(loop.shutdown_default_executor())
        loop.close()
