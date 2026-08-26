<script setup>
import { onMounted, ref, computed, onBeforeUnmount } from 'vue'
import { marked } from 'marked'
import { ElMessage } from 'element-plus'
import { getMeta, createJob, getJob, cancelJob, listReports, getReportText } from '../api'
import { formatTime, REPORT_CATEGORIES } from '../utils/format'

defineOptions({ name: 'Health' })

const meta = ref(null)
const topics = ref([])
const topic = ref('ai')
const reports = ref([])

const running = ref(false)
const progress = ref(0)
const result = ref(null)
const startedAt = ref(null)
const jobId = ref(null)
const cancelled = ref(false)
let timer = null

const viewer = ref({ show: false, title: '', html: '', loading: false })

onMounted(async () => {
  try {
    meta.value = await getMeta()
    topics.value = meta.value.topics || []
    if (topics.value.length) topic.value = topics.value[0].key
  } catch (e) { /* handled */ }
  loadReports()
})

onBeforeUnmount(() => timer && clearInterval(timer))

async function loadReports() {
  try {
    const res = await listReports()
    reports.value = res.reports || []
  } catch (e) { /* handled */ }
}

const healthReports = computed(() =>
  reports.value
    .filter(r => r.category === 'health_md')
    .filter(r => !topic.value || r.topic === topic.value)
)

function topicLabel(key) {
  const t = topics.value.find(x => x.key === key)
  return t ? t.label : key
}

const batchRows = computed(() => {
  if (!result.value?.batch) return []
  return Object.entries(result.value.results || {}).map(([k, r]) => ({
    key: k,
    label: topicLabel(k),
    ok: !!r.ok,
    summary: r.summary || (r.ok ? '正常' : '异常')
  }))
})

async function startBatch() {
  if (running.value) return
  const list = (topics.value.length ? topics.value : [{ key: 'ai' }]).map(t => t.key)
  running.value = true
  result.value = null
  progress.value = 5
  startedAt.value = new Date().toISOString()
  try {
    const res = await createJob('health', { topics: list })
    const jobId = res.job.id
    timer = setInterval(() => poll(jobId), 2000)
  } catch (e) {
    running.value = false
  }
}

async function start() {
  if (running.value) return
  running.value = true
  result.value = null
  progress.value = 5
  cancelled.value = false
  startedAt.value = new Date().toISOString()
  try {
    const res = await createJob('health', { topic: topic.value })
    jobId.value = res.job.id
    timer = setInterval(() => poll(jobId.value), 2000)
  } catch (e) {
    running.value = false
  }
}

async function poll(jid) {
  try {
    const res = await getJob(jid)
    const job = res.job
    if (job.status === 'running' || job.status === 'queued') {
      progress.value = progress.value >= 90 ? 90 : progress.value + 3
      return
    }
    endPolling()
    progress.value = 100
    if (job.status === 'cancelled') {
      cancelled.value = true
      result.value = null
      return
    }
    result.value = job.result || { ok: false }
    await loadReports()
    const reportName = pathName(result.value.report)
    if (reportName) await openReport(reportName)
  } catch (e) {
    endPolling()
  }
}

function endPolling() {
  clearInterval(timer)
  timer = null
  running.value = false
}

async function stop() {
  if (!jobId.value) return
  try {
    await cancelJob(jobId.value)
  } catch (e) { /* handled */ }
  endPolling()
  cancelled.value = true
  result.value = null
  ElMessage.info('巡检已停止')
}

function clearResult() {
  endPolling()
  result.value = null
  startedAt.value = null
  cancelled.value = false
  progress.value = 0
}

function pathName(p) {
  if (!p) return ''
  return String(p).split(/[\\/]+/).pop() || ''
}

async function openReport(name) {
  viewer.value = { show: true, title: name, html: '', loading: true }
  try {
    const content = await getReportText(name)
    viewer.value.html = marked.parse(content)
  } catch (e) { /* handled */ }
  viewer.value.loading = false
}

const summaryParts = computed(() => {
  if (!result.value?.summary) return []
  return result.value.summary.match(/ok=\d+|recovered=\d+|warn=\d+|error=\d+/g) || []
})

function summarize(result) {
  const map = {}
  for (const part of summaryParts.value) {
    const [k, v] = part.split('=')
    map[k] = v
  }
  return map
}

function underline(tail) {
  return (tail || '').trim() || '巡检未返回输出'
}

function isNoCrawler(tail) {
  return /No crawler service configured/i.test(tail || '')
}

const catColor = (c) => (REPORT_CATEGORIES[c] || {}).color || 'info'
</script>

