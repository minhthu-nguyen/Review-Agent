import json
import re
import subprocess
import requests
from openai import OpenAI

OSV_API_URL = "https://api.osv.dev/v1/query"
OSV_TIMEOUT = 5

COMPLEXITY_RATING = {
    range(1, 6): "A",
    range(6, 11): "B",
    range(11, 16): "C",
    range(16, 21): "D",
}


def _rate_complexity(score: int) -> str:
    for r, grade in COMPLEXITY_RATING.items():
        if score in r:
            return grade
    return "F"


# ── Tool 1: check_dependency_cve ─────────────────────────────────────────────

def check_dependency_cve(package_name: str, ecosystem: str, version: str = "") -> dict:
    payload = {
        "package": {"name": package_name, "ecosystem": ecosystem},
    }
    if version:
        payload["version"] = version

    try:
        resp = requests.post(OSV_API_URL, json=payload, timeout=OSV_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        vulns = data.get("vulns", [])
        if not vulns:
            return {"status": "safe", "message": "No known vulnerabilities found."}

        findings = []
        for v in vulns[:5]:  # cap at 5 to keep token count low
            findings.append({
                "id": v.get("id"),
                "summary": v.get("summary", ""),
                "severity": v.get("database_specific", {}).get("severity", "UNKNOWN"),
            })
        return {"status": "vulnerable", "count": len(vulns), "findings": findings}

    except requests.exceptions.Timeout:
        return {"status": "unavailable", "message": "CVE check timed out."}
    except Exception as e:
        return {"status": "unavailable", "message": f"CVE check failed: {e}"}


# ── Tool 2: calculate_complexity ─────────────────────────────────────────────

def _complexity_python(code: str) -> int:
    try:
        result = subprocess.run(
            ["radon", "cc", "-s", "-"],
            input=code,
            capture_output=True,
            text=True,
            timeout=10,
        )
        # radon output: "M 1:0 func_name - A (3)"  → extract the number
        match = re.search(r"\((\d+)\)", result.stdout)
        if match:
            return int(match.group(1))
        # fallback: sum all complexity scores in the output
        scores = re.findall(r"- [A-F] \((\d+)\)", result.stdout)
        return sum(int(s) for s in scores) if scores else 1
    except Exception:
        return _complexity_manual(code)


def _complexity_manual(code: str) -> int:
    # Count decision points: if/elif/else/for/while/case/catch/&&/||/?
    keywords = r"\b(if|elif|else|for|while|case|catch|except|finally)\b"
    logical = r"(\&\&|\|\||and\b|or\b)"
    count = len(re.findall(keywords, code)) + len(re.findall(logical, code))
    return count + 1  # +1 for the base path


def calculate_complexity(code: str, language: str) -> dict:
    if language == "python":
        score = _complexity_python(code)
    else:
        score = _complexity_manual(code)

    rating = _rate_complexity(score)
    result = {"complexity": score, "rating": rating}
    if score > 10:
        result["suggestion"] = "Consider splitting this function into smaller units."
    return result


# ── Tool 3: search_best_practice ─────────────────────────────────────────────

def search_best_practice(query: str, language: str) -> str:
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a senior software engineer. "
                    "Give a concise best practice answer with a short code example. "
                    "Max 150 words. No markdown headers."
                ),
            },
            {"role": "user", "content": f"[{language}] {query}"},
        ],
        max_tokens=250,
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


# ── Dispatcher ────────────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict) -> dict | str:
    if name == "check_dependency_cve":
        return check_dependency_cve(
            package_name=args["package_name"],
            ecosystem=args["ecosystem"],
            version=args.get("version", ""),
        )
    if name == "calculate_complexity":
        return calculate_complexity(
            code=args["code"],
            language=args["language"],
        )
    if name == "search_best_practice":
        return search_best_practice(
            query=args["query"],
            language=args["language"],
        )
    return {"error": f"Unknown tool: {name}"}
