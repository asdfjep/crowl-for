import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({ baseURL: '/api', timeout: 120000 })

http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const detail = err?.response?.data?.detail
    const msg =
      typeof detail === 'string' && detail !== 'Internal Server Error'
        ? detail
        : err.message || '请求失败'
    ElMessage.error(msg.length > 200 ? msg.slice(0, 200) + '…' : msg)
    return Promise.reject(err)
  }
)

export function getMeta() {
  return http.get('/meta')
}

export function getHealth() {
  return http.get('/health')
}

export function listReports() {
  return http.get('/reports')
}

export async function getReportText(name) {
  const data = await http.get(`/reports/${encodeURIComponent(name)}`)
  return data.content || ''
}

export function reportUrl(name) {
  return `/api/reports/${encodeURIComponent(name)}`
}

export function listDataFiles() {
  return http.get('/data-files')
}

export function getDataFile(name) {
  return http.get(`/data-files/${encodeURIComponent(name)}`)
}

export function uploadDataFile(topic, payload) {
  return http.post('/data-files', { topic, payload })
}

export function createJob(kind, payload) {
  return http.post('/jobs', { kind, payload })
}

export function listJobs() {
  return http.get('/jobs')
}

export function getJob(jobId) {
  return http.get(`/jobs/${jobId}`)
}

export function analyzeDirect(payload) {
  return http.post('/analyze', payload)
}

export function downloadText(name, content) {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export default http