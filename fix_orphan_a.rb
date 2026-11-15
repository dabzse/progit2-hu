#!/usr/bin/env ruby

# frozen_string_literal: true

# fix_orphan_a.rb - Language-agnostic / generic orphan 'a' fixer for AsciiDoc files.
#
# Fixes orphan standalone 'a' / 'A' (and optionally other single-letter words)
# at line ends or before words by inserting a non-breaking space (Unicode U+00A0
# or AsciiDoc {nbsp}), preventing awkward typographic line-wrapping.
#
# Protects AsciiDoc syntax:
# - Fenced code blocks (----, ...., ++++)
# - Block metadata, anchors, attributes, includes, and images
# - Inline code spans (`...`), URLs, macros, anchors (<<...>>), index tags (((...))), callouts (<1>)

require 'optparse'

DEFAULT_WORDS = %w[a A].freeze
UNICODE_NBSP = "\u00A0"
ASCIIDOC_NBSP = '{nbsp}'

# Regex to identify inline protected spans in AsciiDoc
INLINE_PROTECTED_RE = Regexp.union(
  /`+[^`\n]+`+/,                                                       # Inline code
  %r{https?://[^\s\[\]<>"'\)]+},                                       # URLs
  /(?:link|xref|image|video|audio|pass|kbd|btn|menu):[^\s\[\]]*\[[^\]]*\]/, # Inline macros
  /<<[^>\n]+>>/,                                                      # Cross-references
  /\(\(\([^)\n]+\)\)\)/,                                              # Index entries
  %r{<[a-zA-Z/][^>\n]*>},                                              # HTML tags
  /<[0-9]+>/                                                          # Callouts
)

SKIP_LINE_PREFIXES = %w[
  image:: video:: audio:: include::
  ifdef:: ifndef:: ifeval:: endif::
  // |===
].freeze

CODE_BLOCK_DELIMITERS = %w[---- .... ++++].freeze

class AsciiDocOrphanFixer
  def initialize(words: DEFAULT_WORDS, nbsp_char: UNICODE_NBSP)
    @words = words
    @nbsp_char = nbsp_char

    escaped_words = @words.map { |w| Regexp.escape(w) }.join('|')
    @orphan_inline_re = /(^|[\s(\[„"'\u00A0])(#{escaped_words})[ \t]+(?=[^\s\.,;:!?\)\]\}"'…\d])/
    @orphan_eol_re = /(^|[\s(\[„"'\u00A0])(#{escaped_words})[ \t]*\n[ \t]*(?=[^\s\.,;:!?\)\]\}"'…\d])/
  end

  def process_text_segment(segment)
    replacements = 0

    res = segment.gsub(@orphan_eol_re) do
      replacements += 1
      "#{$1}#{$2}#{@nbsp_char}"
    end

    res = res.gsub(@orphan_inline_re) do
      replacements += 1
      "#{$1}#{$2}#{@nbsp_char}"
    end

    [res, replacements]
  end

  def process_line(line)
    trimmed = line.strip
    return [line, 0] if trimmed.start_with?(':') && trimmed[1..].include?(':')
    return [line, 0] if trimmed.start_with?('[[') && trimmed.end_with?(']]')
    return [line, 0] if trimmed.start_with?('[#') && trimmed.end_with?(']')
    return [line, 0] if trimmed.start_with?('[') && trimmed.end_with?(']') && !trimmed.start_with?('[appendix')

    # Split line into protected spans and text spans
    tokens = []
    last_end = 0

    line.scan(INLINE_PROTECTED_RE) do
      m = Regexp.last_match
      start_pos = m.begin(0)
      end_pos = m.end(0)

      if start_pos > last_end
        tokens << [:text, line[last_end...start_pos]]
      end
      tokens << [:protected, line[start_pos...end_pos]]
      last_end = end_pos
    end

    if last_end < line.length
      tokens << [:text, line[last_end..]]
    end

    total_replacements = 0
    output_chunks = []

    tokens.each do |kind, chunk|
      if kind == :text
        fixed_chunk, count = process_text_segment(chunk)
        output_chunks << fixed_chunk
        total_replacements += count
      else
        output_chunks << chunk
      end
    end

    [output_chunks.join, total_replacements]
  end

  def process_content(content)
    lines = content.lines
    out_lines = []
    in_code_block = false
    code_delimiter = nil
    total_replacements = 0

    lines.each do |line|
      stripped = line.strip

      if !in_code_block
        CODE_BLOCK_DELIMITERS.each do |delim|
          if stripped.start_with?(delim) && stripped.length >= 4 && stripped.chars.all? { |c| c == delim[0] }
            in_code_block = true
            code_delimiter = delim[0]
            break
          end
        end
        if in_code_block
          out_lines << line
          next
        end
      else
        if stripped.start_with?(code_delimiter * 4) && stripped.chars.all? { |c| c == code_delimiter }
          in_code_block = false
          code_delimiter = nil
        end
        out_lines << line
        next
      end

      if SKIP_LINE_PREFIXES.any? { |prefix| stripped.start_with?(prefix) }
        out_lines << line
        next
      end

      fixed_line, count = process_line(line)
      out_lines << fixed_line
      total_replacements += count
    end

    [out_lines.join, total_replacements]
  end
end

def collect_asc_files(paths)
  asc_files = []
  if paths.empty?
    if Dir.exist?('book')
      Dir.glob('book/**/*.{asc,adoc}').sort.each { |f| asc_files << f }
    end
    Dir.glob('*.{asc,adoc}').sort.each do |f|
      asc_files << f if File.file?(f)
    end
    return asc_files
  end

  paths.each do |path|
    if File.file?(path)
      asc_files << path
    elsif Dir.exist?(path)
      Dir.glob("#{path}/**/*.{asc,adoc}").sort.each { |f| asc_files << f }
    end
  end
  asc_files
end

options = {
  write: false,
  dry_run: false,
  check: false,
  diff: false,
  words: DEFAULT_WORDS,
  use_entity: false
}

OptionParser.new do |opts|
  opts.banner = "Usage: fix_orphan_a.rb [options] [files/directories...]"

  opts.on('-w', '--write', 'Write changes back to files in-place') { options[:write] = true }
  opts.on('-n', '--dry-run', 'Report changes without modifying files') { options[:dry_run] = true }
  opts.on('-c', '--check', 'Exit with status 1 if any orphan words are found') { options[:check] = true }
  opts.on('-d', '--diff', 'Show diff of changes') { options[:diff] = true }
  opts.on('--words WORDS', 'Comma-separated list of words to fix (default: a,A)') do |w|
    options[:words] = w.split(',').map(&:strip)
  end
  opts.on('--use-entity', 'Use AsciiDoc {nbsp} instead of Unicode U+00A0') { options[:use_entity] = true }
  opts.on('-h', '--help', 'Show help') do
    puts opts
    exit
  end
end.parse!

write_mode = options[:write] && !options[:dry_run]
nbsp_char = options[:use_entity] ? ASCIIDOC_NBSP : UNICODE_NBSP

fixer = AsciiDocOrphanFixer.new(words: options[:words], nbsp_char: nbsp_char)
files = collect_asc_files(ARGV)

if files.empty?
  puts "No .asc or .adoc files found."
  exit 0
end

total_files_scanned = files.length
total_files_modified = 0
total_orphans_fixed = 0

mode_desc = write_mode ? "WRITE" : (options[:check] ? "CHECK" : "DRY-RUN")
puts "=== fix_orphan_a.rb [#{mode_desc}] Target words: #{options[:words].inspect} | Format: #{options[:use_entity] ? '{nbsp}' : 'Unicode U+00A0'} ==="

files.each do |file_path|
  content = File.read(file_path, encoding: 'UTF-8')
  fixed_content, replacements = fixer.process_content(content)

  if replacements > 0
    total_files_modified += 1
    total_orphans_fixed += replacements
    puts "  #{file_path}: #{replacements} orphan words found"

    if options[:diff]
      puts "--- a/#{file_path}"
      puts "+++ b/#{file_path}"
      orig_lines = content.lines
      fixed_lines = fixed_content.lines
      orig_lines.each_with_index do |line, idx|
        if line != fixed_lines[idx]
          puts "- #{line.chomp}"
          puts "+ #{fixed_lines[idx].chomp}"
        end
      end
    end

    if write_mode
      File.write(file_path, fixed_content, encoding: 'UTF-8')
    end
  end
end

puts "\nSummary:"
puts "  Files scanned:  #{total_files_scanned}"
puts "  Files affected: #{total_files_modified}"
puts "  Orphans fixed:  #{total_orphans_fixed}"

if write_mode
  puts "Changes written to files."
elsif total_files_modified > 0
  if options[:check]
    puts "Check failed: Unfixed orphan words found."
    exit 1
  else
    puts "Run with -w / --write to apply these changes."
  end
end
