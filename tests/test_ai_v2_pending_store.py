"""Tests for the T3 in-memory PendingRunStore: atomic single-use claim.

No HTTP, no clock sleeps: expiry is driven through an injectable fake
clock. One test per contract rejection plus the concurrency case.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from pydantic import ValidationError

from core.ai_v2.agent.confirmations import (
    PENDING_TTL_S,
    AlreadyClaimedPendingRun,
    ExpiredPendingRun,
    ForeignSessionPendingRun,
    InMemoryPendingRunStore,
    PendingRun,
    PendingRunNotFound,
    PendingRunStore,
    canonical_args_sha256,
    new_invocation_id,
)

SESSION = "sess-1"
ARGS = {"start": [0.0, 0.0], "end": [100.0, 0.0], "n_sections": 5}


def make_run(
    *,
    invocation_id: str | None = None,
    session_id: str = SESSION,
    created_at: float = 1000.0,
    ttl_s: float | None = None,
) -> PendingRun:
    now = created_at
    expires = now + (ttl_s if ttl_s is not None else PENDING_TTL_S)
    return PendingRun(
        invocation_id=invocation_id or new_invocation_id(),
        session_id=session_id,
        run_id="run_abc",
        provider="openai",
        model="gpt-test",
        messages=[{"role": "user", "content": "hola"}],
        tool_call_id="call_1",
        tool_name="generate_sections_auto",
        args_sha256=canonical_args_sha256(ARGS),
        state_fingerprint="fp",
        created_at=now,
        expires_at=expires,
    )


class FakeClock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_store(clock: FakeClock | None = None) -> tuple[InMemoryPendingRunStore, FakeClock]:
    clock = clock or FakeClock()
    return InMemoryPendingRunStore(clock=clock), clock


def test_create_returns_invocation_id_and_claim_returns_run():
    store, clock = make_store()
    run = make_run(created_at=clock.now)
    returned = store.create(run)
    assert returned == run.invocation_id
    claimed = store.claim(run.invocation_id, SESSION)
    assert claimed == run
    assert claimed.tool_name == "generate_sections_auto"
    assert claimed.args_sha256 == canonical_args_sha256(ARGS)


def test_unknown_invocation_id_is_not_found():
    store, _ = make_store()
    with pytest.raises(PendingRunNotFound):
        store.claim("inv_missing", SESSION)


def test_expired_pending_run_is_rejected_and_dropped():
    store, clock = make_store()
    run = make_run(created_at=clock.now)
    store.create(run)
    clock.advance(PENDING_TTL_S + 1.0)
    with pytest.raises(ExpiredPendingRun):
        store.claim(run.invocation_id, SESSION)
    with pytest.raises(PendingRunNotFound):
        store.claim(run.invocation_id, SESSION)


def test_foreign_session_is_rejected_and_run_survives():
    store, clock = make_store()
    run = make_run(created_at=clock.now)
    store.create(run)
    with pytest.raises(ForeignSessionPendingRun):
        store.claim(run.invocation_id, "sess-other")
    claimed = store.claim(run.invocation_id, SESSION)
    assert claimed.session_id == SESSION


def test_claim_is_single_use():
    store, clock = make_store()
    run = make_run(created_at=clock.now)
    store.create(run)
    first = store.claim(run.invocation_id, SESSION)
    assert first.invocation_id == run.invocation_id
    with pytest.raises(AlreadyClaimedPendingRun):
        store.claim(run.invocation_id, SESSION)


def test_concurrent_claims_have_exactly_one_winner():
    store, clock = make_store()
    run = make_run(created_at=clock.now)
    store.create(run)
    barrier = threading.Barrier(8)
    winners: list[str] = []
    errors: list[Exception] = []

    def attempt() -> None:
        barrier.wait()
        try:
            claimed = store.claim(run.invocation_id, SESSION)
            winners.append(claimed.invocation_id)
        except Exception as exc:  # noqa: BLE001 - typed rejections expected
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: attempt(), range(8)))

    assert winners == [run.invocation_id]
    assert len(errors) == 7
    assert all(isinstance(e, AlreadyClaimedPendingRun) for e in errors)


def test_deny_consumes_the_pending_via_claim():
    store, clock = make_store()
    run = make_run(created_at=clock.now)
    store.create(run)
    claimed = store.claim(run.invocation_id, SESSION)
    assert claimed.invocation_id == run.invocation_id
    with pytest.raises(AlreadyClaimedPendingRun):
        store.claim(run.invocation_id, SESSION)


def test_invalidate_drops_pending_and_unknown_is_noop():
    store, clock = make_store()
    run = make_run(created_at=clock.now)
    store.create(run)
    store.invalidate("inv_never_created")
    store.invalidate(run.invocation_id)
    with pytest.raises(PendingRunNotFound):
        store.claim(run.invocation_id, SESSION)


def test_create_sweeps_expired_entries():
    store, clock = make_store()
    old = make_run(created_at=clock.now)
    store.create(old)
    clock.advance(PENDING_TTL_S + 10.0)
    fresh = make_run(created_at=clock.now)
    store.create(fresh)
    with pytest.raises(PendingRunNotFound):
        store.claim(old.invocation_id, SESSION)
    assert store.claim(fresh.invocation_id, SESSION).invocation_id == fresh.invocation_id


def test_store_is_additive_over_frozen_interface():
    assert issubclass(InMemoryPendingRunStore, object)
    for method in ("create", "claim", "invalidate"):
        assert callable(getattr(InMemoryPendingRunStore, method))


# ---------------------------------------------------------------------------
# turn_confirmations: additive per-turn counter (guardrail 4)
# ---------------------------------------------------------------------------


def test_turn_confirmations_defaults_to_one_and_survives_old_payloads():
    run = make_run()
    assert run.turn_confirmations == 1
    dumped = run.model_dump()
    assert dumped["turn_confirmations"] == 1
    del dumped["turn_confirmations"]
    reloaded = PendingRun.model_validate(dumped)
    assert reloaded.turn_confirmations == 1


def test_turn_confirmations_rejects_values_below_one():
    run = make_run()
    with pytest.raises(ValidationError):
        PendingRun(**{**run.model_dump(), "turn_confirmations": 0})


# ---------------------------------------------------------------------------
# Claimed tombstones: bounded via a create-time TTL sweep (T5)
# ---------------------------------------------------------------------------


def test_fresh_tombstone_still_reports_already_claimed():
    store, _clock = make_store()
    run = make_run(created_at=_clock.now)
    store.create(run)
    store.claim(run.invocation_id, SESSION)
    with pytest.raises(AlreadyClaimedPendingRun):
        store.claim(run.invocation_id, SESSION)


def test_tombstones_are_swept_after_pending_ttl():
    store, clock = make_store()
    consumed = make_run(created_at=clock.now)
    store.create(consumed)
    store.claim(consumed.invocation_id, SESSION)
    clock.advance(PENDING_TTL_S + 1.0)
    fresh = make_run(created_at=clock.now)
    store.create(fresh)
    assert store._claimed == {}
    with pytest.raises(PendingRunNotFound):
        store.claim(consumed.invocation_id, SESSION)
    assert store.claim(fresh.invocation_id, SESSION).invocation_id == (
        fresh.invocation_id
    )


def test_tombstone_sweep_inside_ttl_keeps_recent_ids():
    store, clock = make_store()
    consumed = make_run(created_at=clock.now)
    store.create(consumed)
    store.claim(consumed.invocation_id, SESSION)
    clock.advance(PENDING_TTL_S - 1.0)
    fresh = make_run(created_at=clock.now)
    store.create(fresh)
    assert consumed.invocation_id in store._claimed
    with pytest.raises(AlreadyClaimedPendingRun):
        store.claim(consumed.invocation_id, SESSION)


# ---------------------------------------------------------------------------
# Conversation-scoped invalidation + non-consuming peek (T5)
# ---------------------------------------------------------------------------


def make_conversation_run(
    *,
    invocation_id: str | None = None,
    session_id: str = SESSION,
    conversation_id: str | None = "conv_1",
    args_summary: str = "",
    created_at: float = 1000.0,
) -> PendingRun:
    run = make_run(
        invocation_id=invocation_id, session_id=session_id, created_at=created_at
    )
    return PendingRun(
        **{
            **run.model_dump(),
            "conversation_id": conversation_id,
            "args_summary": args_summary,
        }
    )


def test_invalidate_for_conversation_removes_and_tombstones():
    store, _clock = make_store()
    first = make_conversation_run(invocation_id="inv_a", conversation_id="conv_1")
    second = make_conversation_run(invocation_id="inv_b", conversation_id="conv_1")
    other_conv = make_conversation_run(invocation_id="inv_c", conversation_id="conv_2")
    foreign = make_conversation_run(
        invocation_id="inv_d", session_id="sess-other", conversation_id="conv_1"
    )
    for run in (first, second, other_conv, foreign):
        store.create(run)
    count = store.invalidate_for_conversation(SESSION, "conv_1")
    assert count == 2
    for invocation_id in ("inv_a", "inv_b"):
        with pytest.raises(AlreadyClaimedPendingRun):
            store.claim(invocation_id, SESSION)
    assert store.claim("inv_c", SESSION).invocation_id == "inv_c"
    with pytest.raises(ForeignSessionPendingRun):
        store.claim("inv_d", SESSION)


def test_invalidate_for_conversation_without_matches_is_zero():
    store, _clock = make_store()
    store.create(make_conversation_run(invocation_id="inv_a", conversation_id="conv_1"))
    assert store.invalidate_for_conversation(SESSION, "conv_missing") == 0
    assert store.invalidate_for_conversation("sess-other", "conv_1") == 0
    assert store.invalidate_for_conversation(SESSION, "conv_1") == 1


def test_peek_for_conversation_returns_match_without_consuming():
    store, _clock = make_store()
    run = make_conversation_run(
        invocation_id="inv_a", conversation_id="conv_1", args_summary="Genera 5"
    )
    store.create(run)
    peeked = store.peek_for_conversation(SESSION, "conv_1")
    assert peeked is not None
    assert peeked.invocation_id == "inv_a"
    assert peeked.args_summary == "Genera 5"
    claimed = store.claim("inv_a", SESSION)
    assert claimed.invocation_id == "inv_a"


def test_peek_for_conversation_none_on_mismatch_expiry_or_absence():
    store, clock = make_store()
    store.create(make_conversation_run(invocation_id="inv_a", conversation_id="conv_1"))
    assert store.peek_for_conversation(SESSION, "conv_2") is None
    assert store.peek_for_conversation("sess-other", "conv_1") is None
    assert store.peek_for_conversation(SESSION, "conv_1") is not None
    clock.advance(PENDING_TTL_S + 1.0)
    assert store.peek_for_conversation(SESSION, "conv_1") is None


def test_peek_and_invalidate_are_additive_interface_members():
    for method in (
        "invalidate_for_conversation",
        "peek_for_conversation",
        "invalidated_conversation",
    ):
        assert callable(getattr(InMemoryPendingRunStore, method))
        assert callable(getattr(PendingRunStore, method))


def test_invalidated_conversation_binding_survives_the_delete():
    store, _clock = make_store()
    store.create(make_conversation_run(invocation_id="inv_a", conversation_id="conv_1"))
    assert store.invalidated_conversation("inv_a", SESSION) is None
    assert store.invalidate_for_conversation(SESSION, "conv_1") == 1
    assert store.invalidated_conversation("inv_a", SESSION) == "conv_1"


def test_invalidated_conversation_is_none_for_foreign_session_or_sweep():
    store, clock = make_store()
    store.create(make_conversation_run(invocation_id="inv_a", conversation_id="conv_1"))
    store.create(
        make_conversation_run(
            invocation_id="inv_foreign",
            session_id="sess-other",
            conversation_id="conv_1",
        )
    )
    store.invalidate_for_conversation(SESSION, "conv_1")
    store.invalidate_for_conversation("sess-other", "conv_1")
    assert store.invalidated_conversation("inv_a", "sess-other") is None
    assert store.invalidated_conversation("inv_foreign", "sess-other") == "conv_1"
    clock.advance(PENDING_TTL_S + 1.0)
    store.create(make_conversation_run(invocation_id="inv_b", conversation_id="conv_2"))
    assert store.invalidated_conversation("inv_a", SESSION) is None


def test_claim_consumed_ids_have_no_invalidation_binding():
    store, _clock = make_store()
    store.create(make_conversation_run(invocation_id="inv_a", conversation_id="conv_1"))
    store.claim("inv_a", SESSION)
    with pytest.raises(AlreadyClaimedPendingRun):
        store.claim("inv_a", SESSION)
    assert store.invalidated_conversation("inv_a", SESSION) is None


def test_base_store_defaults_refuse_conversation_scoped_operations():
    class MinimalStore(PendingRunStore):
        def create(self, run: PendingRun) -> str:
            return run.invocation_id

        def claim(self, invocation_id: str, session_id: str) -> PendingRun:
            raise PendingRunNotFound(invocation_id)

        def invalidate(self, invocation_id: str) -> None:
            return None

    store = MinimalStore()
    for call in (
        lambda: store.invalidate_for_conversation(SESSION, "conv_1"),
        lambda: store.peek_for_conversation(SESSION, "conv_1"),
        lambda: store.invalidated_conversation("inv_a", SESSION),
    ):
        with pytest.raises(NotImplementedError):
            call()


# ---------------------------------------------------------------------------
# args_summary: additive PendingRun field (T5)
# ---------------------------------------------------------------------------


def test_args_summary_defaults_to_empty_and_survives_old_payloads():
    run = make_run()
    assert run.args_summary == ""
    dumped = run.model_dump()
    del dumped["args_summary"]
    reloaded = PendingRun.model_validate(dumped)
    assert reloaded.args_summary == ""


def test_args_summary_rejects_over_500_chars():
    run = make_run()
    with pytest.raises(ValidationError):
        PendingRun(**{**run.model_dump(), "args_summary": "x" * 501})
