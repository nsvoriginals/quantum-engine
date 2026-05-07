"""HTTP-layer tests for all endpoints."""
import pytest
from tests.conftest import SAMPLE_REQUEST


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "auditsmart-quantum"
    assert data["version"] == "1.0.0"
    assert data["cache"] in ("redis", "in-memory")


def test_health_includes_request_id_header(client):
    resp = client.get("/health")
    assert "x-request-id" in resp.headers


def test_audit_success(client):
    resp = client.post("/audit", json=SAMPLE_REQUEST)
    assert resp.status_code == 200
    data = resp.json()
    assert "audit_id" in data
    assert data["vulnerability"] in [
        "reentrancy_pattern",
        "access_control_weakness",
        "integer_overflow",
        "flash_loan_exposure",
        "none_detected",
    ]
    assert 0.0 <= data["risk_score"] <= 1.0
    assert data["severity"] in ("none", "low", "medium", "high", "critical")
    assert data["method"] == "aggregated_ibm_braket"
    assert isinstance(data["sub_results"], list)
    assert len(data["sub_results"]) == 4


def test_audit_result_cached(client):
    resp1 = client.post("/audit", json=SAMPLE_REQUEST)
    resp2 = client.post("/audit", json=SAMPLE_REQUEST)
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    # Risk scores are identical when cache is hit
    assert resp1.json()["risk_score"] == resp2.json()["risk_score"]


def test_audit_result_retrievable_by_id(client):
    post_resp = client.post("/audit", json=SAMPLE_REQUEST)
    assert post_resp.status_code == 200
    audit_id = post_resp.json()["audit_id"]

    get_resp = client.get(f"/results/{audit_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["audit_id"] == audit_id


def test_results_not_found(client):
    resp = client.get("/results/nonexistent-id-00000000")
    assert resp.status_code == 404


def test_audit_invalid_payload_missing_fields(client):
    resp = client.post("/audit", json={})
    assert resp.status_code == 422


def test_audit_invalid_qubits_too_high(client):
    bad = {**SAMPLE_REQUEST, "n_qubits": 99}
    resp = client.post("/audit", json=bad)
    assert resp.status_code == 422


def test_audit_invalid_shots_too_low(client):
    bad = {**SAMPLE_REQUEST, "shots": 10}
    resp = client.post("/audit", json=bad)
    assert resp.status_code == 422


def test_audit_different_inputs_give_different_cache_keys(client, mock_circuits):
    req_a = {**SAMPLE_REQUEST, "contract_bytecode": "0xAABBCC"}
    req_b = {**SAMPLE_REQUEST, "contract_bytecode": "0x112233"}
    resp_a = client.post("/audit", json=req_a)
    resp_b = client.post("/audit", json=req_b)
    assert resp_a.status_code == 200
    assert resp_b.status_code == 200
    # Different inputs — different audit IDs (cache misses, new UUIDs)
    assert resp_a.json()["audit_id"] != resp_b.json()["audit_id"]


def test_audit_error_does_not_leak_internals(client, mock_circuits):
    from unittest.mock import patch, AsyncMock

    with patch("api.endpoints.run_audit", new_callable=AsyncMock, side_effect=RuntimeError("secret internal state")):
        resp = client.post("/audit", json=SAMPLE_REQUEST)
    assert resp.status_code == 500
    assert "secret internal state" not in resp.json()["detail"]
