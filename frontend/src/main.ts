import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './styles/index.css'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)

// Attempt to restore session from cookie before first navigation
import('@/stores/auth').then(({ useAuthStore }) => {
  const authStore = useAuthStore()
  authStore.fetchMe().catch(() => {
    // No active session — router guard will redirect to /login as needed
  })
})

app.mount('#app')
