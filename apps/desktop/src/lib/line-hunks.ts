export type LineHunkKind = 'equal' | 'del' | 'add'

export interface LineHunk {
  kind: LineHunkKind
  lines: string[]
}

function splitLines(text: string): string[] {
  if (text === '') {
    return []
  }
  return text.split('\n')
}

function lcsTable(a: string[], b: string[]): number[][] {
  const rows = a.length
  const cols = b.length
  const table: number[][] = Array.from({ length: rows + 1 }, () => Array(cols + 1).fill(0))
  for (let i = 1; i <= rows; i++) {
    for (let j = 1; j <= cols; j++) {
      table[i][j] = a[i - 1] === b[j - 1] ? table[i - 1][j - 1] + 1 : Math.max(table[i - 1][j], table[i][j - 1])
    }
  }
  return table
}

function pushHunk(hunks: LineHunk[], kind: LineHunkKind, line: string): void {
  const last = hunks[hunks.length - 1]
  if (last && last.kind === kind) {
    last.lines.push(line)
    return
  }
  hunks.push({ kind, lines: [line] })
}

/** Line-level diff so Cmd+K can accept or skip hunks instead of the whole file. */
export function lineHunks(oldText: string, newText: string): LineHunk[] {
  const a = splitLines(oldText)
  const b = splitLines(newText)
  const table = lcsTable(a, b)
  const hunks: LineHunk[] = []
  let i = a.length
  let j = b.length
  const reverse: LineHunk[] = []
  while (i > 0 && j > 0) {
    if (a[i - 1] === b[j - 1]) {
      pushHunk(reverse, 'equal', a[i - 1])
      i -= 1
      j -= 1
    } else if (table[i - 1][j] >= table[i][j - 1]) {
      pushHunk(reverse, 'del', a[i - 1])
      i -= 1
    } else {
      pushHunk(reverse, 'add', b[j - 1])
      j -= 1
    }
  }
  while (i > 0) {
    pushHunk(reverse, 'del', a[i - 1])
    i -= 1
  }
  while (j > 0) {
    pushHunk(reverse, 'add', b[j - 1])
    j -= 1
  }
  for (let index = reverse.length - 1; index >= 0; index--) {
    const hunk = reverse[index]
    hunks.push({ kind: hunk.kind, lines: hunk.lines.slice().reverse() })
  }
  return hunks
}

export function applyHunks(hunks: LineHunk[], skipped: ReadonlySet<number>): string {
  const out: string[] = []
  hunks.forEach((hunk, index) => {
    switch (hunk.kind) {
      case 'equal':
        out.push(...hunk.lines)
        break
      case 'del':
        if (skipped.has(index)) {
          out.push(...hunk.lines)
        }
        break
      case 'add':
        if (!skipped.has(index)) {
          out.push(...hunk.lines)
        }
        break
      default: {
        const _never: never = hunk.kind
        throw new Error(`unhandled hunk kind: ${_never}`)
      }
    }
  })
  return out.join('\n')
}
