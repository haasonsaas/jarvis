from __future__ import annotations

from jarvis.tools.services_proactive_runtime import (
    has_recent_dispatch,
    nudge_bucket,
    nudge_fingerprint,
    nudge_reason_counts,
    prune_recent_dispatches,
    record_recent_dispatch,
)


def test_nudge_fingerprint_prefers_candidate_id() -> None:
    fingerprint = nudge_fingerprint(
        row={"id": " Leak-ALERT-1 "},
        title="Basement Leak",
        severity="critical",
        source="sensor",
    )
    assert fingerprint == "id:leak-alert-1"


def test_nudge_bucket_interrupt_policy_softens_during_quiet_window() -> None:
    bucket, reason = nudge_bucket(
        policy="interrupt",
        quiet_active=True,
        severity_rank=2,
        overdue_sec=120.0,
        due_soon_sec=60.0,
    )
    assert bucket == "notify"
    assert reason == "quiet_window_softened"


def test_recent_dispatch_prune_and_lookup() -> None:
    rows: list[dict[str, object]] = []
    record_recent_dispatch(rows, fingerprint="id:a", dispatched_at=1000.0)
    record_recent_dispatch(rows, fingerprint="id:b", dispatched_at=1100.0)
    pruned = prune_recent_dispatches(
        rows,
        now_ts=1200.0,
        dedupe_window_sec=150.0,
        max_entries=10,
    )
    assert [str(row["fingerprint"]) for row in pruned] == ["id:b"]
    assert has_recent_dispatch(
        pruned,
        fingerprint="id:b",
        now_ts=1200.0,
        dedupe_window_sec=150.0,
    )
    assert not has_recent_dispatch(
        pruned,
        fingerprint="id:a",
        now_ts=1200.0,
        dedupe_window_sec=150.0,
    )


def test_nudge_reason_counts_collates_all_buckets() -> None:
    counts = nudge_reason_counts(
        interrupt=[{"reason": "policy_interrupt"}],
        notify=[{"reason": "context_user_busy"}],
        defer=[{"reason": "policy_defer"}, {"reason": "policy_defer"}],
    )
    assert counts["policy_interrupt"] == 1
    assert counts["context_user_busy"] == 1
    assert counts["policy_defer"] == 2
