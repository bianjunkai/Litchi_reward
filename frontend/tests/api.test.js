import test from 'node:test'
import assert from 'node:assert/strict'
import { fetchJSON, isDashboard } from '../src/api.js'

test('HTML fallback and malformed responses remain errors instead of fake dashboards', async () => {
  const original = globalThis.fetch
  try {
    globalThis.fetch = async () => new Response('<html>static host</html>', { headers: { 'content-type': 'text/html' } })
    await assert.rejects(fetchJSON('/api/dashboard/1', {}, isDashboard), /有效数据/)
    globalThis.fetch = async () => new Response('{invalid', { headers: { 'content-type': 'application/json' } })
    await assert.rejects(fetchJSON('/api/dashboard/1', {}, isDashboard), /不完整/)
    globalThis.fetch = async () => Response.json({})
    await assert.rejects(fetchJSON('/api/dashboard/1', {}, isDashboard), /格式异常/)
  } finally { globalThis.fetch = original }
})

test('Network failures and expired sessions preserve useful errors', async () => {
  const original = globalThis.fetch
  try {
    globalThis.fetch = async () => { throw new TypeError('Failed to fetch') }
    await assert.rejects(fetchJSON('/api/health'), /无法连接/)
    globalThis.fetch = async () => Response.json({ detail: '家长会话已锁定' }, { status: 401 })
    await assert.rejects(fetchJSON('/api/parent/summary'), error => error.status === 401 && /已锁定/.test(error.message))
  } finally { globalThis.fetch = original }
})
