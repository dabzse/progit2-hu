#!/usr/bin/env python3
"""
fix_hu_typographical_rules.py - Hungarian typographical and orthographical rule fixer for AsciiDoc.

Implements official Hungarian typographical rules (AkH. 12 and typography conventions):
1. 'e-mail-cím' rule:
   - Corrects 'email cím', 'e-mail cím', 'email-cím', etc. to 'e-mail-cím' (with all inflected forms:
     e-mail-címet, e-mail-címek, e-mail-címe, e-mail-címünk, e-mail-címeid, stb.)
   - Uses non-breaking hyphen (Unicode U+2011) so 'e‑mail‑cím' is never broken across lines.
   - Normalizes other e-mail compounds (e-mail-fiók, e-mail-értesítés, e-mail-szolgáltatás,
     e-mail-munkafolyamat, e-mail-alapú, e-mail-üzenet, stb.).
   - Normalizes standalone 'e-mail' with non-breaking hyphen.
2. Hungarian orphan words:
   - Definite articles ('a', 'az', 'A', 'Az')
   - Indefinite articles ('egy', 'Egy')
   - Conjunctions ('és', 's', 'És', 'S', 'de', 'De')
   - Binds to the following word using a non-breaking space (Unicode U+00A0 or {nbsp}).
3. Numbers and units / nouns:
   - Ordinals with nouns: '1. ábra', '2. táblázat', '3. fejezet', '4. szakasz', '5. oldal' -> bound with NBSP
   - Numbers with units: '100 bájt', '64 bit', '10 MB', '5 perc', stb. -> bound with NBSP
   - Abbreviations: 'pl. ', 'kb. ' -> bound with NBSP
4. Dashes (Gondolatjel):
   - ' -- ' or ' – ' -> preceded by non-breaking space (U+00A0) so the dash never wraps to line start.
5. Hungarian quotation marks (optional via --fix-quotes):
   - Straight quotes "..." converted to „...” in prose.

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

UNICODE_NBSP = '\u00A0'
ASCIIDOC_NBSP = '{nbsp}'
UNICODE_NB_HYPHEN = '\u2011'
STANDARD_HYPHEN = '-'

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


def _merge_counts(target: dict[str, int], source: dict[str, int]) -> None:
    """Merge rule occurrence counts into target dictionary."""
    for k, v in source.items():
        target[k] = target.get(k, 0) + v


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


class HungarianTypographyFixer:
    def __init__(
        self,
        nbsp_char: str = UNICODE_NBSP,
        hyphen_char: str = UNICODE_NB_HYPHEN,
        rules: list[str] | None = None,
        fix_quotes: bool = False
    ):
        self.nbsp = nbsp_char
        self.hyphen = hyphen_char
        self.enabled_rules = set(rules) if rules else {'email', 'orphans', 'numbers', 'dashes'}
        self.fix_quotes = fix_quotes

        self._init_regexes()

    def _init_regexes(self):
        # 1. E-mail rules
        self.re_email_cim = re.compile(r'\b([Ee])-?mail[ \t\-]+(cím[a-záéíóöőúüű]*)\b')
        compounds = (
            r'(értesítés[a-záéíóöőúüű]*|fiók[a-záéíóöőúüű]*|üzenet[a-záéíóöőúüű]*|'
            r'küldés[a-záéíóöőúüű]*|szolgáltatás[a-záéíóöőúüű]*|munkafolyamat[a-záéíóöőúüű]*|'
            r'alapú[a-záéíóöőúüű]*|kliens[a-záéíóöőúüű]*|lista[a-záéíóöőúüű]*)'
        )
        self.re_email_other = re.compile(r'\b([Ee])-?mail[ \t]+' + compounds + r'\b')
        self.re_email_standalone = re.compile(r'\b([Ee])-?mail\b(?![a-záéíóöőúüű@\./_-])')

        # 2. Orphan articles & conjunctions
        # Note: \s matches Unicode whitespace including \u00A0 in Python 3
        orphan_words = r'a|A|az|Az|egy|Egy|és|És|s|S|de|De'
        self.re_orphan_inline = re.compile(
            r'(^|[\s(\[„"\'])(' + orphan_words + r')[ \t]+(?=[^\s\.,;:!?\)\]\}"\'…\d])'
        )
        self.re_orphan_eol = re.compile(
            r'(^|[\s(\[„"\'])(' + orphan_words + r')[ \t]*\n[ \t]*(?=[^\s\.,;:!?\)\]\}"\'…\d])'
        )

        # 3. Numbers with nouns & units
        nouns = (
            r'(ábra|ábrán|ábrához|ábrát|ábrák|ábrákon|táblázat|táblázatban|táblázatot|'
            r'fejezet|fejezetben|fejezethez|fejezetet|szakasz|szakaszban|szakaszhoz|'
            r'oldal|oldalon|oldalra|pont|pontban)'
        )
        self.re_ordinals = re.compile(r'(\d+\.)[ \t]+(' + nouns + r')\b')
        units = (
            r'(bájt|bájtot|bájtos|byte|kB|MB|GB|TB|bit|bites|kbit|Mbit|'
            r's|mp|perc|perces|óra|órás|nap|napos|hét|hetes|hónap|hónapos|év|éves)'
        )
        self.re_units = re.compile(r'(\d+)[ \t]+(' + units + r')\b')
        self.re_abbr = re.compile(r'(^|[\s(\[„"\'])(pl|kb|ti|vö)\.[ \t]+(?=[^\s\.,;:!?\)\]\}"\'…\d])')

        # 4. Dashes (Gondolatjel)
        self.re_dashes = re.compile(r'[ \t]+(--|–)[ \t]+')

        # 5. Quotes
        self.re_quotes = re.compile(r'"([^"\n]+)"')

    def _apply_email_rules(self, text: str, counts: dict[str, int]) -> str:
        """Apply rules for e-mail-cím, related compounds, and standalone e-mail."""
        h = self.hyphen

        def repl_cim(m):
            counts['email'] += 1
            lead = 'E' if m.group(1).isupper() else 'e'
            return f"{lead}{h}mail{h}{m.group(2)}"

        def repl_other(m):
            counts['email'] += 1
            lead = 'E' if m.group(1).isupper() else 'e'
            return f"{lead}{h}mail{h}{m.group(2)}"

        def repl_standalone(m):
            counts['email'] += 1
            lead = 'E' if m.group(1).isupper() else 'e'
            return f"{lead}{h}mail"

        text = self.re_email_cim.sub(repl_cim, text)
        text = self.re_email_other.sub(repl_other, text)
        return self.re_email_standalone.sub(repl_standalone, text)

    def _apply_orphan_rules(self, text: str, counts: dict[str, int]) -> str:
        """Apply rules for Hungarian orphan articles and conjunctions."""
        def repl(m):
            counts['orphans'] += 1
            return m.group(1) + m.group(2) + self.nbsp

        text = self.re_orphan_eol.sub(repl, text)
        return self.re_orphan_inline.sub(repl, text)

    def _apply_number_rules(self, text: str, counts: dict[str, int]) -> str:
        """Apply rules for numbers with ordinals, units, and abbreviations."""
        def repl_num(m):
            counts['numbers'] += 1
            return m.group(1) + self.nbsp + m.group(2)

        def repl_abbr(m):
            counts['numbers'] += 1
            return m.group(1) + m.group(2) + '.' + self.nbsp

        text = self.re_ordinals.sub(repl_num, text)
        text = self.re_units.sub(repl_num, text)
        return self.re_abbr.sub(repl_abbr, text)

    def _apply_dash_rules(self, text: str, counts: dict[str, int]) -> str:
        """Apply rules for parenthetical dashes."""
        def repl_dash(m):
            counts['dashes'] += 1
            return self.nbsp + m.group(1) + ' '

        return self.re_dashes.sub(repl_dash, text)

    def _apply_quote_rules(self, text: str, counts: dict[str, int]) -> str:
        """Apply rules for Hungarian low-high quotation marks."""
        def repl_quote(m):
            counts['quotes'] += 1
            return f"„{m.group(1)}”"

        return self.re_quotes.sub(repl_quote, text)

    def apply_rules(self, text: str) -> tuple[str, dict[str, int]]:
        """Apply all enabled typographical rules to a prose text chunk."""
        counts = {'email': 0, 'orphans': 0, 'numbers': 0, 'dashes': 0, 'quotes': 0}
        if 'email' in self.enabled_rules:
            text = self._apply_email_rules(text, counts)
        if 'orphans' in self.enabled_rules:
            text = self._apply_orphan_rules(text, counts)
        if 'numbers' in self.enabled_rules:
            text = self._apply_number_rules(text, counts)
        if 'dashes' in self.enabled_rules:
            text = self._apply_dash_rules(text, counts)
        if self.fix_quotes:
            text = self._apply_quote_rules(text, counts)
        return text, counts

    def process_line(self, line: str) -> tuple[str, dict[str, int]]:
        """Process a single prose line, protecting inline code and macros."""
        if _is_structural_line(line):
            return line, {}

        total_counts: dict[str, int] = {}
        output_chunks = []
        for kind, chunk in _tokenize_line(line):
            if kind == 'text':
                chunk, counts = self.apply_rules(chunk)
                _merge_counts(total_counts, counts)
            output_chunks.append(chunk)

        return ''.join(output_chunks), total_counts

    def process_content(self, content: str) -> tuple[str, dict[str, int]]:
        """Process entire AsciiDoc file content while respecting code blocks."""
        lines = content.splitlines(keepends=True)
        out_lines = []
        tracker = CodeBlockTracker()
        total_counts: dict[str, int] = {}

        for line in lines:
            stripped = line.strip()

            if tracker.process_line(stripped) or any(stripped.startswith(p) for p in SKIP_LINE_PREFIXES):
                out_lines.append(line)
                continue

            fixed_line, counts = self.process_line(line)
            out_lines.append(fixed_line)
            _merge_counts(total_counts, counts)

        return ''.join(out_lines), total_counts


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
    fixer: HungarianTypographyFixer,
    write_mode: bool,
    show_diff: bool
) -> dict[str, int]:
    """Process a single file; write changes or show diff if needed. Return counts dict."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        print(f"Warning: Could not decode {file_path} as UTF-8, skipping.", file=sys.stderr)
        return {}

    fixed_content, counts = fixer.process_content(content)
    total_in_file = sum(counts.values())
    if total_in_file == 0:
        return {}

    details = ', '.join(f"{k}: {v}" for k, v in counts.items() if v > 0)
    print(f"  {file_path}: {total_in_file} fixes ({details})")

    if show_diff:
        _display_diff(file_path, content, fixed_content)

    if write_mode:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(fixed_content)

    return counts


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
            print("Check failed: Typography/spelling issues found.")
            sys.exit(1)
        else:
            print("Run with -w / --write to apply these changes.")


