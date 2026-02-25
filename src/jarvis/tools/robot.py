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
from jarvis.tool_policy import is_tool_allowed

if TYPE_CHECKING:
    from jarvis.robot.controller import RobotController
    from jarvis.presence import PresenceLoop
    from jarvis.robot.controller import HeadPose, MotionStep

log = logging.getLogger(__name__)

# These get bound at startup — avoids circular imports
_robot: RobotController | None = None
_presence: PresenceLoop | None = None
_tool_allowlist: list[str] = []
_tool_denylist: list[str] = []


def bind(robot: RobotController, presence: PresenceLoop, config: Any | None = None) -> None:
    global _robot, _presence, _tool_allowlist, _tool_denylist
    _robot = robot
    _presence = presence
    if config is not None:
        _tool_allowlist = list(getattr(config, "tool_allowlist", []))
        _tool_denylist = list(getattr(config, "tool_denylist", []))


def _tool_permitted(name: str) -> bool:
    return is_tool_allowed(name, _tool_allowlist, _tool_denylist)


def tool_feedback(kind: str) -> None:
    if _presence:
        _presence.tool_feedback(kind)


# ── Embodiment plan tool ─────────────────────────────────────

async def embody(args: dict[str, Any]) -> dict[str, Any]:
    if not _tool_permitted("embody"):
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _presence:
        # Clamp values to schema bounds
        _presence.signals.intent_nod = max(0.0, min(1.0, args.get("nod", 0.0)))
        _presence.signals.intent_tilt = max(-15.0, min(15.0, args.get("tilt", 0.0)))
        _presence.signals.intent_glance_yaw = max(-30.0, min(30.0, args.get("glance_yaw", 0.0)))
    return {"content": [{"type": "text", "text": f"Embodiment set: {args['intent']}/{args['prosody']}"}]}


# ── Direct robot actions (used sparingly) ─────────────────────

async def play_emotion(args: dict[str, Any]) -> dict[str, Any]:
    if not _tool_permitted("play_emotion"):
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _robot:
        _robot.play_emotion(args["name"])
        return {"content": [{"type": "text", "text": f"Playing emotion: {args['name']}"}]}
    return {"content": [{"type": "text", "text": "Robot not connected (simulation mode)"}]}


async def play_dance(args: dict[str, Any]) -> dict[str, Any]:
    if not _tool_permitted("play_dance"):
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _robot:
        _robot.play_dance(args["name"])
        return {"content": [{"type": "text", "text": f"Dancing: {args['name']}"}]}
    return {"content": [{"type": "text", "text": "Robot not connected (simulation mode)"}]}


async def list_animations(args: dict[str, Any]) -> dict[str, Any]:
    if not _tool_permitted("list_animations"):
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    emotions = _robot.list_emotions() if _robot else []
    dances = _robot.list_dances() if _robot else []
    return {"content": [{"type": "text", "text": json.dumps({"emotions": emotions, "dances": dances})}]}


async def run_sequence(args: dict[str, Any]) -> dict[str, Any]:
    if not _tool_permitted("run_sequence"):
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _robot:
        return {"content": [{"type": "text", "text": "Robot not connected (simulation mode)"}]}

    from jarvis.robot.controller import HeadPose, MotionStep

    steps = []
    for raw in args.get("steps", []):
        kind = raw.get("kind")
        duration = float(raw.get("duration", 0.8))
        wait = float(raw.get("wait", 0.0))
        if kind == "head":
            pose = HeadPose(
                yaw=float(raw.get("yaw", 0.0)),
                pitch=float(raw.get("pitch", 0.0)),
                roll=float(raw.get("roll", 0.0)),
                x=float(raw.get("x", 0.0)),
                y=float(raw.get("y", 0.0)),
                z=float(raw.get("z", 0.0)),
            )
            steps.append(MotionStep(kind="head", duration=duration, pose=pose, wait=wait))
        elif kind == "body":
            steps.append(MotionStep(kind="body", duration=duration, body_yaw=float(raw.get("yaw", 0.0)), wait=wait))
        elif kind == "antennas":
            steps.append(MotionStep(
                kind="antennas",
                duration=duration,
                antenna_left=float(raw.get("left", 0.0)),
                antenna_right=float(raw.get("right", 0.0)),
                wait=wait,
            ))
        elif kind in {"emotion", "dance"}:
            name = str(raw.get("name", ""))
            if name:
                steps.append(MotionStep(kind=kind, duration=duration, name=name, wait=wait))
        elif kind == "pause":
            steps.append(MotionStep(kind="pause", duration=duration, wait=wait))

    if not steps:
        return {"content": [{"type": "text", "text": "No valid steps provided"}]}

    _robot.run_sequence(steps, blocking=bool(args.get("blocking", False)))
    return {"content": [{"type": "text", "text": f"Queued {len(steps)} motion steps"}]}


async def stop_motion(args: dict[str, Any]) -> dict[str, Any]:
    if not _tool_permitted("stop_motion"):
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _robot:
        return {"content": [{"type": "text", "text": "Robot not connected (simulation mode)"}]}
    _robot.stop_sequence()
    return {"content": [{"type": "text", "text": "Motion sequence stopped"}]}


async def run_macro(args: dict[str, Any]) -> dict[str, Any]:
    if not _tool_permitted("run_macro"):
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if not _robot:
        return {"content": [{"type": "text", "text": "Robot not connected (simulation mode)"}]}
    name = str(args.get("name", ""))
    if not name:
        return {"content": [{"type": "text", "text": "Macro name required"}]}
    intensity = float(args.get("intensity", 1.0))
    _robot.run_macro(name, intensity=intensity, blocking=bool(args.get("blocking", False)))
    return {"content": [{"type": "text", "text": f"Macro queued: {name}"}]}


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


run_sequence_tool = tool(
    "run_sequence",
    "Run a short motion sequence (head/body/antennas/emotion/dance/pause).",
    {
        "type": "object",
        "properties": {
            "blocking": {
                "type": "boolean",
                "description": "If true, execute synchronously (use sparingly).",
            },
            "steps": {
                "type": "array",
                "description": "Sequence steps in order.",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": ["head", "body", "antennas", "emotion", "dance", "pause"],
                        },
                        "duration": {"type": "number"},
                        "wait": {"type": "number"},
                        "yaw": {"type": "number"},
                        "pitch": {"type": "number"},
                        "roll": {"type": "number"},
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                        "z": {"type": "number"},
                        "left": {"type": "number"},
                        "right": {"type": "number"},
                        "name": {"type": "string"},
                    },
                    "required": ["kind"],
                },
            },
        },
        "required": ["steps"],
    },
)(run_sequence)

stop_motion_tool = tool(
    "stop_motion",
    "Stop any active motion sequence.",
    {},
)(stop_motion)


run_macro_tool = tool(
    "run_macro",
    "Run a named gesture macro (acknowledge, affirm, curious, shrug).",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "intensity": {"type": "number"},
            "blocking": {"type": "boolean"},
        },
        "required": ["name"],
    },
)(run_macro)


# ── Build MCP server ──────────────────────────────────────────

def create_robot_server():
    return create_sdk_mcp_server(
        name="jarvis-robot",
        version="0.1.0",
        tools=[
            embody_tool,
            play_emotion_tool,
            play_dance_tool,
            list_animations_tool,
            run_sequence_tool,
            run_macro_tool,
            stop_motion_tool,
        ],
    )
