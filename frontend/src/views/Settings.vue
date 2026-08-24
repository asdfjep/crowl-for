<script setup>
import { onMounted, ref } from 'vue'
import { getMeta, getHealth } from '../api'
import { formatTime } from '../utils/format'

const meta = ref(null)
const health = ref(null)
const loadedAt = ref(null)

onMounted(async () => {
  try {
    meta.value = await getMeta()
  } catch (e) { /* handled */ }
  try {
    health.value = await getHealth()
    loadedAt.value = new Date().toISOString()
  } catch (e) { /* handled */ }
})
</script>

<template>
  <div>
    <h2 class="page-title">系统设置</h2>
    <p class="page-sub">查看服务信息、LLM 配置状态与各主题板块结构</p>

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
                {{ meta?.llm_ready ? '已就绪' : '未配置（基础模式）' }}
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
            <li>「数据源巡检」需要在服务器上部署抓取服务；未部署时会提示原因。</li>
            <li>如需 LLM 润色，在项目根目录放置 <code>llm_config.local.json</code> 并配置 api_key / base_url / model。</li>
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