#!/usr/bin/env python3
"""Extract paragraphs from a LaTeX manuscript for peer-review analysis.

Usage:
    python3 extract_manuscript.py --file <root.tex>

Output (stdout): JSON array of paragraph objects:
    [{"section": str, "para_idx": int, "text": str, "source_file": str, "line_end": int}, ...]

Follows \\input{} and \\include{} to included files. Strips LaTeX markup to plain text.
Skips preamble, float environments (figure/table), and verbatim blocks.
Assigns global para_idx (0-indexed) across all files in document order.
"""

import argparse
import json
import re
import sys
from pathlib import Path

MAX_PARA_CHARS = 600
SKIP_ENVS = {"figure", "table", "figure*", "table*", "lstlisting", "verbatim", "Verbatim",
             "algorithmic", "algorithm", "tikzpicture", "equation", "equation*",
             "align", "align*", "gather", "gather*", "multline", "multline*"}


def strip_latex(text: str) -> str:
    """Convert LaTeX markup to readable plain text."""
    # Remove comments
    text = re.sub(r'%.*', '', text)
    # Replace display math with placeholder
    text = re.sub(r'\\\[.*?\\\]', '[EQUATION]', text, flags=re.DOTALL)
    text = re.sub(r'\\begin\{equation\*?\}.*?\\end\{equation\*?\}', '[EQUATION]', text, flags=re.DOTALL)
    text = re.sub(r'\\begin\{align\*?\}.*?\\end\{align\*?\}', '[EQUATION]', text, flags=re.DOTALL)
    # Replace inline math with placeholder
    text = re.sub(r'\$\$.*?\$\$', '[MATH]', text, flags=re.DOTALL)
    text = re.sub(r'\$[^$\n]+\$', '[MATH]', text)
    # Unwrap common formatting commands (keep text)
    for cmd in ['textbf', 'textit', 'emph', 'texttt', 'textsc', 'textrm', 'textsf',
                'text', 'mathrm', 'mathbf', 'mathit', 'underline', 'uline',
                'footnote', 'label', 'ref', 'eqref', 'cref', 'Cref',
                'cite', 'citep', 'citet', 'citealp', 'citealt']:
        text = re.sub(r'\\' + cmd + r'\{([^{}]*)\}', r'\1', text)
    # Remove remaining commands with braces
    text = re.sub(r'\\[a-zA-Z]+\*?\{[^{}]*\}', '', text)
    # Remove remaining commands (no braces)
    text = re.sub(r'\\[a-zA-Z]+\*?', '', text)
    # Clean up braces and special chars
    text = re.sub(r'[{}]', '', text)
    text = re.sub(r'\\\\', ' ', text)  # line breaks
    text = re.sub(r'~', ' ', text)
    text = re.sub(r'``|\'\'', '"', text)
    text = re.sub(r'`|\'', "'", text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def section_name(line: str) -> str | None:
    """Return section title from a \\section{...} line, or None."""
    m = re.match(r'\\(?:sub)*section\*?\{([^}]+)\}', line.strip())
    if m:
        return strip_latex(m.group(1))
    return None


def is_include(line: str) -> str | None:
    """Return filename from \\input{} or \\include{} directive, or None."""
    m = re.match(r'\\(?:input|include)\{([^}]+)\}', line.strip())
    if m:
        return m.group(1).strip()
    return None


def process_file(path: Path, root_dir: Path, current_section: list,
                 para_idx: list, paragraphs: list, in_document: list) -> None:
    """Recursively process a .tex file, appending paragraphs to the list."""
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except FileNotFoundError:
        return

    skip_env_depth = 0
    current_env_stack = []
    current_para_lines = []
    para_start_line = None
    line_idx = 0

    while line_idx < len(lines):
        raw = lines[line_idx]
        stripped = raw.strip()

        # Track document start (skip preamble)
        if re.match(r'\\begin\{document\}', stripped):
            in_document[0] = True
            line_idx += 1
            continue
        if re.match(r'\\end\{document\}', stripped):
            in_document[0] = False
            line_idx += 1
            continue
        if not in_document[0]:
            line_idx += 1
            continue

        # Track environment opens/closes
        env_begin = re.match(r'\\begin\{([^}]+)\}', stripped)
        env_end = re.match(r'\\end\{([^}]+)\}', stripped)

        if env_begin:
            env = env_begin.group(1)
            current_env_stack.append(env)
            if env in SKIP_ENVS:
                skip_env_depth += 1

        if env_end:
            env = env_end.group(1)
            if env in SKIP_ENVS and skip_env_depth > 0:
                skip_env_depth -= 1
            if current_env_stack and current_env_stack[-1] == env:
                current_env_stack.pop()

        if skip_env_depth > 0:
            line_idx += 1
            continue

        # Follow includes
        inc = is_include(stripped)
        if inc:
            # Flush current paragraph first
            _flush_para(current_para_lines, para_start_line, current_section,
                        para_idx, paragraphs, str(path))
            current_para_lines = []
            para_start_line = None

            inc_path = root_dir / inc
            if not inc_path.suffix:
                inc_path = inc_path.with_suffix('.tex')
            process_file(inc_path, root_dir, current_section, para_idx,
                         paragraphs, in_document)
            line_idx += 1
            continue

        # Track section headings
        sec = section_name(stripped)
        if sec:
            _flush_para(current_para_lines, para_start_line, current_section,
                        para_idx, paragraphs, str(path))
            current_para_lines = []
            para_start_line = None
            current_section[0] = sec
            line_idx += 1
            continue

        # Skip structural commands that aren't content
        if re.match(r'\\(?:maketitle|tableofcontents|listoffigures|bibliography|bibliographystyle|appendix)', stripped):
            line_idx += 1
            continue

        # Paragraph splitting: blank line flushes current paragraph
        if stripped == '':
            _flush_para(current_para_lines, para_start_line, current_section,
                        para_idx, paragraphs, str(path))
            current_para_lines = []
            para_start_line = None
        else:
            if current_para_lines == []:
                para_start_line = line_idx + 1  # 1-based
            current_para_lines.append((line_idx + 1, stripped))  # (1-based line, content)

        line_idx += 1

    # Flush any remaining paragraph at EOF
    _flush_para(current_para_lines, para_start_line, current_section,
                para_idx, paragraphs, str(path))


def _flush_para(lines_buf: list, start_line: int | None, current_section: list,
                para_idx: list, paragraphs: list, source_file: str) -> None:
    """Assemble buffered lines into a paragraph and append to list."""
    if not lines_buf:
        return
    line_end = lines_buf[-1][0]  # last 1-based line number
    raw_text = ' '.join(content for _, content in lines_buf)
    text = strip_latex(raw_text)
    if len(text) < 20:  # too short to review
        return
    text = text[:MAX_PARA_CHARS]
    paragraphs.append({
        "section": current_section[0],
        "para_idx": para_idx[0],
        "text": text,
        "source_file": source_file,
        "line_end": line_end,
    })
    para_idx[0] += 1


def main():
    parser = argparse.ArgumentParser(description="Extract paragraphs from LaTeX manuscript")
    parser.add_argument("--file", required=True, help="Root .tex file")
    args = parser.parse_args()

    root = Path(args.file).resolve()
    if not root.exists():
        print(json.dumps({"error": f"File not found: {root}"}), file=sys.stderr)
        sys.exit(1)

    root_dir = root.parent
    paragraphs = []
    current_section = ["(preamble)"]
    para_idx = [0]
    in_document = [False]

    process_file(root, root_dir, current_section, para_idx, paragraphs, in_document)

    print(json.dumps(paragraphs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
