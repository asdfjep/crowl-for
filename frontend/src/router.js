import { createRouter, createWebHashHistory } from 'vue-router'
import Dashboard from './views/Dashboard.vue'
import Reports from './views/Reports.vue'
import Analyze from './views/Analyze.vue'
import Health from './views/Health.vue'
import Data from './views/Data.vue'
import Settings from './views/Settings.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: Dashboard, meta: { title: '仪表盘', icon: 'Odometer' } },
    { path: '/reports', component: Reports, meta: { title: '报告中心', icon: 'Document' } },
    { path: '/analyze', component: Analyze, meta: { title: '运行分析', icon: 'Cpu' } },
    { path: '/health', component: Health, meta: { title: '数据源巡检', icon: 'FirstAidKit' } },
    { path: '/data', component: Data, meta: { title: '数据管理', icon: 'FolderOpened' } },
    { path: '/settings', component: Settings, meta: { title: '系统设置', icon: 'Setting' } }
  ]
})

router.afterEach((to) => {
  document.title = `${to.meta.title || ''} · AI 新闻分析中心`
})

export default router