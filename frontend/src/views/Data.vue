<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  getMeta, listDataFiles, getDataFile, uploadDataFile, analyzeDirect
} from '../api'
import { formatSize, formatTime, severity } from '../utils/format'

const router = useRouter()
const topics = ref([])
const files = ref([])
const loading = ref(false)

const uploadTopic = ref('ai')
const uploads = ref({ name: '', payload: null, itemCount: 0 })

const apiText = ref('')
const apiRunning = ref(false)
const apiResult = ref(null)
const apiError = ref('')

const viewer = ref({ show: false, title: '', data: null, loading: false })

onMounted(async () => {
  try {
    const meta = await getMeta()
    topics.value = meta.topics || []
    if (topics.value.length) uploadTopic.value = topics.value[0].key
  } catch (e) { /* handled */ }
  await load()
})

async function load() {
  loading.value = true
  try {
    const res = await listDataFiles()
    files.value = res.files || []
  } catch (e) { /* handled */ }
  loading.value = false
}

function onFileChange(file, fileList) {
  const reader = new FileReader()
  reader.onload = () => {
    try {
      const payload = JSON.parse(reader.result)
      if (!Array.isArray(payload.news)) throw new Error('news 字段必须是数组')
      uploads.value = { name: file.name, payload, itemCount: payload.news.length }
      ElMessage.success(`已解析 ${file.name}，共 ${payload.news.length} 条`)
    } catch (e) {
      uploads.value = { name: '', payload: null, itemCount: 0 }
      ElMessage.error('JSON 解析失败：' + e.message)
    }
  }
  reader.readAsText(file.raw)
  fileList.length = 0
}

async function doUpload() {
  if (!uploads.value.payload) { ElMessage.warning('请先选择 JSON 文件'); return }
  apiRunning.value = true
  try {
    const res = await uploadDataFile(uploadTopic.value, uploads.value.payload)
    ElMessage.success(`已保存到 ${res.topic}：${res.name}（${res.item_count} 条）`)
    uploads.value = { name: '', payload: null, itemCount: 0 }
    await load()
  } catch (e) { /* handled */ }
  apiRunning.value = false
}

async function viewFile(row) {
  viewer.value = { show: true, title: row.name, data: null, loading: true }
  try {
    const info = await getDataFile(row.name)
    viewer.value.data = info
  } catch (e) { /* handled */ }
  viewer.value.loading = false
}

function goAnalyze(row) {
  router.push({ path: '/analyze', query: { topic: row.topic, file: row.name } })
}

async function runApiTest() {
  apiError.value = ''
  apiResult.value = null
  let payload
  try {
    payload = JSON.parse(apiText.value)
    if (!Array.isArray(payload.news)) throw new Error('news 字段必须是数组')
  } catch (e) {
    apiError.value = 'JSON 解析失败：' + e.message
    return
  }
  apiRunning.value = true
  try {
    apiResult.value = await analyzeDirect(payload)
  } catch (e) { /* handled */ }
  apiRunning.value = false
}
</script>

