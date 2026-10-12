import asyncio
from collections.abc import Mapping
from dataclasses import dataclass

from roundtable.debate.caller import ProviderFactory, Sleep, SlotCaller
from roundtable.debate.events import EventBus
from roundtable.debate.orchestrator import Orchestrator
from roundtable.slots.service import SlotService
from roundtable.storage.config import ConfigStore
from roundtable.storage.db import init_db, make_engine
from roundtable.storage.store import DebateStore
from roundtable.usage.recorder import UsageRecorder


@dataclass
class Services:
    store: DebateStore
    slots: SlotService
    usage: UsageRecorder
    config: ConfigStore
    bus: EventBus
    orchestrator: Orchestrator


def build_services(
    db_url: str,
    *,
    environ: Mapping[str, str],
    provider_factory: ProviderFactory,
    sleep: Sleep = asyncio.sleep,
) -> Services:
    engine = make_engine(db_url)
    init_db(engine)
    slots = SlotService(engine, environ=environ)
    slots.seed_defaults()
    usage = UsageRecorder(engine)
    store = DebateStore(engine)
    store.mark_running_as_interrupted()
    bus = EventBus()
    caller = SlotCaller(slots, usage, provider_factory, sleep=sleep)
    return Services(
        store=store, slots=slots, usage=usage, config=ConfigStore(engine),
        bus=bus, orchestrator=Orchestrator(store, caller, bus),
    )