<template>
  <div>
    <h2 class="page-title">数据源巡检</h2>
    <p class="page-sub">检查配置的数据源抓取状态，识别打不开 / 抓不到 / 内容异常等来源</p>

    <el-alert type="info" :closable="false" style="margin-bottom: 16px">
      <template #title>
        源巡检依赖服务器上部署的<b>抓取服务</b>（本仓库不含爬虫）。若服务器未部署，巡检会给出明确提示；
        此时仍可在「运行分析」结果中查看「基于已分析数据的源健康」。
      </template>
    </el-alert>

    <el-card shadow="never" style="margin-bottom: 16px">
      <div style="display: flex; align-items: center; gap: 16px; flex-wrap: wrap">
        <span style="font-weight: 600">巡检主题</span>
        <el-select v-model="topic" style="width: 240px">
          <el-option v-for="t in topics" :key="t.key" :label="`${t.label}（${t.key}）`" :value="t.key" />
        </el-select>
        <el-button type="primary" :loading="running" @click="start">
          {{ running ? '巡检中…' : '开始巡检' }}
        </el-button>
        <el-button type="success" plain :loading="running" @click="startBatch">批量巡检全部主题</el-button>
        <el-button v-if="running" type="danger" plain @click="stop">停止</el-button>
        <el-button v-if="result || cancelled" text @click="clearResult">清除结果</el-button>
        <span v-if="startedAt" style="color:#909399;font-size:12px">开始于 {{ formatTime(startedAt) }}</span>
      </div>
      <el-progress v-if="running" :percentage="progress" :stroke-width="10" style="margin-top: 14px" />
      <div v-if="!running && cancelled" style="margin-top: 12px">
        <el-alert type="warning" :closable="false" title="巡检已停止" description="已取消该巡检任务。" />
      </div>
    </el-card>

    <template v-if="result">
      <template v-if="result.batch">
        <el-card shadow="never" style="margin-bottom: 16px">
          <template #header><span style="font-weight: 700">批量巡检结果（{{ Object.keys(result.results || {}).length }} 个主题）</span></template>
          <el-table :data="batchRows" size="small">
            <el-table-column label="主题" width="160"><template #default="{ row }">{{ row.label }}</template></el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="row.ok ? 'success' : 'error'" size="small">{{ row.ok ? '正常' : '异常' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="summary" label="汇总" min-width="220"></el-table-column>
          </el-table>
        </el-card>
      </template>
      <template v-else>
      <el-card shadow="never" style="margin-bottom: 16px">
        <template #header>
          <span style="font-weight: 700">巡检结果 · {{ topic }}</span>
        </template>

        <el-alert
          v-if="result.ok"
          type="success"
          :closable="false"
          title="巡检完成，全部来源正常或已恢复"
          description="详细的分源明细见下方报告。"
          style="margin-bottom: 12px"
        />
        <el-alert v-else type="error" :closable="false"
          :title="isNoCrawler(result.output_tail) ? '未部署抓取服务，无法执行源巡检' : '巡检未完成/存在失败来源'" />

        <el-descriptions v-if="summaryParts.length" :column="4" size="small" border style="margin-top: 12px">
          <el-descriptions-item label="正常"><el-tag type="success" size="small">ok = {{ summarize(result).ok || 0 }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="恢复"><el-tag type="primary" size="small">recovered = {{ summarize(result).recovered || 0 }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="警告"><el-tag type="warning" size="small">warn = {{ summarize(result).warn || 0 }}</el-tag></el-descriptions-item>
          <el-descriptions-item label="失败"><el-tag type="danger" size="small">error = {{ summarize(result).error || 0 }}</el-tag></el-descriptions-item>
        </el-descriptions>

        <div v-if="!result.ok" style="margin-top: 12px">
          <pre style="background:#fafafa;padding:12px;border-radius:6px;font-size:12px;white-space:pre-wrap;font-family:monospace;max-height:220px;overflow:auto">{{ underline(result.output_tail) }}</pre>
        </div>
      </el-card>
      </template>
    </template>

    <el-card shadow="never">
      <template #header><span style="font-weight:700">历史巡检报告</span></template>
      <el-table :data="healthReports" size="small">
        <el-table-column prop="name" label="报告名称" min-width="260" show-overflow-tooltip />
        <el-table-column label="主题" width="120">
          <template #default="{ row }">{{ row.topic || '—' }}</template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.modified) }}</template>
        </el-table-column>
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ (row.size / 1024).toFixed(1) }} KB</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" text @click="openReport(row.name)">查看</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="暂无巡检报告" :image-size="80" /></template>
      </el-table>
    </el-card>

    <el-dialog v-model="viewer.show" :title="viewer.title" width="70%" top="5vh">
      <div v-loading="viewer.loading" class="md-body" style="max-height: 70vh; overflow: auto">
        <div v-html="viewer.html"></div>
      </div>
    </el-dialog>
  </div>
</template>