def parse_arguments() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Fix Hungarian typographical and orthographical rules in AsciiDoc files."
    )
    parser.add_argument('paths', nargs='*', help='Files or directories to process (default: book/ and *.asc)')
    parser.add_argument('-w', '--write', action='store_true', help='Write changes back to files in-place')
    parser.add_argument('-n', '--dry-run', action='store_true', help='Report changes without modifying files (default)')
    parser.add_argument('-c', '--check', action='store_true', help='Exit with status 1 if any issues are found')
    parser.add_argument('-d', '--diff', action='store_true', help='Show unified diff of changes')
    parser.add_argument('--use-entity', action='store_true', help='Use AsciiDoc {nbsp} instead of Unicode U+00A0')
    parser.add_argument(
        '--standard-hyphen', action='store_true',
        help='Use standard ASCII hyphen instead of non-breaking hyphen U+2011'
    )
    parser.add_argument(
        '--fix-quotes', action='store_true',
        help='Convert straight double quotes "..." to Hungarian „...”'
    )
    parser.add_argument('--rules', default='email,orphans,numbers,dashes',
                        help='Comma-separated list of rules to enable: email,orphans,numbers,dashes (default: all)')
    return parser.parse_args()


def main():
    args = parse_arguments()
    write_mode = args.write and not args.dry_run
    nbsp_char = ASCIIDOC_NBSP if args.use_entity else UNICODE_NBSP
    hyphen_char = STANDARD_HYPHEN if args.standard_hyphen else UNICODE_NB_HYPHEN
    enabled_rules = [r.strip() for r in args.rules.split(',') if r.strip()]

    fixer = HungarianTypographyFixer(
        nbsp_char=nbsp_char,
        hyphen_char=hyphen_char,
        rules=enabled_rules,
        fix_quotes=args.fix_quotes
    )

    files = collect_asc_files(args.paths)
    if not files:
        print("No .asc or .adoc files found.")
        sys.exit(0)

    mode_desc = _determine_mode_desc(write_mode, args.check)
    hyphen_desc = "Standard (-)" if args.standard_hyphen else "Non-breaking (U+2011)"
    nbsp_desc = "{nbsp}" if args.use_entity else "Unicode U+00A0"
    print(
        f"=== fix_hu_typographical_rules.py [{mode_desc}] "
        f"Rules: {enabled_rules} | Hyphen: {hyphen_desc} | NBSP: {nbsp_desc} ==="
    )

    total_modified = 0
    rule_totals: dict[str, int] = {}

    for file_path in files:
        counts = _handle_single_file(file_path, fixer, write_mode, args.diff)
        if sum(counts.values()) > 0:
            total_modified += 1
            _merge_counts(rule_totals, counts)

    print("\nSummary:")
    print(f"  Files scanned:   {len(files)}")
    print(f"  Files affected:  {total_modified}")
    print(f"  Total fixes:     {sum(rule_totals.values())}")
    for k, v in sorted(rule_totals.items()):
        print(f"    - {k}: {v}")

    _print_completion_status(write_mode, total_modified, args.check)


if __name__ == '__main__':
    main()
