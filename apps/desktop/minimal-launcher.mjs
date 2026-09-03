// Compatibility shim: older docs/scripts pointed here, but this file
// used to open Vite at :5174 with no backend. The real desktop app is
// `hermes desktop` (`python -m hermes_cli.main desktop`).
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const python = process.env.HERMES_PYTHON || 'python'
const child = spawn(python, ['-m', 'hermes_cli.main', 'desktop', ...process.argv.slice(2)], {
  cwd: repoRoot,
  stdio: 'inherit',
  shell: process.platform === 'win32',
  env: process.env,
})

child.on('error', (err) => {
  console.error('[minimal-launcher] failed to start hermes desktop:', err.message)
  process.exit(1)
})
child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal)
  process.exit(code ?? 1)
})
