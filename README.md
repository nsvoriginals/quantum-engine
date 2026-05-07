# AuditSmart Quantum

Quantum-powered smart contract and transaction auditing platform.  
IBM (Qiskit / AerSimulator) and AWS Braket (LocalSimulator) circuits run **in parallel** to detect vulnerabilities and produce a risk score.

---

## Architecture

```
auditsmart-quantum/
├── api/
│   └── endpoints.py          ← FastAPI app (uvicorn entry point)
├── circuits/
│   ├── ibm/
│   │   ├── grover_vulnerability_scan.py   ← Grover's algorithm (Qiskit)
│   │   └── quantum_risk_scorer.py         ← Parameterized VQC (Qiskit)
│   └── braket/
│       ├── grover_vulnerability_scan.py   ← Grover's algorithm (Braket)
│       └── quantum_risk_scorer.py         ← Parameterized VQC (Braket)
├── core/
│   ├── cache.py              ← Redis + in-memory fallback
│   ├── models.py             ← Pydantic request / response models
│   └── orchestrator.py       ← Async parallel orchestration
├── .env.example
├── requirements.txt
└── README.md
```

**Default backends (no cost, no network)**  
- IBM → `AerSimulator`  
- Braket → `LocalSimulator`  

Set `"use_real_hardware": true` in the request body to route to real QPUs.

---

## Setup

### Prerequisites

- Python 3.11+
- Redis *(optional — app falls back to in-memory dict if unavailable)*

### Install

```bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements.txt
```

### Environment Variables

```bash
cp .env.example .env
# Edit .env — only REDIS_URL and credentials for real QPU access are needed
```

| Variable | Required | Description |
|---|---|---|
| `REDIS_URL` | No | Redis URL (default: `redis://localhost:6379`) |
| `LOG_LEVEL` | No | `DEBUG` / `INFO` / `WARNING` (default: `INFO`) |
| `IBM_QUANTUM_TOKEN` | Real QPU only | IBM Quantum API token |
| `AWS_ACCESS_KEY_ID` | Real QPU only | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | Real QPU only | AWS secret |
| `AWS_DEFAULT_REGION` | Real QPU only | AWS region (default: `us-east-1`) |

---

## How to Run

```bash
uvicorn api.endpoints:app --host 0.0.0.0 --port 8001 --reload
```

Interactive API docs: <http://localhost:8001/docs>

---

## How to Call the API

### Health check

```bash
curl http://localhost:8001/health
```

### Run a quantum audit

```bash
curl -X POST http://localhost:8001/audit \
  -H "Content-Type: application/json" \
  -d '{
    "contract_bytecode": "0x608060405234801561001057600080fd5b50",
    "transaction_data": "from=0xabc123,to=0xdef456,value=1000000000000000000",
    "use_real_hardware": false,
    "n_qubits": 4,
    "shots": 1024
  }'
```

**Example response**

```json
{
  "audit_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "vulnerability": "reentrancy_pattern",
  "risk_score": 0.6823,
  "severity": "high",
  "method": "aggregated_ibm_braket",
  "sub_results": [
    {
      "vulnerability": "reentrancy_pattern",
      "risk_score": 0.72,
      "severity": "high",
      "method": "ibm_grover_scan",
      "n_qubits": 4,
      "shots": 1024,
      "backend": "AerSimulator"
    },
    { "...": "..." }
  ],
  "timestamp": "2026-04-24T12:00:00+00:00"
}
```

### Retrieve a cached result by ID

```bash
curl http://localhost:8001/results/<audit_id>
```

### Python client example

```python
import httpx

resp = httpx.post("http://localhost:8001/audit", json={
    "contract_bytecode": "0x608060405...",
    "transaction_data": "from=0xabc,to=0xdef,value=1000000",
    "use_real_hardware": False,
})
data = resp.json()
print(data["severity"], data["risk_score"])
```

---

## All Result Fields

Every circuit and the aggregated response always returns these fields:

| Field | Type | Description |
|---|---|---|
| `vulnerability` | `str` | Detected vulnerability label or `none_detected` |
| `risk_score` | `float` 0.0–1.0 | Aggregated quantum risk probability |
| `severity` | `str` | `none` / `low` / `medium` / `high` / `critical` |
| `method` | `str` | Circuit / aggregation method identifier |

---

## Cost Table

| Tier | Compute | Shots / month | Est. Monthly Cost |
|---|---|---|---|
| **MVP** | AerSimulator + LocalSimulator only | Unlimited | **$0** |
| **Growth** | + IBM Quantum Pay-as-you-go | ~10 000 QPU shots | **~$100 – $500** |
| **Scale** | + AWS Braket IonQ / Rigetti + IBM Quantum | 100 000+ QPU shots | **~$1 000 – $5 000** |

> **IBM Quantum** (Pay-as-you-go): ~$1.60 / second of QPU runtime  
> **AWS Braket — IonQ**: $0.01 / two-qubit gate + $0.30 / task  
> **AWS Braket — Rigetti**: $0.00035 / shot + $0.00030 / task  
> **AWS Braket — SV1** (cloud simulator): $0.075 / simulation-hour  
> **AWS Braket — TN1** (cloud simulator): $0.275 / simulation-minute  

All simulator runs (default) are free.

---

## Redis Failover

If Redis is unreachable at startup the application logs a warning and automatically falls back to an in-memory dict:

```
WARNING  core.cache — Redis connection failed (...) — using in-memory dict fallback
```

No manual intervention is required; the API continues to serve requests normally.  
Restart with Redis available to restore persistence and cross-process caching.
