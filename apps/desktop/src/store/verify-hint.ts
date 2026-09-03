import { atom } from 'nanostores'

import { hermesApi } from '@/hermes'

export interface VerifyHint {
  commands: string[]
  hint: string
  lsp: unknown
}

export interface LspMarker {
  column: number
  filePath: string
  line: number
  message: string
  severity: 'error' | 'hint' | 'info' | 'warning'
}

export const $verifyHint = atom<VerifyHint>({ commands: [], hint: '', lsp: null })

const BLOCK_RE = /<diagnostics file="([^"]+)">([\s\S]*?)<\/diagnostics>/g
const LINE_RE = /^(ERROR|WARN|INFO|HINT) \[(\d+):(\d+)\] (.*)$/

function decodeXml(value: string): string {
  return value
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
}

function severityFromLabel(label: string): LspMarker['severity'] {
  switch (label) {
    case 'ERROR':
      return 'error'
    case 'WARN':
      return 'warning'
    case 'INFO':
      return 'info'
    case 'HINT':
      return 'hint'
    default:
      return 'error'
  }
}

export function parseLspDiagnostics(lsp: unknown): LspMarker[] {
  if (!lsp) {
    return []
  }

  if (typeof lsp !== 'string') {
    return []
  }

  const markers: LspMarker[] = []

  for (const match of lsp.matchAll(BLOCK_RE)) {
    const filePath = decodeXml(match[1] ?? '').trim()
    const body = match[2] ?? ''

    for (const raw of body.split('\n')) {
      const line = LINE_RE.exec(raw.trim())

      if (!line || !filePath) {
        continue
      }

      const label = line[1] as 'ERROR' | 'HINT' | 'INFO' | 'WARN'
      markers.push({
        filePath,
        severity: severityFromLabel(label),
        line: Number(line[2]),
        column: Number(line[3]),
        message: line[4] ?? ''
      })
    }
  }

  return markers
}

export function firstLspFile(lsp: unknown): string | null {
  return parseLspDiagnostics(lsp)[0]?.filePath ?? null
}

function pathsMatch(left: string, right: string): boolean {
  const a = left.replace(/\\/g, '/').toLowerCase()
  const b = right.replace(/\\/g, '/').toLowerCase()
  return a === b || a.endsWith(`/${b}`) || b.endsWith(`/${a}`)
}

export function markersForFile(lsp: unknown, filePath: string): LspMarker[] {
  const path = filePath.trim()

  if (!path) {
    return []
  }

  return parseLspDiagnostics(lsp).filter(marker => pathsMatch(marker.filePath, path))
}

export function recordVerifyFromToolResult(result: unknown): void {
  if (!result || typeof result !== 'object') {
    return
  }
  const verify = (result as { verify?: unknown }).verify
  if (!verify || typeof verify !== 'object') {
    return
  }
  const payload = verify as { commands?: unknown; hint?: unknown; lsp?: unknown }
  const commands = Array.isArray(payload.commands)
    ? payload.commands.filter((item): item is string => typeof item === 'string' && Boolean(item.trim()))
    : []
  $verifyHint.set({
    commands,
    hint: typeof payload.hint === 'string' ? payload.hint : '',
    lsp: payload.lsp ?? null
  })
}

export async function refreshVerifyHint(cwd: string): Promise<void> {
  const path = cwd.trim()
  if (!path) {
    $verifyHint.set({ commands: [], hint: '', lsp: null })
    return
  }
  if (typeof window === 'undefined' || !window.hermesDesktop?.api) {
    return
  }
  try {
    const data = await hermesApi<{ commands?: string[]; ok?: boolean }>({
      path: `/api/ide/verify-hint?cwd=${encodeURIComponent(path)}`,
      method: 'GET'
    })
    const commands = Array.isArray(data.commands) ? data.commands.filter(Boolean) : []
    $verifyHint.set({
      commands,
      hint: commands[0] ? `Run ${commands[0]} to verify` : '',
      lsp: $verifyHint.get().lsp
    })
  } catch {
    // Hint is optional — a missing endpoint must not break the rail.
  }
}
