interface CsvColumn {
  key: string
  header: string
}

// Characters that, when leading a field, make spreadsheet apps (Excel,
// Google Sheets, LibreOffice) interpret the field as a formula/macro
// instead of literal text ("CSV/Formula Injection" — see OWASP's CSV
// Injection cheat sheet). Display names in this app are fully
// attacker-controlled (synced from WhatsApp with no length/charset
// restriction), so a name like `=cmd|'/C calc'!A1` must not export unchanged.
const FORMULA_TRIGGER_CHARS = new Set(['=', '+', '-', '@', '\t', '\r'])

function escapeCsvField(value: unknown): string {
  let text = value === null || value === undefined ? '' : String(value)
  if (text.length > 0 && FORMULA_TRIGGER_CHARS.has(text[0]!)) {
    // Standard mitigation: a leading apostrophe forces spreadsheet apps to
    // treat the cell as text. It's invisible in the rendered cell (Excel/
    // Sheets/LibreOffice all strip a single leading `'` from display), so
    // this doesn't corrupt otherwise-legitimate values.
    text = `'${text}`
  }
  if (/["\n\r,]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

/** Serializes rows into RFC4180-quoted CSV text (CRLF line endings). */
export function toCsv(rows: Record<string, unknown>[], columns: CsvColumn[]): string {
  const lines = [columns.map((column) => escapeCsvField(column.header)).join(',')]
  for (const row of rows) {
    lines.push(columns.map((column) => escapeCsvField(row[column.key])).join(','))
  }
  return lines.join('\r\n')
}

/** Triggers a client-side download of CSV text as a file. */
export function downloadCsv(filename: string, csvText: string): void {
  const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

/** Turns a display name into a filesystem/URL-safe slug for use in export filenames. */
export function slugifyFileName(name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return slug || 'export'
}
