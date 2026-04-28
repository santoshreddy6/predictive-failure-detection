# Predictive Failure Detection in CI/CD Pipelines

> A log-based risk analysis system that predicts deployment failures **before** they reach production.

[![CI/CD Pipeline](https://github.com/santoshreddy6/predictive-failure-detection/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/santoshreddy6/predictive-failure-detection/actions/workflows/ci-cd.yml)
![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED)
![Prometheus](https://img.shields.io/badge/Monitoring-Prometheus-E6522C)

---

## The Problem

Modern CI/CD pipelines automate deployment — but **not risk evaluation**. Monitoring tools only react after a failure has already hit production, causing:

- Production crashes and service unavailability
- Costly rollbacks and resource wastage
- No pre-deployment intelligence

## The Solution

This project introduces a **lightweight predictive mechanism** inside the CI/CD pipeline. Before every deployment, pipeline logs are analyzed and a risk score is calculated. Based on the score, the deployment is automatically **ALLOWED**, **WARNED**, or **BLOCKED**.

---

## Architecture

```
Developer (git push)
        │
        ▼
┌─────────────────────────┐
│     GitHub Actions      │
│  Stage 1: Build & Test  │
│  Stage 2: Risk Gate ────┼──── logs ──► Predictor Service (Render)
│  Stage 3: Deploy        │◄─── ALLOW / WARN / BLOCK ────────────
└─────────────────────────┘
        │
        ▼
┌─────────────────────────┐
│  Prometheus + Alertmanager│  ← Monitoring & Alerts
└─────────────────────────┘
```

---

## How It Works

### Risk Scoring

The predictor service analyzes pipeline logs using **15+ weighted regex patterns**:

| Score Range | Decision | Action |
|---|---|---|
| 0 – 29 | ✅ ALLOW | Deployment proceeds |
| 30 – 59 | ⚠️ WARN | Deployment proceeds with warning |
| 60 – 100 | 🚨 BLOCK | Deployment stopped automatically |

### Risk Patterns (sample)

| Pattern | Weight |
|---|---|
| Build failed / Compilation error | +50 |
| Test failures | +30 |
| Out of memory / OOM | +35 |
| Segfault / Core dumped | +40 |
| Connection timeout | +20 |
| Non-zero exit code | +25 |
| Error / Exception / Fatal | +15 |
| Warning / Deprecated | +5 |

### Safe Patterns (reduce score)

| Pattern | Weight |
|---|---|
| All tests passed | -20 |
| Build successful | -20 |
| Health check OK | -10 |

---

## Project Structure

```
predictive-failure-detection/
├── predictor/                  # FastAPI risk analysis service
│   ├── main.py                 # Core logic — patterns, scoring, API
│   ├── requirements.txt
│   └── Dockerfile
│
├── sample-app/                 # App being deployed through the pipeline
│   ├── main.py
│   ├── tests/
│   │   └── test_main.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── .github/
│   └── workflows/
│       └── ci-cd.yml           # Full pipeline with risk gate
│
├── monitoring/
│   ├── prometheus.yml          # Scrape config
│   ├── alerts.yml              # Alert rules
│   └── alertmanager.yml        # Notification routing
│
├── scripts/
│   └── simulate_pipeline.py    # Local simulation script
│
└── docker-compose.yml          # Spin up all 4 services locally
```

---

## Quick Start (Local)

### Prerequisites
- Docker Desktop
- Python 3.11+

### 1. Clone & Start All Services

```bash
git clone https://github.com/santoshreddy6/predictive-failure-detection.git
cd predictive-failure-detection
docker compose up --build
```

| Service | URL |
|---|---|
| Predictor API | http://localhost:8001/docs |
| Sample App | http://localhost:8080 |
| Prometheus | http://localhost:9090 |
| Alertmanager | http://localhost:9093 |

### 2. Test the Predictor

**Healthy logs → ALLOW:**
```bash
curl -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "logs": "All tests passed. Build successful. Health check ok.",
    "pipeline_id": "run-001",
    "branch": "main",
    "commit_sha": "abc123"
  }'
```

**Risky logs → BLOCK:**
```bash
curl -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "logs": "ERROR: Build failed. 3 tests failed. Connection timeout. Fatal error. Exit code 1.",
    "pipeline_id": "run-002",
    "branch": "feature/broken",
    "commit_sha": "def456"
  }'
```

### 3. Run Pipeline Simulator

```bash
# Healthy pipeline (should ALLOW)
python scripts/simulate_pipeline.py

# Risky pipeline (should BLOCK)
python scripts/simulate_pipeline.py --inject-errors

# Run real pytest suite and analyze
python scripts/simulate_pipeline.py --real-tests
```

---

## Live Deployment

| Resource | URL |
|---|---|
| Predictor API (Live) | https://predictive-failure-detection.onrender.com |
| Swagger Docs (Live) | https://predictive-failure-detection.onrender.com/docs |
| GitHub Actions | [View Runs](https://github.com/santoshreddy6/predictive-failure-detection/actions) |

---

## GitHub Actions Setup

### Required Secrets

Go to `Settings → Secrets → Actions` and add:

| Secret | Value |
|---|---|
| `PREDICTOR_URL` | `https://predictive-failure-detection.onrender.com` |
| `SLACK_WEBHOOK_URL` | *(optional)* Slack incoming webhook URL |

### Pipeline Stages

```
Push to any branch
        │
        ├── Stage 1: Build & Test
        │     ├── Install dependencies
        │     ├── Run pytest
        │     ├── Build Docker image
        │     └── Upload logs as artifact
        │
        ├── Stage 2: Risk Analysis Gate
        │     ├── Download log artifact
        │     ├── Wake up predictor (Render free tier)
        │     ├── POST logs to /analyze
        │     ├── Read ALLOW / WARN / BLOCK decision
        │     └── Fail pipeline if BLOCK
        │
        └── Stage 3: Deploy (main branch only)
              └── Runs only if risk gate passed
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Service info |
| GET | `/health` | Health check |
| POST | `/analyze` | Submit logs, get risk decision |
| GET | `/metrics` | Prometheus metrics |
| GET | `/thresholds` | View scoring thresholds |
| GET | `/docs` | Swagger interactive UI |

### POST `/analyze` — Request

```json
{
  "logs": "<full pipeline log output>",
  "pipeline_id": "run-123",
  "branch": "main",
  "commit_sha": "abc1234"
}
```

### POST `/analyze` — Response

```json
{
  "pipeline_id": "run-123",
  "branch": "main",
  "commit_sha": "abc1234",
  "risk_score": 75,
  "decision": "BLOCK",
  "matched_patterns": [
    { "label": "Build Failure", "count": 1, "weight_contribution": 50 },
    { "label": "Test Failures", "count": 2, "weight_contribution": 30 }
  ],
  "safe_patterns": [],
  "summary": "High risk detected (score=75). Deployment BLOCKED.",
  "analyzed_at": 1712345678.0,
  "log_line_count": 42
}
```

---

## Monitoring

### Prometheus Alert Rules

| Alert | Trigger | Severity |
|---|---|---|
| `PredictorServiceDown` | Predictor unreachable for 1 min | Critical |
| `SampleAppDown` | App unreachable for 2 min | Critical |

### Enable Slack Alerts

Edit `monitoring/alertmanager.yml`:

```yaml
receivers:
  - name: "slack"
    slack_configs:
      - api_url: "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
        channel: "#ci-cd-alerts"
        title: "{{ .CommonAnnotations.summary }}"
        text:  "{{ .CommonAnnotations.description }}"
```

---

## Tech Stack

| Component | Technology |
|---|---|
| Risk Analysis Service | Python 3.11, FastAPI |
| CI/CD Pipeline | GitHub Actions |
| Containerization | Docker, Docker Compose |
| Monitoring | Prometheus v2.51 |
| Alerting | Alertmanager v0.27 |
| Cloud Deployment | Render |
| Version Control | GitHub |

---

## Author

**U Santosh Reddy**
Roll No: 12212258 | CSE435 Project
[GitHub](https://github.com/santoshreddy6) · [LinkedIn](https://linkedin.com/in/your-profile)
