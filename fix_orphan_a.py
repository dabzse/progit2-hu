#!/usr/bin/env python3
"""
fix_orphan_a.py - Language-agnostic / generic orphan 'a' fixer for AsciiDoc files.

Fixes orphan standalone 'a' / 'A' (and optionally other single-letter words)
at line ends or before words by inserting a non-breaking space (Unicode U+00A0
or AsciiDoc {nbsp}), preventing awkward typographic line-wrapping.

Protects AsciiDoc syntax:
- Fenced code blocks (----, ...., ++++)
- Block metadata, anchors, attributes, includes, and images
- Inline code spans (`...`), URLs, macros, anchors (<<...>>), index tags (((...))), callouts (<1>)
"""

import argparse
import difflib
import os
import re
import sys

DEFAULT_WORDS = ['a', 'A']
UNICODE_NBSP = '\u00A0'
ASCIIDOC_NBSP = '{nbsp}'

# Regex to identify inline protected spans in AsciiDoc
INLINE_PROTECTED_RE = re.compile(
    r'('
    r'`+[^`\n]+`+'                                                        # Inline code `code` or ``code``
    r'|https?://[^\s\[\]<>"\'\)]+'                                        # URLs
    r'|(?:link|xref|image|video|audio|pass|kbd|btn|menu):[^\s\[\]]*\[[^\]]*\]'  # Inline macros
    r'|<<[^>\n]+>>'                                                       # Cross-references <<anchor,label>>
    r'|\(\(\([^)\n]+\)\)\)'                                               # Index entries (((term)))
    r'|<[a-zA-Z/][^>\n]*>'                                                # HTML tags
    r'|<[0-9]+>'                                                          # Callouts <1>, <2>
    r')'
)

# Line-level patterns that should be completely skipped
SKIP_LINE_PREFIXES = (
    'image::', 'video::', 'audio::', 'include::',
    'ifdef::', 'ifndef::', 'ifeval::', 'endif::',
    '//', '|==='
)

CODE_BLOCK_DELIMITERS = ('----', '....', '++++')


def _detect_code_block_delimiter(stripped: str) -> str | None:
    """Return delimiter character if line enters a code block, else None."""
    for delim in CODE_BLOCK_DELIMITERS:
        if stripped.startswith(delim) and len(stripped) >= 4 and all(c == delim[0] for c in stripped):
            return delim[0]
    return None


def _is_closing_delimiter(stripped: str, delim_char: str) -> bool:
    """Check if line matches the closing code block delimiter."""
    return stripped.startswith(delim_char * 4) and all(c == delim_char for c in stripped)


def _is_structural_line(line: str) -> bool:
    """Check if line is an AsciiDoc attribute definition, anchor, or block attribute."""
    trimmed = line.strip()
    if trimmed.startswith(':') and ':' in trimmed[1:]:
        return True
    if trimmed.startswith(('[[', '[#')) and trimmed.endswith(']'):
        return True
    return trimmed.startswith('[') and trimmed.endswith(']') and not trimmed.startswith('[appendix')


def _tokenize_line(line: str) -> list[tuple[str, str]]:
    """Split line into (kind, chunk) tuples where kind is 'text' or 'protected'."""
    tokens = []
    last_end = 0
    for m in INLINE_PROTECTED_RE.finditer(line):
        start, end = m.span()
        if start > last_end:
            tokens.append(('text', line[last_end:start]))
        tokens.append(('protected', line[start:end]))
        last_end = end
    if last_end < len(line):
        tokens.append(('text', line[last_end:]))
    return tokens


class CodeBlockTracker:
    """Tracks state within AsciiDoc fenced code blocks."""

    def __init__(self):
        self.delimiter: str | None = None

    @property
    def in_block(self) -> bool:
        return self.delimiter is not None

    def process_line(self, stripped: str) -> bool:
        """Update delimiter state; return True if line is inside or transitions a block."""
        if not self.in_block:
            delim = _detect_code_block_delimiter(stripped)
            if delim:
                self.delimiter = delim
                return True
            return False

        if _is_closing_delimiter(stripped, self.delimiter):
            self.delimiter = None
        return True


class AsciiDocOrphanFixer:
    def __init__(self, words: list[str] | None = None, nbsp_char: str = UNICODE_NBSP):
        self.words = words or DEFAULT_WORDS
        self.nbsp_char = nbsp_char
        escaped_words = '|'.join(re.escape(w) for w in self.words)
        # Note: \s matches Unicode whitespace including \u00A0 in Python 3
        pattern_inline = (
            r'(^|[\s(\[„"\'])('
            + escaped_words
            + r')[ \t]+(?=[^\s\.,;:!?\)\]\}"\'…\d])'
        )
        pattern_eol = (
            r'(^|[\s(\[„"\'])('
            + escaped_words
            + r')[ \t]*\n[ \t]*(?=[^\s\.,;:!?\)\]\}"\'…\d])'
        )
        self.orphan_inline_re = re.compile(pattern_inline)
        self.orphan_eol_re = re.compile(pattern_eol)

    def process_text_segment(self, segment: str) -> tuple[str, int]:
        """Fix orphan words in a plain text segment."""
        replacements = 0

        def repl(m):
            nonlocal replacements
            replacements += 1
            return m.group(1) + m.group(2) + self.nbsp_char

        res = self.orphan_eol_re.sub(repl, segment)
        res = self.orphan_inline_re.sub(repl, res)
        return res, replacements

    def process_line(self, line: str) -> tuple[str, int]:
        """Process a single prose line, protecting inline code and macros."""
        if _is_structural_line(line):
            return line, 0

        total_replacements = 0
        output_chunks = []
        for kind, chunk in _tokenize_line(line):
            if kind == 'text':
                chunk, count = self.process_text_segment(chunk)
                total_replacements += count
            output_chunks.append(chunk)

        return ''.join(output_chunks), total_replacements

    def process_content(self, content: str) -> tuple[str, int]:
        """Process entire AsciiDoc file content while respecting code blocks."""
        lines = content.splitlines(keepends=True)
        out_lines = []
        tracker = CodeBlockTracker()
        total_replacements = 0

        for line in lines:
            stripped = line.strip()

            if tracker.process_line(stripped) or any(stripped.startswith(p) for p in SKIP_LINE_PREFIXES):
                out_lines.append(line)
                continue

            fixed_line, count = self.process_line(line)
            out_lines.append(fixed_line)
            total_replacements += count

        return ''.join(out_lines), total_replacements


