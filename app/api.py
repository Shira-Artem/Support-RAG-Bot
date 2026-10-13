"""Search-only HTTP interface for future CRM integration."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.retrieval import FILTER_FIELDS, Retriever
from app.runtime import build_retriever


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
    filters: dict[str, str] = Field(default_factory=dict)


def create_app(retriever: Retriever | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.retriever is None:
            app.state.retriever = build_retriever()
        yield

    app = FastAPI(title="Support RAG Search", version="0.2.0", lifespan=lifespan)
    app.state.retriever = retriever

    @app.post("/search")
    def search(request: SearchRequest):
        if not request.query.strip():
            raise HTTPException(422, "query cannot be blank")
        if set(request.filters) - FILTER_FIELDS:
            raise HTTPException(422, "unsupported filter")
        try:
            hits = app.state.retriever.search(request.query, request.top_k, request.filters)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(503, "Search index unavailable") from exc
        return {"results": [hit.__dict__ for hit in hits]}

    return app


app = create_app()
