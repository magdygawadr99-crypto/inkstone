from __future__ import annotations

import pytest

from inkstone.utils.timer import Profiler, Stopwatch, timed


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


def test_stopwatch_measures_between_start_and_stop(clock):
    watch = Stopwatch(clock=clock)
    assert not watch.running
    assert watch.elapsed == 0.0
    assert watch.start() is watch
    assert watch.running
    clock.advance(1.5)
    assert watch.elapsed == pytest.approx(1.5)
    clock.advance(0.5)
    assert watch.stop() == pytest.approx(2.0)
    assert not watch.running
    clock.advance(10)
    assert watch.elapsed == pytest.approx(2.0)


def test_stopwatch_accumulates_over_restarts(clock):
    watch = Stopwatch(clock=clock).start()
    clock.advance(1)
    watch.stop()
    clock.advance(5)
    watch.start()
    clock.advance(2)
    assert watch.stop() == pytest.approx(3.0)


def test_stopwatch_start_and_stop_are_idempotent(clock):
    watch = Stopwatch(clock=clock).start()
    clock.advance(1)
    watch.start()
    clock.advance(1)
    assert watch.stop() == pytest.approx(2.0)
    clock.advance(1)
    assert watch.stop() == pytest.approx(2.0)


def test_stopwatch_reset(clock):
    watch = Stopwatch(clock=clock).start()
    clock.advance(3)
    watch.reset()
    assert not watch.running
    assert watch.elapsed == 0.0


def test_stopwatch_as_context_manager_and_string(clock):
    with Stopwatch(clock=clock) as watch:
        clock.advance(0.25)
    assert watch.elapsed == pytest.approx(0.25)
    assert str(watch) == "250 ms"


def test_stopwatch_uses_a_real_clock_by_default():
    watch = Stopwatch().start()
    assert watch.stop() >= 0.0


def test_timed_yields_a_running_stopwatch():
    with timed() as watch:
        assert watch.running
    assert not watch.running
    assert watch.elapsed >= 0.0


def test_timed_reports_label_and_duration():
    seen = []
    with timed("render", report=lambda label, seconds: seen.append((label, seconds))):
        pass
    assert len(seen) == 1
    assert seen[0][0] == "render"
    assert seen[0][1] >= 0.0


def test_timed_reports_even_when_the_block_fails():
    profiler = Profiler()
    with pytest.raises(RuntimeError):
        with timed("broken", report=profiler.add):
            raise RuntimeError("boom")
    assert [name for name, _, _ in profiler.phases()] == ["broken"]


def test_profiler_adds_up_phases_in_first_seen_order(clock):
    profiler = Profiler(clock=clock)
    with profiler.phase("load"):
        clock.advance(0.5)
    with profiler.phase("render"):
        clock.advance(2.0)
    with profiler.phase("load"):
        clock.advance(0.25)
    profiler.add("write", 1.25)
    assert profiler.phases() == [
        ("load", pytest.approx(0.75), 2),
        ("render", pytest.approx(2.0), 1),
        ("write", pytest.approx(1.25), 1),
    ]
    assert profiler.total == pytest.approx(4.0)


def test_profiler_phase_records_time_on_error(clock):
    profiler = Profiler(clock=clock)
    with pytest.raises(ValueError):
        with profiler.phase("parse"):
            clock.advance(1)
            raise ValueError("bad input")
    assert profiler.phases() == [("parse", pytest.approx(1.0), 1)]


def test_profiler_summary(clock):
    profiler = Profiler(clock=clock)
    profiler.add("load content", 0.75)
    profiler.add("render", 2.0)
    profiler.add("render", 1.0)
    profiler.add("write", 0.25)
    assert profiler.summary() == (
        "load content  750 ms   19%\n"
        "render        3.00 s   75%  (2 calls)\n"
        "write         250 ms    6%\n"
        "total         4.00 s"
    )


def test_profiler_summary_edge_cases():
    assert Profiler().summary() == ""
    profiler = Profiler()
    profiler.add("x", 0.0)
    assert profiler.summary() == "x      0 ms    0%\ntotal  0 ms"
