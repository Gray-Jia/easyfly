# Copyright 2026 EasyFly Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Opt-in diagnostic timing is observational, never a new safety clock."""

from collections import deque
from types import SimpleNamespace

from easyfly_precision_landing import node
import pytest


@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("kind", ["plain", "header", "clock"])
def test_native_take_once_and_return_original_message(empty, kind):
    """Keep the installed Humble executor take semantics, without extra reads."""
    original = object()
    source = SimpleNamespace(sec=2, nanosec=3)
    if kind == "header":
        original = SimpleNamespace(header=SimpleNamespace(stamp=source))
    elif kind == "clock":
        original = SimpleNamespace(clock=source)
    info = {"source_timestamp": 123, "received_timestamp": 456}
    calls = []
    records = []

    class Handle:
        """Inert native subscription handle with a counted take operation."""

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def take_message(self, kind, raw):
            """Return the original native tuple, or no available message."""
            calls.append((kind, raw))
            return None if empty else (original, info)

    subscription = SimpleNamespace(
        handle=Handle(), msg_type=object, raw=False,
        topic_name="/landing_target",
    )
    executor = SimpleNamespace(recorder=lambda *args: records.append(args))
    result = node.DiagnosticExecutor._take_subscription(executor, subscription)
    assert len(calls) == 1
    assert result is (None if empty else original)
    expected = dict(info)
    if kind != "plain":
        expected["header_source_ns"] = 2000000003
    assert records == ([] if empty else [("/landing_target", expected)])
    assert info == {"source_timestamp": 123, "received_timestamp": 456}


def test_transport_and_receive_queue_delay_are_separate(monkeypatch):
    """A synthetic delay classifies metadata without changing any ROS stamp."""
    monkeypatch.setattr(node.time, "time_ns", lambda: 10000000000)
    observer = SimpleNamespace(diag_transport={})
    node.LandingTransform.diagnostic_transport(observer, "/landing_target", {
        "source_timestamp": 9000000000, "received_timestamp": 9300000000,
    })
    report = observer.diag_transport["/landing_target"]
    assert report["transport_ms"] == pytest.approx(300)
    assert report["receive_to_take_ms"] == pytest.approx(700)
    node.LandingTransform.diagnostic_transport(observer, "/landing_target", {
        "source_timestamp": 9999000000, "received_timestamp": 9999500000,
    })
    report = observer.diag_transport["/landing_target"]
    assert report["transport_ms"] == pytest.approx(0.5)
    assert report["max_transport_ms"] == pytest.approx(300)
    assert report["max_receive_to_take_ms"] == pytest.approx(700)


def test_wall_clock_rollback_is_not_reported_as_valid_latency(monkeypatch):
    """Missing/backwards wall timestamps stay unknown, not safety evidence."""
    monkeypatch.setattr(node.time, "time_ns", lambda: 100)
    observer = SimpleNamespace(diag_transport={})
    node.LandingTransform.diagnostic_transport(observer, "/landing_target", {
        "source_timestamp": 300, "received_timestamp": 200,
    })
    report = observer.diag_transport["/landing_target"]
    assert report["transport_ms"] is None
    assert report["receive_to_take_ms"] is None
    node.LandingTransform.diagnostic_transport(observer, "/unrelated", {})
    assert set(observer.diag_transport) == {"/landing_target"}


def event_observer(enabled=True):
    """Supply diagnostic-only fields, never a vehicle or flight publisher."""
    return SimpleNamespace(
        diagnostics=enabled, diag_event_sequence=0, diag_events=deque(maxlen=256),
        diag_dropped=0, generation=2,
        get_clock=lambda: SimpleNamespace(
            now=lambda: SimpleNamespace(nanoseconds=10000000000)),
    )


def test_event_ring_disabled_and_bounded(monkeypatch):
    """Disabled tracing is inert; enabled tracing exposes all overwritten events."""
    observer = event_observer(False)
    node.LandingTransform.diagnostic_event(observer, "target_entry", 123)
    assert not observer.diag_events and observer.diag_event_sequence == 0
    observer.diagnostics = True
    monkeypatch.setattr(node.time, "monotonic", lambda: 5.0)
    for source in range(300):
        node.LandingTransform.diagnostic_event(observer, "target_entry", source)
    assert len(observer.diag_events) == 256
    assert observer.diag_dropped == 44
    assert observer.diag_events[0]["source_ns"] == 44
    assert observer.diag_events[-1]["sequence"] == 300
    assert observer.diag_events[-1]["generation"] == 2


def test_snapshot_guard_and_forced_final_drain(monkeypatch):
    """An early timer must not drain events; shutdown explicitly flushes the tail."""
    observer = event_observer()
    logs = []
    observer.__dict__.update(
        diag_last_report=5.0, diag_counts={}, diag_max_ms={}, diag_source={},
        diag_source_max_age={}, diag_transport={}, diag_pair={}, pending=None,
        last_good=None, states=[], watermark=0, published_watermark=0,
        pending_sources=[], reset_count=0,
        get_logger=lambda: SimpleNamespace(info=logs.append),
    )
    monkeypatch.setattr(node.time, "monotonic", lambda: 5.999)
    node.LandingTransform.diagnostic_event(observer, "target_entry", 123)
    node.LandingTransform.diagnostic_snapshot(observer)
    assert not logs and len(observer.diag_events) == 1
    monkeypatch.setattr(node.time, "monotonic", lambda: 6.05)
    node.LandingTransform.diagnostic_snapshot(observer)
    assert len(logs) == 1 and not observer.diag_events
    node.LandingTransform.diagnostic_event(observer, "target_entry", 124)
    node.LandingTransform.diagnostic_snapshot(observer, force=True)
    assert len(logs) == 2 and not observer.diag_events


@pytest.mark.parametrize("fails", [False, True])
def test_publish_end_distinguishes_exception_from_success(fails):
    """A finally timestamp must never assert that a failing publish succeeded."""
    events = []

    def publish(message):
        if fails:
            raise RuntimeError("synthetic publication failure")

    observer = SimpleNamespace(
        diagnostics=True, publisher=SimpleNamespace(publish=publish),
        diagnostic_event=lambda *args, **kwargs: events.append((args, kwargs)),
        diag_counts=node.Counter(), diag_max_ms={},
    )
    output = SimpleNamespace(
        header=SimpleNamespace(stamp=SimpleNamespace(sec=1, nanosec=0)),
        valid=True, reason="ok",
    )
    if fails:
        with pytest.raises(RuntimeError):
            node.LandingTransform.publish(observer, output)
    else:
        node.LandingTransform.publish(observer, output)
    assert events[-1][0][0] == "publish_end"
    assert events[-1][1]["succeeded"] is not fails
