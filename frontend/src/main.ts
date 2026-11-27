import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'element-plus/theme-chalk/base.css'
import 'element-plus/theme-chalk/el-message.css'
import 'element-plus/theme-chalk/el-message-box.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import App from './App.vue'
import router from './router'
import './styles/main.css'
import { initializeTheme } from './composables/useTheme'

initializeTheme()
const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
