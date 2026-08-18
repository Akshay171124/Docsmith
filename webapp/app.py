"""FastAPI JSON API for the Docsmith web playground."""

from __future__ import annotations

import logging
import os
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from webapp import service

logger = logging.getLogger(__name__)


class AnalyzeRequest(BaseModel):
    """Request body for ``POST /api/analyze``."""

    pr_url: str
    backend: str = "ollama"
    api_key: str | None = None
    ollama_host: str | None = None
    model: str | None = None


def _cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(title="Docsmith Playground API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness probe for the deploy platform."""
    return {"status": "ok"}


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest) -> dict:
    """Analyze a public PR and return staleness verdicts + proposed fixes.

    Args:
        request: The analyze request body (PR URL, backend, and optional
            credentials/overrides).

    Returns:
        A dict shape of `webapp.service.AnalyzeResult` (`summary`, `results`).

    Raises:
        HTTPException: 400 (bad URL / missing / oversized), 502 (backend unavailable),
            500 (unexpected).
    """
    try:
        result = service.analyze(
            request.pr_url,
            request.backend,
            api_key=request.api_key,
            ollama_host=request.ollama_host,
            model=request.model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface a generic 500, never the credential
        logger.exception("analyze failed")
        raise HTTPException(status_code=500, detail="internal error") from exc
    return asdict(result)
