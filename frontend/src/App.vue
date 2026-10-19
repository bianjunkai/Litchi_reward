<script setup>
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { fetchJSON, isDashboard, isList } from './api.js'
import ParentConsole from './ParentConsole.vue'
import PixelArt from './PixelArt.vue'
import HomePage from './pages/HomePage.vue'
import AdventuresPage from './pages/AdventuresPage.vue'
import BackpackPage from './pages/BackpackPage.vue'
import ShopPage from './pages/ShopPage.vue'
import { childTabs, parseRoute, routeHash } from './navigation.js'

const route = ref(parseRoute(window.location.hash))
const dashboard = ref(null)
const tasks = ref([])
const badges = ref([])
const history = ref([])
const products = ref([])
const token = ref('')
const expiresAt = ref(0)
const setupRequired = ref(false)
const pinInput = ref('')
const confirmPin = ref('')
const toast = ref('')
const error = ref('')
const authError = ref('')
const loading = ref(false)
const busy = ref(false)
const main = ref(null)
let toastTimer
let expiryTimer
let authEpoch = 0

const lock = () => { authEpoch++; token.value = ''; expiresAt.value = 0; pinInput.value = ''; confirmPin.value = '' }
const notify = message => {
  clearTimeout(toastTimer)
  toast.value = message
  toastTimer = setTimeout(() => { toast.value = '' }, 3500)
}
const api = async (url, options = {}, validate) => {
  const credential = token.value
  const headers = { 'Content-Type': 'application/json', ...options.headers }
  if (credential) headers.Authorization = 'Bearer ' + credential
  try { return await fetchJSON(url, { ...options, headers }, validate) }
  catch (err) {
    if (err.status === 401 && credential && token.value === credential) { lock(); authError.value = '家长会话已锁定，请重新解锁。' }
    throw err
  }
}

// Drop the local credential immediately when leaving the parent area, including browser Back.
const revokeSession = async () => {
  const credential = token.value
  lock()
  if (!credential) return
  try { await fetchJSON('/api/auth/logout', { method: 'POST', headers: { Authorization: 'Bearer ' + credential } }) }
  catch { /* A network failure must never keep the device unlocked. */ }
}
const syncRoute = () => {
  const next = parseRoute(window.location.hash)
  if (route.value.page === 'parent' && next.page !== 'parent') {
    void revokeSession()
    authError.value = ''
    notify('已返回孩子模式，家长操作已锁定')
  }
  route.value = next
}
const navigate = (page, section = '') => {
  const hash = routeHash(page, section)
  if (window.location.hash === hash) return
  window.location.hash = hash
  syncRoute()
}
const exitParent = () => navigate('home')

const refresh = async () => {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const data = await Promise.all([
      api('/api/dashboard/1', {}, isDashboard),
      api('/api/tasks?child_id=1', {}, isList),
      api('/api/badges?child_id=1', {}, isList),
      api('/api/shop', {}, isList),
      api('/api/auth/status', {}, value => typeof value?.setup_required === 'boolean'),
      api('/api/badges/history?child_id=1', {}, isList),
    ])
    ;[dashboard.value, tasks.value, badges.value, products.value] = data
    setupRequired.value = data[4].setup_required
    history.value = data[5]
  } catch (err) { error.value = err.message }
  finally { loading.value = false }
}
const login = async () => {
  if (busy.value) return
  authError.value = ''
  if (setupRequired.value && (!/^[0-9]{6,12}$/.test(pinInput.value) || pinInput.value !== confirmPin.value)) {
    authError.value = '请设置 6–12 位数字 PIN，并确保两次输入一致。'
    return
  }
  busy.value = true
  const requestEpoch = authEpoch
  try {
    const session = await api(setupRequired.value ? '/api/auth/setup' : '/api/auth/parent', {
      method: 'POST', body: JSON.stringify({ pin: pinInput.value }),
    }, value => typeof value?.token === 'string' && Number.isFinite(value.expires_in))
    // A late login response must not unlock a page the parent has already left.
    setupRequired.value = false
    if (route.value.page !== 'parent' || requestEpoch !== authEpoch) {
      void fetchJSON('/api/auth/logout', { method: 'POST', headers: { Authorization: 'Bearer ' + session.token } }).catch(() => {})
      return
    }
    token.value = session.token
    expiresAt.value = Date.now() + session.expires_in * 1000
    pinInput.value = ''; confirmPin.value = ''
    notify('家长中心已解锁')
  } catch (err) { if (route.value.page === 'parent' && requestEpoch === authEpoch) authError.value = err.message }
  finally { busy.value = false }
}
const requestProduct = async product => {
  if (busy.value || error.value) return
  busy.value = true
  try {
    const result = await api('/api/redemptions', { method: 'POST', body: JSON.stringify({ child_id: 1, product_id: product.id }) })
    notify(result.message)
  } catch (err) { notify(err.message) }
  finally { busy.value = false }
}

