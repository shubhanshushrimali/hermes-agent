/**
 * InlineEditWidget — Cmd+K inline code edit overlay for Monaco.
 *
 * Appears as a floating input at the cursor/selection position.
 * User types a natural language instruction, the agent returns
 * a code replacement shown as an inline diff.
 *
 * Part of Phase 4: IDE-Grade Code Experience.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { requestInlineEdit, applyInlineEdit } from '@/lib/inline-edit'
import { cn } from '@/lib/utils'

interface InlineEditWidgetProps {
  /** The selected code to edit. */
  selectedCode: string
  /** File being edited. */
  filePath: string
  /** Detected language. */
  language?: string
  /** Lines before selection for context. */
  contextBefore?: string
  /** Lines after selection for context. */
  contextAfter?: string
  /** Position on screen (top, left from editor container). */
  position: { top: number; left: number }
  /** Called when the widget should close. */
  onClose: () => void
  /** Called when an edit is accepted and applied. */
  onApply: (replacement: string) => void
}

export function InlineEditWidget({
  selectedCode,
  filePath,
  language,
  contextBefore,
  contextAfter,
  position,
  onClose,
  onApply,
}: InlineEditWidgetProps) {
  const [instruction, setInstruction] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Auto-focus the input
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // Escape to close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
      }
    }
    document.addEventListener('keydown', handler, true)
    return () => document.removeEventListener('keydown', handler, true)
  }, [onClose])

  const handleSubmit = useCallback(async () => {
    if (!instruction.trim() || loading) return
    setLoading(true)
    setError(null)

    const res = await requestInlineEdit({
      filePath,
      selectedCode,
      instruction: instruction.trim(),
      language,
      contextBefore,
      contextAfter,
    })

    setLoading(false)
    if (res.ok && res.replacement !== undefined) {
      setResult(res.replacement)
    } else {
      setError(res.error ?? 'Failed to generate edit')
    }
  }, [instruction, loading, filePath, selectedCode, language, contextBefore, contextAfter])

  const handleAccept = useCallback(() => {
    if (result !== null) {
      onApply(result)
    }
  }, [result, onApply])

  return (
    <div
      className="aizen-glass aizen-toast"
      style={{
        position: 'absolute',
        top: position.top,
        left: position.left,
        zIndex: 100,
        width: 400,
        borderRadius: 8,
        padding: 0,
        overflow: 'hidden',
      }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Input area */}
      <div style={{ padding: '10px 12px', display: 'flex', gap: 8, alignItems: 'center' }}>
        <span
          style={{
            fontFamily: '"JetBrains Mono", monospace',
            fontSize: 11,
            color: '#6366F1',
            fontWeight: 600,
            whiteSpace: 'nowrap',
          }}
        >
          ⌘K
        </span>
        <input
          ref={inputRef}
          type="text"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSubmit()
            }
          }}
          placeholder="Describe the change..."
          disabled={loading}
          className="aizen-input-glow"
          style={{
            flex: 1,
            background: 'transparent',
            border: '1px solid #23262F',
            borderRadius: 4,
            padding: '6px 8px',
            fontFamily: 'Inter, system-ui, sans-serif',
            fontSize: 13,
            color: '#E4E4E7',
            outline: 'none',
          }}
        />
      </div>

      {/* Loading state */}
      {loading && (
        <div
          style={{
            padding: '8px 12px',
            borderTop: '1px solid #23262F',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <div className="aizen-status-active" style={{ width: 6, height: 6, borderRadius: '50%', background: '#6366F1' }} />
          <span style={{ fontFamily: 'Inter, system-ui, sans-serif', fontSize: 12, color: '#A1A1AA' }}>
            Generating edit…
          </span>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div
          style={{
            padding: '8px 12px',
            borderTop: '1px solid #23262F',
            fontFamily: 'Inter, system-ui, sans-serif',
            fontSize: 12,
            color: '#EF4444',
          }}
        >
          {error}
        </div>
      )}

      {/* Result diff preview */}
      {result !== null && (
        <div style={{ borderTop: '1px solid #23262F' }}>
          {/* Diff view */}
          <div
            style={{
              padding: '8px 12px',
              maxHeight: 200,
              overflow: 'auto',
              fontFamily: '"JetBrains Mono", monospace',
              fontSize: 12,
              lineHeight: 1.6,
            }}
          >
            {/* Removed lines */}
            {selectedCode.split('\n').map((line, i) => (
              <div key={`r-${i}`} className="aizen-diff-remove" style={{ padding: '0 4px' }}>
                - {line}
              </div>
            ))}
            {/* Added lines */}
            {result.split('\n').map((line, i) => (
              <div key={`a-${i}`} className="aizen-diff-add" style={{ padding: '0 4px' }}>
                + {line}
              </div>
            ))}
          </div>

          {/* Action buttons */}
          <div
            style={{
              padding: '8px 12px',
              borderTop: '1px solid #23262F',
              display: 'flex',
              justifyContent: 'flex-end',
              gap: 8,
            }}
          >
            <button
              onClick={onClose}
              className="aizen-btn-press"
              style={{
                background: 'transparent',
                border: '1px solid #23262F',
                borderRadius: 4,
                padding: '4px 12px',
                fontFamily: 'Inter, system-ui, sans-serif',
                fontSize: 12,
                color: '#A1A1AA',
                cursor: 'pointer',
              }}
            >
              Reject
            </button>
            <button
              onClick={handleAccept}
              className="aizen-btn-press"
              style={{
                background: '#6366F1',
                border: 'none',
                borderRadius: 4,
                padding: '4px 12px',
                fontFamily: 'Inter, system-ui, sans-serif',
                fontSize: 12,
                fontWeight: 500,
                color: '#ffffff',
                cursor: 'pointer',
              }}
            >
              Accept
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
