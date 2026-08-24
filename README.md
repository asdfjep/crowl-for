<div align="center">

# AI News Analyzer

统一新闻分析服务 + Vue 3 Web 管理前端

去重 · 事件聚类 · 重要性评分 · A1-A8 板块分类 · 周报 / PDF / HTML 简报生成

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)]()
[![Vue](https://img.shields.io/badge/Vue-3.4-42b883?logo=vuedotjs&logoColor=white)]()
[![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)]()

</div>

独立的新闻分析服务，与抓取模块完全解耦。分析结果既有 **命令行** 入口，也有内置的 **Web 管理前端**（Vue 3 + Element Plus + ECharts），可直接在页面上运行分析、查看报告、上传数据、执行源巡检。

## 快速开始（Docker）

```bash
git clone https://github.com/asdfjep/crowl-for.git
cd crowl-for
docker compose up -d --build
# 打开 http://<服务器>:8011
```

## 功能

- 三级去重（URL / 标题精确 / 标题相似度）
- 事件聚类（关键词重叠 + 24h 时间窗口）
- 重大新闻评分（0-100 分，多维度加权）
- A1-A8 细分板块分类（三个主题各自可配置）
- 综合报告生成（Markdown + PDF + HTML 简报）
- 可选 LLM 润色（需配置 `llm_config.local.json`）
- 支持主题：`ai` 人工智能 / `commercial_space` 商业航天 / `display_polarizer` 偏光板与显示

## 分析管线

```text
读取新闻数据
  -> 日期过滤（报告周期前 7 天）
  -> 主题关键词过滤
  -> 三级去重
  -> 事件聚类
  -> 重要性评分（0-100）
  -> A1-A8 板块分类
  -> 商情标注 / 数据源健康 / 趋势检测
  -> 生成 Markdown / PDF / HTML 简报
```

## Web 管理前端

Docker 启动后访问 `http://<服务器>:8011`：

| 页面 | 功能 |
|---|---|
| 仪表盘 | 服务状态、报告统计、最近报告、主题概览 |
| 报告中心 | 分类浏览 / 查看 / 下载已生成的 md、pdf、html 简报、巡检报告 |
| 运行分析 | 选择主题与数据（最新 / 选择文件 / 上传 / 粘贴 JSON），运行分析并展示事件 & 板块分布 |
| 数据源巡检 | 针对配置的抓取服务做源巡检（需服务器部署爬虫服务） |
| 数据管理 | 浏览/上传新闻数据、调用 `POST /api/analyze` 做接口测试 |
| 系统设置 | 服务信息、LLM 配置状态、各主题板块结构 |

## 本地开发

后端：

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows；Linux 用 .venv/bin/pip
# 或用系统 python: pip install -r requirements.txt
python server.py        # 监听 0.0.0.0:8011
```

前端（热更新，`/api` 代理到 8011）：

```bash
cd frontend
npm install
npm run dev             # http://localhost:5173
npm run build           # 产物输出到 frontend/dist
```

## Docker 部署（Linux）

多阶段构建：`node:20-alpine` 构建前端 → `python:3.12-slim` 运行时统一托管 API 与静态页面。

```bash
docker compose up -d --build
# 打开 http://<服务器>:8011
# 数据上传后写入 ./data，报告生成在 ./reports（挂载持久化）
```

单独使用已有 Dockerfile：

```bash
docker build -t ai-news-analyzer .
docker run -d -p 8011:8011 \
  -e NEWS_DATA_DIR=/app/data -e NEWS_REPORT_DIR=/app/reports \
  -v ./data:/app/data -v ./reports:/app/reports \
  ai-news-analyzer
```

### LLM 润色配置

在项目根目录创建 `llm_config.local.json`（不要提交真实 Key）：

```json
{
  "api_key": "YOUR_API_KEY_HERE",
  "base_url": "https://api.vectorengine.ai/v1",
  "model": "deepseek-v4-flash",
  "timeout": 60
}
```

未配置时分析自动回退为基础模式。

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 探活 |
| POST | `/api/analyze` | 提交新闻 JSON，返回分析结果 |
| GET | `/api/meta` | 服务信息、主题、目录、LLM 状态 |
| GET | `/api/reports` | 报告列表（md / pdf / html 简报 / 巡检，含分类与主题） |
| GET | `/api/reports/{name}` | 报告内容；html / pdf 直接流式返回 |
| GET | `/api/data-files` | 数据文件列表 |
| GET | `/api/data-files/{name}` | 数据文件元信息 + 预览 |
| POST | `/api/data-files` | 保存一份新闻数据 |
| POST | `/api/jobs` | 提交后台任务（`analyze` / `health`） |
| GET | `/api/jobs` · `/api/jobs/{id}` | 任务列表 / 状态轮询 |

## 说明与限制

- 仓库本身不含爬虫服务。`run.py --refresh` 与「数据源巡检」依赖抓取服务（开发机上位于
  `~/.openclaw/workspace/.tmp_<topic>_news_service/`）；新服务器未部署抓取服务时，前端会给出明确提示，
  此时请使用「上传数据 / 分析已有数据」的方式。
- 分析报告同时输出 Markdown 与 PDF；HTML 简报在 Web 环境已默认开启
  （`NEWS_GENERATE_HTML_BRIEF=1`）。
- 报告目录与数据目录可用 `NEWS_REPORT_DIR` / `NEWS_DATA_DIR` 覆盖。

## 项目结构

```
├── server.py               # FastAPI API + 静态前端托管
├── server_jobs.py          # 后台任务队列（分析 / 巡检）
├── services/               # 分析管线（去重 / 聚类 / 评分 / 板块 / 报告生成）
├── frontend/               # Vue 3 + Element Plus + ECharts 管理前端
├── data/                   # 接收的原始 JSON 数据
├── reports/                # 生成的分析报告
├── run.py / run_llm.py     # 命令行分析入口
├── Dockerfile / docker-compose.yml
└── requirements.txt
```