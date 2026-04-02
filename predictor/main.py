"""
Predictive Failure Detection Service
Analyzes CI/CD pipeline logs and returns a risk score before deployment.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import re
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Predictive Failure Detection API",
    description="Log-based risk analysis for CI/CD pipelines",
    version="1.0.0"
)

# ─── Risk Patterns ────────────────────────────────────────────────────────────
# Each pattern has: regex, weight (how much it adds to risk score), label
RISK_PATTERNS = [
    # Critical failures
    {"pattern": r"(?i)(error|exception|fatal|critical)",       "weight": 15, "label": "Error/Exception"},
    {"pattern": r"(?i)(segmentation fault|core dumped)",       "weight": 40, "label": "Segfault"},
    {"pattern": r"(?i)(out of memory|oom|killed)",             "weight": 35, "label": "OOM"},
    {"pattern": r"(?i)(connection refused|connection timeout)", "weight": 20, "label": "Connection Issue"},
    {"pattern": r"(?i)(build failed|compilation error)",       "weight": 50, "label": "Build Failure"},
    {"pattern": r"(?i)(\d+ tests? failed|\d+ failures?)",      "weight": 30, "label": "Test Failures"},
    {"pattern": r"(?i)(timeout|timed out)",                    "weight": 20, "label": "Timeout"},
    {"pattern": r"(?i)(permission denied|access denied)",      "weight": 15, "label": "Permission Error"},
    {"pattern": r"(?i)(disk full|no space left)",              "weight": 40, "label": "Disk Full"},
    {"pattern": r"(?i)(unhandled|uncaught|panic)",             "weight": 35, "label": "Unhandled Error"},
    {"pattern": r"(?i)(deprecated|warning)",                   "weight": 5,  "label": "Warning"},
    {"pattern": r"(?i)(exit code [^0]|exited with \d+[^0])",  "weight": 25, "label": "Non-zero Exit"},
    {"pattern": r"(?i)(npm err|pip error|dependency error)",   "weight": 20, "label": "Dependency Error"},
    {"pattern": r"(?i)(docker.*fail|container.*exit)",         "weight": 25, "label": "Container Failure"},
    {"pattern": r"(?i)(assertion.*fail|assert.*error)",        "weight": 25, "label": "Assertion Failure"},
]

# Green patterns reduce risk slightly
SAFE_PATTERNS = [
    {"pattern": r"(?i)(all tests passed|tests? passed)",  "weight": -20, "label": "Tests Passed"},
    {"pattern": r"(?i)(build successful|build passed)",   "weight": -20, "label": "Build Success"},
    {"pattern": r"(?i)(deployment successful)",           "weight": -15, "label": "Deploy Success"},
    {"pattern": r"(?i)(health check.*ok|healthy)",        "weight": -10, "label": "Health OK"},
]

RISK_THRESHOLD_BLOCK  = 60   # >= this → BLOCK deployment
RISK_THRESHOLD_WARN   = 30   # >= this → WARN but allow


# ─── Request / Response Models ────────────────────────────────────────────────

class LogAnalysisRequest(BaseModel):
    logs: str
    pipeline_id: Optional[str] = "unknown"
    branch: Optional[str] = "unknown"
    commit_sha: Optional[str] = "unknown"

class PatternMatch(BaseModel):
    label: str
    count: int
    weight_contribution: int

class LogAnalysisResponse(BaseModel):
    pipeline_id: str
    branch: str
    commit_sha: str
    risk_score: int                  # 0-100
    decision: str                    # ALLOW | WARN | BLOCK
    matched_patterns: list[PatternMatch]
    safe_patterns: list[PatternMatch]
    summary: str
    analyzed_at: float
    log_line_count: int


# ─── Core Analysis Logic ──────────────────────────────────────────────────────

def analyze_logs(logs: str) -> dict:
    lines = logs.strip().splitlines()
    score = 0
    matched = []
    safe = []

    for rp in RISK_PATTERNS:
        matches = re.findall(rp["pattern"], logs)
        if matches:
            contribution = min(rp["weight"] * len(matches), rp["weight"] * 3)  # cap multiplier at 3
            score += contribution
            matched.append({
                "label": rp["label"],
                "count": len(matches),
                "weight_contribution": contribution
            })

    for sp in SAFE_PATTERNS:
        matches = re.findall(sp["pattern"], logs)
        if matches:
            contribution = sp["weight"] * len(matches)
            score += contribution  # negative value
            safe.append({
                "label": sp["label"],
                "count": len(matches),
                "weight_contribution": contribution
            })

    # Clamp score 0–100
    score = max(0, min(100, score))

    if score >= RISK_THRESHOLD_BLOCK:
        decision = "BLOCK"
        summary = f"High risk detected (score={score}). Deployment BLOCKED. Review errors before proceeding."
    elif score >= RISK_THRESHOLD_WARN:
        decision = "WARN"
        summary = f"Moderate risk detected (score={score}). Deployment allowed with WARNING. Investigate issues."
    else:
        decision = "ALLOW"
        summary = f"Low risk detected (score={score}). Deployment ALLOWED. Pipeline looks healthy."

    return {
        "risk_score": score,
        "decision": decision,
        "matched_patterns": matched,
        "safe_patterns": safe,
        "summary": summary,
        "log_line_count": len(lines),
    }


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "Predictive Failure Detection", "status": "running", "version": "1.0.0"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/analyze", response_model=LogAnalysisResponse)
def analyze(req: LogAnalysisRequest):
    if not req.logs.strip():
        raise HTTPException(status_code=400, detail="Logs cannot be empty.")

    logger.info(f"Analyzing logs for pipeline={req.pipeline_id} branch={req.branch} commit={req.commit_sha}")
    result = analyze_logs(req.logs)

    response = LogAnalysisResponse(
        pipeline_id=req.pipeline_id,
        branch=req.branch,
        commit_sha=req.commit_sha,
        analyzed_at=time.time(),
        **result
    )

    logger.info(f"Result: decision={response.decision} score={response.risk_score}")
    return response

@app.get("/metrics")
def metrics():
    """Basic Prometheus-compatible metrics endpoint."""
    return JSONResponse(
        content="# HELP predictor_up Predictor service is up\n# TYPE predictor_up gauge\npredictor_up 1\n",
        media_type="text/plain"
    )

@app.get("/thresholds")
def get_thresholds():
    return {
        "block_threshold": RISK_THRESHOLD_BLOCK,
        "warn_threshold": RISK_THRESHOLD_WARN,
        "description": {
            "BLOCK": f"risk_score >= {RISK_THRESHOLD_BLOCK}",
            "WARN":  f"risk_score >= {RISK_THRESHOLD_WARN}",
            "ALLOW": f"risk_score < {RISK_THRESHOLD_WARN}",
        }
    }