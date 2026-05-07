"""
AuditSmart Quantum — FastAPI application.

Start with:
    gunicorn api.endpoints:app -c gunicorn.conf.py
    # or for development:
    uvicorn api.endpoints:app --host 0.0.0.0 --port 8001 --reload
"""
import logging
import os
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

load_dotenv()

from core.logging_config import configure_logging
from core.cache import get_cache, RedisCache
from core.models import AuditRequest, AuditResponse
from core.orchestrator import run_audit

configure_logging()
logger = logging.getLogger(__name__)

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    _rate_limit_storage = os.getenv("RATE_LIMIT_STORAGE", "memory://")
    limiter = Limiter(key_func=get_remote_address, storage_uri=_rate_limit_storage)
    _rate_limiting_enabled = True
except ImportError:
    limiter = None
    _rate_limiting_enabled = False
    logger.warning("slowapi not installed — rate limiting disabled")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_cache()
    yield


app = FastAPI(
    title="AuditSmart Quantum",
    description=(
        "Quantum-powered smart contract and transaction auditing. "
        "IBM (Qiskit/AerSimulator) and AWS Braket circuits run in parallel."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

_allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)
app.add_middleware(RequestIDMiddleware)

if _rate_limiting_enabled:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/health", tags=["System"])
async def health():
    cache = await get_cache()
    return {
        "status": "ok",
        "service": "auditsmart-quantum",
        "version": "1.0.0",
        "cache": "redis" if isinstance(cache, RedisCache) else "in-memory",
    }


def _audit_route(func):
    """Apply rate limit decorator only when slowapi is available."""
    if _rate_limiting_enabled:
        return limiter.limit(os.getenv("RATE_LIMIT_AUDIT", "10/minute"))(func)
    return func


@app.post(
    "/audit",
    response_model=AuditResponse,
    status_code=status.HTTP_200_OK,
    tags=["Audit"],
    summary="Run a full quantum audit (IBM + Braket in parallel)",
)
@_audit_route
async def audit_contract(request: Request, body: AuditRequest) -> AuditResponse:
    """
    Submit a smart contract and transaction data for quantum vulnerability analysis.
    IBM and Braket circuits run concurrently; results are aggregated and cached.
    Set `use_real_hardware: true` to route to real QPUs (incurs cost).
    """
    try:
        return await run_audit(body)
    except Exception as exc:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.error("Audit failed request_id=%s: %s", request_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Audit failed. Check server logs for details.",
        )


@app.get(
    "/results/{audit_id}",
    response_model=AuditResponse,
    tags=["Audit"],
    summary="Retrieve a cached audit result by ID",
)
async def get_result(audit_id: str) -> AuditResponse:
    cache = await get_cache()
    data = await cache.get(f"result:{audit_id}")
    if data is None:
        raise HTTPException(status_code=404, detail=f"Audit result '{audit_id}' not found")
    return AuditResponse(**data)
