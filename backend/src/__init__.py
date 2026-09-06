from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.config import CORS_ALLOWED_ORIGINS
from src.db.session import engine
from src.routes.status import status_router
from src.routes.auth import auth_router
from src.routes.injest import injest_router
from src.routes.public import public_router
from src.routes.leaderboard import leaderboard_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Disposes the async engine's connection pool on shutdown -- without
    # this, connections stay bound to whichever event loop created them.
    # Matters most for TestClient-driven tests (each instantiation runs
    # the app on its own event loop in a background thread); undisposed
    # connections from one TestClient session make the next one's real DB
    # call raise "attached to a different loop". Also just correct
    # production hygiene for a long-running server.
    await engine.dispose()


def create_app()-> FastAPI:
    '''
    Created fastapi app, auto configures its metadata and settings
    also has middlewares
    '''
    app = FastAPI(
        title="ResumeRoast Arena",
        description="Instant, anonymized resume roasts: automated, shareable scorecard and targeted fix suggestions.67",
        version="0.0.1",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(status_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(injest_router, prefix="/api/v1")
    app.include_router(public_router)
    app.include_router(leaderboard_router)
    @app.get("/")
    def get_root():
        return {"message":" Welcome to resume roast arena"}

    return app
