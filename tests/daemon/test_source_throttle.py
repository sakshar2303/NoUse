from __future__ import annotations

import time

from nouse.daemon.main import _record_source_result, _source_backoff_remaining


def test_source_throttle_sets_backoff_after_repeated_timeouts():
    state: dict[str, dict] = {}
    key = "file:/tmp/demo.md"

    # three timeout-failures should trigger backoff with default threshold
    _record_source_result(key, state, timed_out=True, relation_count=0, used_fallback=False)
    _record_source_result(key, state, timed_out=True, relation_count=0, used_fallback=False)
    _record_source_result(key, state, timed_out=True, relation_count=0, used_fallback=False)

    remaining = _source_backoff_remaining(key, state, time.time())
    assert remaining > 0


def test_source_throttle_recovers_on_success():
    state: dict[str, dict] = {}
    key = "file:/tmp/demo.md"

    _record_source_result(key, state, timed_out=True, relation_count=0, used_fallback=False)
    _record_source_result(key, state, timed_out=True, relation_count=0, used_fallback=False)
    _record_source_result(key, state, timed_out=True, relation_count=0, used_fallback=False)
    assert int(state[key].get("failures", 0) or 0) >= 3

    _record_source_result(key, state, timed_out=False, relation_count=2, used_fallback=False)
    assert int(state[key].get("failures", 0) or 0) < 3
