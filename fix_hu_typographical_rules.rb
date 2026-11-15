#!/usr/bin/env ruby

# frozen_string_literal: true

# fix_hu_typographical_rules.rb - Hungarian typographical and orthographical rule fixer for AsciiDoc.
#
# Implements official Hungarian typographical rules (AkH. 12 and typography conventions):
# 1. 'e-mail-cím' rule:
#    - Corrects 'email cím', 'e-mail cím', 'email-cím', etc. to 'e-mail-cím' (with all inflected forms:
#      e-mail-címet, e-mail-címek, e-mail-címe, e-mail-címünk, e-mail-címeid, stb.)
#    - Uses non-breaking hyphen (Unicode U+2011) so 'e‑mail‑cím' is never broken across lines.
#    - Normalizes other e-mail compounds (e-mail-fiók, e-mail-értesítés, e-mail-szolgáltatás,
#      e-mail-munkafolyamat, e-mail-alapú, e-mail-üzenet, stb.).
#    - Normalizes standalone 'e-mail' with non-breaking hyphen.
# 2. Hungarian orphan words:
#    - Definite articles ('a', 'az', 'A', 'Az')
#    - Indefinite articles ('egy', 'Egy')
#    - Conjunctions ('és', 's', 'És', 'S', 'de', 'De')
#    - Binds to the following word using a non-breaking space (Unicode U+00A0 or {nbsp}).
# 3. Numbers and units / nouns:
#    - Ordinals with nouns: '1. ábra', '2. táblázat', '3. fejezet', '4. szakasz', '5. oldal' -> bound with NBSP
#    - Numbers with units: '100 bájt', '64 bit', '10 MB', '5 perc', stb. -> bound with NBSP
#    - Abbreviations: 'pl. ', 'kb. ' -> bound with NBSP
# 4. Dashes (Gondolatjel):
#    - ' -- ' or ' – ' -> preceded by non-breaking space (U+00A0) so the dash never wraps to line start.
# 5. Hungarian quotation marks (optional via --fix-quotes):
#    - Straight quotes "..." converted to „...” in prose.
#
# Protects AsciiDoc syntax:
# - Fenced code blocks (----, ...., ++++)
# - Block metadata, anchors, attributes, includes, and images
# - Inline code spans (`...`), URLs, macros, anchors (<<...>>), index tags (((...))), callouts (<1>)

require 'optparse'

UNICODE_NBSP = "\u00A0"
ASCIIDOC_NBSP = '{nbsp}'
UNICODE_NB_HYPHEN = "\u2011"
STANDARD_HYPHEN = '-'

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

