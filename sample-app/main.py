"""
Sample application — this is what gets built/tested/deployed.
The CI/CD pipeline wraps around this.
"""

from fastapi import FastAPI

app = FastAPI(title="Sample App", version="1.0.0")

@app.get("/")
def root():
    return {"message": "Hello from sample-app!", "status": "ok"}

@app.get("/health")
def health():
    return {"status": "healthy"}

def add(a: int, b: int) -> int:
    return a + b

def divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
