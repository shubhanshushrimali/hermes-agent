import { atom } from 'nanostores'

import { $repoStatus } from '@/store/coding-status'
import { $previewTabs } from '@/store/preview'
import { $dirtyPreviewUrls } from '@/store/preview-edit'

export interface EditorSelectionSnapshot {
  startLine: number
  endLine: number
  textPreview: string
}

export interface EditorSnapshot {
  activeFile: string | null
  language: string | null
  selection: EditorSelectionSnapshot | null
  cursorLine: number | null
  unsaved: boolean
}

const emptySnapshot = (): EditorSnapshot => ({
  activeFile: null,
  language: null,
  selection: null,
  cursorLine: null,
  unsaved: false
})

export const $editorSnapshot = atom<EditorSnapshot>(emptySnapshot())
export const $lastTerminalLine = atom<string | null>(null)

export function publishEditorSnapshot(partial: Partial<EditorSnapshot>): void {
  $editorSnapshot.set({ ...$editorSnapshot.get(), ...partial })
}

export function publishLastTerminalLine(line: string): void {
  const trimmed = line.trim()
  if (!trimmed) {
    return
  }
  $lastTerminalLine.set(trimmed.slice(-500))
}

/** Compact sidecar for the current user message — never the system prompt. */
export function formatEditorSnapshotSidecar(): string {
  const snap = $editorSnapshot.get()
  const tabs = $previewTabs.get()
  const dirty = $dirtyPreviewUrls.get()
  const git = $repoStatus.get()
  const terminal = $lastTerminalLine.get()
  const lines: string[] = []

  if (snap.activeFile) {
    lines.push(`Active file: ${snap.activeFile}`)
  }
  if (snap.language) {
    lines.push(`Language: ${snap.language}`)
  }
  if (snap.cursorLine != null) {
    lines.push(`Cursor: line ${snap.cursorLine}`)
  }
  if (snap.selection) {
    lines.push(`Selection: L${snap.selection.startLine}–L${snap.selection.endLine}`)
    if (snap.selection.textPreview) {
      lines.push(`Selected:\n${snap.selection.textPreview}`)
    }
  }
  const openFiles = tabs
    .map(tab => tab.target.path || tab.target.label)
    .filter((value): value is string => Boolean(value))
  if (openFiles.length) {
    lines.push(`Open tabs: ${openFiles.slice(0, 12).join(', ')}`)
  }
  const unsaved = Object.keys(dirty)
  if (unsaved.length || snap.unsaved) {
    lines.push(`Unsaved: ${unsaved.length ? unsaved.slice(0, 8).join(', ') : snap.activeFile || 'active file'}`)
  }
  if (git) {
    const bits = [
      git.branch ? `branch ${git.branch}` : git.detached ? 'detached' : null,
      git.changed ? `${git.changed} changed` : 'clean',
      git.ahead ? `${git.ahead} ahead` : null,
      git.behind ? `${git.behind} behind` : null
    ].filter(Boolean)
    lines.push(`Git: ${bits.join(', ')}`)
  }
  if (terminal) {
    lines.push(`Last terminal: ${terminal}`)
  }

  if (!lines.length) {
    return ''
  }
  return `[Editor]\n${lines.join('\n')}`.slice(0, 2000)
}

export function hasEditorContext(): boolean {
  return formatEditorSnapshotSidecar().length > 0
}

export function editorContextLabel(): string | null {
  const snap = $editorSnapshot.get()
  if (!snap.activeFile) {
    return hasEditorContext() ? 'editor' : null
  }
  return snap.activeFile.split(/[/\\]/).pop() || snap.activeFile
}
