import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from agent.diff_parser import parse_diff
from agent.review_agent import ReviewResult, review_file
from agent.github_commenter import GitHubCommenter, _aggregate_verdict


def _print_summary_to_log(results: list[ReviewResult]) -> None:
    print("\n── Review Summary ──────────────────────────────")
    for r in results:
        status = "✓" if r.verdict in ("LGTM", "NEEDS_MINOR_FIX") else "✗"
        print(f"  {status} {r.filename} — {r.verdict} ({r.score}/100)")
        for issue in r.issues:
            sev = issue.get("severity", "").upper()
            print(f"      [{sev}] {issue.get('title', '')}")
    print("────────────────────────────────────────────────")


def _review_with_delay(file_diff, index: int) -> ReviewResult:
    # Stagger requests to avoid OpenAI rate limit when running in parallel
    time.sleep(index * 0.5)
    return review_file(file_diff)


def main() -> None:
    event_type = os.environ.get("EVENT_TYPE", "push")
    pr_number = os.environ.get("PR_NUMBER")
    base_sha = os.environ.get("BASE_SHA", "")
    head_sha = os.environ.get("HEAD_SHA", "")

    if not base_sha or not head_sha:
        print("BASE_SHA and HEAD_SHA are required. Skipping review.")
        return

    try:
        file_diffs = parse_diff(base_sha, head_sha)
    except Exception as e:
        print(f"Failed to parse diff: {e}. Skipping review.")
        return

    if not file_diffs:
        print("No relevant files changed (.py/.java/.go). Skipping review.")
        return

    print(f"Reviewing {len(file_diffs)} file(s)...")

    all_results: list[ReviewResult] = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_review_with_delay, fd, i): fd
            for i, fd in enumerate(file_diffs)
        }
        for future in as_completed(futures):
            result = future.result()
            all_results.append(result)
            error_note = f" [error: {result.error}]" if result.error else ""
            print(f"  ✓ {result.filename} — {result.verdict} ({result.score}/100){error_note}")

    if event_type == "pull_request" and pr_number:
        commenter = GitHubCommenter(
            token=os.environ["GITHUB_TOKEN"],
            repo_name=os.environ["REPO_NAME"],
        )
        commenter.post_pr_summary(pr_number, all_results)
        commenter.post_inline_comments(pr_number, all_results)

        overall_verdict = _aggregate_verdict(all_results)
        commenter.set_check_status(overall_verdict)

        print(f"\nPosted review to PR #{pr_number} — overall verdict: {overall_verdict}")
    else:
        _print_summary_to_log(all_results)


if __name__ == "__main__":
    main()
