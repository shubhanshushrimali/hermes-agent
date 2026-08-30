/**
 * Monaco Editor — Aizen Theme Definition.
 *
 * Matches the desktop app's Aizen design tokens:
 * - Background: #0B0D10 (near-black)
 * - Foreground: #E4E4E7 (warm zinc)
 * - Accent: #6366F1 (indigo-500)
 * - Gold: #C9A84C (achievement/warning highlights)
 *
 * Registered as 'aizen-dark' in Monaco's theme registry.
 */

import type * as Monaco from 'monaco-editor'

export const AIZEN_THEME_NAME = 'aizen-dark'

export const aizenMonacoTheme: Monaco.editor.IStandaloneThemeData = {
  base: 'vs-dark',
  inherit: true,
  rules: [
    // -- Base tokens --
    { token: '', foreground: 'E4E4E7', background: '0B0D10' },
    { token: 'comment', foreground: '52525B', fontStyle: 'italic' },
    { token: 'keyword', foreground: '818CF8' },         // indigo-400
    { token: 'keyword.control', foreground: '818CF8' },
    { token: 'storage', foreground: '818CF8' },
    { token: 'storage.type', foreground: 'A78BFA' },    // violet-400

    // -- Strings & literals --
    { token: 'string', foreground: '22C55E' },          // green-500
    { token: 'string.escape', foreground: '4ADE80' },   // green-400
    { token: 'number', foreground: 'FACC15' },          // yellow-400
    { token: 'constant', foreground: 'FACC15' },
    { token: 'regexp', foreground: 'F97316' },          // orange-500

    // -- Types & classes --
    { token: 'type', foreground: '22D3EE' },            // cyan-400
    { token: 'type.identifier', foreground: '22D3EE' },
    { token: 'entity.name.type', foreground: '22D3EE' },
    { token: 'entity.name.class', foreground: '22D3EE' },

    // -- Functions --
    { token: 'entity.name.function', foreground: '6366F1' },  // indigo-500
    { token: 'support.function', foreground: '818CF8' },

    // -- Variables --
    { token: 'variable', foreground: 'E4E4E7' },
    { token: 'variable.parameter', foreground: 'C4B5FD' },    // violet-300
    { token: 'variable.other', foreground: 'A1A1AA' },

    // -- Operators & punctuation --
    { token: 'delimiter', foreground: 'A1A1AA' },
    { token: 'operator', foreground: 'C4C4CC' },

    // -- Tags (HTML/JSX) --
    { token: 'tag', foreground: 'EF4444' },             // red-500
    { token: 'attribute.name', foreground: 'C9A84C' },  // gold
    { token: 'attribute.value', foreground: '22C55E' },

    // -- Markdown --
    { token: 'markup.heading', foreground: '6366F1', fontStyle: 'bold' },
    { token: 'markup.bold', fontStyle: 'bold' },
    { token: 'markup.italic', fontStyle: 'italic' },
    { token: 'markup.inline.raw', foreground: '22C55E' },

    // -- JSON --
    { token: 'string.key.json', foreground: '818CF8' },
    { token: 'string.value.json', foreground: '22C55E' },

    // -- Invalid --
    { token: 'invalid', foreground: 'EF4444', fontStyle: 'underline' },
  ],
  colors: {
    // -- Editor chrome --
    'editor.background': '#0B0D10',
    'editor.foreground': '#E4E4E7',
    'editor.lineHighlightBackground': '#14171D',
    'editor.lineHighlightBorder': '#1A1D2400',

    // -- Selection --
    'editor.selectionBackground': '#6366F140',
    'editor.selectionHighlightBackground': '#6366F120',
    'editor.inactiveSelectionBackground': '#6366F120',

    // -- Find matches --
    'editor.findMatchBackground': '#C9A84C40',
    'editor.findMatchHighlightBackground': '#C9A84C20',

    // -- Cursor --
    'editorCursor.foreground': '#6366F1',
    'editorCursor.background': '#0B0D10',

    // -- Whitespace & indentation --
    'editorWhitespace.foreground': '#23262F',
    'editorIndentGuide.background': '#1A1D24',
    'editorIndentGuide.activeBackground': '#23262F',

    // -- Line numbers --
    'editorLineNumber.foreground': '#52525B',
    'editorLineNumber.activeForeground': '#A1A1AA',

    // -- Bracket matching --
    'editorBracketMatch.background': '#6366F130',
    'editorBracketMatch.border': '#6366F180',

    // -- Scrollbar --
    'scrollbarSlider.background': '#6366F120',
    'scrollbarSlider.hoverBackground': '#6366F140',
    'scrollbarSlider.activeBackground': '#6366F160',

    // -- Minimap --
    'minimap.background': '#090B0E',
    'minimap.selectionHighlight': '#6366F140',

    // -- Widget / suggest --
    'editorWidget.background': '#12151A',
    'editorWidget.border': '#23262F',
    'editorSuggestWidget.background': '#12151A',
    'editorSuggestWidget.border': '#23262F',
    'editorSuggestWidget.selectedBackground': '#1E2030',
    'editorSuggestWidget.highlightForeground': '#6366F1',

    // -- Hover --
    'editorHoverWidget.background': '#14171D',
    'editorHoverWidget.border': '#23262F',

    // -- Gutter (diff) --
    'editorGutter.addedBackground': '#22C55E40',
    'editorGutter.modifiedBackground': '#6366F140',
    'editorGutter.deletedBackground': '#EF444440',

    // -- Diff editor --
    'diffEditor.insertedTextBackground': '#22C55E15',
    'diffEditor.removedTextBackground': '#EF444415',

    // -- Overview ruler --
    'editorOverviewRuler.errorForeground': '#EF4444',
    'editorOverviewRuler.warningForeground': '#C9A84C',
    'editorOverviewRuler.infoForeground': '#6366F1',

    // -- Code lens --
    'editorCodeLens.foreground': '#52525B',

    // -- Ghost text --
    'editorGhostText.foreground': '#52525B80',
  },
}
