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
