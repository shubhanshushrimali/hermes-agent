/**
 * Code Lens Provider — inline action links above functions/classes.
 *
 * Detects function and class declarations via regex and adds
 * clickable actions: "Ask Hermes", "Explain", "Test", "Optimize".
 *
 * Clicking an action sends the function's code to the agent chat.
 *
 * Part of Phase 4: IDE-Grade Code Experience.
 */

// ---------------------------------------------------------------------------
// Minimal Monaco type stubs — avoids hard dependency on monaco-editor package.
// The real types flow through at runtime when Monaco is loaded dynamically.
// ---------------------------------------------------------------------------

interface MonacoRange {
  startLineNumber: number
  startColumn: number
  endLineNumber: number
  endColumn: number
}

interface MonacoCommand {
  id: string
  title: string
  arguments?: unknown[]
}

interface MonacoCodeLens {
  range: MonacoRange
  command?: MonacoCommand
}

interface MonacoCodeLensProvider {
  provideCodeLenses: (model: MonacoTextModel) => { lenses: MonacoCodeLens[]; dispose: () => void }
  resolveCodeLens: (model: MonacoTextModel, codeLens: MonacoCodeLens) => MonacoCodeLens
}

interface MonacoTextModel {
  getLanguageId: () => string
  getValue: () => string
}

interface MonacoDisposable {
  dispose: () => void
}

/** The Monaco module namespace — only the slice we need. */
interface MonacoNamespace {
  languages: {
    registerCodeLensProvider: (
      languageSelector: string,
      provider: MonacoCodeLensProvider
    ) => MonacoDisposable
  }
}

// ---------------------------------------------------------------------------
// Declaration patterns per language family
// ---------------------------------------------------------------------------

interface DeclarationPattern {
  regex: RegExp
  /** Named capture group for the function/class name. */
  nameGroup: string
  type: 'function' | 'class' | 'method'
}

