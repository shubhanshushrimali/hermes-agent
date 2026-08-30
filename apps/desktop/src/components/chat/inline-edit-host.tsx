/**
 * InlineEditHost — global listener for Cmd+K inline edit events.
 *
 * Listens to the `aizen-inline-edit` CustomEvent dispatched by the
 * Monaco editor's Cmd+K keybinding, and renders the InlineEditWidget
 * at the correct screen position.
 *
 * Mount this once in the app root (e.g., alongside App in main.tsx).
 *
 * Part of Phase 4: IDE-Grade Code Experience.
 */

import { useEffect, useState } from 'react'

import { InlineEditWidget } from '@/components/chat/inline-edit-widget'

interface InlineEditState {
  filePath: string
  selectedCode: string
  contextBefore: string
  contextAfter: string
  language: string
  position: { top: number; left: number }
  applyReplacement: (replacement: string) => void
}

export function InlineEditHost() {
  const [state, setState] = useState<InlineEditState | null>(null)

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as InlineEditState
      setState(detail)
    }

    window.addEventListener('aizen-inline-edit', handler)
    return () => window.removeEventListener('aizen-inline-edit', handler)
  }, [])

  if (!state) return null

  return (
    <InlineEditWidget
      filePath={state.filePath}
      selectedCode={state.selectedCode}
      language={state.language}
      contextBefore={state.contextBefore}
      contextAfter={state.contextAfter}
      position={state.position}
      onClose={() => setState(null)}
      onApply={(replacement) => {
        state.applyReplacement(replacement)
        setState(null)
      }}
    />
  )
}
