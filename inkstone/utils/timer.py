from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Callable, Iterator

from .text import humanize_duration


class Stopwatch:
    """Measures elapsed time; can be stopped and started again.

        watch = Stopwatch().start()
        ...
        print(watch.stop())
    """

    def __init__(self, *, clock: Callable[[], float] = time.perf_counter):
        self._clock = clock
        self._accumulated = 0.0
        self._started: float | None = None

    @property
    def running(self) -> bool:
        return self._started is not None

    @property
    def elapsed(self) -> float:
        """Seconds measured so far, including the lap still in progress."""
        if self._started is None:
            return self._accumulated
        return self._accumulated + (self._clock() - self._started)

    def start(self) -> Stopwatch:
        if self._started is None:
            self._started = self._clock()
        return self

    def stop(self) -> float:
        if self._started is not None:
            self._accumulated += self._clock() - self._started
            self._started = None
        return self._accumulated

    def reset(self) -> None:
        self._accumulated = 0.0
        self._started = None

    def __enter__(self) -> Stopwatch:
        return self.start()

    def __exit__(self, *exc_info) -> None:
        self.stop()

    def __str__(self) -> str:
        return humanize_duration(self.elapsed)


@contextmanager
def timed(
    label: str = "", *, report: Callable[[str, float], object] | None = None
) -> Iterator[Stopwatch]:
    """Time a block of code.

    The stopwatch is yielded so the caller can read it afterwards. If
    ``report`` is given it is called with the label and the seconds taken,
    also when the block raises:

        with timed("render", report=profiler.add):
            render_all()
    """
    watch = Stopwatch().start()
    try:
        yield watch
    finally:
        watch.stop()
        if report is not None:
            report(label, watch.elapsed)


class Profiler:
    """Adds up the time spent in the named phases of a build."""

    def __init__(self, *, clock: Callable[[], float] = time.perf_counter):
        self._clock = clock
        self._seconds: dict[str, float] = {}
        self._calls: dict[str, int] = {}

    def add(self, name: str, seconds: float) -> None:
        self._seconds[name] = self._seconds.get(name, 0.0) + seconds
        self._calls[name] = self._calls.get(name, 0) + 1

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        started = self._clock()
        try:
            yield
        finally:
            self.add(name, self._clock() - started)

    @property
    def total(self) -> float:
        return sum(self._seconds.values())

    def phases(self) -> list[tuple[str, float, int]]:
        """(name, seconds, calls) in the order the phases first ran."""
        calls = self._calls
        return [(name, spent, calls[name]) for name, spent in self._seconds.items()]

    def summary(self) -> str:
        """The per-phase table printed at the end of a build."""
        rows = self.phases()
        if not rows:
            return ""
        total = self.total
        name_width = max(len("total"), *(len(name) for name, _, _ in rows))
        times = [humanize_duration(seconds) for _, seconds, _ in rows]
        total_text = humanize_duration(total)
        time_width = max(len(total_text), *(len(text) for text in times))
        lines = []
        for (name, seconds, calls), text in zip(rows, times):
            share = seconds / total if total else 0.0
            line = f"{name:<{name_width}}  {text:>{time_width}}  {share:4.0%}"
            if calls > 1:
                line += f"  ({calls} calls)"
            lines.append(line)
        lines.append(f"{'total':<{name_width}}  {total_text:>{time_width}}")
        return "\n".join(lines)
