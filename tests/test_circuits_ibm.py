"""
Unit tests for IBM/Qiskit circuits — simulators mocked to avoid real circuit execution.
Mark tests with @pytest.mark.integration to run against real AerSimulator.
"""
import pytest
from unittest.mock import MagicMock, patch

from circuits.ibm.grover_vulnerability_scan import _severity, run_grover_scan
from circuits.ibm.quantum_risk_scorer import _derive_angles, run_risk_scorer


class TestSeverity:
    @pytest.mark.parametrize("score,expected", [
        (0.85, "critical"),
        (0.80, "critical"),
        (0.79, "high"),
        (0.60, "high"),
        (0.59, "medium"),
        (0.40, "medium"),
        (0.39, "low"),
        (0.20, "low"),
        (0.19, "none"),
        (0.0,  "none"),
    ])
    def test_thresholds(self, score, expected):
        assert _severity(score) == expected


class TestDeriveAngles:
    def test_returns_correct_count(self):
        angles = _derive_angles("test_data", 6)
        assert len(angles) == 6

    def test_deterministic(self):
        a1 = _derive_angles("same_input", 4)
        a2 = _derive_angles("same_input", 4)
        assert a1 == a2

    def test_different_inputs_differ(self):
        a1 = _derive_angles("input_a", 4)
        a2 = _derive_angles("input_b", 4)
        assert a1 != a2

    def test_values_in_range(self):
        import math
        angles = _derive_angles("data", 8)
        for angle in angles:
            assert 0.0 <= angle <= math.pi


class TestIBMGroverScanMocked:
    @pytest.fixture
    def mock_aer(self, monkeypatch):
        counts = {"0110": 820, "0001": 204}
        mock_result = MagicMock()
        mock_result.get_counts.return_value = counts
        mock_job = MagicMock()
        mock_job.result.return_value = mock_result
        mock_sim = MagicMock()
        mock_sim.run.return_value = mock_job

        monkeypatch.setattr(
            "circuits.ibm.grover_vulnerability_scan.AerSimulator", lambda: mock_sim
        )
        monkeypatch.setattr(
            "circuits.ibm.grover_vulnerability_scan.transpile", lambda qc, sim: qc
        )
        return counts

    def test_returns_required_fields(self, mock_aer):
        result = run_grover_scan("0x608060405234801561001057600080fd5b50")
        for field in ("vulnerability", "risk_score", "severity", "method", "backend"):
            assert field in result

    def test_risk_score_bounds(self, mock_aer):
        result = run_grover_scan("0xdeadbeef")
        assert 0.0 <= result["risk_score"] <= 1.0

    def test_method_label(self, mock_aer):
        result = run_grover_scan("0xdeadbeef")
        assert result["method"] == "ibm_grover_scan"

    def test_backend_label_simulator(self, mock_aer):
        result = run_grover_scan("0xdeadbeef", use_real_hardware=False)
        assert result["backend"] == "AerSimulator"

    def test_high_count_gives_reentrancy(self, mock_aer):
        # 820/1024 = 0.801 → critical reentrancy
        result = run_grover_scan("0xdeadbeef", shots=1024)
        assert result["vulnerability"] == "reentrancy_pattern"
        assert result["severity"] == "critical"


class TestIBMRiskScorerMocked:
    @pytest.fixture
    def mock_aer(self, monkeypatch):
        counts = {"111": 700, "000": 324}
        mock_result = MagicMock()
        mock_result.get_counts.return_value = counts
        mock_job = MagicMock()
        mock_job.result.return_value = mock_result
        mock_sim = MagicMock()
        mock_sim.run.return_value = mock_job

        monkeypatch.setattr(
            "circuits.ibm.quantum_risk_scorer.AerSimulator", lambda: mock_sim
        )
        monkeypatch.setattr(
            "circuits.ibm.quantum_risk_scorer.transpile", lambda qc, sim: qc
        )
        return counts

    def test_returns_required_fields(self, mock_aer):
        result = run_risk_scorer("from=0xabc,to=0xdef,value=1e18")
        for field in ("vulnerability", "risk_score", "severity", "method", "backend"):
            assert field in result

    def test_method_label(self, mock_aer):
        result = run_risk_scorer("data")
        assert result["method"] == "ibm_quantum_risk_scorer"


@pytest.mark.integration
class TestIBMGroverRealSimulator:
    """Runs against real AerSimulator — slow, skipped in CI unless -m integration."""

    def test_run_grover_scan_real(self):
        result = run_grover_scan(
            "0x608060405234801561001057600080fd5b50",
            n_qubits=3,
            shots=512,
        )
        assert 0.0 <= result["risk_score"] <= 1.0
        assert result["severity"] in ("none", "low", "medium", "high", "critical")

    def test_run_risk_scorer_real(self):
        result = run_risk_scorer("from=0xabc,to=0xdef,value=1000", n_qubits=3, shots=512)
        assert 0.0 <= result["risk_score"] <= 1.0
