from fastapi import FastAPI

from .routes import agents, ledger, lineage, billing


def create_app() -> FastAPI:
    app = FastAPI(title="Project Genome Ledger", version="1.0.0")

    app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
    app.include_router(ledger.router, prefix="/api/v1/ledger", tags=["ledger"])
    app.include_router(lineage.router, prefix="/api/v1/lineage", tags=["lineage"])
    app.include_router(billing.router, prefix="/api/v1/billing", tags=["billing"])

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
