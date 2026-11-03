export async function fetchJSON(url, options = {}, validate = () => true) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 10000)
  try {
    const response = await fetch(url, { ...options, signal: controller.signal })
    if (!response.headers.get('content-type')?.includes('application/json')) {
      throw new Error('奖励服务没有返回有效数据，请检查服务是否已启动后重试。')
    }
    let body
    try { body = await response.json() }
    catch { throw new Error('奖励服务返回的数据不完整，请重试。') }
    if (!response.ok) {
      const detail = typeof body?.detail === 'string' ? body.detail : '输入内容不符合要求，请检查后重试。'
      const error = new Error(detail)
      error.status = response.status
      throw error
    }
    if (!validate(body)) throw new Error('奖励数据格式异常，请刷新或联系家长。')
    return body
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('连接超时，请检查网络后重试。')
    if (error instanceof TypeError) throw new Error('暂时无法连接奖励服务，请检查网络和服务状态。')
    throw error
  } finally { clearTimeout(timeout) }
}

export const isDashboard = body => Boolean(
  body && typeof body.child?.name === 'string' && typeof body.child?.avatar === 'string'
  && Array.isArray(body.assets) && body.assets.every(a => typeof a.code === 'string' && Number.isInteger(a.balance))
  && Array.isArray(body.badges) && body.badges.every(b => Number.isInteger(b.earned_count) && Number.isInteger(b.available_count))
  && Number.isInteger(body.progress?.target) && body.progress.target > 0 && body.progress.target <= 100
  && Number.isFinite(body.progress?.current) && Number.isFinite(body.progress?.total_stars)
  && Number.isInteger(body.star_total) && Number.isFinite(body.study_progress?.current)
  && Number.isFinite(body.study_progress?.total_stars) && Number.isInteger(body.study_progress?.target)
  && Number.isInteger(body.badge_progress?.available) && body.badge_progress.target === 5
  && Number.isInteger(body.coupons?.balance) && body.coupons.unit_value_fen === 3990
  && Number.isInteger(body.coupons?.total_value_fen)
)

export const isList = body => Array.isArray(body) && body.every(item => item && Number.isInteger(item.id))
