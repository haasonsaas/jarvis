"""Reachy Mini app wrapper for the Jarvis runtime."""

from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextlib import suppress
import importlib.util
import threading
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field
from reachy_mini import ReachyMini, ReachyMiniApp

from jarvis.__main__ import Jarvis as JarvisRuntime
from jarvis.__main__ import parse_args


class ControlRequest(BaseModel):
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)


class Jarvis(ReachyMiniApp):
    """Reachy Mini dashboard app entrypoint for Jarvis."""

    custom_app_url: str | None = "http://0.0.0.0:8042"
    request_media_backend: str | None = None

    def __init__(self, running_on_wireless: bool = False) -> None:
        super().__init__(running_on_wireless=running_on_wireless)
        self._runtime: JarvisRuntime | None = None
        self._runtime_loop: asyncio.AbstractEventLoop | None = None
        if self.settings_app is not None:
            self._register_settings_routes()

    def _register_settings_routes(self) -> None:
        assert self.settings_app is not None

        @self.settings_app.get("/api/health")
        async def health() -> dict[str, Any]:
            return {
                "ok": True,
                "running": self._runtime is not None,
                "stop_requested": self.stop_event.is_set(),
            }

        @self.settings_app.get("/api/control-schema")
        async def control_schema() -> dict[str, Any]:
            runtime = self._runtime
            if runtime is None:
                return {"ok": False, "message": "Jarvis runtime is not ready."}
            return {
                "ok": True,
                "schema": runtime._operator_control_schema(),
                "available_actions": runtime._operator_available_actions(),
            }

        @self.settings_app.get("/api/status")
        async def status() -> dict[str, Any]:
            runtime = self._runtime
            readiness_state = self._readiness_state(runtime)
            if runtime is None:
                return {
                    "ok": False,
                    "state": readiness_state,
                    "message": "Jarvis runtime is not ready.",
                    "app_readiness": {
                        "state": readiness_state,
                        "summary_lines": [],
                        "diagnostics": [],
                        "blockers": [],
                        "capabilities": self._capability_snapshot(None),
                    },
                }
            payload = self._run_on_runtime_loop(
                runtime._operator_status_provider(),
                timeout=10.0,
            )
            if not isinstance(payload, dict):
                return {"ok": False, "message": "Invalid runtime status payload."}
            blockers = runtime._startup_blockers()
            diagnostics = runtime._startup_diagnostics_provider()
            payload["app_readiness"] = {
                "state": self._readiness_state(
                    runtime,
                    blockers=blockers,
                    diagnostics=diagnostics,
                ),
                "summary_lines": runtime._startup_summary_lines(),
                "diagnostics": diagnostics,
                "blockers": blockers,
                "capabilities": self._capability_snapshot(runtime),
            }
            payload["ok"] = True
            return payload

        @self.settings_app.post("/api/control")
        async def control(request: ControlRequest) -> dict[str, Any]:
            runtime = self._runtime
            if runtime is None:
                raise HTTPException(status_code=503, detail="Jarvis runtime is not ready.")
            return self._run_on_runtime_loop(
                runtime._operator_control_handler(request.action, request.payload),
                timeout=15.0,
            )

        @self.settings_app.post("/api/stop")
        async def stop_app() -> dict[str, Any]:
            self.stop()
            return {"ok": True, "message": "Stop requested."}

    def _run_on_runtime_loop(self, coro: Any, *, timeout: float) -> Any:
        loop = self._runtime_loop
        if loop is None or not loop.is_running():
            raise HTTPException(status_code=503, detail="Jarvis runtime loop is not available.")
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            raise HTTPException(status_code=504, detail="Jarvis runtime request timed out.") from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    def _readiness_state(
        self,
        runtime: JarvisRuntime | None,
        *,
        blockers: list[str] | None = None,
        diagnostics: list[str] | None = None,
    ) -> str:
        if runtime is None:
            return "stopping" if self.stop_event.is_set() else "starting"
        if self.stop_event.is_set():
            return "stopping"
        if blockers is None:
            blockers = runtime._startup_blockers()
        if blockers:
            return "blocked"
        if diagnostics is None:
            diagnostics = runtime._startup_diagnostics_provider()
        if diagnostics:
            return "degraded"
        return "running"

    def _capability_snapshot(self, runtime: JarvisRuntime | None) -> dict[str, Any]:
        config = getattr(runtime, "config", None)
        args = getattr(runtime, "args", None)
        return {
            "vision_stack_available": importlib.util.find_spec("ultralytics") is not None,
            "local_audio_stack_available": importlib.util.find_spec("sounddevice") is not None,
            "tts_configured": bool(getattr(config, "elevenlabs_api_key", "")) if config is not None else False,
            "tts_runtime_enabled": bool(getattr(runtime, "tts", None)) if runtime is not None else False,
            "vision_requested": not bool(getattr(args, "no_vision", False)) if args is not None else False,
            "hand_tracking_requested": bool(getattr(config, "hand_track_enabled", False)) if config is not None else False,
            "motion_enabled": bool(getattr(config, "motion_enabled", False)) if config is not None else False,
            "home_enabled": bool(getattr(config, "home_enabled", False)) if config is not None else False,
            "operator_server_embedded": False,
            "settings_ui_available": self.settings_app is not None,
            "space_url": "https://huggingface.co/spaces/EvalOps/jarvis",
            "release_notes_path": "CHANGELOG.md",
            "smoke_test_runbook": "docs/operations/reachy-app-smoke-test.md",
        }

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event) -> None:
        args = parse_args([])
        runtime = JarvisRuntime(
            args,
            reachy_mini=reachy_mini,
            operator_server_enabled=False,
        )
        loop = asyncio.new_event_loop()
        self._runtime = runtime
        self._runtime_loop = loop
        asyncio.set_event_loop(loop)
        task = loop.create_task(runtime.run())

        def cancel_when_stopped() -> None:
            stop_event.wait()
            if task.done():
                return
            loop.call_soon_threadsafe(task.cancel)

        stopper = threading.Thread(
            target=cancel_when_stopped,
            daemon=True,
            name="jarvis-app-stop-watcher",
        )
        stopper.start()

        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass
        finally:
            self._runtime_loop = None
            self._runtime = None
            with suppress(Exception):
                loop.run_until_complete(loop.shutdown_asyncgens())
            with suppress(Exception):
                loop.run_until_complete(loop.shutdown_default_executor())
            asyncio.set_event_loop(None)
            loop.close()
            stopper.join(timeout=1.0)


if __name__ == "__main__":
    app = Jarvis()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
