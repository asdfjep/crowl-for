<script setup>
import { onMounted, ref, computed } from 'vue'
import { marked } from 'marked'
import { listReports, getReportText, reportUrl, downloadText } from '../api'
import { formatSize, formatTime, REPORT_CATEGORIES, TOPIC_KEYS } from '../utils/format'

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

const CATEGORY_ORDER = ['weekly_md', 'weekly_pdf', 'brief_html', 'daily_md', 'daily_pdf', 'health_md', 'health_json']

const groups = computed(() => {
  const byGroup = {}
  for (const r of filtered.value) {
    (byGroup[r.group] = byGroup[r.group] || []).push(r)
  }
  const arr = Object.values(byGroup)
  for (const g of arr) {
    g.sort((a, b) => {
      const ai = CATEGORY_ORDER.indexOf(a.category)
      const bi = CATEGORY_ORDER.indexOf(b.category)
      if (ai !== bi) return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi)
      return b.modified.localeCompare(a.modified)
    })
  }
  arr.sort((a, b) => b[0].modified.localeCompare(a[0].modified))
  return arr.map(g => ({ group: g[0].group, files: g, newest: g[0].modified }))
})

function groupLabel(g) {
  const w = g.match(/^weekly_(.+)$/)
  if (w) return `周报 · ${w[1]}`
  const d = g.match(/^daily_(.+)$/)
  if (d) return `日报 · ${d[1]}`
  const h = g.match(/^health_(\d{8}_\d{4})$/)
  if (h) return `巡检 · ${h[1]}`
  return g
}

function groupTopics(files) {
  return [...new Set(files.map(f => f.topic).filter(Boolean))]
    .map(k => TOPIC_KEYS[k] || k)
    .join(' / ') || '报告'
}

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
    <p class="page-sub">按生成批次捆绑浏览；一次运行产生的 Markdown / PDF / HTML 简报在同一组</p>

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

    <div v-loading="loading">
      <div
        v-for="g in groups"
        :key="g.group"
        class="panel"
        style="margin-bottom: 14px; box-shadow: none; border: 1px solid #f0f0f0"
      >
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px">
          <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap">
          <el-tag size="small" type="info" effect="plain">{{ groupTopics(g.files) }}</el-tag>
          <b style="font-size: 14px">{{ groupLabel(g.group) }}</b>
          <span style="color: #909399; font-size: 12px">{{ g.files.length }} 个文件</span>
        </div>
          <span style="color: #909399; font-size: 12px">{{ formatTime(g.newest) }}</span>
        </div>
        <el-table :data="g.files" size="small">
          <el-table-column label="文件" min-width="300" show-overflow-tooltip>
            <template #default="{ row }">{{ row.name }}</template>
          </el-table-column>
          <el-table-column label="类型" width="160">
            <template #default="{ row }">
              <el-tag size="small" :type="catColor(row.category)">{{ catLabel(row.category) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="大小" width="95">
            <template #default="{ row }">{{ formatSize(row.size) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="210" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" text @click="viewReport(row)">
                {{ textCategory(row.category) ? '查看' : '打开' }}
              </el-button>
              <el-button size="small" text @click="textCategory(row.category) ? downloadMd(row) : openExternal(row)">下载</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-empty v-if="!groups.length && !loading" description="暂无报告，请先在「运行分析」中生成" :image-size="80" />
    </div>

    <el-dialog v-model="viewer.show" :title="viewer.title" width="70%" top="5vh">
      <div v-loading="viewer.loading" class="md-body" style="max-height: 70vh; overflow: auto">
        <div v-html="viewer.html"></div>
      </div>
    </el-dialog>
  </div>
</template>