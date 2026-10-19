import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

const root = fileURLToPath(new URL('../', import.meta.url))
const python = resolve(root, 'backend/.venv/bin/python')
const vite = resolve(root, 'frontend/node_modules/vite/bin/vite.js')
if (!existsSync(python) || !existsSync(vite)) {
  console.error('请先按照 README 安装 backend/.venv 和 frontend 依赖。')
  process.exit(1)
}
// Compose and the development runner share the same persistent database.
if (existsSync(resolve(root, '.env'))) process.loadEnvFile(resolve(root, '.env'))
const children = []
let stopping = false
const stop = (code = 0) => {
  if (stopping) return
  stopping = true
  for (const child of children) {
    if (child.pid) { try { process.kill(-child.pid, 'SIGTERM') } catch {} }
  }
  setTimeout(() => process.exit(code), 500)
}
process.on('SIGINT', () => stop())
process.on('SIGTERM', () => stop())
const launch = (command, args, cwd) => {
  const child = spawn(command, args, { cwd, env: process.env, stdio: 'inherit', detached: true })
  children.push(child)
  child.on('error', error => { console.error(error.message); stop(1) })
  child.on('exit', code => { if (!stopping) stop(code || 1) })
  return child
}
launch(python, ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8000'], resolve(root, 'backend'))
let ready = false
for (let attempt = 0; attempt < 75 && !stopping; attempt++) {
  try {
    const response = await fetch('http://127.0.0.1:8000/api/health', { signal: AbortSignal.timeout(500) })
    if (response.ok) { ready = true; break }
  } catch {}
  await new Promise(resolve => setTimeout(resolve, 200))
}
if (!ready) {
  console.error('奖励服务启动失败，请检查上面的错误信息和 8000 端口占用。')
  stop(1)
} else if (!stopping) {
  launch(process.execPath, [vite, '--host', '0.0.0.0', '--port', process.env.PORT || '8080', '--strictPort'], resolve(root, 'frontend'))
}
