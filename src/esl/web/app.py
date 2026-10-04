from fastapi import FastAPI

from esl.web.routers import catalog, central, health, stores, tags, webhooks


def create_app() -> FastAPI:
    app = FastAPI(title="ESL Pricing Service")
    app.include_router(health.router, prefix="/v1")
    app.include_router(catalog.router, prefix="/v1")
    app.include_router(stores.router, prefix="/v1")
    app.include_router(tags.router, prefix="/v1")
    app.include_router(webhooks.router, prefix="/v1")
    # The store gateway's own contract (api/central-esl-api.yaml) uses
    # absolute /api/... paths, so it mounts without the /v1 prefix.
    app.include_router(central.router)
    return app


app = create_app()
