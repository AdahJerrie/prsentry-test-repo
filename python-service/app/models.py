"""
Request/response shapes for the /review endpoint.

These MUST match docs/api-contract.md at the monorepo root. Go sends
ReviewRequest; this service sends back ReviewResponse. If you change a
field name here, the Go side breaks silently (it'll just get a 422
from FastAPI, or Go will unmarshal into zero-values) — so this file
IS the contract for the Python side.
"""

from pydantic import BaseModel, Field  # pyright: ignore[reportMissingImports]


class FileDiff(BaseModel):
    """One changed file in the PR. Go's review.FileDiff mirrors this."""
    path: str
    diff: str


class ReviewRequest(BaseModel):
    """What Go POSTs to /review."""
    pr_id: int
    files: list[FileDiff]


class FileRisk(BaseModel):
    """One file's individual risk verdict, as computed by _analyze_one_file.
    Part of the response contract now — not just an internal dict."""
    path: str
    risk_score: float = Field(ge=0, le=10)
    reasoning: str


class ReviewResponse(BaseModel):
    """
    What we send back to Go.

    Only pr_id and risk_score are locked in the contract right now.
    summary/flagged_files/file_risks are extras this skeleton adds so
    there's somewhere to put per-file findings — treat them as
    provisional until the contract doc says otherwise. file_risks is
    additive (new field, doesn't touch pr_id/risk_score) — see
    docs/api-contract.md for the note on why this is backward-compatible.
    """
    pr_id: int
    risk_score: float = Field(ge=0, le=10)
    summary: str
    flagged_files: list[str] = []
    file_risks: list[FileRisk] = []