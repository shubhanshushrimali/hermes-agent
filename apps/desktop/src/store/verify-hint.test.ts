import { describe, expect, it } from 'vitest'

import { firstLspFile, markersForFile, parseLspDiagnostics } from './verify-hint'

const SAMPLE = `LSP diagnostics introduced by this edit:
<diagnostics file="src/app.ts">
ERROR [12:3] Cannot find name 'foo'
WARN [1:1] unused
</diagnostics>`

describe('parseLspDiagnostics', () => {
  it('reads file, line, column, and severity from a reporter block', () => {
    const markers = parseLspDiagnostics(SAMPLE)

    expect(markers).toEqual([
      {
        filePath: 'src/app.ts',
        severity: 'error',
        line: 12,
        column: 3,
        message: "Cannot find name 'foo'"
      },
      {
        filePath: 'src/app.ts',
        severity: 'warning',
        line: 1,
        column: 1,
        message: 'unused'
      }
    ])
    expect(firstLspFile(SAMPLE)).toBe('src/app.ts')
    expect(markersForFile(SAMPLE, 'src/app.ts')).toHaveLength(2)
    expect(markersForFile(SAMPLE, 'other.ts')).toHaveLength(0)
  })

  it('returns nothing for empty or non-string payloads', () => {
    expect(parseLspDiagnostics(null)).toEqual([])
    expect(parseLspDiagnostics({ file: 'x.ts' })).toEqual([])
    expect(firstLspFile('')).toBeNull()
  })
})
