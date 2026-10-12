from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from roundtable.api.routes import router
from roundtable.api.services import Services

FRONTEND_ORIGINS = ["http://localhost:3000"]


def create_app(
    services: Services, *, on_shutdown: Callable[[], Awaitable[None]] | None = None
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if on_shutdown is not None:
            await on_shutdown()

    app = FastAPI(title="AI-Roundtable", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=FRONTEND_ORIGINS, allow_methods=["*"], allow_headers=["*"]
    )
    app.state.services = services
    app.include_router(router)
    return app
