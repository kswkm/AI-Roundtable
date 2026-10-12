import asyncio
from collections import defaultdict
from dataclasses import dataclass

TERMINAL_EVENTS = frozenset({"finished", "paused", "error"})


@dataclass(frozen=True)
class Event:
    type: str
    data: dict


class EventBus:
    """토론별 SSE 구독자에게 진행 이벤트를 전달한다. 프로세스 안에서만 동작한다."""

    def __init__(self) -> None:
        self._subscribers: dict[int, set[asyncio.Queue[Event]]] = defaultdict(set)

    def subscribe(self, debate_id: int) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self._subscribers[debate_id].add(queue)
        return queue

    def unsubscribe(self, debate_id: int, queue: asyncio.Queue[Event]) -> None:
        subscribers = self._subscribers.get(debate_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            del self._subscribers[debate_id]

    def subscriber_count(self, debate_id: int) -> int:
        return len(self._subscribers.get(debate_id, ()))

    def publish(self, debate_id: int, type: str, data: dict) -> None:
        for queue in list(self._subscribers.get(debate_id, ())):
            queue.put_nowait(Event(type, data))
