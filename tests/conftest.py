import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

IBM_GROVER = {
    "vulnerability": "reentrancy_pattern",
    "risk_score": 0.72,
    "severity": "high",
    "method": "ibm_grover_scan",
    "n_qubits": 4,
    "shots": 1024,
    "backend": "AerSimulator",
}
IBM_SCORER = {
    "vulnerability": "none_detected",
    "risk_score": 0.10,
    "severity": "none",
    "method": "ibm_quantum_risk_scorer",
    "n_qubits": 3,
    "shots": 1024,
    "backend": "AerSimulator",
}
BRAKET_GROVER = {
    "vulnerability": "access_control_weakness",
    "risk_score": 0.45,
    "severity": "medium",
    "method": "braket_grover_scan",
    "n_qubits": 3,
    "shots": 1000,
    "backend": "LocalSimulator",
}
BRAKET_SCORER = {
    "vulnerability": "none_detected",
    "risk_score": 0.15,
    "severity": "none",
    "method": "braket_quantum_risk_scorer",
    "n_qubits": 3,
    "shots": 1000,
    "backend": "LocalSimulator",
}

SAMPLE_REQUEST = {
    "contract_bytecode": "0x608060405234801561001057600080fd5b50",
    "transaction_data": "from=0xabc123,to=0xdef456,value=1000000000000000000",
    "use_real_hardware": False,
    "n_qubits": 4,
    "shots": 1024,
}


@pytest.fixture(autouse=True)
def reset_cache_singleton():
    import core.cache as cache_module

    cache_module._cache_instance = None
    yield
    cache_module._cache_instance = None


@pytest.fixture
def mock_circuits():
    with (
        patch(
            "circuits.ibm.grover_vulnerability_scan.run_grover_scan",
            return_value=IBM_GROVER,
        ),
        patch(
            "circuits.ibm.quantum_risk_scorer.run_risk_scorer",
            return_value=IBM_SCORER,
        ),
        patch(
            "circuits.braket.grover_vulnerability_scan.run_grover_scan",
            return_value=BRAKET_GROVER,
        ),
        patch(
            "circuits.braket.quantum_risk_scorer.run_risk_scorer",
            return_value=BRAKET_SCORER,
        ),
    ):
        yield


@pytest.fixture
def client(mock_circuits):
    from api.endpoints import app

    with TestClient(app) as c:
        yield c