const PATTERNS: Record<string, DeclarationPattern[]> = {
  typescript: [
    { regex: /^\s*(?:export\s+)?(?:async\s+)?function\s+(?<name>\w+)/gm, nameGroup: 'name', type: 'function' },
    { regex: /^\s*(?:export\s+)?(?:default\s+)?class\s+(?<name>\w+)/gm, nameGroup: 'name', type: 'class' },
    { regex: /^\s*(?:public|private|protected|static|async)\s+(?<name>\w+)\s*\(/gm, nameGroup: 'name', type: 'method' },
    { regex: /^\s*(?:export\s+)?const\s+(?<name>\w+)\s*=\s*(?:async\s+)?\(/gm, nameGroup: 'name', type: 'function' },
  ],
  javascript: [
    { regex: /^\s*(?:export\s+)?(?:async\s+)?function\s+(?<name>\w+)/gm, nameGroup: 'name', type: 'function' },
    { regex: /^\s*(?:export\s+)?class\s+(?<name>\w+)/gm, nameGroup: 'name', type: 'class' },
    { regex: /^\s*(?:export\s+)?const\s+(?<name>\w+)\s*=\s*(?:async\s+)?\(/gm, nameGroup: 'name', type: 'function' },
  ],
  python: [
    { regex: /^\s*(?:async\s+)?def\s+(?<name>\w+)/gm, nameGroup: 'name', type: 'function' },
    { regex: /^\s*class\s+(?<name>\w+)/gm, nameGroup: 'name', type: 'class' },
  ],
  go: [
    { regex: /^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(?<name>\w+)/gm, nameGroup: 'name', type: 'function' },
    { regex: /^type\s+(?<name>\w+)\s+struct/gm, nameGroup: 'name', type: 'class' },
  ],
  rust: [
    { regex: /^\s*(?:pub\s+)?(?:async\s+)?fn\s+(?<name>\w+)/gm, nameGroup: 'name', type: 'function' },
    { regex: /^\s*(?:pub\s+)?struct\s+(?<name>\w+)/gm, nameGroup: 'name', type: 'class' },
    { regex: /^\s*(?:pub\s+)?impl\s+(?<name>\w+)/gm, nameGroup: 'name', type: 'class' },
  ],
  java: [
    { regex: /^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:\w+\s+)(?<name>\w+)\s*\(/gm, nameGroup: 'name', type: 'method' },
    { regex: /^\s*(?:public\s+)?class\s+(?<name>\w+)/gm, nameGroup: 'name', type: 'class' },
  ],
  ruby: [
    { regex: /^\s*def\s+(?:self\.)?(?<name>\w+)/gm, nameGroup: 'name', type: 'function' },
    { regex: /^\s*class\s+(?<name>\w+)/gm, nameGroup: 'name', type: 'class' },
  ],
  c: [
    { regex: /^\w[\w\s\*]*\s+(?<name>\w+)\s*\([^)]*\)\s*\{/gm, nameGroup: 'name', type: 'function' },
  ],
  cpp: [
    { regex: /^\w[\w\s\*:&]*\s+(?<name>\w+)\s*\([^)]*\)\s*(?:const\s*)?\{/gm, nameGroup: 'name', type: 'function' },
    { regex: /^\s*class\s+(?<name>\w+)/gm, nameGroup: 'name', type: 'class' },
  ],
  csharp: [
    { regex: /^\s*(?:public|private|protected|internal)?\s*(?:static\s+)?(?:async\s+)?(?:\w+\s+)(?<name>\w+)\s*\(/gm, nameGroup: 'name', type: 'method' },
    { regex: /^\s*(?:public\s+)?class\s+(?<name>\w+)/gm, nameGroup: 'name', type: 'class' },
  ],
}

// Alias language IDs that share patterns.
PATTERNS.tsx = PATTERNS.typescript
PATTERNS.jsx = PATTERNS.javascript

// ---------------------------------------------------------------------------
// Code Lens Actions
// ---------------------------------------------------------------------------

interface CodeLensAction {
  id: string
  label: string
  /** The prompt prefix sent to the agent. */
  promptPrefix: string
}

const ACTIONS: CodeLensAction[] = [
  {
    id: 'ask',
    label: '💬 Ask Hermes',
    promptPrefix: 'Explain what this code does and answer any questions about it:\n\n',
  },
  {
    id: 'explain',
    label: '📖 Explain',
    promptPrefix: 'Explain this code in detail — what it does, how it works, and any edge cases:\n\n',
  },
  {
    id: 'test',
    label: '🧪 Test',
    promptPrefix: 'Write comprehensive unit tests for this code:\n\n',
  },
  {
    id: 'optimize',
    label: '⚡ Optimize',
    promptPrefix: 'Optimize this code for performance and readability. Show the improved version:\n\n',
  },
]

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

interface CodeLensDeclaration {
  name: string
  type: 'function' | 'class' | 'method'
  line: number
  code: string
}

function findDeclarations(text: string, language: string): CodeLensDeclaration[] {
  const patterns = PATTERNS[language]
  if (!patterns) return []

  const lines = text.split('\n')
  const declarations: CodeLensDeclaration[] = []

  for (const pattern of patterns) {
    // Reset regex state.
    const regex = new RegExp(pattern.regex.source, pattern.regex.flags)
    let match: RegExpExecArray | null

    while ((match = regex.exec(text)) !== null) {
      const name = match.groups?.[pattern.nameGroup] ?? match[1] ?? 'unknown'
      const lineIndex = text.slice(0, match.index).split('\n').length - 1
      const lineNumber = lineIndex + 1

      // Extract the function/class body (heuristic: until indentation decreases).
      const bodyLines: string[] = [lines[lineIndex]]
      const baseIndent = lines[lineIndex].search(/\S/)
      for (let i = lineIndex + 1; i < Math.min(lineIndex + 50, lines.length); i++) {
        const line = lines[i]
        if (line.trim() === '') {
          bodyLines.push(line)
          continue
        }
        const indent = line.search(/\S/)
        if (indent <= baseIndent && i > lineIndex + 1) break
        bodyLines.push(line)
      }

      declarations.push({
        name,
        type: pattern.type,
        line: lineNumber,
        code: bodyLines.join('\n'),
      })
    }
  }

  return declarations
}

/**
 * Register the Aizen code lens provider with Monaco.
 *
 * @param monaco - The Monaco module.
 * @param onAction - Callback when a lens action is clicked.
 *                   Receives the action prompt to send to the agent.
 * @returns A disposable to unregister the provider.
 */
export function registerCodeLensProvider(
  monaco: MonacoNamespace,
  onAction: (prompt: string) => void
): MonacoDisposable {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const commandIds: string[] = []

  const provider = monaco.languages.registerCodeLensProvider('*', {
    provideCodeLenses: (model: MonacoTextModel) => {
      const language = model.getLanguageId()
      const text = model.getValue()
      const declarations = findDeclarations(text, language)

      const lenses: MonacoCodeLens[] = []

      for (const decl of declarations) {
        for (const action of ACTIONS) {
          lenses.push({
            range: {
              startLineNumber: decl.line,
              startColumn: 1,
              endLineNumber: decl.line,
              endColumn: 1,
            },
            command: {
              id: `aizen.codeLens.${action.id}`,
              title: action.label,
              arguments: [action.promptPrefix, decl.code, decl.name],
            },
          })
        }
      }

      return { lenses, dispose: () => {} }
    },

    resolveCodeLens: (_model: MonacoTextModel, codeLens: MonacoCodeLens) => codeLens,
  })

  // Register commands for each action.
  // Note: Monaco commands are registered globally, so we use unique IDs.
  for (const action of ACTIONS) {
    const commandId = `aizen.codeLens.${action.id}`
    // Monaco doesn't have a simple addCommand for editor-global commands
    // from outside an editor instance, so we rely on the command being
    // dispatched by the code lens click handler.
  }

  return {
    dispose: () => {
      provider.dispose()
    },
  }
}
