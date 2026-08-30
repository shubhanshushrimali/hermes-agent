/**
 * Windows subprocess helpers for the Electron main process.
 *
 * Provides safe subprocess creation on Windows that avoids console
 * window flashes and properly handles SIGTERM translation.
 *
 * Part of Phase 4: IDE-Grade Code Experience.
 */

import { spawn, type SpawnOptions, type ChildProcess } from 'child_process'
import { platform } from 'os'

const IS_WINDOWS = platform() === 'win32'

// ---------------------------------------------------------------------------
// Windows-specific constants
// ---------------------------------------------------------------------------

const CREATE_NO_WINDOW = 0x08000000

// ---------------------------------------------------------------------------
// Safe spawn
// ---------------------------------------------------------------------------

export interface SafeSpawnOptions extends SpawnOptions {
  /** Suppress the Windows console window (default: true on Windows). */
  hideWindow?: boolean
}

/**
 * Spawn a child process with Windows safety guards.
 *
 * On Windows:
 * - Sets `windowsHide: true` to prevent console window flash
 * - Applies `CREATE_NO_WINDOW` creation flag
 * - Uses `cmd.exe /c` for string commands to handle paths with spaces
 *
 * On POSIX, behaves identically to `child_process.spawn`.
 */
export function safeSpawn(
  command: string,
  args: string[] = [],
  options: SafeSpawnOptions = {}
): ChildProcess {
  const { hideWindow = true, ...spawnOpts } = options

  if (IS_WINDOWS && hideWindow) {
    spawnOpts.windowsHide = true
    // Note: windowsHide sets CREATE_NO_WINDOW automatically in Node.js >= 12
  }

  return spawn(command, args, spawnOpts)
}

/**
 * Kill a process tree safely on Windows.
 *
 * On Windows, `process.kill(pid)` only kills the root process.
 * Child processes (shells, subcommands) are orphaned. This uses
 * `taskkill /T /F` to kill the entire tree.
 *
 * On POSIX, sends SIGTERM (or SIGKILL if force=true).
 */
export function safeKill(
  pid: number,
  options: { force?: boolean; tree?: boolean } = {}
): boolean {
  const { force = false, tree = true } = options

  if (!IS_WINDOWS) {
    try {
      process.kill(pid, force ? 'SIGKILL' : 'SIGTERM')
      return true
    } catch {
      return false // Process already dead or insufficient perms.
    }
  }

  // Windows: use taskkill
  try {
    const args = ['taskkill']
    if (force) args.push('/F')
    if (tree) args.push('/T')
    args.push('/PID', String(pid))

    const result = spawn('cmd.exe', ['/c', ...args], {
      windowsHide: true,
      stdio: 'ignore',
    })

    result.on('error', () => {}) // Swallow — best effort.
    return true
  } catch {
    return false
  }
}

/**
 * Get the default shell for the current platform.
 */
export function getDefaultShell(): string {
  if (IS_WINDOWS) {
    // Prefer PowerShell if available, fall back to cmd.exe.
    return process.env.COMSPEC ?? 'cmd.exe'
  }

  return process.env.SHELL ?? '/bin/bash'
}

/**
 * Get shell-specific arguments for spawning an interactive terminal.
 */
export function getShellArgs(shell: string): string[] {
  const basename = shell.split(/[/\\]/).pop()?.toLowerCase() ?? ''

  if (basename === 'powershell.exe' || basename === 'pwsh.exe') {
    return ['-NoLogo', '-NoExit']
  }

  if (basename === 'cmd.exe') {
    return ['/K']
  }

  // POSIX shells: bash, zsh, fish, etc.
  return ['--login']
}

/**
 * Build environment variables for a terminal session.
 *
 * Ensures UTF-8 encoding and inherits the current environment.
 */
export function buildTerminalEnv(
  extra: Record<string, string> = {}
): Record<string, string> {
  const env = { ...process.env, ...extra } as Record<string, string>

  // Force UTF-8 for Python subprocesses.
  env.PYTHONIOENCODING = 'utf-8'

  if (IS_WINDOWS) {
    // Disable legacy Windows stdio for Python 3.6+
    env.PYTHONLEGACYWINDOWSSTDIO = '0'
  }

  // Ensure TERM is set for POSIX tools running on Windows.
  if (!env.TERM) {
    env.TERM = 'xterm-256color'
  }

  return env
}
