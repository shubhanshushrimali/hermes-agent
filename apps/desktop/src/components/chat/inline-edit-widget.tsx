/**
 * InlineEditWidget — Cmd+K inline code edit overlay for Monaco.
 *
 * Appears as a floating input at the cursor/selection position.
 * User types a natural language instruction, the agent returns
 * a code replacement shown as line-level hunks (Keep / skip per hunk).
 *
 * Part of Phase 4: IDE-Grade Code Experience.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { requestInlineEdit } from '@/lib/inline-edit'
import { applyHunks, lineHunks, type LineHunk } from '@/lib/line-hunks'
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

function hunkLabel(kind: LineHunk['kind']): string {
  switch (kind) {
    case 'equal':
      return ' '
    case 'del':
      return '-'
    case 'add':
      return '+'
    default: {
      const _never: never = kind
      return _never
    }
  }
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
  const [skipped, setSkipped] = useState<Set<number>>(() => new Set())
  const inputRef = useRef<HTMLInputElement>(null)

  const hunks = useMemo(
    () => (result === null ? [] : lineHunks(selectedCode, result)),
    [result, selectedCode]
  )

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onClose()
        return
      }
      if (e.key === 'Tab' && result !== null && !loading) {
        e.preventDefault()
        e.stopPropagation()
        onApply(applyHunks(hunks, skipped))
      }
    }
    document.addEventListener('keydown', handler, true)
    return () => document.removeEventListener('keydown', handler, true)
  }, [onClose, onApply, result, loading, hunks, skipped])

  const handleSubmit = useCallback(async () => {
    if (!instruction.trim() || loading) return
    setLoading(true)
    setError(null)
    setSkipped(new Set())

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
      onApply(applyHunks(hunks, skipped))
    }
  }, [result, onApply, hunks, skipped])

  const toggleHunk = (index: number, kind: LineHunk['kind']) => {
    if (kind === 'equal') {
      return
    }
    setSkipped(prev => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  return (
    <div
      className="overflow-hidden rounded-lg border border-border bg-background shadow-md"
      onClick={e => e.stopPropagation()}
      style={{
        left: position.left,
        position: 'absolute',
        top: position.top,
        width: 420,
        zIndex: 100
      }}
    >
      <div className="flex items-center gap-2 px-3 py-2">
        <span className="shrink-0 font-mono text-[0.6875rem] font-semibold text-(--ui-text-tertiary)">⌘K</span>
        <Input
          disabled={loading}
          onChange={e => setInstruction(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              void handleSubmit()
            }
          }}
          placeholder="Describe the change..."
          ref={inputRef}
          size="sm"
          type="text"
          value={instruction}
        />
      </div>

      {loading && (
        <div className="flex items-center gap-2 border-t border-border px-3 py-2">
          <span className="size-1.5 rounded-full bg-primary" />
          <span className="text-xs text-muted-foreground">Generating edit…</span>
        </div>
      )}

      {error && (
        <div className="border-t border-border px-3 py-2 text-xs text-destructive">{error}</div>
      )}

      {result !== null && (
        <div className="border-t border-border">
          <div className="max-h-60 overflow-auto px-3 py-2 font-mono text-xs leading-5">
            {hunks.map((hunk, index) => {
              const skippedHunk = skipped.has(index)
              const interactive = hunk.kind !== 'equal'
              return (
                <div className="mb-1" key={`${hunk.kind}-${index}`}>
                  {interactive && (
                    <Button
                      className="mb-0.5 h-auto px-0 text-[0.625rem]"
                      onClick={() => toggleHunk(index, hunk.kind)}
                      size="inline"
                      type="button"
                      variant="text"
                    >
                      {skippedHunk ? 'Skipped' : 'Keep'} {hunk.kind === 'add' ? 'additions' : 'deletions'}
                    </Button>
                  )}
                  {hunk.lines.map((line, lineIndex) => (
                    <div
                      className={cn(
                        'px-1',
                        hunk.kind === 'del' && !skippedHunk && 'bg-destructive/15 text-destructive',
                        hunk.kind === 'add' && !skippedHunk && 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
                      )}
                      key={`${index}-${lineIndex}`}
                      style={{ opacity: skippedHunk ? 0.4 : 1 }}
                    >
                      {hunkLabel(hunk.kind)} {line}
                    </div>
                  ))}
                </div>
              )
            })}
          </div>

          <div className="flex items-center justify-between gap-2 border-t border-border px-3 py-2">
            <span className="text-[0.625rem] text-muted-foreground">Tab accept · Esc reject</span>
            <div className="flex gap-2">
              <Button onClick={onClose} size="sm" type="button" variant="outline">
                Reject
              </Button>
              <Button onClick={handleAccept} size="sm" type="button">
                Accept
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
