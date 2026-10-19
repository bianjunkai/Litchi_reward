import { createApp } from 'vue'
import App from './App.vue'
import './style.css'
import './mario-theme.css'
import './page-layout.css'

createApp(App).mount('#app')

if (import.meta.env.PROD && 'serviceWorker' in navigator && window.isSecureContext) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // Online use still works when the browser declines offline caching.
    })
  })
}
