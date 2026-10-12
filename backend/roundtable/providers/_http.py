import httpx

from roundtable.providers.base import ProviderError

TIMEOUT_SECONDS = 120.0


async def post_json(
    client: httpx.AsyncClient, url: str, headers: dict[str, str], body: dict
) -> httpx.Response:
    try:
        return await client.post(url, headers=headers, json=body, timeout=TIMEOUT_SECONDS)
    except httpx.TimeoutException as exc:
        raise ProviderError(f"시간 초과 ({TIMEOUT_SECONDS:.0f}초)") from exc
    except httpx.HTTPError as exc:
        raise ProviderError(f"네트워크 오류: {exc}") from exc


def error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:500]
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error)
    if isinstance(error, str):
        return error
    return str(data)[:500]


def retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
