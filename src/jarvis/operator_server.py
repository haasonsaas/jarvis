from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import deque
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiohttp import web

from jarvis.tool_summary import list_summaries
from jarvis.tools.services import AUDIT_LOG, decode_audit_entry_line

_ACTION_REDACT_TOKENS = {
    "token",
    "ticket",
    "secret",
    "password",
    "authorization",
    "api_key",
    "code",
}
_ACTION_MAX_STRING_CHARS = 512
_AUDIT_TAIL_SCAN_MULTIPLIER = 6
_SESSION_COOKIE_NAME = "jarvis_operator_session"
_SESSION_TTL_SEC = 8 * 60 * 60
_CSRF_HEADER_NAME = "X-CSRF-Token"
_LOGIN_ATTEMPT_WINDOW_SEC = 5 * 60
_LOGIN_MAX_FAILURES = 5
_LOGIN_BLOCK_SEC = 15 * 60


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


def _dashboard_html(auth_mode: str = "token", csp_nonce: str = "") -> str:
    return """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Jarvis Operator Console</title>
  <style nonce="__CSP_NONCE__">
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
    input, select, textarea {
      border: 1px solid rgba(16, 24, 32, 0.2);
      border-radius: 10px;
      padding: 6px 8px;
      margin: 4px;
      background: rgba(255,255,255,0.9);
      color: var(--ink);
    }
    textarea {
      min-width: 280px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
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
  <p><strong>Auth mode:</strong> __AUTH_MODE__</p>
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
      <h2>Router Canary</h2>
      <pre id=\"canary\">loading...</pre>
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
        <button onclick=\"control('set_persona_style',{style:'jarvis'})\">Persona Jarvis</button>
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
        <button onclick=\"control('set_voice_profile',{user:'operator',verbosity:'brief',confirmations:'minimal',pace:'fast',tone:'direct'})\">Operator Brief Profile</button>
        <button onclick=\"control('set_voice_profile',{user:'operator',verbosity:'detailed',confirmations:'strict',pace:'slow',tone:'formal'})\">Operator Detailed Profile</button>
      </div>
      <div>
        <button onclick=\"control('list_voice_profiles',{})\">List Voice Profiles</button>
        <button data-danger=\"true\" onclick=\"control('clear_voice_profile',{user:'operator'})\">Clear Operator Profile</button>
      </div>
      <div>
        <button onclick=\"control('apply_control_preset',{preset:'quiet_hours'})\">Preset Quiet Hours</button>
        <button onclick=\"control('apply_control_preset',{preset:'demo_mode'})\">Preset Demo</button>
        <button onclick=\"control('apply_control_preset',{preset:'maintenance_mode'})\">Preset Maintenance</button>
      </div>
      <div>
        <button onclick=\"control('export_runtime_profile',{})\">Export Runtime Profile</button>
        <button onclick=\"control('import_runtime_profile',{profile:{wake_mode:'wake_word',sleeping:false,timeout_profile:'normal',push_to_talk_active:false,motion_enabled:true,home_enabled:true,safe_mode_enabled:false,tts_enabled:true,persona_style:'composed',backchannel_style:'balanced'}})\">Import Baseline Profile</button>
      </div>
      <div>
        <button onclick=\"control('skills_reload',{})\">Reload Skills</button>
      </div>
      <div>
        <button data-danger=\"true\" onclick=\"control('clear_inbound_webhooks',{})\">Clear Inbound Webhooks</button>
      </div>
      <div>
        <button onclick=\"listPendingApprovals()\">List Pending Approvals</button>
        <input id=\"approval-limit\" type=\"number\" min=\"1\" max=\"200\" value=\"20\" placeholder=\"Approval limit\" />
      </div>
      <div>
        <input id=\"approval-id\" type=\"text\" placeholder=\"approval-123\" />
        <input id=\"approval-resolver\" type=\"text\" placeholder=\"resolver (default: operator)\" />
      </div>
      <div>
        <input id=\"approval-notes\" type=\"text\" placeholder=\"approval notes\" />
        <button onclick=\"resolveApproval(true,false)\">Approve</button>
        <button onclick=\"resolveApproval(true,true)\">Approve + Execute</button>
        <button data-danger=\"true\" onclick=\"resolveApproval(false,false)\">Reject</button>
      </div>
      <div>
        <button onclick=\"deadLetterStatus()\">Dead-Letter Status</button>
        <button onclick=\"deadLetterReplay(false)\">Dead-Letter Replay</button>
        <button onclick=\"deadLetterReplay(true)\">Dead-Letter Dry-Run</button>
        <input id=\"dead-letter-limit\" type=\"number\" min=\"1\" max=\"50\" value=\"10\" placeholder=\"DLQ limit\" />
      </div>
      <div>
        <select id=\"dead-letter-status-filter\">
          <option value=\"open\" selected>open</option>
          <option value=\"all\">all</option>
          <option value=\"pending\">pending</option>
          <option value=\"failed\">failed</option>
          <option value=\"replayed\">replayed</option>
        </select>
        <input id=\"dead-letter-entry-id\" type=\"text\" placeholder=\"optional entry_id\" />
      </div>
      <div>
        <button onclick=\"listAutonomyReplans()\">List Autonomy Replans</button>
        <button onclick=\"applyAutonomyReplan()\">Apply Autonomy Replan</button>
        <input id=\"autonomy-replan-limit\" type=\"number\" min=\"1\" max=\"200\" value=\"50\" placeholder=\"Replan limit\" />
      </div>
      <div>
        <input id=\"autonomy-task-id\" type=\"text\" placeholder=\"autonomy task_id\" />
        <input id=\"autonomy-execute-at\" type=\"number\" step=\"0.1\" placeholder=\"execute_at (optional epoch)\" />
        <label><input id=\"autonomy-reset-progress\" type=\"checkbox\" checked /> reset progress</label>
      </div>
      <div>
        <input id=\"autonomy-notes\" type=\"text\" placeholder=\"replan notes (optional)\" />
      </div>
      <div>
        <textarea id=\"autonomy-plan-steps\" rows=\"3\" placeholder='optional plan_steps JSON array, e.g. [\"Step one\", \"Step two\"]'></textarea>
      </div>
      <div>
        <textarea id=\"autonomy-step-contracts\" rows=\"3\" placeholder='optional step_contracts JSON array of objects'></textarea>
      </div>
      <div>
        <button onclick=\"copilotActions()\">Copilot Actions</button>
        <button onclick=\"copilotExecute()\">Copilot Execute</button>
        <input id=\"copilot-action-id\" type=\"text\" placeholder=\"copilot action_id\" />
      </div>
      <div>
        <input id=\"operator-token\" type=\"password\" placeholder=\"Operator token (optional)\" />
        <button onclick=\"saveToken()\">Save Token</button>
        <button onclick=\"sessionLogin()\">Session Login</button>
        <button onclick=\"sessionLogout()\">Session Logout</button>
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
  <script nonce="__CSP_NONCE__">
    const authMode = '__AUTH_MODE__';
    let operatorToken = sessionStorage.getItem('jarvisOperatorToken') || '';
    let operatorCsrfToken = sessionStorage.getItem('jarvisOperatorCsrfToken') || '';
    function authHeaders(extra) {
      const headers = Object.assign({}, extra || {});
      if (operatorToken && authMode === 'token') headers['x-operator-token'] = operatorToken;
      if (operatorCsrfToken && authMode === 'session') headers['x-csrf-token'] = operatorCsrfToken;
      return headers;
    }
    function saveToken() {
      const input = document.getElementById('operator-token');
      operatorToken = (input.value || '').trim();
      if (operatorToken) {
        sessionStorage.setItem('jarvisOperatorToken', operatorToken);
      } else {
        sessionStorage.removeItem('jarvisOperatorToken');
      }
    }
    function clearToken() {
      operatorToken = '';
      operatorCsrfToken = '';
      sessionStorage.removeItem('jarvisOperatorToken');
      sessionStorage.removeItem('jarvisOperatorCsrfToken');
      const input = document.getElementById('operator-token');
      input.value = '';
    }
    function fieldValue(id) {
      const el = document.getElementById(id);
      if (!el) return '';
      return String(el.value || '').trim();
    }
    function boundedInt(id, fallback, min, max) {
      const raw = Number.parseInt(fieldValue(id), 10);
      if (!Number.isFinite(raw)) return fallback;
      return Math.max(min, Math.min(max, raw));
    }
    async function listPendingApprovals() {
      const limit = boundedInt('approval-limit', 20, 1, 200);
      await control('list_pending_approvals', {limit});
    }
    async function resolveApproval(approved, execute) {
      const approvalId = fieldValue('approval-id').toLowerCase();
      if (!approvalId) {
        document.getElementById('control-result').textContent = 'approval_id is required.';
        return;
      }
      const resolverId = fieldValue('approval-resolver') || 'operator';
      const notes = fieldValue('approval-notes');
      await control('resolve_approval', {
        approval_id: approvalId,
        approved: !!approved,
        execute: !!execute,
        resolver_id: resolverId,
        notes,
      });
    }
    async function deadLetterStatus() {
      const limit = boundedInt('dead-letter-limit', 20, 1, 200);
      const statusFilter = fieldValue('dead-letter-status-filter') || 'open';
      await control('dead_letter_status', {limit, status_filter: statusFilter});
    }
    async function deadLetterReplay(dryRun) {
      const limit = boundedInt('dead-letter-limit', 10, 1, 50);
      const statusFilter = fieldValue('dead-letter-status-filter') || 'open';
      const entryId = fieldValue('dead-letter-entry-id');
      const payload = {limit, status_filter: statusFilter, dry_run: !!dryRun};
      if (entryId) payload.entry_id = entryId;
      await control('dead_letter_replay', payload);
    }
    function parseOptionalJsonArray(id, label, elementValidator) {
      const raw = fieldValue(id);
      if (!raw) return {ok: true, value: null};
      try {
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) {
          return {ok: false, message: `${label} must be a JSON array.`};
        }
        if (typeof elementValidator === 'function') {
          for (let i = 0; i < parsed.length; i += 1) {
            if (!elementValidator(parsed[i])) {
              return {ok: false, message: `${label}[${i}] has invalid shape.`};
            }
          }
        }
        return {ok: true, value: parsed};
      } catch (_) {
        return {ok: false, message: `${label} must be valid JSON.`};
      }
    }
    async function listAutonomyReplans() {
      const limit = boundedInt('autonomy-replan-limit', 50, 1, 200);
      await control('list_autonomy_replans', {limit});
    }
    async function applyAutonomyReplan() {
      const taskId = fieldValue('autonomy-task-id');
      if (!taskId) {
        document.getElementById('control-result').textContent = 'task_id is required.';
        return;
      }
      const executeAtRaw = fieldValue('autonomy-execute-at');
      const payload = {
        task_id: taskId,
        notes: fieldValue('autonomy-notes'),
        reset_progress: !!document.getElementById('autonomy-reset-progress').checked,
      };
      if (executeAtRaw) {
        const executeAt = Number.parseFloat(executeAtRaw);
        if (!Number.isFinite(executeAt)) {
          document.getElementById('control-result').textContent = 'execute_at must be numeric.';
          return;
        }
        payload.execute_at = executeAt;
      }
      const planSteps = parseOptionalJsonArray(
        'autonomy-plan-steps',
        'plan_steps',
        (item) => typeof item === 'string',
      );
      if (!planSteps.ok) {
        document.getElementById('control-result').textContent = planSteps.message;
        return;
      }
      if (planSteps.value !== null) {
        payload.plan_steps = planSteps.value;
      }
      const stepContracts = parseOptionalJsonArray(
        'autonomy-step-contracts',
        'step_contracts',
        (item) => !!item && typeof item === 'object' && !Array.isArray(item),
      );
      if (!stepContracts.ok) {
        document.getElementById('control-result').textContent = stepContracts.message;
        return;
      }
      if (stepContracts.value !== null) {
        payload.step_contracts = stepContracts.value;
      }
      await control('apply_autonomy_replan', payload);
    }
    async function copilotActions() {
      await control('copilot_actions', {});
    }
    async function copilotExecute() {
      const actionId = fieldValue('copilot-action-id').toLowerCase();
      if (!actionId) {
        document.getElementById('control-result').textContent = 'copilot action_id is required.';
        return;
      }
      await control('copilot_execute', {action_id: actionId});
    }
    async function json(url, opts) {
      const options = Object.assign({}, opts || {});
      options.headers = authHeaders(options.headers || {});
      options.credentials = 'same-origin';
      const res = await fetch(url, options);
      if (!res.ok) throw new Error(`${url}: ${res.status}`);
      return await res.json();
    }
    async function sessionLogin() {
      if (authMode !== 'session') {
        document.getElementById('control-result').textContent = 'Session login is only available in session auth mode.';
        return;
      }
      const token = (document.getElementById('operator-token').value || '').trim();
      try {
        const res = await fetch('/api/session/login', {
          method: 'POST',
          headers: authHeaders({'content-type': 'application/json'}),
          credentials: 'same-origin',
          body: JSON.stringify({token}),
        });
        if (!res.ok) throw new Error(`/api/session/login: ${res.status}`);
        const payload = await res.json();
        operatorCsrfToken = String(payload.csrf_token || '').trim();
        if (operatorCsrfToken) {
          sessionStorage.setItem('jarvisOperatorCsrfToken', operatorCsrfToken);
        } else {
          sessionStorage.removeItem('jarvisOperatorCsrfToken');
        }
        document.getElementById('control-result').textContent = JSON.stringify(payload, null, 2);
        await refresh();
      } catch (err) {
        document.getElementById('control-result').textContent = String(err);
      }
    }
    async function sessionLogout() {
      if (authMode !== 'session') {
        document.getElementById('control-result').textContent = 'Session logout is only available in session auth mode.';
        return;
      }
      try {
        const res = await fetch('/api/session/logout', {
          method: 'POST',
          headers: authHeaders({}),
          credentials: 'same-origin',
        });
        if (!res.ok) throw new Error(`/api/session/logout: ${res.status}`);
        const payload = await res.json();
        operatorCsrfToken = '';
        sessionStorage.removeItem('jarvisOperatorCsrfToken');
        document.getElementById('control-result').textContent = JSON.stringify(payload, null, 2);
        await refresh();
      } catch (err) {
        document.getElementById('control-result').textContent = String(err);
      }
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
        const canary = ((((status || {}).observability) || {}).router_canary_analytics) || {};
        document.getElementById('status').textContent = JSON.stringify(status, null, 2);
        document.getElementById('stt').textContent = JSON.stringify(stt, null, 2);
        document.getElementById('canary').textContent = JSON.stringify(canary, null, 2);
        document.getElementById('tools').textContent = JSON.stringify(tools, null, 2);
        document.getElementById('startup').textContent = JSON.stringify(startup, null, 2);
        document.getElementById('audit').textContent = JSON.stringify(audit, null, 2);
        document.getElementById('actions').textContent = JSON.stringify(actions, null, 2);
        document.getElementById('trace').textContent = JSON.stringify(trace, null, 2);
        document.getElementById('control-schema').textContent = JSON.stringify(controlSchema, null, 2);
      } catch (err) {
        document.getElementById('status').textContent = String(err);
        document.getElementById('stt').textContent = String(err);
        document.getElementById('canary').textContent = String(err);
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
""".replace("__AUTH_MODE__", auth_mode).replace("__CSP_NONCE__", csp_nonce)