def _scan_directory(dir_path: str) -> list[str]:
    """Find all AsciiDoc files within a directory tree."""
    results = []
    for root, _, files in os.walk(dir_path):
        for f in sorted(files):
            if f.endswith(('.asc', '.adoc')):
                results.append(os.path.join(root, f))
    return results


def _collect_default_files() -> list[str]:
    """Collect AsciiDoc files from default locations (book/ and current directory)."""
    asc_files = []
    if os.path.isdir('book'):
        asc_files.extend(_scan_directory('book'))
    for f in sorted(os.listdir('.')):
        if f.endswith(('.asc', '.adoc')) and os.path.isfile(f):
            asc_files.append(f)
    return asc_files


def collect_asc_files(paths: list[str] | None = None) -> list[str]:
    """Collect all .asc / .adoc files from given paths or defaults."""
    if not paths:
        return _collect_default_files()

    asc_files = []
    for path in paths:
        if os.path.isfile(path):
            asc_files.append(path)
        elif os.path.isdir(path):
            asc_files.extend(_scan_directory(path))
    return asc_files


def _display_diff(file_path: str, original: str, fixed: str) -> None:
    """Print unified diff between original and fixed content."""
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        fixed.splitlines(keepends=True),
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=2
    )
    sys.stdout.writelines(diff)


def _handle_single_file(
    file_path: str,
    fixer: AsciiDocOrphanFixer,
    write_mode: bool,
    show_diff: bool
) -> int:
    """Process a single file; write changes or show diff if needed. Return replacements count."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        print(f"Warning: Could not decode {file_path} as UTF-8, skipping.", file=sys.stderr)
        return 0

    fixed_content, replacements = fixer.process_content(content)
    if replacements == 0:
        return 0

    print(f"  {file_path}: {replacements} orphan words found")
    if show_diff:
        _display_diff(file_path, content, fixed_content)
    if write_mode:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(fixed_content)

    return replacements


def _determine_mode_desc(write_mode: bool, check_mode: bool) -> str:
    """Return descriptive mode string: WRITE, CHECK, or DRY-RUN."""
    if write_mode:
        return "WRITE"
    if check_mode:
        return "CHECK"
    return "DRY-RUN"


def _print_completion_status(write_mode: bool, modified_count: int, check_mode: bool) -> None:
    """Print exit status message and exit with 1 if check failed."""
    if write_mode:
        print("Changes written to files.")
    elif modified_count > 0:
        if check_mode:
            print("Check failed: Unfixed orphan words found.")
            sys.exit(1)
        else:
            print("Run with -w / --write to apply these changes.")


def parse_arguments() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Fix orphan 'a' and single-letter words in AsciiDoc files."
    )
    parser.add_argument('paths', nargs='*', help='Files or directories to process (default: book/ and *.asc)')
    parser.add_argument('-w', '--write', action='store_true', help='Write changes back to files in-place')
    parser.add_argument(
        '-n', '--dry-run', action='store_true',
        help='Report changes without modifying files (default if not --write)'
    )
    parser.add_argument('-c', '--check', action='store_true', help='Exit with status 1 if any orphan words are found')
    parser.add_argument('-d', '--diff', action='store_true', help='Show unified diff of changes')
    parser.add_argument('--words', default='a,A', help='Comma-separated list of words to fix (default: a,A)')
    parser.add_argument('--use-entity', action='store_true', help='Use AsciiDoc {nbsp} instead of Unicode U+00A0')
    return parser.parse_args()


def main():
    args = parse_arguments()
    write_mode = args.write and not args.dry_run
    words = [w.strip() for w in args.words.split(',') if w.strip()]
    nbsp_char = ASCIIDOC_NBSP if args.use_entity else UNICODE_NBSP

    fixer = AsciiDocOrphanFixer(words=words, nbsp_char=nbsp_char)
    files = collect_asc_files(args.paths)
    if not files:
        print("No .asc or .adoc files found.")
        sys.exit(0)

    mode_desc = _determine_mode_desc(write_mode, args.check)
    fmt_desc = "{nbsp}" if args.use_entity else "Unicode U+00A0"
    print(f"=== fix_orphan_a.py [{mode_desc}] Target words: {words} | Format: {fmt_desc} ===")

    total_modified = 0
    total_replacements = 0

    for file_path in files:
        count = _handle_single_file(file_path, fixer, write_mode, args.diff)
        if count > 0:
            total_modified += 1
            total_replacements += count

    print("\nSummary:")
    print(f"  Files scanned:  {len(files)}")
    print(f"  Files affected: {total_modified}")
    print(f"  Orphans fixed:  {total_replacements}")

    _print_completion_status(write_mode, total_modified, args.check)


if __name__ == '__main__':
    main()
