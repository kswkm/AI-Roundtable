import json
from pathlib import Path

import httpx

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def mock_client(
    status: int,
    payload: dict | None = None,
    *,
    headers: dict[str, str] | None = None,
    text: str | None = None,
    capture: list[httpx.Request] | None = None,
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        if text is not None:
            return httpx.Response(status, text=text, headers=headers)
        return httpx.Response(status, json=payload, headers=headers)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))
