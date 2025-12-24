from fastapi import FastAPI
from src.routes.status import status_router
from src.routes.auth import auth_router
from src.routes.injest import injest_router
def create_app()-> FastAPI:
    '''
    Created fastapi app, auto configures its metadata and settings
    also has middlewares
    '''
    app = FastAPI(
        title="ResumeRoast Arena",
        description="Instant, anonymized resume roasts: automated, shareable scorecard and targeted fix suggestions.67",
        version="0.0.1",
    )
    app.include_router(status_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(injest_router, prefix="/api/v1")
    @app.get("/")
    def get_root():
        return {"message":" Welcome to resume roast arena"}

    return app
