"""
Unit tests for AWS Braket circuits — simulators mocked to avoid real circuit execution.
Mark tests with @pytest.mark.integration to run against real LocalSimulator.
"""
import pytest
from unittest.mock import MagicMock

from circuits.braket.grover_vulnerability_scan import _severity, run_grover_scan
from circuits.braket.quantum_risk_scorer import _derive_angles, run_risk_scorer


class TestSeverity:
    @pytest.mark.parametrize("score,expected", [
        (0.85, "critical"),
        (0.65, "high"),
        (0.50, "medium"),
        (0.25, "low"),
        (0.10, "none"),
    ])
    def test_thresholds(self, score, expected):
        assert _severity(score) == expected


class TestDeriveAngles:
    def test_deterministic(self):
        import math
        a = _derive_angles("tx_data", 6)
        assert len(a) == 6
        assert all(0.0 <= v <= math.pi for v in a)

    def test_different_inputs_differ(self):
        a1 = _derive_angles("a", 4)
        a2 = _derive_angles("b", 4)
        assert a1 != a2


class TestBraketGroverScanMocked:
    @pytest.fixture
    def mock_device(self, monkeypatch):
        counts = {"001": 700, "000": 300}
        mock_result = MagicMock()
        mock_result.measurement_counts = counts
        mock_task = MagicMock()
        mock_task.result.return_value = mock_result
        mock_dev = MagicMock()
        mock_dev.run.return_value = mock_task

        monkeypatch.setattr(
            "circuits.braket.grover_vulnerability_scan.LocalSimulator", lambda: mock_dev
        )
        return counts

    def test_returns_required_fields(self, mock_device):
        result = run_grover_scan("0x608060405234801561001057600080fd5b50")
        for field in ("vulnerability", "risk_score", "severity", "method", "backend"):
            assert field in result

    def test_risk_score_bounds(self, mock_device):
        result = run_grover_scan("0xdeadbeef")
        assert 0.0 <= result["risk_score"] <= 1.0

    def test_method_label(self, mock_device):
        result = run_grover_scan("0xdeadbeef")
        assert result["method"] == "braket_grover_scan"

    def test_backend_label_local_simulator(self, mock_device):
        result = run_grover_scan("0xdeadbeef", use_real_hardware=False)
        assert result["backend"] == "LocalSimulator"

    def test_high_count_gives_reentrancy(self, mock_device):
        # 700/1000 = 0.7 → high → reentrancy_pattern
        result = run_grover_scan("0xdeadbeef", shots=1000)
        assert result["vulnerability"] == "reentrancy_pattern"

    def test_qubit_cap_respected(self, mock_device):
        result = run_grover_scan("0xdeadbeef", n_qubits=10)
        assert result["n_qubits"] <= 3  # _MAX_QUBITS cap


class TestBraketRiskScorerMocked:
    @pytest.fixture
    def mock_device(self, monkeypatch):
        counts = {"111": 650, "000": 350}
        mock_result = MagicMock()
        mock_result.measurement_counts = counts
        mock_task = MagicMock()
        mock_task.result.return_value = mock_result
        mock_dev = MagicMock()
        mock_dev.run.return_value = mock_task

        monkeypatch.setattr(
            "circuits.braket.quantum_risk_scorer.LocalSimulator", lambda: mock_dev
        )
        return counts

    def test_returns_required_fields(self, mock_device):
        result = run_risk_scorer("from=0xabc,to=0xdef,value=1e18")
        for field in ("vulnerability", "risk_score", "severity", "method", "backend"):
            assert field in result

    def test_method_label(self, mock_device):
        result = run_risk_scorer("data")
        assert result["method"] == "braket_quantum_risk_scorer"


@pytest.mark.integration
class TestBraketRealLocalSimulator:
    """Runs against real Braket LocalSimulator — slow, skipped in CI unless -m integration."""

    def test_run_grover_scan_real(self):
        result = run_grover_scan(
            "0x608060405234801561001057600080fd5b50",
            shots=500,
        )
        assert 0.0 <= result["risk_score"] <= 1.0

    def test_run_risk_scorer_real(self):
        result = run_risk_scorer("from=0xabc,to=0xdef,value=1000", shots=500)
        assert 0.0 <= result["risk_score"] <= 1.0
