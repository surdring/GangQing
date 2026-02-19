#!/usr/bin/env python3
import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path


OUTPUT_REQUIREMENT_TEMPLATE_LINES = [
    "# Output Requirement",
    "交付方式：**摘要 + 关键片段 + 文件路径**（禁止在聊天中粘贴大文件全文）。",
    "- 摘要：说明本次修改了哪些文件、哪些章节/段落发生变更。",
    "- 关键片段：仅粘贴与本子任务契约/实现要求直接相关的最小必要片段。",
    "- 文件路径：给出修改后的文件路径，作为权威落盘产物（以仓库文件为准）。",
    "- 输出验证命令与关键输出摘要（文本）。",
]


@dataclass
class Change:
    file_path: Path
    changed: bool
    reason: str


_SUBTASK_HEADING_RE = re.compile(r"^###\\s+Task\\s+(\\d+)\\.(\\d+)\\b")
_CODE_FENCE_START_RE = re.compile(r"^```markdown\\s*$")
_CODE_FENCE_END_RE = re.compile(r"^```\\s*$")


def _replace_output_requirement_in_codeblock(lines: list[str]) -> tuple[list[str], bool]:
    """Replace the Output Requirement section inside a markdown code block.

    The code block is represented as the full list of lines between ```markdown and ```.
    """

    out: list[str] = []
    changed = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == "# Output Requirement":
            out.extend([l + "\n" for l in OUTPUT_REQUIREMENT_TEMPLATE_LINES])
            changed = True
            i += 1
            while i < len(lines) and not lines[i].startswith("# "):
                i += 1
            continue

        out.append(line)
        i += 1

    return out, changed


def process_file(file_path: Path) -> Change:
    raw = file_path.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=True)

    out: list[str] = []
    i = 0
    changed_any = False

    while i < len(lines):
        line = lines[i]
        m = _SUBTASK_HEADING_RE.match(line.rstrip("\n"))
        if not m:
            out.append(line)
            i += 1
            continue

        out.append(line)
        i += 1

        while i < len(lines) and not _CODE_FENCE_START_RE.match(lines[i].rstrip("\n")):
            out.append(lines[i])
            i += 1

        if i >= len(lines):
            break

        out.append(lines[i])
        i += 1

        codeblock_lines: list[str] = []
        while i < len(lines) and not _CODE_FENCE_END_RE.match(lines[i].rstrip("\n")):
            codeblock_lines.append(lines[i])
            i += 1

        if i >= len(lines):
            out.extend(codeblock_lines)
            break

        replaced_block, changed = _replace_output_requirement_in_codeblock(codeblock_lines)
        out.extend(replaced_block)
        changed_any = changed_any or changed

        out.append(lines[i])
        i += 1

    new_raw = "".join(out)
    if new_raw == raw:
        return Change(file_path=file_path, changed=False, reason="no_change")

    file_path.write_text(new_raw, encoding="utf-8")
    return Change(file_path=file_path, changed=True, reason="updated_output_requirement")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default="docs/task-prompts",
        help="Directory containing task prompt markdown files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report changes without writing files",
    )
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Invalid root directory: {root}")

    md_files = sorted(root.glob("*.md"))
    if not md_files:
        raise SystemExit(f"No markdown files found in {root}")

    changes: list[Change] = []
    for file_path in md_files:
        if args.dry_run:
            before = file_path.read_text(encoding="utf-8")
            c = process_file(file_path)
            after = file_path.read_text(encoding="utf-8")
            if before != after:
                file_path.write_text(before, encoding="utf-8")
                changes.append(Change(file_path=file_path, changed=True, reason="would_change"))
            else:
                changes.append(Change(file_path=file_path, changed=False, reason="no_change"))
        else:
            changes.append(process_file(file_path))

    changed = [c for c in changes if c.changed]
    print(f"Total files: {len(changes)}")
    print(f"Changed files: {len(changed)}")
    for c in changed:
        rel = os.path.relpath(c.file_path, Path.cwd())
        print(f"- {rel}: {c.reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
