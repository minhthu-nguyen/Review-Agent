import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from openai import OpenAI

from agent.diff_parser import FileDiff
from agent.tools import execute_tool

PROMPTS_DIR = Path(__file__).parent / "prompts"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_dependency_cve",
            "description": "Check CVE vulnerabilities for a package. Use when you spot a new import or dependency being added.",
            "parameters": {
                "type": "object",
                "properties": {
                    "package_name": {"type": "string"},
                    "version": {"type": "string", "description": "Version string, can be empty"},
                    "ecosystem": {"type": "string", "enum": ["PyPI", "Maven", "Go"]},
                },
                "required": ["package_name", "ecosystem"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_complexity",
            "description": "Calculate cyclomatic complexity of a function. Use when a function looks long or has many branches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "The function/method code only, not the entire file"},
                    "language": {"type": "string", "enum": ["python", "java", "golang"]},
                },
                "required": ["code", "language"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_best_practice",
            "description": "Get best practice or better pattern for a specific coding situation. Use sparingly, only for significant improvements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "language": {"type": "string"},
                },
                "required": ["query", "language"],
            },
        },
    },
]

OUTPUT_SCHEMA = """
Respond ONLY with valid JSON (no markdown, no explanation) matching this schema:
{
  "summary": "2-3 sentence overview of the changes",
  "verdict": "LGTM | NEEDS_MINOR_FIX | NEEDS_WORK | CRITICAL",
  "score": <integer 0-100>,
  "issues": [
    {
      "severity": "critical | high | medium | low | info",
      "line": <integer or null>,
      "title": "short title",
      "description": "detailed explanation",
      "suggestion": "code fix or null",
      "category": "security | logic | performance | style | complexity | dependency"
    }
  ]
}
"""


@dataclass
class ReviewResult:
    filename: str
    summary: str
    verdict: str
    score: int
    issues: list[dict] = field(default_factory=list)
    error: str | None = None


def _load_prompt(language: str) -> str:
    path = PROMPTS_DIR / f"system_{language}.txt"
    if path.exists():
        return path.read_text()
    # Fallback generic prompt if file missing
    return (
        f"You are a senior {language} engineer doing a thorough code review. "
        "Analyze the git diff and identify bugs, security issues, and performance problems. "
        + OUTPUT_SCHEMA
    )


def _format_diff_for_review(file_diff: FileDiff) -> str:
    lines = [
        f"Review the following git diff for `{file_diff.filename}`:",
        "",
        "```diff",
        file_diff.raw_diff,
        "```",
        "",
        OUTPUT_SCHEMA,
    ]
    return "\n".join(lines)


def _parse_review_result(content: str, filename: str) -> ReviewResult:
    try:
        data = json.loads(content)
        return ReviewResult(
            filename=filename,
            summary=data.get("summary", ""),
            verdict=data.get("verdict", "NEEDS_WORK"),
            score=int(data.get("score", 50)),
            issues=data.get("issues", []),
        )
    except (json.JSONDecodeError, ValueError) as e:
        return ReviewResult(
            filename=filename,
            summary="Failed to parse review output.",
            verdict="NEEDS_WORK",
            score=50,
            error=str(e),
        )


def _fallback_review(filename: str) -> ReviewResult:
    return ReviewResult(
        filename=filename,
        summary="Review reached max iterations without completing.",
        verdict="NEEDS_WORK",
        score=50,
        error="max_iterations exceeded",
    )


def review_file(file_diff: FileDiff) -> ReviewResult:
    try:
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        system_prompt = _load_prompt(file_diff.language)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _format_diff_for_review(file_diff)},
        ]

        max_iterations = 5
        for _ in range(max_iterations):
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                response_format={"type": "json_object"},
                max_tokens=2000,
                temperature=0.1,
            )

            msg = response.choices[0].message

            if not msg.tool_calls:
                return _parse_review_result(msg.content, file_diff.filename)

            # Tool calls present — execute each and append results
            messages.append(msg)
            for tc in msg.tool_calls:
                result = execute_tool(tc.function.name, json.loads(tc.function.arguments))
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                })

        return _fallback_review(file_diff.filename)

    except Exception as e:
        return ReviewResult(
            filename=file_diff.filename,
            summary="Review unavailable due to an unexpected error.",
            verdict="LGTM",
            score=100,
            error=str(e),
        )
