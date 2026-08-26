<script setup>
import { onMounted, onActivated, onBeforeUnmount, ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { marked } from 'marked'
import { ElMessage } from 'element-plus'
import { getMeta, listDataFiles, createJob, getJob, cancelJob, reportUrl, getReportText } from '../api'
import { formatTime, severity } from '../utils/format'
import EChart from '../components/EChart.vue'

defineOptions({ name: 'Analyze' })

const route = useRoute()

const meta = ref(null)
const files = ref([])
const topics = ref([])

const topic = ref('ai')
const date = ref(today())
const useLlm = ref(false)

const dataSource = ref('latest')
const selectedFile = ref('')
const uploaded = ref(null)   // { name, payload, itemCount }
const pasted = ref('')
const pastedError = ref('')

const running = ref(false)
const polling = ref(false)
const progress = ref(0)
const elapsed = ref(0)
const jobIdRef = ref(null)
const currentJob = ref(null)
const result = ref(null)
const errorMsg = ref('')

const reportViewer = ref({ show: false, title: '', html: '', loading: false })

let timer = null

function today() {
  return new Date().toISOString().slice(0, 10)
}

onMounted(async () => {
  try {
    meta.value = await getMeta()
    topics.value = meta.value.topics || []
    if (topics.value.length && !topics.value.some(t => t.key === topic.value)) {
      topic.value = topics.value[0].key
    }
    // LLM 已配置时默认开启润色（周报中文翻译）
    if (meta.value.llm_ready) useLlm.value = true
  } catch (e) { /* handled */ }
  await loadFiles()
})

// 组件被 keep-alive 缓存：切走再切回时保留已填状态；
// 仅当带了 query（数据管理页「用此分析」跳转）才覆盖主题/文件。
onActivated(() => {
  if (route.query.topic) topic.value = route.query.topic
  if (route.query.file) {
    dataSource.value = 'file'
    selectedFile.value = route.query.file
  }
})

onBeforeUnmount(() => timer && clearInterval(timer))

async function loadFiles() {
  try {
    const res = await listDataFiles()
    files.value = res.files || []
    selectedFile.value = ''
  } catch (e) { /* handled */ }
}

const topicFiles = computed(() => files.value.filter(f => f.topic === topic.value))

const bundleOptions = computed(() => {
  const by = {}
  for (const f of files.value) {
    if (!f.bundle) continue
    (by[f.bundle] = by[f.bundle] || []).push(f)
  }
  const arr = Object.entries(by).map(([bundle, fs]) => ({
    bundle,
    files: fs,
    newest: fs[0] && fs[0].modified
  }))
  arr.sort((a, b) => (b.newest || '').localeCompare(a.newest || ''))
  return arr
})

function bundleLabel(b) {
  const t = new Date(b.newest)
  return Number.isNaN(t.getTime()) ? b.bundle : t.toLocaleString('zh-CN', { hour12: false })
}

const selectedBundle = ref('')
const selectedBundleFile = computed(() => {
  const b = bundleOptions.value.find(x => x.bundle === selectedBundle.value)
  return b && b.files.length ? b.files[0].name : ''
})

const llmReady = computed(() => !!meta.value?.llm_ready)

function topicName(key) {
  const t = topics.value.find(x => x.key === key)
  return t ? t.label : key
}

function openUrl(url) {
  window.open(url, '_blank')
}

async function submitBatch(sharedDataFile) {
  if (running.value) return
  const list = (topics.value.length ? topics.value : [{ key: 'ai' }]).map(t => t.key)
  result.value = null
  errorMsg.value = ''
  running.value = true
  polling.value = true
  progress.value = 5
  elapsed.value = 0
  try {
    const payload = {
      topics: list,
      use_llm: useLlm.value,
      date: date.value || today()
    }
    // 指定了捆绑包/共享数据文件时，整批共用同一份数据。
    if (sharedDataFile) payload.data_file = sharedDataFile
    const res = await createJob('analyze', payload)
    const jobId = res.job.id
    currentJob.value = res.job
    timer = setInterval(() => poll(jobId), 2000)
  } catch (e) {
    running.value = false
    polling.value = false
  }
}

async function startBatch() {
  // 「选择文件」模式下，批量共用该文件；否则用各主题最新。
  const file = dataSource.value === 'file' ? selectedFile.value : ''
  await submitBatch(file || undefined)
}

function onFileChange(file, fileList) {
  const reader = new FileReader()
  reader.onload = () => {
    try {
      const payload = JSON.parse(reader.result)
      uploaded.value = {
        name: file.name,
        payload,
        itemCount: Array.isArray(payload.news) ? payload.news.length : 0
      }
      ElMessage.success(`已解析 ${file.name}，共 ${uploaded.value.itemCount} 条`)
    } catch (e) {
      uploaded.value = null
      ElMessage.error('JSON 解析失败，请检查文件内容')
    }
  }
  reader.readAsText(file.raw)
  fileList.length = 0
}

function validatePasted() {
  if (dataSource.value !== 'paste') return null
  try {
    const payload = JSON.parse(pasted.value)
    uploaded.value = { name: '粘贴数据', payload, itemCount: Array.isArray(payload.news) ? payload.news.length : 0 }
    pastedError.value = ''
    return payload
  } catch (e) {
    pastedError.value = 'JSON 解析失败：' + e.message
    return null
  }
}

async function start() {
  if (running.value) return
  // 选了「数据捆绑包」→ 自动走批量分析（全部主题共用该批次数据）。
  if (dataSource.value === 'bundle') {
    if (!selectedBundle.value) { ElMessage.warning('请先选择数据批次'); return }
    if (!selectedBundleFile.value) { ElMessage.warning('该批次暂无可用数据文件'); return }
    await submitBatch(selectedBundleFile.value)
    return
  }
  const payload = {
    topic: topic.value,
    use_llm: useLlm.value,
    date: date.value || today()
  }
  if (dataSource.value === 'file') {
    if (!selectedFile.value) { ElMessage.warning('请选择数据文件'); return }
    payload.data_file = selectedFile.value
  } else if (dataSource.value === 'upload' || dataSource.value === 'paste') {
    if (dataSource.value === 'paste') {
      const ok = validatePasted()
      if (!ok) return
    }
    if (!uploaded.value) { ElMessage.warning('请先上传或粘贴数据'); return }
    payload.data = uploaded.value.payload
  }
  // dataSource === 'latest'（默认）: 不传 data/data_file，使用主题目录最新文件

  result.value = null
  errorMsg.value = ''
  running.value = true
  polling.value = true
  progress.value = 5
  elapsed.value = 0
  try {
    const res = await createJob('analyze', payload)
    jobIdRef.value = res.job.id
    currentJob.value = res.job
    timer = setInterval(() => poll(jobIdRef.value), 2000)
  } catch (e) {
    running.value = false
    polling.value = false
  }
}

async function poll(jobId) {
  try {
    const res = await getJob(jobId)
    const job = res.job
    currentJob.value = job
    if (job.status === 'running' || job.status === 'queued') {
      progress.value = progress.value >= 90 ? 90 : progress.value + 3
      elapsed.value += 2
      return
    }
    clearInterval(timer)
    timer = null
    running.value = false
    polling.value = false
    if (job.status === 'success') {
      progress.value = 100
      result.value = job.result
    } else {
      errorMsg.value = job.error || '未知错误'
    }
  } catch (e) {
    clearInterval(timer)
    timer = null
    running.value = false
    polling.value = false
  }
}

async function stop() {
  if (!jobIdRef.value) return
  try {
    await cancelJob(jobIdRef.value)
  } catch (e) { /* handled */ }
  if (timer) { clearInterval(timer); timer = null }
  running.value = false
  polling.value = false
  ElMessage.info('分析已停止')
}

function clearAll() {
  if (timer) { clearInterval(timer); timer = null }
  running.value = false
  polling.value = false
  result.value = null
  errorMsg.value = ''
  progress.value = 0
  elapsed.value = 0
  uploaded.value = null
  pasted.value = ''
  pastedError.value = ''
  selectedFile.value = ''
  dataSource.value = 'latest'
}

const boardOption = computed(() => {
  const rows = result.value?.board_breakdown || []
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 4, right: 30, top: 10, bottom: 10, containLabel: true },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category', inverse: true, data: rows.map(r => r.parent_board) },
    series: [{
      type: 'bar',
      data: rows.map(r => r.count),
      itemStyle: { color: '#409eff', borderRadius: [0, 4, 4, 0] },
      label: { show: true, position: 'right' },
      barMaxWidth: 26
    }]
  }
})

