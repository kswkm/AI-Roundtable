from roundtable.debate.events import Event, EventBus


async def test_publish_reaches_only_subscribers_of_that_debate():
    bus = EventBus()
    first = bus.subscribe(1)
    other = bus.subscribe(2)
    bus.publish(1, "message", {"label": "A"})
    assert first.get_nowait() == Event("message", {"label": "A"})
    assert other.empty()


async def test_unsubscribe_and_count():
    bus = EventBus()
    queue = bus.subscribe(1)
    assert bus.subscriber_count(1) == 1
    bus.unsubscribe(1, queue)
    assert bus.subscriber_count(1) == 0
    bus.publish(1, "message", {})  # 구독자가 없어도 오류 없음
    assert queue.empty()
