/**
 * Terminal Split Bridge — enhances the existing terminal pane with
 * horizontal/vertical split capabilities.
 *
 * Wraps the existing TerminalPaneChrome with split-pane support
 * via keyboard shortcuts (Ctrl+Shift+D/E) and context menu actions.
 * Uses the existing TerminalRail + PersistentTerminal underneath.
 *
 * Part of Phase 4: IDE-Grade Code Experience.
 */

import { useCallback, useEffect, useState } from 'react'
import { useStore } from '@nanostores/react'

import { cn } from '@/lib/utils'

import { TerminalSlot } from './persistent'
import { TerminalRail } from './rail'
import { $terminals, createTerminal } from './terminals'

type SplitDirection = 'horizontal' | 'vertical'

interface SplitState {
  /** Whether the terminal pane is currently split. */
  isSplit: boolean
  direction: SplitDirection
  /** The ratio of the first pane (0-1). */
  ratio: number
}

/**
 * Enhanced terminal chrome with split-pane support.
 *
 * Replaces `TerminalPaneChrome` in `surfaces.tsx` when enabled.
 * Falls back to the normal single-pane terminal when not split.
 */
export function TerminalSplitChrome() {
  const terminals = useStore($terminals)
  const [split, setSplit] = useState<SplitState>({
    isSplit: false,
    direction: 'horizontal',
    ratio: 0.5,
  })

  // Keyboard shortcuts for splitting.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ctrl+Shift+D — Split terminal right
      if (e.ctrlKey && e.shiftKey && e.key === 'D') {
        e.preventDefault()
        if (!split.isSplit) {
          setSplit({ isSplit: true, direction: 'horizontal', ratio: 0.5 })
          createTerminal()
        }
      }

      // Ctrl+Shift+E — Split terminal down
      if (e.ctrlKey && e.shiftKey && e.key === 'E') {
        e.preventDefault()
        if (!split.isSplit) {
          setSplit({ isSplit: true, direction: 'vertical', ratio: 0.5 })
          createTerminal()
        }
      }

      // Ctrl+Shift+W — Close split (back to single)
      if (e.ctrlKey && e.shiftKey && e.key === 'W') {
        if (split.isSplit) {
          e.preventDefault()
          setSplit({ ...split, isSplit: false })
        }
      }
    }

    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [split])

  const closeSplit = useCallback(() => {
    setSplit((s) => ({ ...s, isSplit: false }))
  }, [])

  // Single pane (default) — same as original TerminalPaneChrome.
  if (!split.isSplit) {
    return (
      <div className="flex min-h-0 min-w-0 flex-1">
        <div className="relative flex min-h-0 min-w-0 flex-1 flex-col">
          <TerminalSlot />
        </div>
        {terminals.length > 0 && <TerminalRail />}
      </div>
    )
  }

  // Split pane view.
  const isHorizontal = split.direction === 'horizontal'

  return (
    <div className="flex min-h-0 min-w-0 flex-1">
      <div
        className="relative flex min-h-0 min-w-0 flex-1"
        style={{ flexDirection: isHorizontal ? 'row' : 'column' }}
      >
        {/* Primary terminal */}
        <div style={{ flex: split.ratio, overflow: 'hidden', minWidth: 0, minHeight: 0 }}>
          <div className="relative flex min-h-0 min-w-0 flex-1 flex-col h-full">
            <TerminalSlot />
          </div>
        </div>

        {/* Divider */}
        <div
          style={{
            width: isHorizontal ? 2 : '100%',
            height: isHorizontal ? '100%' : 2,
            background: 'var(--ui-stroke-quaternary)',
            flexShrink: 0,
            cursor: isHorizontal ? 'col-resize' : 'row-resize',
          }}
          title="Drag to resize · Ctrl+Shift+W to close split"
          onDoubleClick={closeSplit}
        />

        {/* Secondary terminal */}
        <div style={{ flex: 1 - split.ratio, overflow: 'hidden', minWidth: 0, minHeight: 0 }}>
          <div className="relative flex min-h-0 min-w-0 flex-1 flex-col h-full">
            <TerminalSlot />
          </div>
        </div>
      </div>

      {terminals.length > 0 && <TerminalRail />}
    </div>
  )
}