class HungarianTypographyFixer
  attr_reader :enabled_rules, :fix_quotes, :nbsp, :hyphen

  def initialize(nbsp_char: UNICODE_NBSP, hyphen_char: UNICODE_NB_HYPHEN, rules: nil, fix_quotes: false)
    @nbsp = nbsp_char
    @hyphen = hyphen_char
    @enabled_rules = rules ? rules.map(&:to_s) : %w[email orphans numbers dashes]
    @fix_quotes = fix_quotes

    init_regexes
  end

  def init_regexes
    # 1. E-mail rules
    @re_email_cim = /\b([Ee])(?:-?mail|mail)[ \t\-]+(cím[a-záéíóöőúüű]*)\b/
    compounds = /(értesítés[a-záéíóöőúüű]*|fiók[a-záéíóöőúüű]*|üzenet[a-záéíóöőúüű]*|küldés[a-záéíóöőúüű]*|szolgáltatás[a-záéíóöőúüű]*|munkafolyamat[a-záéíóöőúüű]*|alapú[a-záéíóöőúüű]*|kliens[a-záéíóöőúüű]*|lista[a-záéíóöőúüű]*)/
    @re_email_other = /\b([Ee])(?:-?mail|mail)[ \t]+#{compounds}\b/
    @re_email_standalone = /\b([Ee])(?:-?mail|mail)\b(?![a-záéíóöőúüű@\.\/_\-])/

    # 2. Orphan articles & conjunctions
    orphan_words = 'a|A|az|Az|egy|Egy|és|És|s|S|de|De'
    @re_orphan_inline = /(^|[\s(\[„"'\u00A0])(#{orphan_words})[ \t]+(?=[^\s\.,;:!?\)\]\}"'…\d])/
    @re_orphan_eol = /(^|[\s(\[„"'\u00A0])(#{orphan_words})[ \t]*\n[ \t]*(?=[^\s\.,;:!?\)\]\}"'…\d])/

    # 3. Numbers with nouns & units
    nouns = '(ábra|ábrán|ábrához|ábrát|ábrák|ábrákon|táblázat|táblázatban|táblázatot|fejezet|fejezetben|fejezethez|fejezetet|szakasz|szakaszban|szakaszhoz|oldal|oldalon|oldalra|pont|pontban)'
    @re_ordinals = /(\d+\.)[ \t]+(#{nouns})\b/

    units = '(bájt|bájtot|bájtos|byte|kB|MB|GB|TB|bit|bites|kbit|Mbit|s|mp|perc|perces|óra|órás|nap|napos|hét|hetes|hónap|hónapos|év|éves)'
    @re_units = /(\d+)[ \t]+(#{units})\b/

    @re_abbr = /(^|[\s(\[„"'\u00A0])(pl|kb|ti|vö)\.[ \t]+(?=[^\s\.,;:!?\)\]\}"'…\d])/

    # 4. Dashes
    @re_dashes = /[ \t]+(--|–)[ \t]+/

    # 5. Quotes
    @re_quotes = /"([^"\n]+)"/
  end

  def apply_rules(text)
    counts = Hash.new(0)

    if @enabled_rules.include?('email')
      h = @hyphen

      text = text.gsub(@re_email_cim) do
        counts['email'] += 1
        lead = $1 == $1.upcase ? 'E' : 'e'
        "#{lead}#{h}mail#{h}#{$2}"
      end

      text = text.gsub(@re_email_other) do
        counts['email'] += 1
        lead = $1 == $1.upcase ? 'E' : 'e'
        "#{lead}#{h}mail#{h}#{$2}"
      end

      text = text.gsub(@re_email_standalone) do
        counts['email'] += 1
        lead = $1 == $1.upcase ? 'E' : 'e'
        "#{lead}#{h}mail"
      end
    end

    if @enabled_rules.include?('orphans')
      text = text.gsub(@re_orphan_eol) do
        counts['orphans'] += 1
        "#{$1}#{$2}#{@nbsp}"
      end

      text = text.gsub(@re_orphan_inline) do
        counts['orphans'] += 1
        "#{$1}#{$2}#{@nbsp}"
      end
    end

    if @enabled_rules.include?('numbers')
      text = text.gsub(@re_ordinals) do
        counts['numbers'] += 1
        "#{$1}#{@nbsp}#{$2}"
      end

      text = text.gsub(@re_units) do
        counts['numbers'] += 1
        "#{$1}#{@nbsp}#{$2}"
      end

      text = text.gsub(@re_abbr) do
        counts['numbers'] += 1
        "#{$1}#{$2}.#{@nbsp}"
      end
    end

    if @enabled_rules.include?('dashes')
      text = text.gsub(@re_dashes) do
        counts['dashes'] += 1
        "#{@nbsp}#{$1} "
      end
    end

    if @fix_quotes
      text = text.gsub(@re_quotes) do
        counts['quotes'] += 1
        "„#{$1}”"
      end
    end

    [text, counts]
  end

  def process_line(line)
    trimmed = line.strip
    return [line, {}] if trimmed.start_with?(':') && trimmed[1..].include?(':')
    return [line, {}] if trimmed.start_with?('[[') && trimmed.end_with?(']]')
    return [line, {}] if trimmed.start_with?('[#') && trimmed.end_with?(']')
    return [line, {}] if trimmed.start_with?('[') && trimmed.end_with?(']') && !trimmed.start_with?('[appendix')

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

    total_counts = Hash.new(0)
    output_chunks = []

    tokens.each do |kind, chunk|
      if kind == :text
        fixed_chunk, counts = apply_rules(chunk)
        output_chunks << fixed_chunk
        counts.each { |k, v| total_counts[k] += v }
      else
        output_chunks << chunk
      end
    end

    [output_chunks.join, total_counts]
  end

  def process_content(content)
    lines = content.lines
    out_lines = []
    in_code_block = false
    code_delimiter = nil
    total_counts = Hash.new(0)

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

      fixed_line, counts = process_line(line)
      out_lines << fixed_line
      counts.each { |k, v| total_counts[k] += v }
    end

    [out_lines.join, total_counts]
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
  use_entity: false,
  standard_hyphen: false,
  fix_quotes: false,
  rules: %w[email orphans numbers dashes]
}

OptionParser.new do |opts|
  opts.banner = "Usage: fix_hu_typographical_rules.rb [options] [files/directories...]"

  opts.on('-w', '--write', 'Write changes back to files in-place') { options[:write] = true }
  opts.on('-n', '--dry-run', 'Report changes without modifying files') { options[:dry_run] = true }
  opts.on('-c', '--check', 'Exit with status 1 if any issues are found') { options[:check] = true }
  opts.on('-d', '--diff', 'Show diff of changes') { options[:diff] = true }
  opts.on('--use-entity', 'Use AsciiDoc {nbsp} instead of Unicode U+00A0') { options[:use_entity] = true }
  opts.on('--standard-hyphen', 'Use standard ASCII hyphen instead of non-breaking hyphen U+2011') { options[:standard_hyphen] = true }
  opts.on('--fix-quotes', 'Convert straight double quotes "..." to Hungarian „...”') { options[:fix_quotes] = true }
  opts.on('--rules RULES', 'Comma-separated rules: email,orphans,numbers,dashes (default: all)') do |r|
    options[:rules] = r.split(',').map(&:strip)
  end
  opts.on('-h', '--help', 'Show help') do
    puts opts
    exit
  end
end.parse!

write_mode = options[:write] && !options[:dry_run]
nbsp_char = options[:use_entity] ? ASCIIDOC_NBSP : UNICODE_NBSP
hyphen_char = options[:standard_hyphen] ? STANDARD_HYPHEN : UNICODE_NB_HYPHEN

fixer = HungarianTypographyFixer.new(
  nbsp_char: nbsp_char,
  hyphen_char: hyphen_char,
  rules: options[:rules],
  fix_quotes: options[:fix_quotes]
)

files = collect_asc_files(ARGV)
if files.empty?
  puts "No .asc or .adoc files found."
  exit 0
end

total_files_scanned = files.length
total_files_modified = 0
rule_totals = Hash.new(0)

mode_desc = write_mode ? "WRITE" : (options[:check] ? "CHECK" : "DRY-RUN")
hyphen_desc = options[:standard_hyphen] ? "Standard (-)" : "Non-breaking (U+2011)"
nbsp_desc = options[:use_entity] ? "{nbsp}" : "Unicode U+00A0"
puts "=== fix_hu_typographical_rules.rb [#{mode_desc}] Rules: #{options[:rules].inspect} | Hyphen: #{hyphen_desc} | NBSP: #{nbsp_desc} ==="

files.each do |file_path|
  content = File.read(file_path, encoding: 'UTF-8')
  fixed_content, counts = fixer.process_content(content)
  total_in_file = counts.values.sum

  if total_in_file > 0
    total_files_modified += 1
    counts.each { |k, v| rule_totals[k] += v }

    details = counts.select { |_, v| v > 0 }.map { |k, v| "#{k}: #{v}" }.join(', ')
    puts "  #{file_path}: #{total_in_file} fixes (#{details})"

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
puts "  Files scanned:   #{total_files_scanned}"
puts "  Files affected:  #{total_files_modified}"
puts "  Total fixes:     #{rule_totals.values.sum}"
rule_totals.sort.each do |k, v|
  puts "    - #{k}: #{v}"
end

if write_mode
  puts "Changes written to files."
elsif total_files_modified > 0
  if options[:check]
    puts "Check failed: Typography/spelling issues found."
    exit 1
  else
    puts "Run with -w / --write to apply these changes."
  end
end
