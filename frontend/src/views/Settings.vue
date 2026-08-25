<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getMeta, getHealth, getLlmConfig, saveLlmConfig, testLlmConfig } from '../api'
import { formatTime } from '../utils/format'

const meta = ref(null)
const health = ref(null)
const loadedAt = ref(null)

const llm = ref({
  base_url: '',
  model: '',
  api_key: '',
  api_key_set: false,
  api_key_masked: '',
  timeout: 60,
  configured: false
})
const llmSaving = ref(false)
const llmTesting = ref(false)
const testResult = ref(null)

onMounted(async () => {
  try {
    meta.value = await getMeta()
  } catch (e) { /* handled */ }
  try {
    health.value = await getHealth()
    loadedAt.value = new Date().toISOString()
  } catch (e) { /* handled */ }
  loadLlm()
})

async function loadLlm() {
  try {
    const cfg = await getLlmConfig()
    llm.value = {
      ...cfg,
      api_key: '' // 不回显明文 key，留空表示沿用
    }
  } catch (e) { /* handled */ }
}

async function saveLlm() {
  llmSaving.value = true
  try {
    const res = await saveLlmConfig({
      base_url: llm.value.base_url || null,
      model: llm.value.model || null,
      api_key: llm.value.api_key || null,
      timeout: Number(llm.value.timeout) || 60
    })
    ElMessage.success(`LLM 配置已保存（${res.api_key_masked}）`)
    testResult.value = null
    await loadLlm()
    meta.value = await getMeta() // 刷新 llm_ready 状态
  } catch (e) { /* handled */ }
  llmSaving.value = false
}

async function testLlm() {
  llmTesting.value = true
  testResult.value = null
  try {
    const res = await testLlmConfig({
      base_url: llm.value.base_url || null,
      model: llm.value.model || null,
      api_key: llm.value.api_key || null,
      timeout: Number(llm.value.timeout) || 60
    })
    testResult.value = res
    if (res.ok) {
      ElMessage.success(`连接成功：${res.reply}`)
    } else {
      ElMessage.error(`连接失败：${res.error}`)
    }
  } catch (e) { /* handled */ }
  llmTesting.value = false
}
</script>

<template>
  <div>
    <h2 class="page-title">系统设置</h2>
    <p class="page-sub">服务信息、LLM 配置与各主题板块结构</p>

    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header>
        <span style="font-weight:700">LLM 配置</span>
        <el-tag :type="meta?.llm_ready ? 'success' : 'info'" size="small" style="margin-left: 8px">
          {{ meta?.llm_ready ? '已配置' : '未配置' }}
        </el-tag>
      </template>
      <el-alert type="info" :closable="false" style="margin-bottom: 14px">
        所有 LLM 需求（周报中文润色 / 标题翻译）统一走这里的配置。保存后立即生效，持久化在数据目录中。
      </el-alert>
      <el-form label-width="110px" label-position="left" style="max-width: 720px">
        <el-form-item label="API Base URL">
          <el-input v-model="llm.base_url" placeholder="https://api.openai.com/v1 或你的中转地址" />
        </el-form-item>
        <el-form-item label="Model">
          <el-input v-model="llm.model" placeholder="gpt-4o-mini / deepseek-v4-flash" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input
            v-model="llm.api_key"
            type="password"
            show-password
            :placeholder="llm.api_key_set ? `已设置（${llm.api_key_masked}），留空保持不变` : '请输入 API Key'"
          />
        </el-form-item>
        <el-form-item label="超时（秒）">
          <el-input-number v-model="llm.timeout" :min="10" :max="300" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="llmSaving" @click="saveLlm">保存</el-button>
          <el-button :loading="llmTesting" @click="testLlm">{{ llmTesting ? '测试中…' : '测试连接' }}</el-button>
        </el-form-item>
      </el-form>
      <el-alert
        v-if="testResult"
        :type="testResult.ok ? 'success' : 'error'"
        :title="testResult.ok ? `连接成功，模型回复：${testResult.reply}` : `连接失败：${testResult.error}`"
        :closable="false"
      />
    </el-card>

    <el-row :gutter="16">
      <el-col :xs="24" :md="12">
        <el-card shadow="never">
          <template #header><span style="font-weight:700">服务信息</span></template>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="服务">{{ meta?.service }} v{{ meta?.version }}</el-descriptions-item>
            <el-descriptions-item label="运行状态">
              <el-tag v-if="health" type="success" size="small">正常（{{ health.status }}）</el-tag>
              <el-tag v-else type="danger" size="small">离线</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="Python">{{ meta?.python }}</el-descriptions-item>
            <el-descriptions-item label="数据目录">{{ meta?.data_dir }}</el-descriptions-item>
            <el-descriptions-item label="报告目录">{{ meta?.report_dir }}</el-descriptions-item>
            <el-descriptions-item label="LLM 配置">
              <el-tag :type="meta?.llm_ready ? 'success' : 'info'" size="small">
                {{ meta?.llm_ready ? '已配置' : '未配置（基础模式）' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="最近探活">{{ loadedAt ? formatTime(loadedAt) : '—' }}</el-descriptions-item>
          </el-descriptions>
        </el-card>

        <el-card shadow="never" style="margin-top: 16px">
          <template #header><span style="font-weight:700">使用说明</span></template>
          <ul style="line-height:1.8;color:#606266;font-size:13px;padding-left:18px;margin:0">
            <li>运行一次分析会依次执行：日期过滤 → 主题过滤 → 去重 → 事件聚类 → 评分 → 板块分类 → 商情标注 → 源健康 → 趋势检测 → 报告生成。</li>
            <li>报告同时输出 Markdown 与 PDF；可选输出 HTML 简报（生产环境已默认开启）。</li>
            <li>「数据源巡检」在「系统设置 → LLM 配置」无关；未部署抓取服务时会提示原因。</li>
          </ul>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="12">
        <el-card shadow="never">
          <template #header><span style="font-weight:700">主题与板块</span></template>
          <template v-for="t in meta?.topics || []" :key="t.key">
            <el-divider content-position="left" style="font-size:13px;color:#409eff;margin:8px 0">
              {{ t.label }}（{{ t.key }}） · {{ t.source_count }} 个数据源
            </el-divider>
            <div style="display:flex;flex-wrap:wrap;gap:8px;padding:0 0 12px">
              <el-tag v-for="b in t.board_order || []" :key="typeof b === 'string' ? b : b.name" size="small" effect="plain">
                {{ typeof b === 'string' ? b : b.name }}
              </el-tag>
            </div>
          </template>
          <el-empty v-if="!meta?.topics?.length" description="未读取到主题配置" :image-size="80" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>