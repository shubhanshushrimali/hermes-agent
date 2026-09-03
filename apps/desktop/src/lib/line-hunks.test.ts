import { describe, expect, it } from 'vitest'

import { applyHunks, lineHunks } from './line-hunks'

describe('lineHunks', () => {
  it('keeps unchanged lines and isolates a replacement', () => {
    const hunks = lineHunks('a\nb\nc', 'a\nB\nc')
    expect(hunks).toEqual([
      { kind: 'equal', lines: ['a'] },
      { kind: 'del', lines: ['b'] },
      { kind: 'add', lines: ['B'] },
      { kind: 'equal', lines: ['c'] }
    ])
  })

  it('applies only accepted hunks', () => {
    const hunks = lineHunks('a\nb\nc', 'a\nB\nc')
    expect(applyHunks(hunks, new Set())).toBe('a\nB\nc')
    expect(applyHunks(hunks, new Set([1, 2]))).toBe('a\nb\nc')
  })
})
