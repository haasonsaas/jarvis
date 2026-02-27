from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiohttp import web

from jarvis.tool_summary import list_summaries
from jarvis.tools.services import AUDIT_LOG, decode_audit_entry_line


def _dashboard_html() -> str:
    return """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Jarvis Operator Console</title>
  <style>
    :root {
      --bg: radial-gradient(circle at 20% 0%, #f4efe2, #d7dde8 52%, #c5cde0);
      --panel: rgba(255,255,255,0.72);
      --ink: #101820;
      --accent: #1f6f8b;
      --danger: #8b1f3a;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: 'Avenir Next', 'Segoe UI', sans-serif;
      color: var(--ink);
      background: var(--bg);
      padding: 20px;
    }
    .grid { display: grid; grid-template-columns: 1.2fr 1fr; gap: 16px; }
    .card {
      background: var(--panel);
      backdrop-filter: blur(8px);
      border: 1px solid rgba(16, 24, 32, 0.12);
      border-radius: 16px;
      padding: 14px;
      box-shadow: 0 12px 24px rgba(16, 24, 32, 0.08);
    }
    h1 { margin: 0 0 10px; font-size: 1.35rem; letter-spacing: 0.02em; }
    h2 { margin: 0 0 10px; font-size: 1rem; text-transform: uppercase; letter-spacing: 0.08em; }
    button {
      border: 0;
      border-radius: 999px;
      background: var(--accent);
      color: #fff;
      padding: 8px 12px;
      margin: 4px;
      cursor: pointer;
    }
    button[data-danger=\"true\"] { background: var(--danger); }
    pre {
      margin: 0;
      white-space: pre-wrap;
      font-size: 0.82rem;
      line-height: 1.4;
      max-height: 280px;
      overflow: auto;
    }
    @media (max-width: 920px) {
      .grid { grid-template-columns: 1fr; }
      body { padding: 12px; }
    }
  </style>
</head>
<body>
  <h1>Jarvis Operator Console</h1>
  <div class=\"grid\">
    <section class=\"card\">
      <h2>Runtime Status</h2>
      <pre id=\"status\">loading...</pre>
    </section>
    <section class=\"card\">
      <h2>Quick Controls</h2>
      <div>
        <button onclick=\"control('set_wake_mode',{mode:'always_listening'})\">Always Listening</button>
        <button onclick=\"control('set_wake_mode',{mode:'wake_word'})\">Wake Word</button>
        <button onclick=\"control('set_wake_mode',{mode:'push_to_talk'})\">Push-to-Talk</button>
      </div>
      <div>
        <button onclick=\"control('set_timeout_profile',{profile:'short'})\">Timeout Short</button>
        <button onclick=\"control('set_timeout_profile',{profile:'normal'})\">Timeout Normal</button>
        <button onclick=\"control('set_timeout_profile',{profile:'long'})\">Timeout Long</button>
      </div>
      <div>
        <button onclick=\"control('set_push_to_talk',{active:true})\">PTT On</button>
        <button onclick=\"control('set_push_to_talk',{active:false})\">PTT Off</button>
      </div>
      <div>
        <button onclick=\"control('set_motion_enabled',{enabled:true})\">Motion On</button>
        <button onclick=\"control('set_motion_enabled',{enabled:false})\">Motion Off</button>
      </div>
      <div>
        <button onclick=\"control('set_home_enabled',{enabled:true})\">Home On</button>
        <button onclick=\"control('set_home_enabled',{enabled:false})\">Home Off</button>
      </div>
      <div>
        <button onclick=\"control('set_tts_enabled',{enabled:true})\">TTS On</button>
        <button onclick=\"control('set_tts_enabled',{enabled:false})\">TTS Off</button>
      </div>
      <div>
        <button onclick=\"control('skills_reload',{})\">Reload Skills</button>
      </div>
      <div>
        <button data-danger=\"true\" onclick=\"control('clear_inbound_webhooks',{})\">Clear Inbound Webhooks</button>
      </div>
      <pre id=\"control-result\">ready</pre>
    </section>
    <section class=\"card\">
      <h2>Tool Outcomes</h2>
      <pre id=\"tools\">loading...</pre>
    </section>
    <section class=\"card\">
      <h2>Startup Diagnostics</h2>
      <pre id=\"startup\">loading...</pre>
    </section>
    <section class=\"card\">
      <h2>Audit Preview</h2>
      <pre id=\"audit\">loading...</pre>
    </section>
    <section class=\"card\">
      <h2>Operator Actions</h2>
      <pre id=\"actions\">loading...</pre>
    </section>
  </div>
  <script>
    async function json(url, opts) {
      const res = await fetch(url, opts || {});
      if (!res.ok) throw new Error(`${url}: ${res.status}`);
      return await res.json();
    }
    async function refresh() {
      try {
        const [status, tools, startup, audit, actions] = await Promise.all([
          json('/api/status'),
          json('/api/tools/recent?limit=20'),
          json('/api/startup-diagnostics'),
          json('/api/audit?limit=20'),
          json('/api/operator-actions?limit=20'),
        ]);
        document.getElementById('status').textContent = JSON.stringify(status, null, 2);
        document.getElementById('tools').textContent = JSON.stringify(tools, null, 2);
        document.getElementById('startup').textContent = JSON.stringify(startup, null, 2);
        document.getElementById('audit').textContent = JSON.stringify(audit, null, 2);
        document.getElementById('actions').textContent = JSON.stringify(actions, null, 2);
      } catch (err) {
        document.getElementById('status').textContent = String(err);
      }
    }
    async function control(action, payload) {
      try {
        const result = await json('/api/control', {
          method: 'POST',
          headers: {'content-type': 'application/json'},
          body: JSON.stringify({action, payload}),
        });
        document.getElementById('control-result').textContent = JSON.stringify(result, null, 2);
        await refresh();
      } catch (err) {
        document.getElementById('control-result').textContent = String(err);
      }
    }
    refresh();
    setInterval(refresh, 4000);
  </script>
</body>
</html>
"""


