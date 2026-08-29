/**
 * Layout Presets — configurable workspace layouts for the Aizen Version.
 *
 * Presets define the sidebar width, right-rail visibility, terminal position,
 * and panel sizes. Users can switch presets via the command palette or settings.
 *
 * Part of Phase 3: UI/UX Optimization.
 */

export interface LayoutPreset {
  id: string
  name: string
  description: string
  icon: string
  sidebarWidth: number        // px
  sidebarCollapsed: boolean
  rightRailVisible: boolean
  rightRailWidth: number      // px
  terminalPosition: 'bottom' | 'right' | 'hidden'
  terminalHeight: number      // px (when bottom) or width (when right)
  composerPosition: 'center' | 'bottom'
  maxContentWidth: string     // CSS max-width for chat area
}

export const LAYOUT_PRESETS: Record<string, LayoutPreset> = {
  classic: {
    id: 'classic',
    name: 'Classic',
    description: 'Traditional chat layout with sidebar',
    icon: '💬',
    sidebarWidth: 260,
    sidebarCollapsed: false,
    rightRailVisible: false,
    rightRailWidth: 400,
    terminalPosition: 'hidden',
    terminalHeight: 250,
    composerPosition: 'center',
    maxContentWidth: '48rem',
  },
  ide: {
    id: 'ide',
    name: 'IDE',
    description: 'Full IDE with preview + terminal',
    icon: '💻',
    sidebarWidth: 240,
    sidebarCollapsed: false,
    rightRailVisible: true,
    rightRailWidth: 480,
    terminalPosition: 'bottom',
    terminalHeight: 280,
    composerPosition: 'bottom',
    maxContentWidth: '100%',
  },
  focused: {
    id: 'focused',
    name: 'Focused',
    description: 'Minimal distractions, maximum flow',
    icon: '🎯',
    sidebarWidth: 0,
    sidebarCollapsed: true,
    rightRailVisible: false,
    rightRailWidth: 400,
    terminalPosition: 'hidden',
    terminalHeight: 250,
    composerPosition: 'center',
    maxContentWidth: '42rem',
  },
  review: {
    id: 'review',
    name: 'Code Review',
    description: 'Side-by-side chat + code review',
    icon: '🔍',
    sidebarWidth: 200,
    sidebarCollapsed: false,
    rightRailVisible: true,
    rightRailWidth: 560,
    terminalPosition: 'hidden',
    terminalHeight: 250,
    composerPosition: 'bottom',
    maxContentWidth: '100%',
  },
  mobile: {
    id: 'mobile',
    name: 'Mobile',
    description: 'Optimized for narrow screens',
    icon: '📱',
    sidebarWidth: 0,
    sidebarCollapsed: true,
    rightRailVisible: false,
    rightRailWidth: 0,
    terminalPosition: 'hidden',
    terminalHeight: 200,
    composerPosition: 'bottom',
    maxContentWidth: '100%',
  },
}

export const DEFAULT_LAYOUT = 'classic'

const STORAGE_KEY = 'hermes-aizen-layout-preset'

/** Get the persisted layout preset ID. */
export function getActiveLayoutId(): string {
  if (typeof localStorage === 'undefined') return DEFAULT_LAYOUT
  return localStorage.getItem(STORAGE_KEY) || DEFAULT_LAYOUT
}

/** Get the active layout preset. */
export function getActiveLayout(): LayoutPreset {
  return LAYOUT_PRESETS[getActiveLayoutId()] || LAYOUT_PRESETS[DEFAULT_LAYOUT]
}

/** Persist a layout preset choice. */
export function setActiveLayout(presetId: string): void {
  if (presetId in LAYOUT_PRESETS) {
    localStorage.setItem(STORAGE_KEY, presetId)
  }
}

/** Get all presets as an ordered list. */
export function getPresetList(): LayoutPreset[] {
  return Object.values(LAYOUT_PRESETS)
}
