from fastapi import FastAPI

from esl.web.routers import catalog, health, stores, tags, webhooks


def create_app() -> FastAPI:
    app = FastAPI(title="ESL Pricing Service")
    app.include_router(health.router, prefix="/v1")
    app.include_router(catalog.router, prefix="/v1")
    app.include_router(stores.router, prefix="/v1")
    app.include_router(tags.router, prefix="/v1")
    app.include_router(webhooks.router, prefix="/v1")
    return app


app = create_app()
