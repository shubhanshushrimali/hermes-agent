/**
 * GhostTextProvider — integrates ghost text suggestions with Monaco.
 *
 * Registers as a Monaco InlineCompletionProvider that shows faded
 * text ahead of the cursor. User presses Tab to accept.
 *
 * Part of Phase 4: IDE-Grade Code Experience.
 */

import { useEffect, useRef } from 'react'
import { createDebouncedGhostRequester } from '@/lib/ghost-text'

type Monaco = typeof import('monaco-editor')
type IStandaloneCodeEditor = import('monaco-editor').editor.IStandaloneCodeEditor

/**
 * Hook that registers a ghost text InlineCompletionProvider on a Monaco editor.
 *
 * Usage:
 *   useGhostText(editorRef.current, monacoRef.current, filePath)
 */
export function useGhostText(
  editor: IStandaloneCodeEditor | null,
  monaco: Monaco | null,
  filePath: string,
  options: {
    enabled?: boolean
    debounceMs?: number
  } = {}
): void {
  const { enabled = true, debounceMs = 300 } = options
  const disposableRef = useRef<import('monaco-editor').IDisposable | null>(null)

  useEffect(() => {
    if (!editor || !monaco || !enabled) return

    const requester = createDebouncedGhostRequester(debounceMs)

    // Register an inline completion provider.
    const provider = monaco.languages.registerInlineCompletionsProvider('*', {
      provideInlineCompletions: async (model, position, _context, token) => {
        // Build prefix/suffix from cursor position.
        const textBeforeCursor = model.getValueInRange({
          startLineNumber: 1,
          startColumn: 1,
          endLineNumber: position.lineNumber,
          endColumn: position.column,
        })

        const totalLines = model.getLineCount()
        const lastLineLength = model.getLineLength(totalLines)
        const textAfterCursor = model.getValueInRange({
          startLineNumber: position.lineNumber,
          startColumn: position.column,
          endLineNumber: totalLines,
          endColumn: lastLineLength + 1,
        })

        // Get the language of the model.
        const language = model.getLanguageId()

        return new Promise((resolve) => {
          if (token.isCancellationRequested) {
            resolve({ items: [] })
            return
          }

          requester(
            {
              prefix: textBeforeCursor,
              suffix: textAfterCursor,
              filePath,
              language,
            },
            (result) => {
              if (token.isCancellationRequested || !result.ok || !result.completion) {
                resolve({ items: [] })
                return
              }

              resolve({
                items: [
                  {
                    insertText: result.completion,
                    range: {
                      startLineNumber: position.lineNumber,
                      startColumn: position.column,
                      endLineNumber: position.lineNumber,
                      endColumn: position.column,
                    },
                  },
                ],
              })
            }
          )
        })
      },

      freeInlineCompletions: () => {
        // Nothing to clean up.
      },
    })

    disposableRef.current = provider

    return () => {
      provider.dispose()
      disposableRef.current = null
    }
  }, [editor, monaco, filePath, enabled, debounceMs])
}
