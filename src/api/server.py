"""FastAPI Application factory for SchemaLink Server."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.annotations import router as annotations_router
from src.api.routes.databases import router as databases_router
from src.api.routes.retrieval import router as retrieval_router
from src.engine import SchemaLink


def create_app(engine: SchemaLink | None = None) -> FastAPI:
    app = FastAPI(
        title="SchemaLink API",
        description="High-Precision Schema RAG & Discovery Engine for Text-to-SQL Systems",
        version="0.1.0",
    )

    app.state.schemalink = engine or SchemaLink()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(databases_router)
    app.include_router(annotations_router)
    app.include_router(retrieval_router)

    @app.get("/health")
    def health_check():
        return {"status": "ok", "service": "schemalink"}

    return app
