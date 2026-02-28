#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _parse_simple_assertion(text: str) -> tuple[str, str] | None:
    cleaned_chars: list[str] = []
    for ch in str(text or "").strip().lower():
        if ch.isalnum() or ch in {" ", "_", "-"}:
            cleaned_chars.append(ch)
        else:
            cleaned_chars.append(" ")
    normalized = " ".join("".join(cleaned_chars).split())
    if not normalized:
        return None
    tokens = normalized.split()
    if len(tokens) < 3:
        return None
    try:
        predicate_index = tokens.index("is")
    except ValueError:
        return None
    if predicate_index <= 0 or predicate_index >= (len(tokens) - 1):
        return None
    subject = " ".join(tokens[:predicate_index]).strip()
    remainder = tokens[predicate_index + 1 :]
    polarity_prefix = "yes:"
    if remainder and remainder[0] == "not":
        polarity_prefix = "not:"
        remainder = remainder[1:]
    value = " ".join(remainder).strip()
    if len(subject) < 2 or len(subject) > 80 or not value or len(value) > 120:
        return None
    return subject, f"{polarity_prefix}{value}"


def _memory_path(default_path: str) -> str:
    env_value = str(os.environ.get("MEMORY_PATH", "")).strip()
    if env_value:
        return env_value
    return default_path


def _contradiction_report(store: Any, *, limit: int) -> dict[str, Any]:
    entries = sorted(
        store.recent(limit=limit, include_inactive=True),
        key=lambda item: float(getattr(item, "created_at", 0.0) or 0.0),
    )
    assertions: dict[str, dict[str, Any]] = {}
    contradictions: list[dict[str, Any]] = []
    for entry in entries:
        parsed = _parse_simple_assertion(getattr(entry, "text", ""))
        if parsed is None:
            continue
        subject, value = parsed
        previous = assertions.get(subject)
        current = {
            "memory_id": int(getattr(entry, "id", 0) or 0),
            "value": value,
            "created_at": float(getattr(entry, "created_at", 0.0) or 0.0),
            "source": str(getattr(entry, "source", "")),
            "text": str(getattr(entry, "text", "")),
        }
        if previous is not None and str(previous.get("value", "")) != value:
            contradictions.append(
                {
                    "subject": subject,
                    "previous_memory_id": int(previous.get("memory_id", 0) or 0),
                    "previous_value": str(previous.get("value", "")),
                    "current_memory_id": int(current.get("memory_id", 0) or 0),
                    "current_value": value,
                    "current_created_at": float(current.get("created_at", 0.0) or 0.0),
                }
            )
        assertions[subject] = current
    return {
        "scanned": len(entries),
        "contradiction_count": len(contradictions),
        "subjects_with_assertions": len(assertions),
        "rows": contradictions[:200],
    }


def run() -> int:
    parser = argparse.ArgumentParser(
        description="Run nightly memory maintenance (doctor, compaction flush, contradiction report)."
    )
    parser.add_argument(
        "--memory-path",
        default="",
        help="Path to memory sqlite file (defaults to MEMORY_PATH env or ~/.jarvis/memory.sqlite).",
    )
    parser.add_argument(
        "--scan-limit",
        type=int,
        default=500,
        help="How many recent memory entries to scan for contradiction reporting.",
    )
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="Run SQLite VACUUM after optimization.",
    )
    parser.add_argument(
        "--output",
        default=".artifacts/quality/memory-maintenance.json",
        help="Path to write JSON report.",
    )
    args = parser.parse_args()

    scan_limit = max(50, min(5000, int(args.scan_limit)))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    memory_path = str(args.memory_path).strip() or _memory_path(os.path.expanduser("~/.jarvis/memory.sqlite"))
    from jarvis.memory import MemoryStore

    started = time.time()
    store = MemoryStore(memory_path)
    try:
        doctor = store.memory_doctor()
        flush_payload = store.pre_compaction_flush(reason="nightly_memory_maintenance")
        store.optimize()
        vacuum_ran = False
        if bool(args.vacuum):
            store.vacuum()
            vacuum_ran = True
        contradiction_report = _contradiction_report(store, limit=scan_limit)
        report = {
            "generated_at": time.time(),
            "duration_sec": max(0.0, time.time() - started),
            "memory_path": memory_path,
            "doctor": doctor,
            "compaction": {
                "pre_compaction_flush": flush_payload,
                "optimize_ran": True,
                "vacuum_ran": vacuum_ran,
            },
            "contradictions": contradiction_report,
            "status": (
                "ok"
                if str(doctor.get("status", "")).strip().lower() == "ok"
                and int(contradiction_report.get("contradiction_count", 0) or 0) == 0
                else "review"
            ),
        }
    finally:
        store.close()

    text = json.dumps(report, indent=2)
    output_path.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
