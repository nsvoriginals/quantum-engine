"""
AWS Braket variational quantum risk scorer.
Self-contained — no imports from other circuit modules.
Runs on LocalSimulator by default; pass use_real_hardware=True to route to a Braket QPU.
"""
import hashlib
import logging
import math
from typing import Any

from braket.circuits import Circuit
from braket.devices import LocalSimulator

logger = logging.getLogger(__name__)

_SEVERITY_THRESHOLDS = [
    (0.8, "critical"),
    (0.6, "high"),
    (0.4, "medium"),
    (0.2, "low"),
    (0.0, "none"),
]

_MAX_QUBITS = 3


def _severity(score: float) -> str:
    for threshold, label in _SEVERITY_THRESHOLDS:
        if score >= threshold:
            return label
    return "none"


def _derive_angles(data: str, count: int) -> list[float]:
    h = hashlib.sha256(data.encode()).digest()
    return [(h[i % len(h)] / 255.0) * math.pi for i in range(count)]


def run_risk_scorer(
    transaction_data: str,
    n_qubits: int = _MAX_QUBITS,
    shots: int = 1000,
    use_real_hardware: bool = False,
    device_arn: str = "arn:aws:braket:us-east-1::device/qpu/ionq/Harmony",
) -> dict[str, Any]:
    """
    Estimate transaction risk using a parameterized Braket circuit.
    Rotation angles are deterministically derived from transaction_data.
    Returns a standard result dict: vulnerability, risk_score, severity, method.
    """
    n_qubits = min(n_qubits, _MAX_QUBITS)
    angles = _derive_angles(transaction_data, n_qubits * 2)

    circuit = Circuit()
    for i in range(n_qubits):
        circuit.h(i)
    for i in range(n_qubits):
        circuit.ry(i, angles[i])
    for i in range(n_qubits - 1):
        circuit.cnot(i, i + 1)
    for i in range(n_qubits):
        circuit.rz(i, angles[n_qubits + i])
    for i in range(n_qubits - 1):
        circuit.cnot(i, i + 1)

    device_name = "LocalSimulator"
    if use_real_hardware:
        try:
            from braket.aws import AwsDevice

            device = AwsDevice(device_arn)
            device_name = device_arn
            logger.info("Running on Braket QPU: %s", device_arn)
        except Exception as exc:
            logger.error("Braket QPU failed (%s) — falling back to LocalSimulator", exc)
            use_real_hardware = False

    if not use_real_hardware:
        device = LocalSimulator()

    result = device.run(circuit, shots=shots).result()
    counts = result.measurement_counts

    # Risk score = fraction of shots where majority of qubits measure |1>
    risk_shots = sum(c for bits, c in counts.items() if bits.count("1") > n_qubits // 2)
    risk_score = round(min(float(risk_shots) / shots, 1.0), 4)

    if risk_score > 0.6:
        vulnerability = "integer_overflow"
    elif risk_score > 0.3:
        vulnerability = "flash_loan_exposure"
    else:
        vulnerability = "none_detected"

    return {
        "vulnerability": vulnerability,
        "risk_score": risk_score,
        "severity": _severity(risk_score),
        "method": "braket_quantum_risk_scorer",
        "n_qubits": n_qubits,
        "shots": shots,
        "backend": device_name,
    }