const sourceHealth = computed(() => result.value?.source_health || {})
const reportName = computed(() => result.value?.report_name || '')
const reportPdfName = computed(() => result.value?.report_pdf_name || '')
const briefName = computed(() => result.value?.brief_name || '')

async function viewReport(name) {
  reportViewer.value = { show: true, title: name, html: '', loading: true }
  try {
    const content = await getReportText(name)
    reportViewer.value.html = marked.parse(content)
  } catch (e) { /* handled */ }
  reportViewer.value.loading = false
}

function openPdf() {
  if (reportPdfName.value) window.open(reportUrl(reportPdfName.value), '_blank')
}

function openBrief() {
  window.open(reportUrl(briefName.value), '_blank')
}

function openRaw() {
  window.open(reportUrl(reportName.value), '_blank')
}
</script>

<template>
  <div>
    <h2 class="page-title">运行分析</h2>
    <p class="page-sub">选择主题与数据，运行完整分析管线并生成报告</p>

    <el-card shadow="never" style="margin-bottom: 16px">
      <el-form label-width="110px" label-position="left">
        <el-form-item label="分析主题">
          <el-select v-model="topic" style="width: 280px" @change="selectedFile=''">
            <el-option v-for="t in topics" :key="t.key" :label="`${t.label}（${t.key}）`" :value="t.key" />
          </el-select>
        </el-form-item>

        <el-form-item label="报告日期">
          <el-date-picker v-model="date" type="date" value-format="YYYY-MM-DD"
            :clearable="false" style="width: 200px" />
          <span style="color:#909399;margin-left:12px;font-size:13px">报告周期 = 该日期往前 7 天</span>
        </el-form-item>

        <el-form-item label="LLM 润色">
          <el-switch v-model="useLlm" />
          <el-tag v-if="useLlm && !llmReady" type="warning" size="small" style="margin-left: 12px">
            未检测到 LLM 配置，将自动回退为基础模式
          </el-tag>
        </el-form-item>

        <el-form-item label="数据来源">
          <el-radio-group v-model="dataSource">
            <el-radio value="latest">最新数据文件</el-radio>
            <el-radio value="file">选择文件</el-radio>
            <el-radio value="bundle">数据捆绑包（批量分析）</el-radio>
            <el-radio value="upload">上传文件</el-radio>
            <el-radio value="paste">粘贴 JSON</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="dataSource === 'file'" label="数据文件">
          <el-select v-model="selectedFile" placeholder="选择该主题下的数据文件" style="width: 420px" filterable>
            <el-option v-for="f in topicFiles" :key="f.name" :value="f.name"
              :label="`${f.name}（${f.item_count} 条）`" />
          </el-select>
          <el-button text type="primary" @click="loadFiles" style="margin-left: 8px">刷新</el-button>
        </el-form-item>

        <el-form-item v-if="dataSource === 'bundle'" label="数据批次">
          <el-select v-model="selectedBundle" placeholder="选择数据批次（将按全部主题批量分析）" style="width: 460px" filterable>
            <el-option v-for="b in bundleOptions" :key="b.bundle" :value="b.bundle"
              :label="`${bundleLabel(b)}（${b.files.length} 个文件）`" />
          </el-select>
          <el-button text type="primary" @click="loadFiles" style="margin-left: 8px">刷新</el-button>
        </el-form-item>

        <el-form-item v-if="dataSource === 'upload'" label="上传数据">
          <el-upload :auto-upload="false" :show-file-list="false" :on-change="onFileChange" accept=".json">
            <el-button type="primary" plain>选择 JSON 文件</el-button>
          </el-upload>
          <el-tag v-if="uploaded" type="success" size="small" style="margin-left: 12px">
            {{ uploaded.name }} · {{ uploaded.itemCount }} 条，待提交
          </el-tag>
        </el-form-item>

        <el-form-item v-if="dataSource === 'paste'" label="粘贴 JSON">
          <el-input type="textarea" v-model="pasted" :rows="6" placeholder='{"news":[...],"sources":[...]}' />
          <div v-if="pastedError" style="color:#f56c6c;font-size:12px;margin-top:4px">{{ pastedError }}</div>
          <el-tag v-if="uploaded && !pastedError" type="success" size="small" style="margin-left: 12px; margin-top: 8px">
            {{ uploaded.itemCount }} 条，待提交
          </el-tag>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" size="large" :loading="running" @click="start">
            {{ running ? '分析中…' : '开始分析' }}
          </el-button>
          <el-button size="large" :loading="running" @click="startBatch" style="margin-left: 12px">
            批量分析全部主题
          </el-button>
          <el-button v-if="running || polling" type="danger" size="large" plain @click="stop">停止</el-button>
          <el-button v-if="result || errorMsg" size="large" text @click="clearAll">清除结果</el-button>
        </el-form-item>
      </el-form>

      <el-progress v-if="polling" :percentage="progress" :stroke-width="10" style="margin: 4px 0 4px" />
      <div v-if="polling" style="color:#909399;font-size:12px;margin:0 0 8px">
        分析进行中，已运行 {{ elapsed }} 秒（数据量越大、开启 LLM 润色时耗时越长，请勿关闭页面）
      </div>
    </el-card>

    <el-alert v-if="errorMsg" type="error" :title="errorMsg" :closable="false" style="margin-bottom: 16px" />

    <template v-if="result">
      <template v-if="result.batch">
        <el-card shadow="never" style="margin-bottom: 16px">
          <template #header><span style="font-weight: 700">批量分析结果（{{ Object.keys(result.results || {}).length }} 个主题）</span></template>
          <el-row :gutter="16">
            <el-col v-for="(r, t) in result.results" :key="t" :xs="24" :md="8" style="margin-bottom: 12px">
              <div class="panel" style="box-shadow:none;border:1px solid #f0f0f0">
                <div style="font-weight: 700; margin-bottom: 8px">{{ topicName(t) }}</div>
                <el-descriptions :column="2" size="small" border>
                  <el-descriptions-item label="过滤后输入">{{ r.summary?.input_count }}</el-descriptions-item>
                  <el-descriptions-item label="事件簇">{{ r.summary?.cluster_count }}</el-descriptions-item>
                  <el-descriptions-item label="板块分组">{{ r.summary?.board_count }}</el-descriptions-item>
                  <el-descriptions-item label="生成时间">{{ formatTime(r.generated_at) }}</el-descriptions-item>
                </el-descriptions>
                <div style="margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap">
                  <el-tag v-if="r.report_name" type="primary" size="large" class="link-btn" @click="viewReport(r.report_name)">Markdown</el-tag>
                  <el-tag v-if="r.report_pdf_name" type="success" size="large" class="link-btn" @click="openUrl(reportUrl(r.report_pdf_name))">PDF</el-tag>
                  <el-tag v-if="r.brief_name" type="warning" size="large" class="link-btn" @click="openUrl(reportUrl(r.brief_name))">简报</el-tag>
                </div>
              </div>
            </el-col>
          </el-row>
        </el-card>
      </template>
      <template v-else>
      <el-card shadow="never" style="margin-bottom: 16px">
        <template #header>
          <div style="display: flex; justify-content: space-between; align-items: center">
            <span style="font-weight: 700">分析结果</span>
            <span style="color:#909399;font-size:12px">生成于 {{ formatTime(result.generated_at) }}</span>
          </div>
        </template>

        <el-row :gutter="16">
          <el-col :xs="12" :sm="6">
            <div class="stat-card"><div>
              <div class="stat-value">{{ result.summary.input_count }}</div>
              <div class="stat-label">过滤后输入</div>
            </div></div>
          </el-col>
          <el-col :xs="12" :sm="6">
            <div class="stat-card"><div>
              <div class="stat-value">{{ result.summary.unique_count }}</div>
              <div class="stat-label">去重后保留</div>
            </div></div>
          </el-col>
          <el-col :xs="12" :sm="6">
            <div class="stat-card"><div>
              <div class="stat-value">{{ result.summary.cluster_count }}</div>
              <div class="stat-label">事件簇</div>
            </div></div>
          </el-col>
          <el-col :xs="12" :sm="6">
            <div class="stat-card"><div>
              <div class="stat-value">{{ result.summary.board_count }}</div>
              <div class="stat-label">板块分组</div>
            </div></div>
          </el-col>
        </el-row>

        <el-descriptions :column="3" size="small" border style="margin-top: 16px">
          <el-descriptions-item label="报告周期">
            {{ result.period?.start_date }} ~ {{ result.period?.end_date }}
          </el-descriptions-item>
          <el-descriptions-item label="重复剔除">{{ result.summary.duplicate_count }}</el-descriptions-item>
          <el-descriptions-item label="商情标注">
            高{{ result.business_relevance?.high || 0 }} / 中{{ result.business_relevance?.medium || 0 }} /
            低{{ result.business_relevance?.low || 0 }}
          </el-descriptions-item>
        </el-descriptions>

        <div style="margin-top: 14px; display: flex; gap: 10px; flex-wrap: wrap">
          <el-tag v-if="reportPdfName" type="success" size="large" class="link-btn" @click="openPdf()">查看 PDF 报告</el-tag>
          <el-tag v-if="reportName" type="primary" size="large" class="link-btn" @click="viewReport(reportName)">查看 Markdown</el-tag>
          <el-tag v-if="briefName" type="warning" size="large" class="link-btn" @click="openBrief()">打开 HTML 简报</el-tag>
          <el-tag v-if="reportName" size="large" class="link-btn" @click="openRaw">下载源文件</el-tag>
        </div>
      </el-card>

      <el-row :gutter="16">
        <el-col :xs="24" :md="14">
          <el-card shadow="never">
            <template #header><span style="font-weight:700">TOP 事件</span></template>
            <div v-if="result.top_events.length">
              <div v-for="(e, i) in result.top_events" :key="i" class="panel" style="margin-bottom: 10px; box-shadow:none">
                <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
                  <span style="font-weight:700;color:#409eff">#{{ i + 1 }}</span>
                  <el-tag :type="severity(e.score).type" size="small">{{ severity(e.score).label }}</el-tag>
                  <el-tag size="small" effect="plain">{{ e.score }}</el-tag>
                  <el-tag v-if="e.board" size="small" type="info" effect="plain">{{ e.board }}</el-tag>
                </div>
                <div style="font-weight:600;margin:8px 0 4px">{{ e.title }}</div>
                <div style="color:#909399;font-size:12px">
                  {{ e.count }} 条报道 · 来源：{{ e.sources.join('、') || '—' }}
                </div>
              </div>
            </div>
            <el-empty v-else description="本周期无匹配事件" :image-size="80" />
          </el-card>
        </el-col>
        <el-col :xs="24" :md="10">
          <el-card shadow="never">
            <template #header><span style="font-weight:700">板块分布</span></template>
            <EChart v-if="result.board_breakdown.length" :option="boardOption" />
            <el-empty v-else description="无板块数据" :image-size="60" />
          </el-card>

          <el-card shadow="never" style="margin-top: 16px">
            <template #header><span style="font-weight:700">数据源健康</span></template>
            <el-descriptions :column="3" size="small" border>
              <el-descriptions-item label="活跃源">
                <el-tag type="success" size="small">{{ sourceHealth.active?.length || 0 }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="缺失源">
                <el-tag type="danger" size="small">{{ sourceHealth.missing?.length || 0 }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="贡献源">
                <el-tag type="info" size="small">{{ sourceHealth.zero?.length || 0 }}</el-tag>
              </el-descriptions-item>
            </el-descriptions>
            <template v-if="sourceHealth.missing?.length">
              <div style="margin-top:10px;font-size:12px;color:#c0c4cc">
                未捕获报道的配置源：{{ sourceHealth.missing.map(m => m.name).join('、') }}
              </div>
            </template>
          </el-card>
        </el-col>
      </el-row>
      </template>
    </template>

    <el-dialog v-model="reportViewer.show" :title="reportViewer.title" width="70%" top="5vh">
      <div v-loading="reportViewer.loading" class="md-body" style="max-height: 70vh; overflow: auto">
        <div v-html="reportViewer.html"></div>
      </div>
    </el-dialog>
  </div>
</template>