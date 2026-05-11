import subprocess
import re
from dataclasses import dataclass, field

SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".java": "java",
    ".go": "golang",
}

MAX_DIFF_LINES = 400
CHUNK_SIZE = 200


@dataclass
class FileDiff:
    filename: str
    language: str
    added_lines: list[tuple[int, str]] = field(default_factory=list)
    removed_lines: list[tuple[int, str]] = field(default_factory=list)
    context_lines: list[tuple[int, str]] = field(default_factory=list)
    raw_diff: str = ""


def _detect_language(filename: str) -> str | None:
    for ext, lang in SUPPORTED_EXTENSIONS.items():
        if filename.endswith(ext):
            return lang
    return None


def _get_raw_diff(base_sha: str, head_sha: str) -> str:
    result = subprocess.run(
        ["git", "diff", f"{base_sha}..{head_sha}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _parse_file_chunks(raw_diff: str) -> list[tuple[str, str]]:
    """Split raw diff into per-file chunks. Returns list of (filename, chunk)."""
    chunks = []
    current_file = None
    current_lines = []

    for line in raw_diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current_file and current_lines:
                chunks.append((current_file, "".join(current_lines)))
            current_file = None
            current_lines = [line]
        elif line.startswith("+++ b/") and current_file is None:
            current_file = line[6:].strip()
            current_lines.append(line)
        else:
            current_lines.append(line)

    if current_file and current_lines:
        chunks.append((current_file, "".join(current_lines)))

    return chunks


def _parse_hunks(raw_chunk: str) -> tuple[list, list, list]:
    """Parse a single file diff chunk into added/removed/context line lists."""
    added = []
    removed = []
    context = []

    current_new_line = 0
    in_hunk = False

    for line in raw_chunk.splitlines():
        # @@ -old_start,old_count +new_start,new_count @@
        hunk_match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if hunk_match:
            current_new_line = int(hunk_match.group(1))
            in_hunk = True
            continue

        if not in_hunk:
            continue

        if line.startswith("+") and not line.startswith("+++"):
            added.append((current_new_line, line[1:]))
            current_new_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed.append((current_new_line, line[1:]))
        elif line.startswith(" "):
            context.append((current_new_line, line[1:]))
            current_new_line += 1

    return added, removed, context


def _split_into_subchunks(file_diff: FileDiff) -> list[FileDiff]:
    """Split an oversized FileDiff into sub-chunks of CHUNK_SIZE lines."""
    lines = file_diff.raw_diff.splitlines(keepends=True)
    sub_diffs = []
    header_lines = []

    # Collect header (everything before first hunk)
    i = 0
    while i < len(lines) and not lines[i].startswith("@@"):
        header_lines.append(lines[i])
        i += 1

    hunk_lines = lines[i:]
    chunks = [hunk_lines[j:j + CHUNK_SIZE] for j in range(0, len(hunk_lines), CHUNK_SIZE)]

    for idx, chunk in enumerate(chunks):
        # Ensure each sub-chunk has a hunk header so _parse_hunks can process it
        if not chunk[0].startswith("@@"):
            chunk = [f"@@ -1 +1 @@\n"] + chunk
        raw = "".join(header_lines + chunk)
        added, removed, context = _parse_hunks(raw)
        sub_diffs.append(FileDiff(
            filename=f"{file_diff.filename}#chunk{idx + 1}",
            language=file_diff.language,
            added_lines=added,
            removed_lines=removed,
            context_lines=context,
            raw_diff=raw,
        ))

    return sub_diffs


def parse_diff(base_sha: str, head_sha: str) -> list[FileDiff]:
    raw = _get_raw_diff(base_sha, head_sha)
    file_chunks = _parse_file_chunks(raw)

    results = []
    for filename, chunk in file_chunks:
        language = _detect_language(filename)
        if language is None:
            continue

        added, removed, context = _parse_hunks(chunk)
        fd = FileDiff(
            filename=filename,
            language=language,
            added_lines=added,
            removed_lines=removed,
            context_lines=context,
            raw_diff=chunk,
        )

        total_lines = len(added) + len(removed)
        if total_lines > MAX_DIFF_LINES:
            results.extend(_split_into_subchunks(fd))
        else:
            results.append(fd)

    return results
