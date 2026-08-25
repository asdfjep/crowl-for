<script setup>
import { useRoute } from 'vue-router'
import { getHealth } from './api'
import { ref, onMounted, onBeforeUnmount } from 'vue'

const route = useRoute()
const online = ref(null)
let timer = null

function ping() {
  getHealth()
    .then(() => (online.value = true))
    .catch(() => (online.value = false))
}

onMounted(() => {
  ping()
  timer = setInterval(ping, 30000)
})

onBeforeUnmount(() => clearInterval(timer))

const menus = [
  { path: '/dashboard', title: '仪表盘', icon: 'Odometer' },
  { path: '/reports', title: '报告中心', icon: 'Document' },
  { path: '/analyze', title: '运行分析', icon: 'Cpu' },
  { path: '/health', title: '数据源巡检', icon: 'FirstAidKit' },
  { path: '/data', title: '数据管理', icon: 'FolderOpened' },
  { path: '/settings', title: '系统设置', icon: 'Setting' }
]
</script>

<template>
  <el-container class="layout">
    <el-aside width="216px">
      <div class="logo">
        <el-icon :size="22"><DataAnalysis /></el-icon>
        <span>AI 新闻分析中心</span>
      </div>
      <el-menu
        :default-active="route.path"
        router
        background-color="#001529"
        text-color="#a6adb4"
        active-text-color="#ffffff"
      >
        <el-menu-item v-for="m in menus" :key="m.path" :index="m.path">
          <el-icon><component :is="m.icon" /></el-icon>
          <span>{{ m.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header>
        <div style="font-weight: 600">{{ route.meta.title || '' }}</div>
        <div style="display: flex; align-items: center; gap: 10px">
          <el-tag :type="online === null ? 'info' : online ? 'success' : 'danger'" size="small" effect="plain">
            {{ online === null ? '检测中' : online ? 'API 正常' : 'API 离线' }}
          </el-tag>
        </div>
      </el-header>
      <el-main>
        <router-view v-slot="{ Component }">
          <keep-alive include="Analyze,Health">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>