def _dashboard_onclick_csp_hashes() -> tuple[str, ...]:
    # Allow legacy inline onclick handlers without enabling global unsafe-inline.
    html = _dashboard_html(auth_mode="token", csp_nonce="")
    hashes: set[str] = set()
    marker = 'onclick="'
    cursor = 0
    while True:
        start = html.find(marker, cursor)
        if start < 0:
            break
        value_start = start + len(marker)
        value_end = html.find('"', value_start)
        if value_end < 0:
            break
        handler = str(html[value_start:value_end]).strip()
        cursor = value_end + 1
        if not handler:
            continue
        digest = hashlib.sha256(handler.encode("utf-8")).digest()
        b64 = base64.b64encode(digest).decode("ascii")
        hashes.add(f"'sha256-{b64}'")
    return tuple(sorted(hashes))


_DASHBOARD_ONCLICK_CSP_HASHES = _dashboard_onclick_csp_hashes()


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
        operator_auth_mode: str = "",
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
        self._operator_auth_mode = self._normalize_operator_auth_mode(
            operator_auth_mode,
            token_present=bool(self._operator_auth_token),
        )
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._actions: list[dict[str, Any]] = []
        self._last_action_signature = ""
        self._sessions: dict[str, float] = {}
        self._session_operator_ids: dict[str, str] = {}
        self._session_csrf_tokens: dict[str, str] = {}
        self._login_failures: dict[str, list[float]] = {}
        self._login_blocked_until: dict[str, float] = {}
        key_source = self._operator_auth_token or self._inbound_token or "jarvis-operator-audit"
        self._action_chain_key = str(key_source).encode("utf-8")
        token_fingerprint = hashlib.sha256(self._operator_auth_token.encode("utf-8")).hexdigest()[:12]
        self._token_operator_identity = f"token-{token_fingerprint}" if token_fingerprint else "token-operator"

    @staticmethod
    def _normalize_operator_auth_mode(mode: str, *, token_present: bool) -> str:
        normalized = str(mode or "").strip().lower()
        if normalized in {"off", "token", "session"}:
            return normalized
        return "token" if token_present else "off"

    def _sign_operator_action(self, payload: dict[str, Any], previous_signature: str) -> str:
        canonical = json.dumps(
            {
                "previous_signature": str(previous_signature or ""),
                "payload": payload,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hmac.new(self._action_chain_key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()

    def _append_operator_action(
        self,
        *,
        action: str,
        payload: Any,
        result: Any,
        source: str,
    ) -> None:
        payload_item = {
            "timestamp": time.time(),
            "action": str(action or "").strip(),
            "payload": _sanitize_action_value(payload),
            "result": _sanitize_action_value(result),
            "source": str(source or "operator"),
        }
        previous_signature = self._last_action_signature
        signature = self._sign_operator_action(payload_item, previous_signature)
        log_item = {
            **payload_item,
            "previous_signature": previous_signature,
            "signature": signature,
            "signature_alg": "hmac-sha256",
        }
        self._last_action_signature = signature
        self._actions.append(log_item)
        if len(self._actions) > 500:
            del self._actions[:-500]

    def _record_security_event(
        self,
        request: web.Request,
        *,
        event: str,
        reason: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "event": str(event).strip().lower(),
            "reason": str(reason).strip().lower(),
            "method": str(request.method),
            "path": str(request.path),
            "auth_mode": self._operator_auth_mode,
        }
        if isinstance(details, dict):
            for key, value in details.items():
                payload[str(key)] = value
        self._append_operator_action(
            action="security_event",
            payload=payload,
            result={"ok": False, "status_code": int(status_code)},
            source=self._source_id(request),
        )

    def _prune_sessions(self) -> None:
        now = time.time()
        expired = [token for token, expires_at in self._sessions.items() if expires_at <= now]
        for token in expired:
            self._sessions.pop(token, None)
            self._session_operator_ids.pop(token, None)
            self._session_csrf_tokens.pop(token, None)

    def _source_id(self, request: web.Request) -> str:
        return str(request.remote or "unknown").strip() or "unknown"

    def _prune_login_tracking(self, *, now: float) -> None:
        stale_failures: list[str] = []
        for source, attempts in self._login_failures.items():
            recent = [ts for ts in attempts if (now - ts) <= float(_LOGIN_ATTEMPT_WINDOW_SEC)]
            if recent:
                self._login_failures[source] = recent
            else:
                stale_failures.append(source)
        for source in stale_failures:
            self._login_failures.pop(source, None)
        expired_blocks = [source for source, until in self._login_blocked_until.items() if until <= now]
        for source in expired_blocks:
            self._login_blocked_until.pop(source, None)

    def _is_login_blocked(self, *, source: str, now: float) -> bool:
        self._prune_login_tracking(now=now)
        blocked_until = float(self._login_blocked_until.get(source, 0.0) or 0.0)
        return blocked_until > now

    def _record_login_failure(self, *, source: str, now: float) -> None:
        self._prune_login_tracking(now=now)
        attempts = self._login_failures.setdefault(source, [])
        attempts.append(now)
        attempts[:] = [ts for ts in attempts if (now - ts) <= float(_LOGIN_ATTEMPT_WINDOW_SEC)]
        if len(attempts) >= int(_LOGIN_MAX_FAILURES):
            self._login_blocked_until[source] = now + float(_LOGIN_BLOCK_SEC)

    def _clear_login_failures(self, *, source: str) -> None:
        self._login_failures.pop(source, None)
        self._login_blocked_until.pop(source, None)

    def _issue_session(self) -> tuple[str, int, str, str]:
        self._prune_sessions()
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(24)
        session_fingerprint = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
        operator_identity = f"session-{session_fingerprint}"
        ttl_sec = int(_SESSION_TTL_SEC)
        self._sessions[token] = time.time() + float(ttl_sec)
        self._session_operator_ids[token] = operator_identity
        self._session_csrf_tokens[token] = csrf_token
        return token, ttl_sec, csrf_token, operator_identity

    def _session_valid(self, token: str) -> bool:
        self._prune_sessions()
        expires_at = self._sessions.get(token)
        if expires_at is None:
            return False
        if expires_at <= time.time():
            self._sessions.pop(token, None)
            self._session_operator_ids.pop(token, None)
            self._session_csrf_tokens.pop(token, None)
            return False
        return True

    def _operator_identity(self, request: web.Request) -> str:
        if self._operator_auth_mode == "token":
            return self._token_operator_identity
        if self._operator_auth_mode == "session":
            session_token = self._session_token_from_request(request)
            if session_token and self._session_valid(session_token):
                identity = str(self._session_operator_ids.get(session_token, "")).strip()
                if identity:
                    return identity
            return "session-unknown"
        return "operator"

    def _session_token_from_request(self, request: web.Request) -> str:
        return request.cookies.get(_SESSION_COOKIE_NAME, "").strip()

    def _require_session_csrf(self, request: web.Request) -> None:
        if self._operator_auth_mode != "session":
            return
        session_token = self._session_token_from_request(request)
        if not session_token or not self._session_valid(session_token):
            self._record_security_event(
                request,
                event="csrf",
                reason="session_missing_or_invalid",
                status_code=401,
            )
            raise web.HTTPUnauthorized(text="operator session required")
        expected = self._session_csrf_tokens.get(session_token, "")
        provided = request.headers.get(_CSRF_HEADER_NAME, "").strip()
        if not expected:
            self._record_security_event(
                request,
                event="csrf",
                reason="session_state_invalid",
                status_code=403,
            )
            raise web.HTTPForbidden(text="invalid session state")
        if not provided:
            self._record_security_event(
                request,
                event="csrf",
                reason="csrf_missing",
                status_code=401,
            )
            raise web.HTTPUnauthorized(text="csrf token required")
        if not _secure_token_match(expected, provided):
            self._record_security_event(
                request,
                event="csrf",
                reason="csrf_invalid",
                status_code=403,
            )
            raise web.HTTPForbidden(text="invalid csrf token")

    @web.middleware
    async def _security_headers_middleware(
        self,
        request: web.Request,
        handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
    ) -> web.StreamResponse:
        if request.path == "/":
            request["dashboard_csp_nonce"] = secrets.token_urlsafe(18)
        was_http_exception = False
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            response = exc
            was_http_exception = True
        csp_nonce = str(request.get("dashboard_csp_nonce", "")).strip()
        style_src_parts = ["'self'"]
        script_src_parts = ["'self'"]
        if csp_nonce:
            nonce_token = f"'nonce-{csp_nonce}'"
            style_src_parts.append(nonce_token)
            script_src_parts.append(nonce_token)
        if _DASHBOARD_ONCLICK_CSP_HASHES:
            script_src_parts.append("'unsafe-hashes'")
            script_src_parts.extend(_DASHBOARD_ONCLICK_CSP_HASHES)
        style_src = " ".join(style_src_parts)
        script_src = " ".join(script_src_parts)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'; "
            f"img-src 'self' data:; connect-src 'self'; style-src {style_src}; script-src {script_src}",
        )
        if str(request.path).startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        if was_http_exception:
            raise response
        return response

    async def start(self) -> None:
        if self._runner is not None:
            return
        app = web.Application(middlewares=[self._security_headers_middleware])
        app.router.add_get("/", self._handle_dashboard)
        app.router.add_get("/api/status", self._handle_status)
        app.router.add_get("/api/tools/recent", self._handle_recent_tools)
        app.router.add_get("/api/audit", self._handle_audit)
        app.router.add_get("/api/startup-diagnostics", self._handle_startup_diagnostics)
        app.router.add_get("/api/operator-actions", self._handle_operator_actions)
        app.router.add_get("/api/conversation-trace", self._handle_conversation_trace)
        app.router.add_get("/api/control-schema", self._handle_control_schema)
        app.router.add_post("/api/control", self._handle_control)
        app.router.add_post("/api/session/login", self._handle_session_login)
        app.router.add_post("/api/session/logout", self._handle_session_logout)
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
        csp_nonce = str(request.get("dashboard_csp_nonce", "")).strip()
        return web.Response(text=_dashboard_html(self._operator_auth_mode, csp_nonce), content_type="text/html")

    def _require_operator_auth(self, request: web.Request) -> None:
        if self._operator_auth_mode == "off":
            return
        if not self._operator_auth_token:
            self._record_security_event(
                request,
                event="operator_auth",
                reason="token_not_configured",
                status_code=503,
            )
            raise web.HTTPServiceUnavailable(text="operator auth token not configured")
        if self._operator_auth_mode == "token":
            provided = request.headers.get("X-Operator-Token", "").strip()
            if not provided:
                provided = _extract_bearer_token(request.headers.get("Authorization"))
            if not provided:
                self._record_security_event(
                    request,
                    event="operator_auth",
                    reason="token_missing",
                    status_code=401,
                )
                raise web.HTTPUnauthorized(text="operator token required")
            if not _secure_token_match(self._operator_auth_token, provided):
                self._record_security_event(
                    request,
                    event="operator_auth",
                    reason="token_invalid",
                    status_code=403,
                )
                raise web.HTTPForbidden(text="invalid operator token")
            return
        session_token = request.cookies.get(_SESSION_COOKIE_NAME, "").strip()
        if not session_token:
            self._record_security_event(
                request,
                event="operator_auth",
                reason="session_missing",
                status_code=401,
            )
            raise web.HTTPUnauthorized(text="operator session required")
        if not self._session_valid(session_token):
            self._record_security_event(
                request,
                event="operator_auth",
                reason="session_invalid_or_expired",
                status_code=403,
            )
            raise web.HTTPForbidden(text="invalid or expired operator session")

    async def _handle_session_login(self, request: web.Request) -> web.Response:
        if self._operator_auth_mode != "session":
            raise web.HTTPNotFound()
        if not self._operator_auth_token:
            raise web.HTTPServiceUnavailable(text="operator auth token not configured")
        source = self._source_id(request)
        now = time.time()
        if self._is_login_blocked(source=source, now=now):
            blocked_until = float(self._login_blocked_until.get(source, 0.0) or 0.0)
            self._record_security_event(
                request,
                event="session_login",
                reason="throttled",
                status_code=429,
                details={
                    "blocked_until": blocked_until,
                    "window_sec": int(_LOGIN_ATTEMPT_WINDOW_SEC),
                },
            )
            raise web.HTTPTooManyRequests(text="too many failed login attempts")
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid_json"}, status=400)
        token = ""
        if isinstance(body, dict):
            token = str(body.get("token", "")).strip()
        if not token:
            token = request.headers.get("X-Operator-Token", "").strip()
        if not token:
            token = _extract_bearer_token(request.headers.get("Authorization"))
        if not token:
            self._record_security_event(
                request,
                event="session_login",
                reason="token_missing",
                status_code=401,
            )
            raise web.HTTPUnauthorized(text="operator token required")
        if not _secure_token_match(self._operator_auth_token, token):
            self._record_login_failure(source=source, now=now)
            attempts = len(self._login_failures.get(source, []))
            blocked_until = float(self._login_blocked_until.get(source, 0.0) or 0.0)
            self._record_security_event(
                request,
                event="session_login",
                reason="token_invalid",
                status_code=403,
                details={
                    "attempt_count": attempts,
                    "window_sec": int(_LOGIN_ATTEMPT_WINDOW_SEC),
                    "max_failures": int(_LOGIN_MAX_FAILURES),
                },
            )
            if blocked_until > now:
                self._record_security_event(
                    request,
                    event="session_login",
                    reason="throttle_armed",
                    status_code=429,
                    details={"blocked_until": blocked_until},
                )
            raise web.HTTPForbidden(text="invalid operator token")
        self._clear_login_failures(source=source)
        session_token, ttl_sec, csrf_token, operator_identity = self._issue_session()
        response = web.json_response(
            {
                "ok": True,
                "mode": "session",
                "expires_in_sec": ttl_sec,
                "csrf_header": _CSRF_HEADER_NAME,
                "csrf_token": csrf_token,
                "operator_identity": operator_identity,
            }
        )
        response.set_cookie(
            _SESSION_COOKIE_NAME,
            session_token,
            max_age=ttl_sec,
            httponly=True,
            samesite="Strict",
            secure=bool(request.secure),
            path="/",
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    async def _handle_session_logout(self, request: web.Request) -> web.Response:
        if self._operator_auth_mode != "session":
            raise web.HTTPNotFound()
        self._require_operator_auth(request)
        self._require_session_csrf(request)
        token = self._session_token_from_request(request)
        if token:
            self._sessions.pop(token, None)
            self._session_operator_ids.pop(token, None)
            self._session_csrf_tokens.pop(token, None)
        response = web.json_response({"ok": True})
        response.del_cookie(_SESSION_COOKIE_NAME, path="/")
        response.headers["Cache-Control"] = "no-store"
        return response

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
        self._require_session_csrf(request)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "invalid_json"}, status=400)
        action = str(body.get("action", "")).strip()
        payload = body.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        if action.strip().lower() in {"resolve_approval", "apply_autonomy_replan"}:
            payload = dict(payload)
            payload.pop("__operator_identity", None)
            payload["__operator_identity"] = self._operator_identity(request)
        try:
            result = await self._control_handler(action, payload)
        except ValueError as exc:
            return web.json_response({"ok": False, "error": "invalid_payload", "message": str(exc)}, status=400)
        status = 200
        if isinstance(result, dict) and result.get("ok") is False:
            error = str(result.get("error", "")).strip().lower()
            if error in {"invalid_action", "unknown_action", "invalid_payload"}:
                status = 400
        self._append_operator_action(
            action=action,
            payload=payload,
            result=result,
            source=request.remote or "operator",
        )
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
            or _extract_bearer_token(request.headers.get("Authorization"))
        )
        if self._inbound_token and not _secure_token_match(self._inbound_token, provided_token):
            self._record_security_event(
                request,
                event="inbound_webhook_auth",
                reason="token_invalid",
                status_code=403,
            )
            raise web.HTTPForbidden(text="invalid token")
        try:
            payload = await request.json()
        except Exception:
            payload = {"raw": await request.text()}
        headers = {key: value for key, value in request.headers.items()}
        event_id = self._inbound_callback(payload, headers, str(request.path), str(request.remote or "unknown"))
        return web.json_response({"ok": True, "event_id": event_id})
