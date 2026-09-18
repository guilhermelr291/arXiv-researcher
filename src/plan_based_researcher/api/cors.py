"""CORS install shared by create_app and route tests."""

from __future__ import annotations

import os

from fastapi.middleware.cors import CORSMiddleware

__all__ = ["install_cors", "web_origin"]

DEFAULT_WEB_ORIGIN = "http://localhost:3000"


def web_origin() -> str:
    return os.environ.get("WEB_ORIGIN", DEFAULT_WEB_ORIGIN)


def install_cors(app, origin: str | None = None) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin or web_origin()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