watch(() => route.value.page + '/' + route.value.section, async () => {
  await nextTick()
  main.value?.focus({ preventScroll: true })
  window.scrollTo({ top: 0, behavior: 'instant' })
})
onMounted(() => {
  refresh()
  window.addEventListener('hashchange', syncRoute)
  expiryTimer = setInterval(() => {
    if (token.value && Date.now() >= expiresAt.value) { lock(); notify('家长会话已到期') }
  }, 1000)
})
onUnmounted(() => {
  clearTimeout(toastTimer)
  clearInterval(expiryTimer)
  window.removeEventListener('hashchange', syncRoute)
})
</script>

<template>
  <div class="app-shell" :class="{'parent-shell': route.page === 'parent'}">
    <header class="topbar">
      <button class="brand" aria-label="返回城堡首页" @click="navigate('home')"><PixelArt kind="mushroom" :size="30" /><span><strong>奖励城堡</strong><small>SUPER FAMILY · 快乐成长</small></span></button>
      <div class="topbar-actions">
        <button v-if="route.page === 'parent'" class="parent-entry" @click="exitParent">返回孩子模式</button>
        <button v-else class="parent-entry" @click="navigate('parent', 'today')"><PixelArt kind="crown" :size="18" /> 家长入口</button>
        <button class="refresh-button" aria-label="刷新奖励数据" @click="refresh" :disabled="loading">↻</button>
      </div>
    </header>
    <main ref="main" class="page-wrap" tabindex="-1" aria-label="页面内容">
      <section v-if="error" class="status-card error-card" role="alert">
        <h1>暂时无法打开奖励城堡</h1><p>{{ error }}</p>
        <p v-if="dashboard">下方为上次加载的数据，恢复连接后才能继续操作。</p>
        <button class="primary-button" @click="refresh" :disabled="loading">{{ loading ? '正在重试…' : '重新连接' }}</button>
      </section>
      <section v-if="loading && !dashboard" class="status-card" role="status"><h1>正在打开你的奖励城堡… 🏰</h1><p>正在整理星星和徽章，请稍等。</p></section>
      <template v-if="dashboard">
        <HomePage v-if="route.page === 'home'" :dashboard="dashboard" :tasks="tasks" :badges="badges" @navigate="navigate" />
        <AdventuresPage v-else-if="route.page === 'adventures'" :tasks="tasks" :badges="badges" :category="route.section" :offline="!!error" @navigate="navigate" />
        <BackpackPage v-else-if="route.page === 'backpack'" :dashboard="dashboard" :badges="badges" :history="history" :section="route.section" @navigate="navigate" />
        <ShopPage v-else-if="route.page === 'shop'" :dashboard="dashboard" :products="products" :busy="busy" :offline="!!error" @request="requestProduct" @navigate="navigate" />
        <section v-else-if="route.page === 'parent'" class="view parent-view">
          <form v-if="!token" class="pin-card" @submit.prevent="login">
            <div class="lock"><PixelArt kind="crown" :size="48" /></div><h1>{{ setupRequired ? '设置家长 PIN' : '家长中心' }}</h1>
            <p>{{ setupRequired ? '请家长设置 6–12 位数字 PIN，保护奖励管理。' : '输入家长 PIN，继续管理奖励。' }}</p>
            <label class="sr-only" for="parent-pin">家长 PIN</label><input id="parent-pin" v-model="pinInput" type="password" inputmode="numeric" maxlength="12" autocomplete="off" placeholder="家长 PIN" required />
            <input v-if="setupRequired" v-model="confirmPin" aria-label="再次输入 PIN" type="password" inputmode="numeric" maxlength="12" autocomplete="off" placeholder="再次输入 PIN" required />
            <p v-if="authError" class="inline-error" role="alert">{{ authError }}</p>
            <button class="primary-button" :disabled="busy || !!error">{{ busy ? '正在验证…' : setupRequired ? '设置并进入' : '解锁控制台' }}</button>
            <small>返回孩子模式会自动锁定；解锁会话最长 30 分钟。</small>
          </form>
          <ParentConsole v-else :key="token" :api="api" :dashboard="dashboard" :tasks="tasks" :offline="!!error" :section="route.section" @navigate="section => navigate('parent', section)" @changed="refresh" @notify="notify" @lock="lock" />
        </section>
      </template>
    </main>
    <nav v-if="route.page !== 'parent'" class="bottom-nav child-nav" aria-label="主导航"><a v-for="tab in childTabs" :key="tab.page" :href="routeHash(tab.page)" :class="{active: route.page === tab.page}" :aria-current="route.page === tab.page ? 'page' : undefined"><PixelArt :kind="tab.icon" :size="24" /><span>{{ tab.label }}</span></a></nav>
    <div v-if="toast" class="toast" role="status">{{ toast }}</div>
  </div>
</template>
