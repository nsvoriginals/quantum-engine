"""
IBM/Qiskit variational quantum risk scorer.
Self-contained — no imports from other circuit modules.
Runs on AerSimulator by default; pass use_real_hardware=True to route to IBM Quantum.
"""
import hashlib
import logging
from typing import Any

import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

logger = logging.getLogger(__name__)

_SEVERITY_THRESHOLDS = [
    (0.8, "critical"),
    (0.6, "high"),
    (0.4, "medium"),
    (0.2, "low"),
    (0.0, "none"),
]


def _severity(score: float) -> str:
    for threshold, label in _SEVERITY_THRESHOLDS:
        if score >= threshold:
            return label
    return "none"


def _derive_angles(data: str, count: int) -> list[float]:
    h = hashlib.sha256(data.encode()).digest()
    return [(h[i % len(h)] / 255.0) * np.pi for i in range(count)]


def _build_vqc(n_qubits: int, angles: list[float]) -> QuantumCircuit:
    """Two-layer parameterized circuit: RY → CNOT ladder → RZ → CNOT ladder."""
    qc = QuantumCircuit(n_qubits, n_qubits)
    qc.h(range(n_qubits))
    for i in range(n_qubits):
        qc.ry(angles[i], i)
    for i in range(n_qubits - 1):
        qc.cx(i, i + 1)
    for i in range(n_qubits):
        qc.rz(angles[n_qubits + i], i)
    for i in range(n_qubits - 1):
        qc.cx(i, i + 1)
    qc.measure(range(n_qubits), range(n_qubits))
    return qc


def run_risk_scorer(
    transaction_data: str,
    n_qubits: int = 3,
    shots: int = 1024,
    use_real_hardware: bool = False,
) -> dict[str, Any]:
    """
    Estimate transaction risk using a parameterized (variational) quantum circuit.
    Rotation angles are deterministically derived from transaction_data.
    Returns a standard result dict: vulnerability, risk_score, severity, method.
    """
    angles = _derive_angles(transaction_data, n_qubits * 2)
    qc = _build_vqc(n_qubits, angles)

    backend_name = "AerSimulator"
    counts: dict[str, int] = {}

    if use_real_hardware:
        try:
            from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

            service = QiskitRuntimeService()
            backend = service.least_busy(operational=True, simulator=False)
            backend_name = backend.name
            logger.info("Running on IBM QPU: %s", backend_name)
            tqc = transpile(qc, backend)
            job = Sampler(backend).run([tqc], shots=shots)
            counts = job.result()[0].data.c.get_counts()
        except Exception as exc:
            logger.error("IBM QPU failed (%s) — falling back to AerSimulator", exc)
            use_real_hardware = False
            backend_name = "AerSimulator"

    if not use_real_hardware:
        sim = AerSimulator()
        tqc = transpile(qc, sim)
        counts = sim.run(tqc, shots=shots).result().get_counts()

    # Risk score = fraction of shots where a majority of qubits measure |1>
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
        "method": "ibm_quantum_risk_scorer",
        "n_qubits": n_qubits,
        "shots": shots,
        "backend": backend_name,
    }
