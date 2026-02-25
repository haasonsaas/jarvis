"""Claude Agent SDK custom tools for Reachy Mini robot control.

Instead of calling raw emotion names, the LLM outputs an "embodiment plan"
with intent, prosody, and motion primitives. The renderer maps these to
the animation library and presence loop signals.
"""

from __future__ import annotations

import json
import logging
from typing import Any, TYPE_CHECKING

from claude_agent_sdk import tool, create_sdk_mcp_server

if TYPE_CHECKING:
    from jarvis.robot.controller import RobotController
    from jarvis.presence import PresenceLoop

log = logging.getLogger(__name__)

# These get bound at startup — avoids circular imports
_robot: RobotController | None = None
_presence: PresenceLoop | None = None


def bind(robot: RobotController, presence: PresenceLoop) -> None:
    global _robot, _presence
    _robot = robot
    _presence = presence


# ── Embodiment plan tool ─────────────────────────────────────

async def embody(args: dict[str, Any]) -> dict[str, Any]:
    if _presence:
        # Clamp values to schema bounds
        _presence.signals.intent_nod = max(0.0, min(1.0, args.get("nod", 0.0)))
        _presence.signals.intent_tilt = max(-15.0, min(15.0, args.get("tilt", 0.0)))
        _presence.signals.intent_glance_yaw = max(-30.0, min(30.0, args.get("glance_yaw", 0.0)))
    return {"content": [{"type": "text", "text": f"Embodiment set: {args['intent']}/{args['prosody']}"}]}


# ── Direct robot actions (used sparingly) ─────────────────────

async def play_emotion(args: dict[str, Any]) -> dict[str, Any]:
    if _robot:
        _robot.play_emotion(args["name"])
        return {"content": [{"type": "text", "text": f"Playing emotion: {args['name']}"}]}
    return {"content": [{"type": "text", "text": "Robot not connected (simulation mode)"}]}


async def play_dance(args: dict[str, Any]) -> dict[str, Any]:
    if _robot:
        _robot.play_dance(args["name"])
        return {"content": [{"type": "text", "text": f"Dancing: {args['name']}"}]}
    return {"content": [{"type": "text", "text": "Robot not connected (simulation mode)"}]}


async def list_animations(args: dict[str, Any]) -> dict[str, Any]:
    emotions = _robot.list_emotions() if _robot else []
    dances = _robot.list_dances() if _robot else []
    return {"content": [{"type": "text", "text": json.dumps({"emotions": emotions, "dances": dances})}]}


# ── Tool objects (kept separate so the underlying Python functions stay callable in tests) ──

embody_tool = tool(
    "embody",
    "Express physical behavior. Call this alongside your verbal response to control "
    "how Jarvis physically behaves while speaking. This is NOT for emotions library "
    "playback — it sets continuous parameters for the presence loop.",
    {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["acknowledge", "clarify", "answer", "decline", "greet", "alert", "amused"],
                "description": "The conversational intent driving the physical behavior.",
            },
            "prosody": {
                "type": "string",
                "enum": ["calm", "energetic", "terse", "warm", "serious"],
                "description": "The emotional tone — affects motion amplitude and speed.",
            },
            "nod": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Nod intensity (0 = none, 1 = emphatic). Use for agreement/acknowledgment.",
            },
            "tilt": {
                "type": "number",
                "minimum": -15.0,
                "maximum": 15.0,
                "description": "Head tilt in degrees. Positive = right ear toward shoulder. Use for curiosity/empathy.",
            },
            "glance_yaw": {
                "type": "number",
                "minimum": -30.0,
                "maximum": 30.0,
                "description": "Brief gaze offset in degrees. Use sparingly for 'looking at something' or 'recalling'.",
            },
        },
        "required": ["intent", "prosody"],
    },
)(embody)


play_emotion_tool = tool(
    "play_emotion",
    "Play a pre-recorded emotion animation from the library. Use this for strong, "
    "specific emotional moments (celebration, surprise) — not for subtle conversational cues.",
    {"name": str},
)(play_emotion)


play_dance_tool = tool(
    "play_dance",
    "Play a pre-recorded dance. Use when the user asks for entertainment or celebration.",
    {"name": str},
)(play_dance)


list_animations_tool = tool(
    "list_animations",
    "List available emotions and dances.",
    {},
)(list_animations)


# ── Build MCP server ──────────────────────────────────────────

def create_robot_server():
    return create_sdk_mcp_server(
        name="jarvis-robot",
        version="0.1.0",
        tools=[embody_tool, play_emotion_tool, play_dance_tool, list_animations_tool],
    )
