"""
Entry point. This is what Go's webhook handler will POST to once
the forwarding step is wired up on the Go side (Week 2 work).

Run locally with:
    uvicorn app.main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException

from app.analysis import analyze_pr
from app.models import ReviewRequest, ReviewResponse

app = FastAPI(title="PRSentry Python Service")


@app.get("/health")
def health():
    """Simple liveness check — handy for confirming the service is up
    before Go ever tries to talk to it."""
    return {"status": "ok"}


@app.post("/review", response_model=ReviewResponse)
def review(request: ReviewRequest):
    """
    Receives PR file diffs from the Go service, runs LLM-based risk
    analysis, and returns a risk score + summary.
    """
    try:
        result = analyze_pr(request.files)
    except Exception as exc:
        # Anything from the Anthropic API (rate limit, network, auth)
        # surfaces here. Bubble up as a 502 so Go knows THIS service
        # failed, not that the request itself was malformed.
        raise HTTPException(status_code=502, detail=f"Analysis failed: {exc}")

    return ReviewResponse(
        pr_id=request.pr_id,
        risk_score=result["risk_score"],
        summary=result["summary"],
        flagged_files=result["flagged_files"],
        file_risks=result["file_risks"],
    )