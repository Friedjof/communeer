import { describe, expect, it } from 'vitest'
import { slugifyFileName, toCsv } from './csv'

describe('toCsv', () => {
  it('passes plain values through unquoted', () => {
    const csv = toCsv([{ name: 'Alice', age: 30 }], [
      { key: 'name', header: 'Name' },
      { key: 'age', header: 'Age' },
    ])
    expect(csv).toBe('Name,Age\r\nAlice,30')
  })

  it('RFC4180-quotes values containing commas, quotes, or newlines', () => {
    const csv = toCsv(
      [
        { name: 'Smith, John' },
        { name: 'Say "hi"' },
        { name: 'Line1\nLine2' },
      ],
      [{ key: 'name', header: 'Name' }],
    )
    const rows = csv.split('\r\n')
    expect(rows[0]).toBe('Name')
    expect(rows[1]).toBe('"Smith, John"')
    expect(rows[2]).toBe('"Say ""hi"""')
    expect(rows[3]).toBe('"Line1\nLine2"')
  })

  it('handles null/undefined values as empty fields', () => {
    const csv = toCsv([{ name: null }, { name: undefined }], [{ key: 'name', header: 'Name' }])
    expect(csv).toBe('Name\r\n\r\n')
  })

  describe('CSV formula-injection mitigation', () => {
    it.each([
      ["=cmd|'/C calc'!A1", "'=cmd|'/C calc'!A1"],
      ['+1+1', "'+1+1"],
      ['-1+1', "'-1+1"],
      ['@SUM(A1:A9)', "'@SUM(A1:A9)"],
      ['\tmalicious', "'\tmalicious"],
      ['\rmalicious', "'\rmalicious"],
    ])('prefixes a leading apostrophe for %j', (input, expected) => {
      const csv = toCsv([{ name: input }], [{ key: 'name', header: 'Name' }])
      const rows = csv.split('\r\n')
      // Quoting may still apply on top of the apostrophe prefix (e.g. the
      // \r case also matches the RFC4180 quote trigger) — strip surrounding
      // quotes and undo doubled-quote escaping before comparing.
      const raw = rows[1]!.startsWith('"') ? rows[1]!.slice(1, -1).replace(/""/g, '"') : rows[1]!
      expect(raw).toBe(expected)
    })

    it('does not prefix a value that merely contains, but does not start with, a trigger character', () => {
      const csv = toCsv([{ name: 'John=Doe' }], [{ key: 'name', header: 'Name' }])
      expect(csv.split('\r\n')[1]).toBe('John=Doe')
    })

    it('does not prefix ordinary values', () => {
      const csv = toCsv([{ name: 'Alice' }], [{ key: 'name', header: 'Name' }])
      expect(csv.split('\r\n')[1]).toBe('Alice')
    })
  })
})

describe('slugifyFileName', () => {
  it('slugifies a display name', () => {
    expect(slugifyFileName('  My Community! ')).toBe('my-community')
  })

  it('falls back to "export" when nothing slug-able remains', () => {
    expect(slugifyFileName('!!!')).toBe('export')
  })
})
