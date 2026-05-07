from typing import Any

from pydantic import BaseModel, Field


class AuditRequest(BaseModel):
    contract_bytecode: str = Field(..., description="Smart contract bytecode or source code to audit")
    transaction_data: str = Field(..., description="Transaction metadata for risk scoring")
    use_real_hardware: bool = Field(False, description="Route to real QPU (incurs cost)")
    n_qubits: int = Field(4, ge=2, le=10, description="Qubit count for IBM circuits")
    shots: int = Field(1024, ge=100, le=10000, description="Measurement shots per circuit")


class AuditResponse(BaseModel):
    audit_id: str
    vulnerability: str
    risk_score: float = Field(..., ge=0.0, le=1.0)
    severity: str
    method: str
    sub_results: list[dict[str, Any]] = []
    timestamp: str = ""
