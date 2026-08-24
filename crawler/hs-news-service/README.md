# HS News Service (Standalone Crawler)

独立新闻爬虫服务，从 `hs_news` 项目中剥离并重构。

## 📂 项目结构

```text
hs-news-service/
├── app/                  # 核心应用代码
│   ├── main.py           # (待开发) FastAPI 服务入口
│   └── scheduler.py      # 任务调度器 (已迁移)
├── sources/              # 爬虫源 (24 个)
│   ├── base.py           # 基础类
│   ├── playwright_base.py# 浏览器爬虫基类
│   ├── aerospace/        # 航空航天
│   ├── ai/               # 人工智能
│   └── finance/          # 财经
├── config/               # 配置文件
├── data/                 # 抓取的数据输出目录
├── Dockerfile            # 容器构建文件
└── requirements.txt      # Python 依赖
```

## 🚀 快速开始

### 1. 环境准备
确保已安装 Python 3.12+ 和 Playwright。

```bash
pip install -r requirements.txt
playwright install --with-deps chromium
```

### 2. 运行爬虫
```bash
python run.py
```

## 📦 部署到云服务器

```bash
docker build -t hs-news-service .
docker run -d -p 8000:8000 -v ./data:/app/data hs-news-service
```

## 📊 下一步计划
- [ ] 开发 FastAPI 管理后台 (API 配置抓取间隔)
- [ ] 实现内网数据推送模块 (Webhook)
- [ ] 数据库持久化 (SQLite)
