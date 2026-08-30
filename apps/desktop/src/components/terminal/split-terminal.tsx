/**
 * SplitTerminal — multi-tab, split-pane terminal panel.
 *
 * Orchestrates terminal sessions with a tab bar, split layout,
 * and keyboard shortcuts.
 *
 * Keyboard shortcuts:
 * - Ctrl+Shift+` — New terminal
 * - Ctrl+Shift+← / → — Switch tabs
 * - Ctrl+Shift+D — Split right
 * - Ctrl+Shift+E — Split down
 *
 * Part of Phase 4: IDE-Grade Code Experience.
 */

import { useCallback, useEffect, useSyncExternalStore } from 'react'

import { cn } from '@/lib/utils'
import {
  getTerminalManager,
  type SplitNode,
  type TerminalManagerState,
} from '@/lib/terminal-manager'
import { TerminalTabBar } from './terminal-tab-bar'
import { TerminalInstance } from './terminal-instance'

interface SplitTerminalProps {
  className?: string
  /** Initial working directory for new terminals. */
  cwd?: string
}

// ---------------------------------------------------------------------------
// Subscribe to the terminal manager singleton
// ---------------------------------------------------------------------------

function useTerminalManager(): TerminalManagerState {
  const manager = getTerminalManager()

  return useSyncExternalStore(
    (callback) => manager.subscribe(callback),
    () => manager.getState()
  )
}

// ---------------------------------------------------------------------------
// Layout renderer
// ---------------------------------------------------------------------------

function SplitLayout({
  node,
  activeSessionId,
}: {
  node: SplitNode
  activeSessionId: string | null
}) {
  if (node.type === 'terminal') {
    if (!node.sessionId) {
      return (
        <div
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: '#0B0D10',
            color: '#52525B',
            fontFamily: 'Inter, system-ui, sans-serif',
            fontSize: 13,
          }}
        >
          No terminal
        </div>
      )
    }

    return (
      <TerminalInstance
        sessionId={node.sessionId}
        active={node.sessionId === activeSessionId}
      />
    )
  }

  if (node.type === 'split' && node.children) {
    const isHorizontal = node.direction === 'horizontal'
    const ratio = node.ratio ?? 0.5

    return (
      <div
        style={{
          display: 'flex',
          flexDirection: isHorizontal ? 'row' : 'column',
          flex: 1,
          height: '100%',
          width: '100%',
        }}
      >
        <div style={{ flex: ratio, overflow: 'hidden' }}>
          <SplitLayout node={node.children[0]} activeSessionId={activeSessionId} />
        </div>
        {/* Divider */}
        <div
          style={{
            width: isHorizontal ? 2 : '100%',
            height: isHorizontal ? '100%' : 2,
            background: '#1E2128',
            flexShrink: 0,
          }}
        />
        <div style={{ flex: 1 - ratio, overflow: 'hidden' }}>
          <SplitLayout node={node.children[1]} activeSessionId={activeSessionId} />
        </div>
      </div>
    )
  }

  return null
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function SplitTerminal({ className, cwd }: SplitTerminalProps) {
  const manager = getTerminalManager()
  const state = useTerminalManager()

  // Auto-create a terminal if none exist.
  useEffect(() => {
    if (state.sessions.length === 0) {
      manager.createSession({ cwd })
    }
  }, [state.sessions.length, manager, cwd])

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ctrl+Shift+` — New terminal
      if (e.ctrlKey && e.shiftKey && e.key === '`') {
        e.preventDefault()
        manager.createSession({ cwd })
      }

      // Ctrl+Shift+Left — Previous tab
      if (e.ctrlKey && e.shiftKey && e.key === 'ArrowLeft') {
        e.preventDefault()
        manager.cycleSession('prev')
      }

      // Ctrl+Shift+Right — Next tab
      if (e.ctrlKey && e.shiftKey && e.key === 'ArrowRight') {
        e.preventDefault()
        manager.cycleSession('next')
      }

      // Ctrl+Shift+D — Split right
      if (e.ctrlKey && e.shiftKey && e.key === 'D') {
        e.preventDefault()
        if (state.activeSessionId) {
          manager.splitTerminal(state.activeSessionId, 'horizontal', { cwd })
        }
      }

      // Ctrl+Shift+E — Split down
      if (e.ctrlKey && e.shiftKey && e.key === 'E') {
        e.preventDefault()
        if (state.activeSessionId) {
          manager.splitTerminal(state.activeSessionId, 'vertical', { cwd })
        }
      }
    }

    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [manager, state.activeSessionId, cwd])

  const handleCreate = useCallback(() => {
    manager.createSession({ cwd })
  }, [manager, cwd])

  const handleSelect = useCallback(
    (sessionId: string) => manager.setActive(sessionId),
    [manager]
  )

  const handleClose = useCallback(
    (sessionId: string) => manager.closeSession(sessionId),
    [manager]
  )

  const handleRename = useCallback(
    (sessionId: string, name: string) => manager.renameSession(sessionId, name),
    [manager]
  )

  const handleSplitRight = useCallback(
    (sessionId: string) => manager.splitTerminal(sessionId, 'horizontal', { cwd }),
    [manager, cwd]
  )

  const handleSplitDown = useCallback(
    (sessionId: string) => manager.splitTerminal(sessionId, 'vertical', { cwd }),
    [manager, cwd]
  )

  return (
    <div
      className={cn('flex flex-col', className)}
      style={{
        background: '#090B0E',
        borderRadius: 8,
        overflow: 'hidden',
        border: '1px solid #1E2128',
      }}
    >
      {/* Tab bar */}
      <TerminalTabBar
        sessions={state.sessions}
        activeSessionId={state.activeSessionId}
        onSelect={handleSelect}
        onClose={handleClose}
        onRename={handleRename}
        onCreate={handleCreate}
        onSplitRight={handleSplitRight}
        onSplitDown={handleSplitDown}
      />

      {/* Terminal content area */}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <SplitLayout
          node={state.layout}
          activeSessionId={state.activeSessionId}
        />
      </div>
    </div>
  )
}
