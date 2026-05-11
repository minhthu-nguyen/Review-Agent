import os
from datetime import datetime, timezone

from github import Github
from github.GithubException import GithubException

from agent.review_agent import ReviewResult

SEVERITY_EMOJI = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🟢",
    "info": "⚪",
}

VERDICT_LABEL = {
    "LGTM": "✅ LGTM",
    "NEEDS_MINOR_FIX": "⚠️ Needs minor fix",
    "NEEDS_WORK": "🚫 Needs work",
    "CRITICAL": "🚫 Critical issues",
}

BOT_MARKER = "🤖 AI Code Review"


def _aggregate_verdict(results: list[ReviewResult]) -> str:
    priority = ["CRITICAL", "NEEDS_WORK", "NEEDS_MINOR_FIX", "LGTM"]
    verdicts = {r.verdict for r in results}
    for v in priority:
        if v in verdicts:
            return v
    return "LGTM"


def _count_by_severity(results: list[ReviewResult]) -> dict:
    counts = {s: 0 for s in SEVERITY_EMOJI}
    for r in results:
        for issue in r.issues:
            sev = issue.get("severity", "info")
            if sev in counts:
                counts[sev] += 1
    return counts


def _build_summary_body(results: list[ReviewResult]) -> str:
    avg_score = round(sum(r.score for r in results) / len(results)) if results else 0
    verdict = _aggregate_verdict(results)
    counts = _count_by_severity(results)
    reviewed_files = len(results)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Medium/Low issues listed in summary (not posted inline)
    medium_low_issues = []
    for r in results:
        for issue in r.issues:
            if issue.get("severity") in ("medium", "low", "info"):
                medium_low_issues.append((r.filename, issue))

    lines = [
        f"## {BOT_MARKER} — Score: {avg_score}/100",
        "",
        "### 📋 Summary",
    ]

    for r in results:
        if r.summary:
            lines.append(f"- **{r.filename}**: {r.summary}")

    lines += [
        "",
        "### Findings",
        "| Severity | Count |",
        "|----------|-------|",
        f"| 🔴 Critical | {counts['critical']} |",
        f"| 🟠 High     | {counts['high']} |",
        f"| 🟡 Medium   | {counts['medium']} |",
        f"| 🟢 Low      | {counts['low']} |",
        "",
        f"### Verdict: {VERDICT_LABEL.get(verdict, verdict)}",
    ]

    if medium_low_issues:
        lines += ["", "### 🟡 Medium / Low findings"]
        for filename, issue in medium_low_issues:
            emoji = SEVERITY_EMOJI.get(issue.get("severity", "info"), "⚪")
            line_ref = f" (line {issue['line']})" if issue.get("line") else ""
            lines.append(f"- {emoji} **{filename}**{line_ref}: {issue.get('title', '')}")
            if issue.get("description"):
                lines.append(f"  {issue['description']}")

    lines += [
        "",
        "---",
        f"*Reviewed {reviewed_files} file{'s' if reviewed_files != 1 else ''} · "
        f"Powered by gpt-4o-mini · {timestamp}*",
    ]

    return "\n".join(lines)


def _build_inline_body(issue: dict) -> str:
    severity = issue.get("severity", "info")
    emoji = SEVERITY_EMOJI.get(severity, "⚪")
    category = issue.get("category", "")
    title = issue.get("title", "")
    description = issue.get("description", "")
    suggestion = issue.get("suggestion")

    lines = [f"**{emoji} [{category}] {title}**", "", description]

    if suggestion:
        lines += ["", "```suggestion", suggestion, "```"]

    return "\n".join(lines)


class GitHubCommenter:
    def __init__(self, token: str, repo_name: str):
        self._gh = Github(token)
        self._repo = self._gh.get_repo(repo_name)

    def post_pr_summary(self, pr_number: int, results: list[ReviewResult]) -> None:
        pr = self._repo.get_pull(int(pr_number))
        body = _build_summary_body(results)

        # Update existing bot comment if present (re-push case)
        for comment in pr.get_issue_comments():
            if BOT_MARKER in comment.body:
                comment.edit(body)
                return

        pr.create_issue_comment(body)

    def post_inline_comments(self, pr_number: int, results: list[ReviewResult]) -> None:
        pr = self._repo.get_pull(int(pr_number))
        commit = self._repo.get_commit(pr.head.sha)

        for result in results:
            filename = result.filename.split("#chunk")[0]  # strip sub-chunk suffix
            for issue in result.issues:
                if issue.get("severity") not in ("critical", "high"):
                    continue
                line = issue.get("line")
                if not line:
                    continue
                try:
                    pr.create_review_comment(
                        body=_build_inline_body(issue),
                        commit=commit,
                        path=filename,
                        line=line,
                    )
                except GithubException:
                    # Line may not be in the diff — skip silently
                    pass

    def set_check_status(self, verdict: str) -> None:
        sha = os.environ.get("HEAD_SHA", "")
        if not sha:
            return

        conclusion = "success" if verdict in ("LGTM", "NEEDS_MINOR_FIX") else "failure"
        summary = VERDICT_LABEL.get(verdict, verdict)

        try:
            self._repo.create_check_run(
                name="AI Code Review",
                head_sha=sha,
                status="completed",
                conclusion=conclusion,
                output={"title": f"AI Code Review: {verdict}", "summary": summary},
            )
        except GithubException:
            pass
