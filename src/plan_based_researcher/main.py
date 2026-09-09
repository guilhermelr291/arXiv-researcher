"""FastAPI process: compile the graph once, ping Postgres (PAT-07, PAT-12, THR-01)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from plan_based_researcher.adapters.arxiv import ArxivPaperAdapter
from plan_based_researcher.adapters.hybrid import HybridRetrieveAdapter
from plan_based_researcher.adapters.voyage_embeddings import VoyageEmbeddingAdapter
from plan_based_researcher.agents.factory import AgentFactory
from plan_based_researcher.api.executor import ResearchExecutor
from plan_based_researcher.api.routes import router
from plan_based_researcher.api.stream_dispatcher import StreamDispatcher
from plan_based_researcher.config import Settings
from plan_based_researcher.eval.strategies import (
    RetrieveEvalStrategy,
    SearchEvalStrategy,
)
from plan_based_researcher.graph.build import GraphDeps
from plan_based_researcher.graph.research_graph import ResearchGraph
from plan_based_researcher.repo.chunks import PgChunkRepository


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        kwargs={"autocommit": True, "row_factory": dict_row},
        open=False,
    )
    await pool.open()
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()
    repo = PgChunkRepository(pool)
    await repo.ensure_schema()
    embeddings = VoyageEmbeddingAdapter(api_key=settings.voyage_api_key)
    papers = ArxivPaperAdapter(mock_arxiv_id=settings.mock_arxiv_id or None)
    hybrid = HybridRetrieveAdapter(repo, embeddings)
    factory = AgentFactory(
        papers,
        repo,
        embeddings,
        hybrid,
        api_key=settings.openai_api_key,
        voyage_api_key=settings.voyage_api_key,
    )
    deps = GraphDeps(
        factory=factory,
        search_eval=SearchEvalStrategy(api_key=settings.openai_api_key),
        retrieve_eval=RetrieveEvalStrategy(api_key=settings.openai_api_key),
    )
    app.state.settings = settings
    app.state.pool = pool
    app.state.executor = ResearchExecutor(
        ResearchGraph(deps, checkpointer=checkpointer),
        StreamDispatcher.default(),
    )
    yield
    await pool.close()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.include_router(router)

    @app.get("/health")
    async def health():
        pool = app.state.pool
        async with pool.connection() as conn:
            await conn.execute("SELECT 1")
        return {"status": "ok"}

    return app


app = create_app()
