"""FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from contractguard import __version__
from contractguard.api.routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app() -> FastAPI:
    app = FastAPI(
        title="contractguard",
        description="Contract review assistant: clause segmentation, risk-pattern detection with severity, obligation extraction with deadlines, and clause-library RAG with cited answers.",
        version=__version__,
    )
    app.include_router(router)
    return app


app = create_app()
