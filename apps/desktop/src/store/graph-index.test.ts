import { describe, expect, it } from 'vitest'

import { applyGraphWorkspace, clearGraphIndex, graphIndexVisible, $graphIndex } from './graph-index'

describe('graph index chip', () => {
  it('hides when the index is healthy', () => {
    const next = applyGraphWorkspace({
      workspace: { indexed: true, backend: 'ast', nodes: 12, degraded: false, stale: false, warnings: [] }
    })
    expect(next.visible).toBe(false)
    expect(graphIndexVisible(next)).toBe(false)
    clearGraphIndex()
  })

  it('shows regex fallback, stale index, and Graphify warnings', () => {
    expect(
      applyGraphWorkspace({
        workspace: { indexed: true, backend: 'regex', degraded: true, stale: false, nodes: 3, warnings: [] }
      }).visible
    ).toBe(true)
    expect(
      applyGraphWorkspace({
        workspace: { indexed: true, backend: 'ast', degraded: false, stale: true, nodes: 3, warnings: [] }
      }).visible
    ).toBe(true)
    expect(
      applyGraphWorkspace({
        workspace: {
          indexed: true,
          backend: 'regex',
          degraded: true,
          stale: false,
          nodes: 1,
          warnings: ['Graphify not installed — using regex fallback']
        }
      }).warnings[0]
    ).toContain('Graphify')
    clearGraphIndex()
    expect($graphIndex.get().visible).toBe(false)
  })
})
