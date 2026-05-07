"""
Async orchestrator: IBM and Braket circuits always run in parallel via asyncio.gather.
Qiskit and Braket SDKs are synchronous, so circuits are offloaded to a thread pool.
"""
import asyncio
import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = ["none", "low", "medium", "high", "critical"]


def _max_severity(results: list[dict[str, Any]]) -> str:
    return max(
        (r.get("severity", "none") for r in results),
        key=lambda s: _SEVERITY_ORDER.index(s) if s in _SEVERITY_ORDER else -1,
        default="none",
    )


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "vulnerability": "unknown",
            "risk_score": 0.0,
            "severity": "none",
            "method": "aggregated_ibm_braket",
        }

    scores = [r["risk_score"] for r in results]
    avg_score = sum(scores) / len(scores)
    max_score = max(scores)
    # 70% weight on worst-case, 30% on average signal
    final_score = round(0.7 * max_score + 0.3 * avg_score, 4)

    detected = [r["vulnerability"] for r in results if r["vulnerability"] != "none_detected"]
    primary = detected[0] if detected else "none_detected"

    return {
        "vulnerability": primary,
        "risk_score": final_score,
        "severity": _max_severity(results),
        "method": "aggregated_ibm_braket",
        "sub_results": results,
    }


async def _run_ibm(request: Any) -> list[dict[str, Any]]:
    """Run IBM Grover scan and risk scorer concurrently inside a thread pool."""
    from circuits.ibm.grover_vulnerability_scan import run_grover_scan
    from circuits.ibm.quantum_risk_scorer import run_risk_scorer

    loop = asyncio.get_running_loop()
    grover, scorer = await asyncio.gather(
        loop.run_in_executor(
            None,
            lambda: run_grover_scan(
                request.contract_bytecode,
                n_qubits=request.n_qubits,
                shots=request.shots,
                use_real_hardware=request.use_real_hardware,
            ),
        ),
        loop.run_in_executor(
            None,
            lambda: run_risk_scorer(
                request.transaction_data,
                shots=request.shots,
                use_real_hardware=request.use_real_hardware,
            ),
        ),
    )
    return [grover, scorer]


async def _run_braket(request: Any) -> list[dict[str, Any]]:
    """Run Braket Grover scan and risk scorer concurrently inside a thread pool."""
    from circuits.braket.grover_vulnerability_scan import run_grover_scan
    from circuits.braket.quantum_risk_scorer import run_risk_scorer

    loop = asyncio.get_running_loop()
    grover, scorer = await asyncio.gather(
        loop.run_in_executor(
            None,
            lambda: run_grover_scan(
                request.contract_bytecode,
                shots=request.shots,
                use_real_hardware=request.use_real_hardware,
            ),
        ),
        loop.run_in_executor(
            None,
            lambda: run_risk_scorer(
                request.transaction_data,
                shots=request.shots,
                use_real_hardware=request.use_real_hardware,
            ),
        ),
    )
    return [grover, scorer]


async def run_audit(request: Any) -> Any:
    """
    Run a full quantum audit.
    IBM circuits and Braket circuits execute in parallel; results are aggregated.
    Responses are cached by request hash; individual results are retrievable by audit_id.
    """
    from core.cache import get_cache
    from core.models import AuditResponse

    audit_id = str(uuid.uuid4())
    cache = await get_cache()

    digest = hashlib.sha256(
        (request.contract_bytecode + request.transaction_data).encode()
    ).hexdigest()
    cache_key = f"audit:{digest}"
    cached = await cache.get(cache_key)
    if cached:
        logger.info("Cache hit for audit key=%s", cache_key)
        cached["audit_id"] = audit_id
        return AuditResponse(**cached)

    logger.info("Starting parallel IBM + Braket audit (audit_id=%s)", audit_id)

    timeout = int(os.getenv("AUDIT_TIMEOUT_SECONDS", "120"))
    try:
        ibm_results, braket_results = await asyncio.wait_for(
            asyncio.gather(_run_ibm(request), _run_braket(request)),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise RuntimeError(f"Audit timed out after {timeout}s")

    aggregated = _aggregate(ibm_results + braket_results)
    response = AuditResponse(
        audit_id=audit_id,
        vulnerability=aggregated["vulnerability"],
        risk_score=aggregated["risk_score"],
        severity=aggregated["severity"],
        method=aggregated["method"],
        sub_results=aggregated.get("sub_results", []),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    payload = response.model_dump()
    await asyncio.gather(
        cache.set(cache_key, payload, ttl=3600),
        cache.set(f"result:{audit_id}", payload, ttl=3600),
    )

    return response
