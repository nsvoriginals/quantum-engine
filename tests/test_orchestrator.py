"""Unit tests for aggregation logic and orchestrator helpers."""
import pytest
from core.orchestrator import _aggregate, _max_severity


class TestMaxSeverity:
    def test_picks_highest(self):
        results = [
            {"severity": "low"},
            {"severity": "high"},
            {"severity": "medium"},
        ]
        assert _max_severity(results) == "high"

    def test_critical_wins(self):
        results = [{"severity": "critical"}, {"severity": "high"}]
        assert _max_severity(results) == "critical"

    def test_empty_returns_none(self):
        assert _max_severity([]) == "none"

    def test_all_none(self):
        results = [{"severity": "none"}, {"severity": "none"}]
        assert _max_severity(results) == "none"

    def test_unknown_severity_ignored(self):
        results = [{"severity": "low"}, {"severity": "bogus"}]
        assert _max_severity(results) == "low"


class TestAggregate:
    def test_empty_input(self):
        result = _aggregate([])
        assert result["vulnerability"] == "unknown"
        assert result["risk_score"] == 0.0
        assert result["severity"] == "none"

    def test_weighted_score(self):
        results = [{"vulnerability": "none_detected", "risk_score": 0.8, "severity": "critical"},
                   {"vulnerability": "none_detected", "risk_score": 0.2, "severity": "low"}]
        agg = _aggregate(results)
        # 0.7 * 0.8 + 0.3 * 0.5 = 0.56 + 0.15 = 0.71
        assert agg["risk_score"] == pytest.approx(0.71, abs=0.001)

    def test_primary_vulnerability_is_first_detected(self):
        results = [
            {"vulnerability": "none_detected", "risk_score": 0.1, "severity": "none"},
            {"vulnerability": "reentrancy_pattern", "risk_score": 0.8, "severity": "critical"},
            {"vulnerability": "integer_overflow", "risk_score": 0.7, "severity": "high"},
        ]
        agg = _aggregate(results)
        assert agg["vulnerability"] == "reentrancy_pattern"

    def test_all_none_detected(self):
        results = [{"vulnerability": "none_detected", "risk_score": 0.05, "severity": "none"}]
        agg = _aggregate(results)
        assert agg["vulnerability"] == "none_detected"

    def test_sub_results_preserved(self):
        results = [
            {"vulnerability": "reentrancy_pattern", "risk_score": 0.72, "severity": "high"},
            {"vulnerability": "none_detected", "risk_score": 0.10, "severity": "none"},
        ]
        agg = _aggregate(results)
        assert agg["sub_results"] == results

    def test_method_label(self):
        results = [{"vulnerability": "none_detected", "risk_score": 0.1, "severity": "none"}]
        assert _aggregate(results)["method"] == "aggregated_ibm_braket"
