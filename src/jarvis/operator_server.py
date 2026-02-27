from __future__ import annotations

import asyncio
import hmac
import json
import time
from collections import deque
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiohttp import web

from jarvis.tool_summary import list_summaries
from jarvis.tools.services import AUDIT_LOG, decode_audit_entry_line

_ACTION_REDACT_TOKENS = {
    "token",
    "secret",
    "password",
    "authorization",
    "api_key",
    "code",
}
_ACTION_MAX_STRING_CHARS = 512
_AUDIT_TAIL_SCAN_MULTIPLIER = 6


def _extract_bearer_token(header_value: str | None) -> str:
    if not header_value:
        return ""
    value = str(header_value).strip()
    if not value:
        return ""
    prefix = "bearer "
    if value.lower().startswith(prefix):
        return value[len(prefix):].strip()
    return ""


def _secure_token_match(expected: str, provided: str) -> bool:
    if not expected:
        return False
    if not provided:
        return False
    return hmac.compare_digest(expected, provided)


def _read_tail_lines(path: Path, *, limit: int) -> list[str]:
    if limit <= 0:
        return []
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            recent = deque(maxlen=max(limit * _AUDIT_TAIL_SCAN_MULTIPLIER, limit))
            for line in handle:
                text = line.strip()
                if text:
                    recent.append(text)
    except OSError:
        return []
    return list(recent)


