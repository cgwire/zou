#!/usr/bin/env python3
"""
Add missing newlines after opening and before closing triple quotes.
"""

from __future__ import annotations

import io
import sys
import tokenize
from pathlib import Path


def _quote_style(source: str) -> str | None:
    if source.startswith('"""'):
        return '"""'
    if source.startswith("'''"):
        return "'''"
    return None


def _needs_fix(inner: str) -> bool:
    if not inner:
        return False

    if not inner.strip():
        return not inner.startswith("\n") or bool(inner.split("\n")[-1].strip())

    if not inner.startswith("\n"):
        return True

    last_line = inner.split("\n")[-1]
    return bool(last_line.strip())


def _fix_inner(inner: str, line_indent: str) -> str:
    body_indent = line_indent

    text = inner
    if text.startswith("\n"):
        text = text[1:]
    while text.endswith("\n"):
        text = text[:-1]

    lines = text.split("\n")
    content_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            content_lines.append(f"{body_indent}{stripped}")
        elif content_lines and content_lines[-1] != "":
            content_lines.append("")

    if not content_lines:
        return f"\n{line_indent}"

    body = "\n".join(content_lines)
    return f"\n{body}\n{line_indent}"


def _fix_docstring(source: str, line_indent: str) -> str:
    quote = _quote_style(source)
    if quote is None:
        return source

    inner = source[len(quote) : -len(quote)]
    if not _needs_fix(inner):
        return source

    return f"{quote}{_fix_inner(inner, line_indent)}{quote}"


def _line_indent(source: str, start: tuple[int, int]) -> str:
    row, _col = start
    line = source.splitlines()[row - 1]
    return line[: len(line) - len(line.lstrip(" \t"))]


def _is_docstring(
    token: tokenize.TokenInfo,
    prev_significant: tokenize.TokenInfo | None,
) -> bool:
    if token.type != tokenize.STRING:
        return False

    if _quote_style(token.string) is None:
        return False

    if prev_significant is None:
        return True

    if prev_significant.type == tokenize.INDENT:
        return True

    return prev_significant.type in {tokenize.NEWLINE, tokenize.NL}


def fix_source(source: str) -> tuple[str, int]:
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    if not tokens:
        return source, 0

    prev_significant: tokenize.TokenInfo | None = None
    replacements: list[tuple[tuple[int, int], tuple[int, int], str]] = []
    fixes = 0

    for token in tokens:
        if _is_docstring(token, prev_significant):
            line_indent = _line_indent(source, token.start)
            fixed = _fix_docstring(token.string, line_indent)
            if fixed != token.string:
                replacements.append((token.start, token.end, fixed))
                fixes += 1

        if token.type not in {tokenize.NL, tokenize.COMMENT, tokenize.ENCODING}:
            prev_significant = token

    if not replacements:
        return source, 0

    lines = source.splitlines(keepends=True)
    for (start_row, start_col), (end_row, end_col), replacement in sorted(
        replacements, reverse=True
    ):
        start_idx = start_row - 1
        end_idx = end_row - 1
        start_line = lines[start_idx]
        end_line = lines[end_idx]

        if start_idx == end_idx:
            lines[start_idx] = (
                start_line[:start_col] + replacement + start_line[end_col:]
            )
            continue

        prefix = start_line[:start_col]
        suffix = end_line[end_col:]
        replacement_lines = replacement.splitlines(keepends=True)
        if not replacement_lines:
            lines[start_idx : end_idx + 1] = [prefix + suffix]
            continue

        merged = [prefix + replacement_lines[0]] + replacement_lines[1:]
        merged[-1] = merged[-1] + suffix
        lines[start_idx : end_idx + 1] = merged

    return "".join(lines), fixes


def fix_file(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    fixed, count = fix_source(source)
    if count:
        path.write_text(fixed, encoding="utf-8")
    return count


def main(argv: list[str]) -> int:
    roots = [Path(arg) for arg in argv[1:]] or [
        Path("zou"),
        Path("tests"),
        Path("scripts"),
        Path("conftest.py"),
    ]

    total_files = 0
    total_fixes = 0

    for root in roots:
        paths = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for path in paths:
            if "migrations" in path.parts:
                continue
            fixes = fix_file(path)
            if fixes:
                total_files += 1
                total_fixes += fixes
                print(f"{path}: {fixes}")

    print(f"Fixed {total_fixes} docstrings in {total_files} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
