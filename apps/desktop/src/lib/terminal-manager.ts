/**
 * Terminal Manager — manages terminal sessions and split layout.
 *
 * Provides CRUD operations for terminal tabs, split management,
 * and persistence of tab names and layout in localStorage.
 *
 * Part of Phase 4: IDE-Grade Code Experience.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TerminalSession {
  id: string
  name: string
  cwd: string
  /** Whether this terminal is currently active (visible). */
  active: boolean
  /** ISO timestamp of creation. */
  createdAt: string
}

export type SplitDirection = 'horizontal' | 'vertical'

export interface SplitNode {
  type: 'terminal' | 'split'
  /** Only for type === 'terminal'. */
  sessionId?: string
  /** Only for type === 'split'. */
  direction?: SplitDirection
  /** Only for type === 'split'. Two children. */
  children?: [SplitNode, SplitNode]
  /** Size ratio (0-1) for split children. */
  ratio?: number
}

// ---------------------------------------------------------------------------
// Storage
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'hermes-aizen-terminals'

interface PersistedState {
  sessions: TerminalSession[]
  layout: SplitNode
  activeSessionId: string | null
}

function loadState(): PersistedState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    return JSON.parse(raw) as PersistedState
  } catch {
    return null
  }
}

function saveState(state: PersistedState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Storage full or unavailable — best effort.
  }
}

// ---------------------------------------------------------------------------
// ID generation
// ---------------------------------------------------------------------------

let nextId = 1

function generateId(): string {
  return `term-${Date.now()}-${nextId++}`
}

// ---------------------------------------------------------------------------
// Terminal Manager
// ---------------------------------------------------------------------------

export type TerminalManagerListener = (state: TerminalManagerState) => void

export interface TerminalManagerState {
  sessions: TerminalSession[]
  layout: SplitNode
  activeSessionId: string | null
}

export class TerminalManager {
  private sessions: Map<string, TerminalSession> = new Map()
  private layout: SplitNode = { type: 'terminal', sessionId: undefined }
  private activeSessionId: string | null = null
  private listeners: Set<TerminalManagerListener> = new Set()

  constructor() {
    // Restore persisted state.
    const saved = loadState()
    if (saved) {
      for (const session of saved.sessions) {
        this.sessions.set(session.id, session)
      }
      this.layout = saved.layout
      this.activeSessionId = saved.activeSessionId
    }
  }

  // ---- Public API ----

  getState(): TerminalManagerState {
    return {
      sessions: Array.from(this.sessions.values()),
      layout: this.layout,
      activeSessionId: this.activeSessionId,
    }
  }

  subscribe(listener: TerminalManagerListener): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  /**
   * Create a new terminal session.
   */
  createSession(options: { name?: string; cwd?: string } = {}): TerminalSession {
    const id = generateId()
    const sessionCount = this.sessions.size + 1
    const session: TerminalSession = {
      id,
      name: options.name ?? `Terminal ${sessionCount}`,
      cwd: options.cwd ?? process.cwd?.() ?? '~',
      active: true,
      createdAt: new Date().toISOString(),
    }

    // Deactivate all other sessions.
    for (const s of this.sessions.values()) {
      s.active = false
    }

    this.sessions.set(id, session)
    this.activeSessionId = id

    // If no layout yet, set this as the root terminal.
    if (!this.layout.sessionId && this.layout.type === 'terminal') {
      this.layout = { type: 'terminal', sessionId: id }
    }

    this.persist()
    this.notify()
    return session
  }

  /**
   * Close a terminal session.
   */
  closeSession(sessionId: string): void {
    this.sessions.delete(sessionId)

    // Remove from layout.
    this.layout = this.removeFromLayout(this.layout, sessionId)

    // If the closed session was active, activate the first remaining.
    if (this.activeSessionId === sessionId) {
      const remaining = Array.from(this.sessions.values())
      this.activeSessionId = remaining[0]?.id ?? null
      if (this.activeSessionId) {
        const s = this.sessions.get(this.activeSessionId)
        if (s) s.active = true
      }
    }

    this.persist()
    this.notify()
  }

  /**
   * Rename a terminal session.
   */
  renameSession(sessionId: string, name: string): void {
    const session = this.sessions.get(sessionId)
    if (session) {
      session.name = name
      this.persist()
      this.notify()
    }
  }

  /**
   * Set the active terminal.
   */
  setActive(sessionId: string): void {
    for (const s of this.sessions.values()) {
      s.active = s.id === sessionId
    }
    this.activeSessionId = sessionId
    this.persist()
    this.notify()
  }

  /**
   * Split the current terminal.
   */
  splitTerminal(
    sessionId: string,
    direction: SplitDirection,
    options: { name?: string; cwd?: string } = {}
  ): TerminalSession {
    const newSession = this.createSession(options)

    // Find the terminal node in the layout and replace it with a split.
    this.layout = this.splitInLayout(this.layout, sessionId, newSession.id, direction)

    this.persist()
    this.notify()
    return newSession
  }

  /**
   * Navigate to the next/previous terminal.
   */
  cycleSession(direction: 'next' | 'prev'): void {
    const sessions = Array.from(this.sessions.values())
    if (sessions.length <= 1) return

    const currentIdx = sessions.findIndex((s) => s.id === this.activeSessionId)
    const delta = direction === 'next' ? 1 : -1
    const nextIdx = (currentIdx + delta + sessions.length) % sessions.length
    this.setActive(sessions[nextIdx].id)
  }

  // ---- Private helpers ----

  private removeFromLayout(node: SplitNode, sessionId: string): SplitNode {
    if (node.type === 'terminal') {
      if (node.sessionId === sessionId) {
        return { type: 'terminal', sessionId: undefined }
      }
      return node
    }

    if (node.children) {
      const [left, right] = node.children
      if (left.type === 'terminal' && left.sessionId === sessionId) {
        return right
      }
      if (right.type === 'terminal' && right.sessionId === sessionId) {
        return left
      }
      return {
        ...node,
        children: [
          this.removeFromLayout(left, sessionId),
          this.removeFromLayout(right, sessionId),
        ],
      }
    }

    return node
  }

  private splitInLayout(
    node: SplitNode,
    targetId: string,
    newId: string,
    direction: SplitDirection
  ): SplitNode {
    if (node.type === 'terminal' && node.sessionId === targetId) {
      return {
        type: 'split',
        direction,
        ratio: 0.5,
        children: [
          { type: 'terminal', sessionId: targetId },
          { type: 'terminal', sessionId: newId },
        ],
      }
    }

    if (node.children) {
      return {
        ...node,
        children: [
          this.splitInLayout(node.children[0], targetId, newId, direction),
          this.splitInLayout(node.children[1], targetId, newId, direction),
        ],
      }
    }

    return node
  }

  private persist(): void {
    saveState({
      sessions: Array.from(this.sessions.values()),
      layout: this.layout,
      activeSessionId: this.activeSessionId,
    })
  }

  private notify(): void {
    const state = this.getState()
    for (const listener of this.listeners) {
      listener(state)
    }
  }
}

// ---------------------------------------------------------------------------
// Singleton instance
// ---------------------------------------------------------------------------

let instance: TerminalManager | null = null

export function getTerminalManager(): TerminalManager {
  if (!instance) {
    instance = new TerminalManager()
  }
  return instance
}
