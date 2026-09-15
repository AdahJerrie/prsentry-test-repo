"""
Core analysis logic: take a PR's file diffs, ask an LLM to assess risk
per file, then combine those into one score for the whole PR.

Flow:
    files (from Go) -> analyze one file at a time -> combine scores

Why per-file instead of one big prompt with every diff mashed together?
Two reasons: (1) large PRs can blow past context limits fast, and
(2) asking "rate this one file" gets a more consistent answer than
asking an LLM to juggle five files in its head at once. The tradeoff
is more API calls (slower, pricier) — fine for v1, worth revisiting
if PRs regularly have 20+ files.
"""

import json
import os

import anthropic

from app.models import FileDiff

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """You are a senior code reviewer assessing risk in a single file's diff.
Respond with ONLY a JSON object, no other text, in this exact shape:
{"risk_score": <0-10 float>, "reasoning": "<one sentence>"}

Score guide:
0-2  = trivial (formatting, comments, docs)
3-5  = normal change, low blast radius
6-8  = touches auth, data handling, error paths, or public APIs
9-10 = looks dangerous: secrets, missing validation, could break prod
"""


def _analyze_one_file(file: FileDiff) -> dict:
    """
    Send a single file's diff to the model and parse its risk verdict.

    Returns a dict like {"path": ..., "risk_score": ..., "reasoning": ...}.
    If the model response isn't valid JSON, we fail safe with a mid-range
    score rather than crashing the whole PR review over one bad file.
    """
    message = client.messages.create(
        model=MODEL,
        max_tokens=200,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"File: {file.path}\n\nDiff:\n{file.diff}",
            }
        ],
    )

    raw_text = message.content[0].text

    try:
        parsed = json.loads(raw_text)
        risk_score = float(parsed["risk_score"])
        reasoning = parsed.get("reasoning", "")
    except (json.JSONDecodeError, KeyError, ValueError):
        # Model didn't follow the format. Don't let one malformed
        # response take down the whole request — log it and move on
        # with a cautious default.
        risk_score = 5.0
        reasoning = "Could not parse model response; defaulted to medium risk."

    return {"path": file.path, "risk_score": risk_score, "reasoning": reasoning}


def analyze_pr(files: list[FileDiff]) -> dict:
    """
    Analyze every file in the PR and roll the results up into one
    PR-level verdict.

    Aggregation rule for v1: PR risk = highest single-file risk score.
    Rationale: one dangerous file (e.g. a secrets leak) should flag the
    whole PR even if the other nine files are trivial — averaging would
    dilute it away. Revisit if this feels too trigger-happy in practice.
    """
    if not files:
        return {"risk_score": 0.0, "summary": "No files to review.", "flagged_files": [], "file_risks": []}

    results = [_analyze_one_file(f) for f in files]

    highest = max(results, key=lambda r: r["risk_score"])
    flagged = [r["path"] for r in results if r["risk_score"] >= 6]

    summary = (
        f"Reviewed {len(results)} file(s). Highest risk: "
        f"{highest['path']} ({highest['risk_score']}/10) — {highest['reasoning']}"
    )

    return {
        "risk_score": highest["risk_score"],
        "summary": summary,
        "flagged_files": flagged,
        "file_risks": results,
    }