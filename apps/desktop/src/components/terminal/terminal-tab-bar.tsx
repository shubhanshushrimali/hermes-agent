/**
 * TerminalTabBar — tab strip for named terminal sessions.
 *
 * Features:
 * - Tab creation with "+" button
 * - Double-click to rename
 * - Right-click context menu (rename, split, close)
 * - Active tab indicator (Aizen indigo underline)
 * - Close button per tab
 * - Keyboard shortcuts
 *
 * Part of Phase 4: IDE-Grade Code Experience.
 */

import { useCallback, useRef, useState } from 'react'

import { cn } from '@/lib/utils'
import type { TerminalSession } from '@/lib/terminal-manager'

interface TerminalTabBarProps {
  sessions: TerminalSession[]
  activeSessionId: string | null
  onSelect: (sessionId: string) => void
  onClose: (sessionId: string) => void
  onRename: (sessionId: string, name: string) => void
  onCreate: () => void
  onSplitRight: (sessionId: string) => void
  onSplitDown: (sessionId: string) => void
}

export function TerminalTabBar({
  sessions,
  activeSessionId,
  onSelect,
  onClose,
  onRename,
  onCreate,
  onSplitRight,
  onSplitDown,
}: TerminalTabBarProps) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const [contextMenu, setContextMenu] = useState<{
    sessionId: string
    x: number
    y: number
  } | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleDoubleClick = useCallback(
    (sessionId: string, currentName: string) => {
      setEditingId(sessionId)
      setEditValue(currentName)
      // Focus the input after render.
      setTimeout(() => inputRef.current?.focus(), 0)
    },
    []
  )

  const handleRenameSubmit = useCallback(() => {
    if (editingId && editValue.trim()) {
      onRename(editingId, editValue.trim())
    }
    setEditingId(null)
  }, [editingId, editValue, onRename])

  const handleContextMenu = useCallback(
    (e: React.MouseEvent, sessionId: string) => {
      e.preventDefault()
      setContextMenu({ sessionId, x: e.clientX, y: e.clientY })
    },
    []
  )

  const closeContextMenu = useCallback(() => {
    setContextMenu(null)
  }, [])

  return (
    <>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          height: 34,
          background: '#090B0E',
          borderBottom: '1px solid #1E2128',
          overflow: 'hidden',
        }}
      >
        {/* Tab list */}
        <div
          style={{
            display: 'flex',
            flex: 1,
            overflow: 'auto',
            gap: 0,
          }}
        >
          {sessions.map((session) => {
            const isActive = session.id === activeSessionId
            const isEditing = session.id === editingId

            return (
              <div
                key={session.id}
                className={cn('aizen-sidebar-item', isActive && 'aizen-btn-press')}
                onClick={() => onSelect(session.id)}
                onDoubleClick={() => handleDoubleClick(session.id, session.name)}
                onContextMenu={(e) => handleContextMenu(e, session.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '0 12px',
                  height: 34,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                  borderBottom: isActive
                    ? '2px solid #6366F1'
                    : '2px solid transparent',
                  background: isActive
                    ? 'rgba(99, 102, 241, 0.06)'
                    : 'transparent',
                  transition: 'background 150ms ease, border-color 150ms ease',
                }}
              >
                {/* Terminal icon */}
                <span style={{ fontSize: 12, opacity: 0.5 }}>⬛</span>

                {/* Name or edit input */}
                {isEditing ? (
                  <input
                    ref={inputRef}
                    type="text"
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    onBlur={handleRenameSubmit}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleRenameSubmit()
                      if (e.key === 'Escape') setEditingId(null)
                    }}
                    style={{
                      width: 100,
                      background: 'transparent',
                      border: '1px solid #6366F1',
                      borderRadius: 2,
                      padding: '1px 4px',
                      fontFamily: 'Inter, system-ui, sans-serif',
                      fontSize: 12,
                      color: '#E4E4E7',
                      outline: 'none',
                    }}
                  />
                ) : (
                  <span
                    style={{
                      fontFamily: 'Inter, system-ui, sans-serif',
                      fontSize: 12,
                      color: isActive ? '#E4E4E7' : '#A1A1AA',
                      fontWeight: isActive ? 500 : 400,
                    }}
                  >
                    {session.name}
                  </span>
                )}

                {/* Close button */}
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    onClose(session.id)
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 16,
                    height: 16,
                    borderRadius: 2,
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    fontSize: 10,
                    color: '#52525B',
                    opacity: isActive ? 1 : 0,
                    transition: 'opacity 150ms ease',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = 'rgba(239, 68, 68, 0.2)'
                    e.currentTarget.style.color = '#EF4444'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'transparent'
                    e.currentTarget.style.color = '#52525B'
                  }}
                >
                  ✕
                </button>
              </div>
            )
          })}
        </div>

        {/* New terminal button */}
        <button
          onClick={onCreate}
          className="aizen-btn-press"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 28,
            height: 28,
            margin: '0 4px',
            borderRadius: 4,
            background: 'transparent',
            border: '1px solid #23262F',
            cursor: 'pointer',
            fontSize: 14,
            color: '#A1A1AA',
          }}
          title="New Terminal (Ctrl+Shift+`)"
        >
          +
        </button>
      </div>

      {/* Context menu */}
      {contextMenu && (
        <>
          {/* Backdrop to close */}
          <div
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: 9998,
            }}
            onClick={closeContextMenu}
          />
          <div
            className="aizen-glass"
            style={{
              position: 'fixed',
              top: contextMenu.y,
              left: contextMenu.x,
              zIndex: 9999,
              minWidth: 160,
              borderRadius: 6,
              padding: '4px 0',
              boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
            }}
          >
            {[
              {
                label: '✏️ Rename',
                action: () => {
                  const session = sessions.find((s) => s.id === contextMenu.sessionId)
                  if (session) handleDoubleClick(session.id, session.name)
                  closeContextMenu()
                },
              },
              {
                label: '↔ Split Right',
                action: () => {
                  onSplitRight(contextMenu.sessionId)
                  closeContextMenu()
                },
              },
              {
                label: '↕ Split Down',
                action: () => {
                  onSplitDown(contextMenu.sessionId)
                  closeContextMenu()
                },
              },
              { label: '---', action: () => {} },
              {
                label: '🗑️ Close',
                action: () => {
                  onClose(contextMenu.sessionId)
                  closeContextMenu()
                },
              },
            ].map((item, i) =>
              item.label === '---' ? (
                <div
                  key={i}
                  style={{
                    height: 1,
                    background: '#23262F',
                    margin: '4px 8px',
                  }}
                />
              ) : (
                <button
                  key={i}
                  onClick={item.action}
                  className="aizen-sidebar-item"
                  style={{
                    display: 'block',
                    width: '100%',
                    textAlign: 'left',
                    padding: '6px 12px',
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    fontFamily: 'Inter, system-ui, sans-serif',
                    fontSize: 12,
                    color: '#E4E4E7',
                  }}
                >
                  {item.label}
                </button>
              )
            )}
          </div>
        </>
      )}
    </>
  )
}