<template>
  <div>
    <h2 class="page-title">数据管理</h2>
    <p class="page-sub">浏览、上传历史抓取数据，并可直接调用 /api/analyze 做接口测试</p>

    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-weight:700">数据文件</span>
          <el-button size="small" :loading="loading" @click="load">刷新</el-button>
        </div>
      </template>
      <el-table v-loading="loading" :data="files" size="small">
        <el-table-column label="主题" width="150">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.topic }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="文件" min-width="240" show-overflow-tooltip />
        <el-table-column label="条数" width="90">
          <template #default="{ row }">{{ row.item_count >= 0 ? row.item_count : '?' }}</template>
        </el-table-column>
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ formatSize(row.size) }}</template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.modified) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="viewFile(row)">查看</el-button>
            <el-button size="small" text @click="goAnalyze(row)">用此分析</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="暂无数据文件，可在下方上传" :image-size="80" /></template>
      </el-table>
    </el-card>

    <el-row :gutter="16">
      <el-col :xs="24" :md="12">
        <el-card shadow="never" style="margin-bottom: 16px">
          <template #header><span style="font-weight:700">上传数据</span></template>
          <el-form label-width="80px" label-position="left">
            <el-form-item label="主题">
              <el-select v-model="uploadTopic" style="width: 200px">
                <el-option v-for="t in topics" :key="t.key" :label="t.label" :value="t.key" />
              </el-select>
            </el-form-item>
            <el-form-item label="JSON 文件">
              <el-upload :auto-upload="false" :show-file-list="false" :on-change="onFileChange" accept=".json">
                <el-button type="primary" plain>选择文件</el-button>
              </el-upload>
            </el-form-item>
            <el-form-item>
              <el-tag v-if="uploads.payload" type="success" size="small">{{ uploads.name }} · {{ uploads.itemCount }} 条</el-tag>
              <span v-else style="color:#c0c4cc;font-size:12px">文件格式：{"news":[...],"sources":[...],"crawlTime":"..."}</span>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="apiRunning" :disabled="!uploads.payload" @click="doUpload">保存到主题数据目录</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="12">
        <el-card shadow="never" style="margin-bottom: 16px">
          <template #header><span style="font-weight:700">API 测试（POST /api/analyze）</span></template>
          <el-input type="textarea" v-model="apiText" :rows="7"
            placeholder='{"news":[{"title":"...","source":"...","publishTime":"2026-08-24T08:00:00","url":"http://..."}],"sources":["..."]}' />
          <div v-if="apiError" style="color:#f56c6c;font-size:12px;margin-top:4px">{{ apiError }}</div>
          <el-button type="primary" style="margin-top: 10px" :loading="apiRunning" @click="runApiTest">
            调用分析接口
          </el-button>

          <template v-if="apiResult">
            <el-divider content-position="left" style="font-size:13px;color:#909399">接口响应</el-divider>
            <el-descriptions :column="3" size="small" border>
              <el-descriptions-item label="成功">
                <el-tag :type="apiResult.success ? 'success' : 'danger'" size="small">{{ apiResult.success }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="去重后">{{ apiResult.summary?.unique_count }}</el-descriptions-item>
              <el-descriptions-item label="事件簇">{{ apiResult.summary?.cluster_count }}</el-descriptions-item>
            </el-descriptions>
            <div v-if="apiResult.top_events?.length" style="margin-top: 10px">
              <div v-for="(e, i) in apiResult.top_events.slice(0, 5)" :key="i" style="display:flex;gap:8px;align-items:center;padding:6px 0;border-bottom:1px solid #f5f5f5">
                <el-tag :type="severity(e.score).type" size="small">{{ e.score }}</el-tag>
                <span style="font-size:13px">{{ e.title }}</span>
              </div>
            </div>
            <div v-else style="color:#c0c4cc;font-size:13px;margin-top:10px">无匹配事件</div>
          </template>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="viewer.show" :title="viewer.title" width="60%" top="5vh">
      <div v-loading="viewer.loading">
        <template v-if="viewer.data">
          <el-descriptions :column="3" size="small" border>
            <el-descriptions-item label="抓取时间">{{ viewer.data.crawlTime || '—' }}</el-descriptions-item>
            <el-descriptions-item label="新闻条数">{{ viewer.data.item_count }}</el-descriptions-item>
            <el-descriptions-item label="数据源数">{{ viewer.data.sources?.length || 0 }}</el-descriptions-item>
          </el-descriptions>
          <el-table :data="viewer.data.preview" size="small" style="margin-top: 12px">
            <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
            <el-table-column prop="source" label="来源" width="140" />
            <el-table-column prop="publishTime" label="发布时间" width="170" />
          </el-table>
          <div style="color:#c0c4cc;font-size:12px;margin-top:8px">仅预览前 {{ viewer.data.preview?.length || 0 }} 条</div>
        </template>
      </div>
    </el-dialog>
  </div>
</template>