def _sanitize_action_value(value: Any, *, key_hint: str | None = None, depth: int = 0) -> Any:
    if depth > 6:
        return "<max_depth>"
    if key_hint:
        lowered = key_hint.strip().lower()
        if any(token in lowered for token in _ACTION_REDACT_TOKENS):
            return "***REDACTED***"
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= 80:
                sanitized["<truncated_keys>"] = max(0, len(value) - 80)
                break
            key_text = str(key)
            sanitized[key_text] = _sanitize_action_value(item, key_hint=key_text, depth=depth + 1)
        return sanitized
    if isinstance(value, list):
        limited = value[:80]
        out = [_sanitize_action_value(item, key_hint=key_hint, depth=depth + 1) for item in limited]
        if len(value) > 80:
            out.append(f"<truncated_items:{len(value) - 80}>")
        return out
    if isinstance(value, str):
        if len(value) > _ACTION_MAX_STRING_CHARS:
            return value[:_ACTION_MAX_STRING_CHARS] + "...<truncated>"
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    text = str(value)
    if len(text) > _ACTION_MAX_STRING_CHARS:
        return text[:_ACTION_MAX_STRING_CHARS] + "...<truncated>"
    return text


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
      <h2>STT Confidence</h2>
      <pre id=\"stt\">loading...</pre>
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
        <button onclick=\"control('set_sleeping',{sleeping:true})\">Sleep</button>
        <button onclick=\"control('set_sleeping',{sleeping:false})\">Wake</button>
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
        <button onclick=\"control('set_persona_style',{style:'terse'})\">Persona Terse</button>
        <button onclick=\"control('set_persona_style',{style:'composed'})\">Persona Composed</button>
        <button onclick=\"control('set_persona_style',{style:'friendly'})\">Persona Friendly</button>
      </div>
      <div>
        <button onclick=\"control('set_backchannel_style',{style:'quiet'})\">Backchannel Quiet</button>
        <button onclick=\"control('set_backchannel_style',{style:'balanced'})\">Backchannel Balanced</button>
        <button onclick=\"control('set_backchannel_style',{style:'expressive'})\">Backchannel Expressive</button>
      </div>
      <div>
        <button onclick=\"control('preview_personality',{persona_style:'friendly',backchannel_style:'expressive'})\">Preview Friendly+</button>
        <button onclick=\"control('preview_personality',{persona_style:'terse',backchannel_style:'quiet'})\">Preview Terse+</button>
      </div>
      <div>
        <button onclick=\"control('commit_personality_preview',{})\">Commit Preview</button>
        <button data-danger=\"true\" onclick=\"control('rollback_personality_preview',{})\">Rollback Preview</button>
      </div>
      <div>
        <button onclick=\"control('set_voice_profile',{user:'operator',verbosity:'brief',confirmations:'minimal',pace:'fast'})\">Operator Brief Profile</button>
        <button onclick=\"control('set_voice_profile',{user:'operator',verbosity:'detailed',confirmations:'strict',pace:'slow'})\">Operator Detailed Profile</button>
      </div>
      <div>
        <button onclick=\"control('list_voice_profiles',{})\">List Voice Profiles</button>
        <button data-danger=\"true\" onclick=\"control('clear_voice_profile',{user:'operator'})\">Clear Operator Profile</button>
      </div>
      <div>
        <button onclick=\"control('skills_reload',{})\">Reload Skills</button>
      </div>
      <div>
        <button data-danger=\"true\" onclick=\"control('clear_inbound_webhooks',{})\">Clear Inbound Webhooks</button>
      </div>
      <div>
        <input id=\"operator-token\" type=\"password\" placeholder=\"Operator token (optional)\" />
        <button onclick=\"saveToken()\">Save Token</button>
        <button data-danger=\"true\" onclick=\"clearToken()\">Clear Token</button>
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
    <section class=\"card\">
      <h2>Conversation Trace</h2>
      <pre id=\"trace\">loading...</pre>
    </section>
    <section class=\"card\">
      <h2>Control Schema</h2>
      <pre id=\"control-schema\">loading...</pre>
    </section>
  </div>
  <script>
    let operatorToken = localStorage.getItem('jarvisOperatorToken') || '';
    function authHeaders(extra) {
      const headers = Object.assign({}, extra || {});
      if (operatorToken) headers['x-operator-token'] = operatorToken;
      return headers;
    }
    function saveToken() {
      const input = document.getElementById('operator-token');
      operatorToken = (input.value || '').trim();
      if (operatorToken) {
        localStorage.setItem('jarvisOperatorToken', operatorToken);
      } else {
        localStorage.removeItem('jarvisOperatorToken');
      }
    }
    function clearToken() {
      operatorToken = '';
      localStorage.removeItem('jarvisOperatorToken');
      const input = document.getElementById('operator-token');
      input.value = '';
    }
    async function json(url, opts) {
      const options = Object.assign({}, opts || {});
      options.headers = authHeaders(options.headers || {});
      const res = await fetch(url, options);
      if (!res.ok) throw new Error(`${url}: ${res.status}`);
      return await res.json();
    }
    async function refresh() {
      try {
        const [status, tools, startup, audit, actions, trace] = await Promise.all([
          json('/api/status'),
          json('/api/tools/recent?limit=20'),
          json('/api/startup-diagnostics'),
          json('/api/audit?limit=20'),
          json('/api/operator-actions?limit=20'),
          json('/api/conversation-trace?limit=20'),
        ]);
        const controlSchema = await json('/api/control-schema');
        const stt = (((status || {}).voice_attention || {}).stt_diagnostics) || {};
        document.getElementById('status').textContent = JSON.stringify(status, null, 2);
        document.getElementById('stt').textContent = JSON.stringify(stt, null, 2);
        document.getElementById('tools').textContent = JSON.stringify(tools, null, 2);
        document.getElementById('startup').textContent = JSON.stringify(startup, null, 2);
        document.getElementById('audit').textContent = JSON.stringify(audit, null, 2);
        document.getElementById('actions').textContent = JSON.stringify(actions, null, 2);
        document.getElementById('trace').textContent = JSON.stringify(trace, null, 2);
        document.getElementById('control-schema').textContent = JSON.stringify(controlSchema, null, 2);
      } catch (err) {
        document.getElementById('status').textContent = String(err);
        document.getElementById('stt').textContent = String(err);
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
    document.getElementById('operator-token').value = operatorToken;
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
        control_schema_provider: Callable[[], dict[str, Any]],
        metrics_provider: Callable[[], str],
        events_provider: Callable[[], list[dict[str, Any]]],
        inbound_callback: Callable[[Any, dict[str, Any], str, str], int],
        inbound_enabled: bool,
        inbound_token: str,
        operator_auth_token: str,
        conversation_trace_provider: Callable[[int], list[dict[str, Any]]] | None = None,
    ) -> None:
        self._host = host
        self._port = int(port)
        self._status_provider = status_provider
        self._diagnostics_provider = diagnostics_provider
        self._control_handler = control_handler
        self._control_schema_provider = control_schema_provider
        self._metrics_provider = metrics_provider
        self._events_provider = events_provider
        self._conversation_trace_provider = conversation_trace_provider or (lambda limit=20: [])
        self._inbound_callback = inbound_callback
        self._inbound_enabled = bool(inbound_enabled)
        self._inbound_token = str(inbound_token).strip()
        self._operator_auth_token = str(operator_auth_token).strip()
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
        app.router.add_get("/api/conversation-trace", self._handle_conversation_trace)
        app.router.add_get("/api/control-schema", self._handle_control_schema)
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

    def _require_operator_auth(self, request: web.Request) -> None:
        if not self._operator_auth_token:
            return
        provided = request.headers.get("X-Operator-Token", "").strip()
        if not provided:
            provided = _extract_bearer_token(request.headers.get("Authorization"))
        if not provided:
            raise web.HTTPUnauthorized(text="operator token required")
        if not _secure_token_match(self._operator_auth_token, provided):
            raise web.HTTPForbidden(text="invalid operator token")

    async def _handle_status(self, request: web.Request) -> web.Response:
        self._require_operator_auth(request)
        return web.json_response(await self._status_provider())

    async def _handle_recent_tools(self, request: web.Request) -> web.Response:
        self._require_operator_auth(request)
        try:
            limit = int(request.query.get("limit", "20"))
        except ValueError:
            limit = 20
        limit = max(1, min(200, limit))
        return web.json_response(list_summaries(limit=limit))

    async def _handle_audit(self, request: web.Request) -> web.Response:
        self._require_operator_auth(request)
        try:
            limit = int(request.query.get("limit", "20"))
        except ValueError:
            limit = 20
        limit = max(1, min(200, limit))
        entries: list[dict[str, Any]] = []
        path = Path(AUDIT_LOG)
        lines = _read_tail_lines(path, limit=limit)
        for line in reversed(lines):
            payload = decode_audit_entry_line(line)
            if payload is None:
                continue
            entries.append(payload)
            if len(entries) >= limit:
                break
        return web.json_response(entries)

    async def _handle_startup_diagnostics(self, request: web.Request) -> web.Response:
        self._require_operator_auth(request)
        return web.json_response({"warnings": self._diagnostics_provider()})

    async def _handle_operator_actions(self, request: web.Request) -> web.Response:
        self._require_operator_auth(request)
        try:
            limit = int(request.query.get("limit", "20"))
        except ValueError:
            limit = 20
        limit = max(1, min(200, limit))
        return web.json_response(list(reversed(self._actions))[:limit])

    async def _handle_conversation_trace(self, request: web.Request) -> web.Response:
        self._require_operator_auth(request)
        try:
            limit = int(request.query.get("limit", "20"))
        except ValueError:
            limit = 20
        limit = max(1, min(200, limit))
        rows = self._conversation_trace_provider(limit)
        if not isinstance(rows, list):
            rows = []
        return web.json_response(rows[:limit])

    async def _handle_control_schema(self, request: web.Request) -> web.Response:
        self._require_operator_auth(request)
        return web.json_response(self._control_schema_provider())

    async def _handle_control(self, request: web.Request) -> web.Response:
        self._require_operator_auth(request)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid_json"}, status=400)
        action = str(body.get("action", "")).strip()
        payload = body.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        try:
            result = await self._control_handler(action, payload)
        except ValueError as exc:
            return web.json_response({"ok": False, "error": "invalid_payload", "message": str(exc)}, status=400)
        status = 200
        if isinstance(result, dict) and result.get("ok") is False:
            error = str(result.get("error", "")).strip().lower()
            if error in {"invalid_action", "unknown_action", "invalid_payload"}:
                status = 400
        log_item = {
            "timestamp": time.time(),
            "action": action,
            "payload": _sanitize_action_value(payload),
            "result": _sanitize_action_value(result),
            "source": request.remote or "operator",
        }
        self._actions.append(log_item)
        if len(self._actions) > 500:
            del self._actions[:-500]
        return web.json_response(result, status=status)

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        self._require_operator_auth(request)
        return web.Response(text=self._metrics_provider(), content_type="text/plain")

    async def _handle_events(self, request: web.Request) -> web.StreamResponse:
        self._require_operator_auth(request)
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
                    try:
                        await response.write(f"event: runtime\ndata: {payload}\n\n".encode("utf-8"))
                    except (ConnectionResetError, RuntimeError):
                        return response
                sent = len(events)
            else:
                try:
                    await response.write(b": keepalive\n\n")
                except (ConnectionResetError, RuntimeError):
                    return response
            await asyncio.sleep(0.5)
        try:
            await response.write_eof()
        except (ConnectionResetError, RuntimeError):
            return response
        return response

    async def _handle_inbound_webhook(self, request: web.Request) -> web.Response:
        if not self._inbound_enabled:
            raise web.HTTPNotFound()
        if not self._inbound_token:
            raise web.HTTPServiceUnavailable(text="inbound token not configured")
        provided_token = (
            request.headers.get("X-Webhook-Token", "").strip()
            or request.query.get("token", "").strip()
            or _extract_bearer_token(request.headers.get("Authorization"))
        )
        if self._inbound_token and not _secure_token_match(self._inbound_token, provided_token):
            raise web.HTTPForbidden(text="invalid token")
        try:
            payload = await request.json()
        except Exception:
            payload = {"raw": await request.text()}
        headers = {key: value for key, value in request.headers.items()}
        event_id = self._inbound_callback(payload, headers, str(request.path), str(request.remote or "unknown"))
        return web.json_response({"ok": True, "event_id": event_id})
