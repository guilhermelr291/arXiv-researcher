"""CORS install shared by create_app and route tests."""

from __future__ import annotations

from fastapi.middleware.cors import CORSMiddleware

from plan_based_researcher.config import DEFAULT_WEB_ORIGIN, web_origin

__all__ = ["DEFAULT_WEB_ORIGIN", "install_cors", "web_origin"]


def install_cors(app, origin: str | None = None) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin or web_origin()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
