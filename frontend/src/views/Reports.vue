<script setup>
import { onMounted, ref, computed } from 'vue'
import { marked } from 'marked'
import { listReports, getReportText, reportUrl, downloadText } from '../api'
import { formatSize, formatTime, REPORT_CATEGORIES } from '../utils/format'

const reports = ref([])
const loading = ref(false)

const filterType = ref('')
const filterTopic = ref('')
const search = ref('')

const viewer = ref({
  show: false,
  name: '',
  title: '',
  html: '',
  loading: false
})

onMounted(load)

async function load() {
  loading.value = true
  try {
    const res = await listReports()
    reports.value = res.reports || []
  } catch (e) { /* handled */ }
  loading.value = false
}

const typeOptions = Object.keys(REPORT_CATEGORIES).map(k => ({ value: k, label: REPORT_CATEGORIES[k].label }))
const topicOptions = computed(() => [...new Set(reports.value.map(r => r.topic).filter(Boolean))])

const filtered = computed(() => {
  return reports.value.filter(r => {
    if (filterType.value && r.category !== filterType.value) return false
    if (filterTopic.value && r.topic !== filterTopic.value) return false
    if (search.value && !r.name.toLowerCase().includes(search.value.toLowerCase())) return false
    return true
  })
})

function textCategory(cat) {
  return cat === 'weekly_md' || cat === 'daily_md' || cat === 'health_md'
}

async function viewReport(row) {
  if (!textCategory(row.category)) {
    return window.open(reportUrl(row.name), '_blank')
  }
  viewer.value = { show: true, name: row.name, title: row.name, html: '', loading: true }
  try {
    const content = await getReportText(row.name)
    viewer.value.html = marked.parse(content)
  } catch (e) { /* handled */ }
  viewer.value.loading = false
}

async function downloadMd(row) {
  const content = await getReportText(row.name)
  downloadText(row.name, content)
}

function openExternal(row) {
  window.open(reportUrl(row.name), '_blank')
}

function catColor(cat) {
  return (REPORT_CATEGORIES[cat] || {}).color || 'info'
}
function catLabel(cat) {
  return (REPORT_CATEGORIES[cat] || { label: cat }).label
}
</script>

<template>
  <div>
    <h2 class="page-title">报告中心</h2>
    <p class="page-sub">查看与下载已生成的周报 / 日报 / 简报 / 巡检报告</p>

    <el-card shadow="never" style="margin-bottom: 16px">
      <el-row :gutter="12" align="middle">
        <el-col :xs="24" :sm="7">
          <el-select v-model="filterType" placeholder="全部类型" clearable style="width: 100%">
            <el-option v-for="o in typeOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-col>
        <el-col :xs="24" :sm="5">
          <el-select v-model="filterTopic" placeholder="全部主题" clearable style="width: 100%">
            <el-option v-for="t in topicOptions" :key="t" :label="t" :value="t" />
          </el-select>
        </el-col>
        <el-col :xs="24" :sm="8">
          <el-input v-model="search" placeholder="搜索报告名称" clearable />
        </el-col>
        <el-col :xs="24" :sm="4" style="text-align: right">
          <el-button :loading="loading" @click="load">刷新</el-button>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="filtered" size="small">
        <el-table-column prop="name" label="报告名称" min-width="300" show-overflow-tooltip />
        <el-table-column label="类型" width="150">
          <template #default="{ row }">
            <el-tag size="small" :type="catColor(row.category)">{{ catLabel(row.category) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="主题" width="110">
          <template #default="{ row }">
            <span v-if="row.topic">{{ row.topic }}</span>
            <span v-else style="color:#c0c4cc">—</span>
          </template>
        </el-table-column>
        <el-table-column label="大小" width="90">
          <template #default="{ row }">{{ formatSize(row.size) }}</template>
        </el-table-column>
        <el-table-column label="更新时间" width="160">
          <template #default="{ row }">{{ formatTime(row.modified) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" text @click="viewReport(row)">
              {{ textCategory(row.category) ? '查看' : '打开' }}
            </el-button>
            <el-button size="small" text @click="downloadMd(row)" v-if="textCategory(row.category)">下载</el-button>
            <el-button size="small" text @click="openExternal(row)" v-else>下载</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无报告，请先在「运行分析」中生成" :image-size="80" />
        </template>
      </el-table>
    </el-card>

    <el-dialog v-model="viewer.show" :title="viewer.title" width="70%" top="5vh">
      <div v-loading="viewer.loading" class="md-body" style="max-height: 70vh; overflow: auto">
        <div v-html="viewer.html"></div>
      </div>
    </el-dialog>
  </div>
</template>