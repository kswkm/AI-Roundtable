from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from roundtable.api.routes import router
from roundtable.api.services import Services

FRONTEND_ORIGINS = ["http://localhost:3000"]
# DNS rebinding 방지: 기본은 로컬 호스트 이름만 허용한다. 테스트는 allowed_hosts로 직접 넘긴다.
DEFAULT_ALLOWED_HOSTS = ["localhost", "127.0.0.1"]


UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class OriginCheckMiddleware:
    """CSRF 방지: 상태를 바꾸는 요청의 Origin이 프론트엔드나 서버 자신이 아니면 403으로 거부한다.

    본문 없는 POST(중단·재개)는 다른 사이트의 폼으로도 보낼 수 있어 CORS만으로는 막히지 않는다.
    Origin이 없는 요청(curl 등 브라우저가 아닌 도구)은 허용한다.
    """

    def __init__(self, app, allowed_origins: list[str]) -> None:
        self.app = app
        self.allowed_origins = set(allowed_origins)

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope["method"] in UNSAFE_METHODS:
            headers = {key.decode("latin-1"): value.decode("latin-1") for key, value in scope["headers"]}
            origin = headers.get("origin")
            same_origin = f"{scope.get('scheme', 'http')}://{headers.get('host', '')}"
            if origin is not None and origin not in self.allowed_origins and origin != same_origin:
                response = JSONResponse(status_code=403, content={"detail": f"허용되지 않은 출처의 요청입니다: {origin}"})
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _korean_detail(exc: RequestValidationError) -> str:
    messages = []
    for error in exc.errors():
        if error["type"] == "value_error":
            messages.append(str(error["msg"]).removeprefix("Value error, "))
        else:
            field = ".".join(str(part) for part in error["loc"] if part != "body") or "요청"
            messages.append(f"입력값이 올바르지 않습니다: {field}")
    return "; ".join(dict.fromkeys(messages))


def create_app(
    services: Services,
    *,
    on_shutdown: Callable[[], Awaitable[None]] | None = None,
    allowed_hosts: list[str] | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if on_shutdown is not None:
            await on_shutdown()

    app = FastAPI(title="AI-Roundtable", lifespan=lifespan)
    app.add_middleware(OriginCheckMiddleware, allowed_origins=FRONTEND_ORIGINS)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts or DEFAULT_ALLOWED_HOSTS)
    app.add_middleware(
        CORSMiddleware, allow_origins=FRONTEND_ORIGINS, allow_methods=["*"], allow_headers=["*"]
    )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": _korean_detail(exc)})

    app.state.services = services
    app.include_router(router)
    return app
