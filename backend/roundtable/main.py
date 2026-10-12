"""실행: uv run uvicorn roundtable.main:app --host 127.0.0.1 --port 8000

인증이 없으므로 반드시 127.0.0.1에만 바인딩한다. 0.0.0.0으로 열지 않는다.
"""

import os

import httpx
from dotenv import load_dotenv

from roundtable.api.app import create_app
from roundtable.api.services import build_services
from roundtable.providers.registry import build_provider

load_dotenv()

_client = httpx.AsyncClient()
services = build_services(
    os.environ.get("ROUNDTABLE_DB", "sqlite:///./roundtable.db"),
    environ=os.environ,
    provider_factory=lambda slot, key: build_provider(slot.provider, slot.model, key, _client),
)
app = create_app(services, on_shutdown=_client.aclose)
