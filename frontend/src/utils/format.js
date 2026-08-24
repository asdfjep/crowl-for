export function formatSize(bytes) {
  if (bytes == null) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(2) + ' MB'
}

export function formatTime(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', { hour12: false })
}

export const REPORT_CATEGORIES = {
  weekly_md: { label: '周报 · Markdown', color: 'blue' },
  weekly_pdf: { label: '周报 · PDF', color: 'danger' },
  daily_md: { label: '日报 · Markdown', color: 'cyan' },
  daily_pdf: { label: '日报 · PDF', color: 'danger' },
  brief_html: { label: 'HTML 简报', color: 'success' },
  health_md: { label: '巡检 · Markdown', color: 'warning' },
  health_json: { label: '巡检 · JSON', color: 'info' }
}

export function severity(score) {
  if (score >= 80) return { label: '极重大', type: 'danger' }
  if (score >= 60) return { label: '重大', type: 'warning' }
  if (score >= 40) return { label: '重要', type: 'primary' }
  return { label: '一般', type: 'info' }
}

export const TOPIC_KEYS = {
  ai: '人工智能',
  commercial_space: '商业航天',
  display_polarizer: '偏光板与显示'
}