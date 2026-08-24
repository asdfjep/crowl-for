<script setup>
import { onMounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { getMeta, listReports } from '../api'
import { formatTime, REPORT_CATEGORIES } from '../utils/format'
import StatCard from '../components/StatCard.vue'
import EChart from '../components/EChart.vue'

const router = useRouter()
const meta = ref(null)
const reports = ref([])

onMounted(async () => {
  try {
    meta.value = await getMeta()
  } catch (e) { /* handled by interceptor */ }
  try {
    const res = await listReports()
    reports.value = res.reports || []
  } catch (e) { /* handled by interceptor */ }
})

const recent = computed(() => reports.value.slice(0, 6))
const mdCount = computed(() => reports.value.filter(r => r.category === 'weekly_md' || r.category === 'daily_md').length)
const pdfCount = computed(() => reports.value.filter(r => r.category === 'weekly_pdf' || r.category === 'daily_pdf').length)
const briefCount = computed(() => reports.value.filter(r => r.category === 'brief_html').length)
const healthCount = computed(() => reports.value.filter(r => r.category.startsWith('health')).length)

const pieOption = computed(() => {
  const counts = {}
  for (const r of reports.value) counts[r.category] = (counts[r.category] || 0) + 1
  const legend = Object.keys(counts)
  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, type: 'scroll' },
    series: [{
      name: '报告分布',
      type: 'pie',
      radius: ['40%', '68%'],
      avoidLabelOverlap: true,
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 16, fontWeight: 'bold' } },
      labelLine: { show: false },
      data: legend.map(k => ({
        name: (REPORT_CATEGORIES[k] || { label: k }).label,
        value: counts[k]
      }))
    }]
  }
})

function categoryLabel(k) {
  return (REPORT_CATEGORIES[k] || { label: k }).label
}
</script>

<template>
  <div>
    <h2 class="page-title">仪表盘</h2>
    <p class="page-sub">AI 新闻分析服务运行概览</p>

    <el-row :gutter="16">
      <el-col :xs="12" :sm="8" :md="4">
        <StatCard icon="Tickets" color="#409eff" :value="reports.length" label="报告总数" />
      </el-col>
      <el-col :xs="12" :sm="8" :md="4">
        <StatCard icon="Document" color="#67c23a" :value="mdCount" label="Markdown 报告" />
      </el-col>
      <el-col :xs="12" :sm="8" :md="4">
        <StatCard icon="DocumentCopy" color="#e6a23c" :value="pdfCount" label="PDF 报告" />
      </el-col>
      <el-col :xs="12" :sm="8" :md="4">
        <StatCard icon="DataLine" color="#f56c6c" :value="briefCount" label="HTML 简报" />
      </el-col>
      <el-col :xs="12" :sm="8" :md="4">
        <StatCard icon="FirstAidKit" color="#909399" :value="healthCount" label="巡检报告" />
      </el-col>
      <el-col :xs="12" :sm="8" :md="4">
        <StatCard icon="Grid" color="#795548" :value="meta?.topics?.length || 0" label="分析主题" />
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :xs="24" :md="10">
        <div class="panel">
          <div class="panel-title">报告类型分布</div>
          <div class="chart-box" style="height: 300px">
            <EChart v-if="reports.length" :option="pieOption" />
            <el-empty v-else description="暂无报告" :image-size="80" />
          </div>
        </div>
      </el-col>
      <el-col :xs="24" :md="14">
        <div class="panel">
          <div class="panel-title" style="display: flex; justify-content: space-between; align-items: center">
            <span>最近报告</span>
            <el-link type="primary" @click="router.push('/reports')">查看全部</el-link>
          </div>
          <el-table :data="recent" size="small" height="300">
            <el-table-column prop="name" label="报告名称" min-width="220" show-overflow-tooltip />
            <el-table-column label="类型" width="130">
              <template #default="{ row }">
                <el-tag size="small" :type="(REPORT_CATEGORIES[row.category] || {}).color || 'info'">
                  {{ categoryLabel(row.category) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="更新时间" width="150">
              <template #default="{ row }">{{ formatTime(row.modified) }}</template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :xs="24" :md="14">
        <div class="panel">
          <div class="panel-title">分析主题</div>
          <el-table :data="meta?.topics || []" size="small">
            <el-table-column prop="label" label="主题" width="140" />
            <el-table-column prop="key" label="配置标识" width="180" />
            <el-table-column prop="source_count" label="数据源数" width="110" />
            <el-table-column prop="board_order" label="板块数" width="100">
              <template #default="{ row }">{{ row.board_order?.length || 0 }}</template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
      <el-col :xs="24" :md="10">
        <div class="panel">
          <div class="panel-title">服务信息</div>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="服务">{{ meta?.service }} v{{ meta?.version }}</el-descriptions-item>
            <el-descriptions-item label="Python">{{ meta?.python }}</el-descriptions-item>
            <el-descriptions-item label="数据目录">{{ meta?.data_dir }}</el-descriptions-item>
            <el-descriptions-item label="报告目录">{{ meta?.report_dir }}</el-descriptions-item>
            <el-descriptions-item label="LLM 配置">
              <el-tag :type="meta?.llm_ready ? 'success' : 'info'" size="small">
                {{ meta?.llm_ready ? '已就绪' : '未配置（将使用基础模式）' }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </div>
      </el-col>
    </el-row>
  </div>
</template>