class OperatorServer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        status_provider: Callable[[], Awaitable[dict[str, Any]]],
        diagnostics_provider: Callable[[], list[str]],
        control_handler: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
        metrics_provider: Callable[[], str],
        events_provider: Callable[[], list[dict[str, Any]]],
        inbound_callback: Callable[[Any, dict[str, Any], str, str], int],
        inbound_enabled: bool,
        inbound_token: str,
    ) -> None:
        self._host = host
        self._port = int(port)
        self._status_provider = status_provider
        self._diagnostics_provider = diagnostics_provider
        self._control_handler = control_handler
        self._metrics_provider = metrics_provider
        self._events_provider = events_provider
        self._inbound_callback = inbound_callback
        self._inbound_enabled = bool(inbound_enabled)
        self._inbound_token = str(inbound_token).strip()
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._actions: list[dict[str, Any]] = []

    async def start(self) -> None:
        if self._runner is not None:
            return
        app = web.Application()
        app.router.add_get("/", self._handle_dashboard)
        app.router.add_get("/api/status", self._handle_status)
        app.router.add_get("/api/tools/recent", self._handle_recent_tools)
        app.router.add_get("/api/audit", self._handle_audit)
        app.router.add_get("/api/startup-diagnostics", self._handle_startup_diagnostics)
        app.router.add_get("/api/operator-actions", self._handle_operator_actions)
        app.router.add_post("/api/control", self._handle_control)
        app.router.add_get("/metrics", self._handle_metrics)
        app.router.add_get("/events", self._handle_events)
        app.router.add_post("/api/webhook/inbound", self._handle_inbound_webhook)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host=self._host, port=self._port)
        await self._site.start()

    async def stop(self) -> None:
        if self._runner is None:
            return
        await self._runner.cleanup()
        self._runner = None
        self._site = None

    async def _handle_dashboard(self, request: web.Request) -> web.Response:
        return web.Response(text=_dashboard_html(), content_type="text/html")

    async def _handle_status(self, request: web.Request) -> web.Response:
        return web.json_response(await self._status_provider())

    async def _handle_recent_tools(self, request: web.Request) -> web.Response:
        try:
            limit = int(request.query.get("limit", "20"))
        except ValueError:
            limit = 20
        limit = max(1, min(200, limit))
        return web.json_response(list_summaries(limit=limit))

    async def _handle_audit(self, request: web.Request) -> web.Response:
        try:
            limit = int(request.query.get("limit", "20"))
        except ValueError:
            limit = 20
        limit = max(1, min(200, limit))
        entries: list[dict[str, Any]] = []
        path = Path(AUDIT_LOG)
        if path.exists():
            try:
                lines = path.read_text().splitlines()
            except OSError:
                lines = []
            for line in reversed(lines):
                if not line.strip():
                    continue
                payload = decode_audit_entry_line(line)
                if payload is None:
                    continue
                entries.append(payload)
                if len(entries) >= limit:
                    break
        return web.json_response(entries)

    async def _handle_startup_diagnostics(self, request: web.Request) -> web.Response:
        return web.json_response({"warnings": self._diagnostics_provider()})

    async def _handle_operator_actions(self, request: web.Request) -> web.Response:
        try:
            limit = int(request.query.get("limit", "20"))
        except ValueError:
            limit = 20
        limit = max(1, min(200, limit))
        return web.json_response(list(reversed(self._actions))[:limit])

    async def _handle_control(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid_json"}, status=400)
        action = str(body.get("action", "")).strip()
        payload = body.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        result = await self._control_handler(action, payload)
        log_item = {
            "timestamp": time.time(),
            "action": action,
            "payload": payload,
            "result": result,
            "source": request.remote or "operator",
        }
        self._actions.append(log_item)
        if len(self._actions) > 500:
            del self._actions[:-500]
        return web.json_response(result)

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        return web.Response(text=self._metrics_provider(), content_type="text/plain")

    async def _handle_events(self, request: web.Request) -> web.StreamResponse:
        try:
            timeout_sec = float(request.query.get("timeout_sec", "10"))
        except ValueError:
            timeout_sec = 10.0
        timeout_sec = max(0.5, min(30.0, timeout_sec))
        response = web.StreamResponse(
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        await response.prepare(request)
        start = time.monotonic()
        sent = 0
        while (time.monotonic() - start) < timeout_sec:
            events = self._events_provider()
            if sent < len(events):
                for item in events[sent:]:
                    payload = json.dumps(item, default=str)
                    await response.write(f"event: runtime\ndata: {payload}\n\n".encode("utf-8"))
                sent = len(events)
            else:
                await response.write(b": keepalive\n\n")
            await asyncio.sleep(0.5)
        await response.write_eof()
        return response

    async def _handle_inbound_webhook(self, request: web.Request) -> web.Response:
        if not self._inbound_enabled:
            raise web.HTTPNotFound()
        provided_token = (
            request.headers.get("X-Webhook-Token", "").strip()
            or request.query.get("token", "").strip()
            or request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        )
        if self._inbound_token and provided_token != self._inbound_token:
            raise web.HTTPForbidden(text="invalid token")
        try:
            payload = await request.json()
        except Exception:
            payload = {"raw": await request.text()}
        headers = {key: value for key, value in request.headers.items()}
        event_id = self._inbound_callback(payload, headers, str(request.path), str(request.remote or "unknown"))
        return web.json_response({"ok": True, "event_id": event_id})
