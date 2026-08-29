/**
 * Mobile Access Settings Panel — Hermes Agent Aizen Version.
 *
 * Allows users to:
 * - Enable/disable mobile remote control
 * - Create and manage PINs with scoped permissions
 * - View active mobile sessions
 * - Generate QR codes for pairing
 * - Revoke sessions and PINs
 */

import type { ReactNode } from 'react'
import { useCallback, useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { Monitor, Lock, Network, Trash2, Plus, RefreshCw } from '@/lib/icons'

import { ListRow, SectionHeading, SettingsContent, ToggleRow } from './primitives'

// ---- Types ----

interface PinEntry {
  pin_id: string
  scope: string
  label: string
  created_at: number
  expires_at: number
}

interface MobileSession {
  session_id: string
  scope: string
  client_ip: string
  label: string
  created_at: number
  expires_at: number
  last_activity: number
}

// ---- Local storage state ----

const MOBILE_ENABLED_KEY = 'hermes-mobile-enabled'
const MOBILE_PORT_KEY = 'hermes-mobile-port'

function getMobileEnabled(): boolean {
  return localStorage.getItem(MOBILE_ENABLED_KEY) === 'true'
}

function setMobileEnabled(enabled: boolean): void {
  localStorage.setItem(MOBILE_ENABLED_KEY, String(enabled))
}

function getMobilePort(): number {
  return parseInt(localStorage.getItem(MOBILE_PORT_KEY) || '8765', 10)
}

// ---- Helpers ----

const CAPTION = 'text-[length:var(--conversation-caption-font-size)] text-(--ui-text-tertiary)'

function Caption({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn(CAPTION, className)}>{children}</p>
}

function ScopeLabel({ scope }: { scope: string }) {
  const colors: Record<string, string> = {
    admin: 'text-red-400 bg-red-400/10',
    operator: 'text-amber-400 bg-amber-400/10',
    viewer: 'text-green-400 bg-green-400/10',
  }
  return (
    <span className={cn('px-2 py-0.5 rounded-md text-xs font-medium', colors[scope] || 'text-zinc-400 bg-zinc-400/10')}>
      {scope}
    </span>
  )
}

function TimeAgo({ timestamp }: { timestamp: number }) {
  const now = Date.now() / 1000
  const diff = now - timestamp
  let text = 'just now'
  if (diff > 86400) text = `${Math.floor(diff / 86400)}d ago`
  else if (diff > 3600) text = `${Math.floor(diff / 3600)}h ago`
  else if (diff > 60) text = `${Math.floor(diff / 60)}m ago`
  return <span className="text-xs text-(--ui-text-tertiary)">{text}</span>
}

// ---- Component ----

export function MobileAccessSettings() {
  const [enabled, setEnabled] = useState(getMobileEnabled)
  const [pins, setPins] = useState<PinEntry[]>([])
  const [sessions, setSessions] = useState<MobileSession[]>([])
  const [newPinScope, setNewPinScope] = useState('operator')
  const [newPinLabel, setNewPinLabel] = useState('')
  const [showCreatePin, setShowCreatePin] = useState(false)
  const [generatedPin, setGeneratedPin] = useState('')
  const port = getMobilePort()

  const toggleEnabled = useCallback((v: boolean) => {
    setEnabled(v)
    setMobileEnabled(v)
  }, [])

  // Generate a random 6-digit PIN
  const generatePin = useCallback(() => {
    const pin = String(Math.floor(100000 + Math.random() * 900000))
    setGeneratedPin(pin)
    // In a real integration, this would call the gateway API
    setPins(prev => [
      ...prev,
      {
        pin_id: Math.random().toString(36).slice(2, 10),
        scope: newPinScope,
        label: newPinLabel || `PIN ${prev.length + 1}`,
        created_at: Date.now() / 1000,
        expires_at: Date.now() / 1000 + 86400,
      },
    ])
    setShowCreatePin(false)
    setNewPinLabel('')
  }, [newPinScope, newPinLabel])

  const revokePin = useCallback((pinId: string) => {
    setPins(prev => prev.filter(p => p.pin_id !== pinId))
  }, [])

  const revokeSession = useCallback((sessionId: string) => {
    setSessions(prev => prev.filter(s => s.session_id !== sessionId))
  }, [])

  return (
    <SettingsContent>
      {/* Header */}
      <SectionHeading icon={Monitor} title="Mobile Access" />
      <Caption className="mb-4 leading-(--conversation-caption-line-height)">
        Control Hermes Agent from your phone. Enable mobile access, create PINs
        with scoped permissions, and pair devices via QR code.
      </Caption>

      {/* Enable/Disable */}
      <ToggleRow
        checked={enabled}
        description={`Mobile API server on port ${port}`}
        label="Enable Mobile Remote Control"
        onChange={toggleEnabled}
      />

      {enabled && (
        <>
          {/* Connection Info */}
          <div className="mt-4 p-4 rounded-xl border border-(--ui-stroke-secondary) bg-(--ui-bg-card)">
            <div className="flex items-center gap-2 mb-2">
              <Network className="w-4 h-4 text-(--ui-text-tertiary)" />
              <span className="text-sm font-medium">Connection</span>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-(--ui-text-tertiary)">URL</span>
                <div className="font-mono text-xs mt-0.5">http://localhost:{port}</div>
              </div>
              <div>
                <span className="text-(--ui-text-tertiary)">Status</span>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="text-xs text-emerald-400">Active</span>
                </div>
              </div>
            </div>
          </div>

          {/* PINs */}
          <div className="mt-6">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Lock className="w-4 h-4 text-(--ui-text-tertiary)" />
                <span className="text-sm font-medium">Access PINs</span>
              </div>
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5"
                onClick={() => setShowCreatePin(!showCreatePin)}
              >
                <Plus className="w-3.5 h-3.5" />
                New PIN
              </Button>
            </div>

            {/* Create PIN form */}
            {showCreatePin && (
              <div className="p-4 rounded-xl border border-(--ui-stroke-secondary) bg-(--ui-bg-card) mb-3 aizen-panel-enter">
                <div className="flex gap-3 mb-3">
                  <input
                    className="flex-1 px-3 py-2 rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-bg-input) text-sm aizen-input-glow"
                    placeholder="Label (e.g. My Phone)"
                    value={newPinLabel}
                    onChange={e => setNewPinLabel(e.target.value)}
                  />
                  <Select value={newPinScope} onValueChange={setNewPinScope}>
                    <SelectTrigger className="w-32">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="viewer">Viewer</SelectItem>
                      <SelectItem value="operator">Operator</SelectItem>
                      <SelectItem value="admin">Admin</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex justify-between items-center">
                  <Caption>PIN expires after 24 hours</Caption>
                  <div className="flex gap-2">
                    <Button size="sm" variant="ghost" onClick={() => setShowCreatePin(false)}>
                      Cancel
                    </Button>
                    <Button size="sm" onClick={generatePin}>
                      Generate PIN
                    </Button>
                  </div>
                </div>
              </div>
            )}

            {/* Generated PIN display */}
            {generatedPin && (
              <div className="p-4 rounded-xl border border-indigo-500/30 bg-indigo-500/5 mb-3 aizen-panel-enter">
                <Caption className="mb-2">Your PIN (shown once):</Caption>
                <div className="font-mono text-3xl font-bold tracking-[0.3em] text-center text-indigo-400">
                  {generatedPin}
                </div>
                <Caption className="mt-2 text-center">Enter this on your phone to connect</Caption>
                <Button
                  size="sm"
                  variant="ghost"
                  className="mt-2 w-full"
                  onClick={() => setGeneratedPin('')}
                >
                  Dismiss
                </Button>
              </div>
            )}

            {/* PIN list */}
            {pins.length === 0 ? (
              <Caption>No PINs configured. Create one to enable mobile access.</Caption>
            ) : (
              <div className="space-y-2">
                {pins.map(pin => (
                  <div
                    key={pin.pin_id}
                    className="flex items-center justify-between p-3 rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-bg-card)"
                  >
                    <div className="flex items-center gap-3">
                      <div>
                        <div className="text-sm font-medium">{pin.label}</div>
                        <TimeAgo timestamp={pin.created_at} />
                      </div>
                      <ScopeLabel scope={pin.scope} />
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-red-400 hover:text-red-300"
                      onClick={() => revokePin(pin.pin_id)}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Active Sessions */}
          <div className="mt-6">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <RefreshCw className="w-4 h-4 text-(--ui-text-tertiary)" />
                <span className="text-sm font-medium">Active Sessions</span>
              </div>
              <span className="text-xs text-(--ui-text-tertiary)">
                {sessions.length} connected
              </span>
            </div>

            {sessions.length === 0 ? (
              <Caption>No active mobile sessions.</Caption>
            ) : (
              <div className="space-y-2">
                {sessions.map(session => (
                  <div
                    key={session.session_id}
                    className="flex items-center justify-between p-3 rounded-lg border border-(--ui-stroke-secondary) bg-(--ui-bg-card)"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{session.client_ip}</span>
                        <ScopeLabel scope={session.scope} />
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <Caption>Last active: </Caption>
                        <TimeAgo timestamp={session.last_activity} />
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-red-400 hover:text-red-300"
                      onClick={() => revokeSession(session.session_id)}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </SettingsContent>
  )
}
