from collections import deque
from pathlib import Path
from typing import Protocol

from .events import ObsEvent


class EventSink(Protocol):
    def emit(self, event: ObsEvent) -> None: ...


class InMemorySink:
    def __init__(self) -> None:
        self.events: list[ObsEvent] = []

    def emit(self, event: ObsEvent) -> None:
        self.events.append(event)


class JsonlSink:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.write_text("", encoding="utf-8")

    def emit(self, event: ObsEvent) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")


class ObservationBuffer:
    def __init__(self, capacity: int = 1000, max_retries: int = 3) -> None:
        self.capacity, self.max_retries = capacity, max_retries
        self._q: deque[tuple[ObsEvent, int]] = deque()
        self.emitted = self.delivered = 0
        self.dropped: dict[str, int] = {}
        self.sink_errors = 0

    def enqueue(self, event: ObsEvent) -> bool:
        self.emitted += 1
        if len(self._q) >= self.capacity:
            self.dropped["buffer_full"] = self.dropped.get("buffer_full", 0) + 1
            return False
        self._q.append((event, 0))
        return True

    def drain(self, sink: EventSink, max_events: int = 100) -> int:
        sent = 0
        for _ in range(min(max_events, len(self._q))):
            event, tries = self._q.popleft()
            try:
                sink.emit(event)
            except Exception:
                self.sink_errors += 1
                if tries + 1 >= self.max_retries:
                    self.dropped["sink_error"] = self.dropped.get("sink_error", 0) + 1
                else:
                    self._q.append((event, tries + 1))
                continue
            self.delivered += 1
            sent += 1
        return sent

    @property
    def buffered(self) -> int:
        return len(self._q)

    @property
    def dropped_total(self) -> int:
        return sum(self.dropped.values())

    def balanced(self) -> bool:
        return self.emitted == self.delivered + self.dropped_total + self.buffered
