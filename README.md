# Predictive Failure Detection in CI/CD Pipelines
> Log-Based Risk Analysis to prevent deployment failures before they happen.

---

## Architecture

```
Developer pushes code
        │
        ▼
┌─────────────────────┐
│  GitHub Actions     │  ← CI/CD Pipeline
│  1. Build & Test    │
│  2. Collect Logs    │
└────────┬────────────┘
         │  logs (JSON)
         ▼
┌─────────────────────┐
│  Predictor Service  │  ← FastAPI  (port 8000)
│  - Pattern matching │
│  - Risk scoring     │
│  - ALLOW/WARN/BLOCK │
└────────┬────────────┘
         │  decision
         ▼
┌─────────────────────┐
│  Deploy Gate        │
│  ALLOW → deploy     │
│  WARN  → deploy +   │
│          alert      │
│  BLOCK → stop +     │
│          notify     │
└─────────────────────┘
         │
         ▼
┌─────────────────────┐
│  Prometheus         │  ← Monitoring (port 9090)
│  Alertmanager       │  ← Alerting   (port 9093)
└─────────────────────┘
```

---

## Project Structure

```
predictive-failure-detection/
├── predictor/               # FastAPI risk analysis service
│   ├── main.py              # Core logic — patterns, scoring, API
│   ├── requirements.txt
│   └── Dockerfile
│
├── sample-app/              # The app being deployed through the pipeline
│   ├── main.py
│   ├── tests/
│   │   └── test_main.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── .github/
│   └── workflows/
│       └── ci-cd.yml        # GitHub Actions pipeline with risk gate
│
├── monitoring/
│   ├── prometheus.yml       # Scrape config
│   ├── alerts.yml           # Alert rules
│   └── alertmanager.yml     # Email + Slack routing
│
├── scripts/
│   └── simulate_pipeline.py # Local simulation without GitHub Actions
│
└── docker-compose.yml       # Spin up everything locally
```

---

## Quick Start (Local)

### 1. Clone & Start Everything

```bash
git clone <your-repo>
cd predictive-failure-detection

docker compose up --build
```

| Service      | URL                        |
|--------------|----------------------------|
| Predictor    | http://localhost:8000      |
| Predictor UI | http://localhost:8000/docs |
| Sample App   | http://localhost:8080      |
| Prometheus   | http://localhost:9090      |
| Alertmanager | http://localhost:9093      |

---

### 2. Test the Predictor Directly

**Healthy logs → ALLOW:**
```bash
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "logs": "All tests passed. Build successful.",
    "pipeline_id": "run-001",
    "branch": "main",
    "commit_sha": "abc123"
  }' | jq .
```

**Risky logs → BLOCK:**
```bash
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "logs": "ERROR: Build failed. 3 tests failed. Connection timeout. Fatal error.",
    "pipeline_id": "run-002",
    "branch": "feature/risky",
    "commit_sha": "def456"
  }' | jq .
```

---

### 3. Run the Pipeline Simulator

```bash
# Simulate with healthy logs (should ALLOW)
python scripts/simulate_pipeline.py

# Simulate with risky logs (should BLOCK)
python scripts/simulate_pipeline.py --inject-errors

# Run real pytest suite and analyze
python scripts/simulate_pipeline.py --real-tests
```

---

## GitHub Actions Setup

### Required Secrets

Go to `Settings → Secrets → Actions` in your GitHub repo and add:

| Secret              | Value                                    |
|---------------------|------------------------------------------|
| `PREDICTOR_URL`     | URL where your predictor is hosted       |
| `SLACK_WEBHOOK_URL` | (optional) Slack incoming webhook URL    |

### How the Pipeline Works

1. **Build & Test** — installs deps, runs pytest, builds Docker image, collects all output into a log file
2. **Risk Analysis Gate** — downloads the log artifact, POSTs to predictor, reads decision
   - `ALLOW` → pipeline continues
   - `WARN`  → pipeline continues, warning annotation added, Slack notified
   - `BLOCK` → pipeline fails, deployment stopped, Slack alert sent
3. **Deploy** — only runs on `main`/`master` after gate passes

---

## Risk Scoring

### How Scores Are Calculated

Each line of the pipeline log is matched against patterns. Matched patterns add weight to the risk score. Safe patterns reduce it.

| Score Range | Decision | Meaning                            |
|-------------|----------|------------------------------------|
| 0 – 29      | ✅ ALLOW  | Pipeline looks healthy             |
| 30 – 59     | ⚠️ WARN   | Issues found, proceed with caution |
| 60 – 100    | 🚨 BLOCK  | High risk, deployment stopped      |

### Risk Patterns (sample)

| Pattern                    | Weight |
|----------------------------|--------|
| Error / Exception / Fatal  | +15    |
| Build Failed               | +50    |
| Test Failures              | +30    |
| OOM / Out of Memory        | +35    |
| Segfault                   | +40    |
| Timeout                    | +20    |
| Warning / Deprecated       | +5     |
| Non-zero Exit Code         | +25    |

### Safe Patterns (reduce score)

| Pattern            | Weight |
|--------------------|--------|
| All Tests Passed   | -20    |
| Build Successful   | -20    |
| Health Check OK    | -10    |

---

## Monitoring (Prometheus + Alertmanager)

### Configure Alerting

Edit `monitoring/alertmanager.yml`:

```yaml
# Slack
api_url: "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# Email
smtp_smarthost: "smtp.gmail.com:587"
smtp_auth_username: "you@gmail.com"
smtp_auth_password: "your-app-password"
```

### Alerts Defined

| Alert                        | Trigger                            | Severity |
|------------------------------|------------------------------------|----------|
| `PredictorServiceDown`       | Predictor unreachable for 1 min    | Critical |
| `HighRiskDeploymentAttempted`| A BLOCK decision was issued        | Warning  |
| `SampleAppDown`              | App unreachable for 2 min          | Critical |

---

## API Reference

| Method | Endpoint     | Description                          |
|--------|--------------|--------------------------------------|
| GET    | `/`          | Service info                         |
| GET    | `/health`    | Health check                         |
| POST   | `/analyze`   | Submit logs, get risk decision       |
| GET    | `/thresholds`| View current scoring thresholds      |
| GET    | `/docs`      | Swagger interactive API docs         |

### POST `/analyze` — Request Body

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
