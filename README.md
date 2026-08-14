# AI News Analyzer

独立的新闻分析服务，与抓取模块（ai-news-service）完全解耦。

## 功能

- 三级去重（URL / 标题精确 / 标题相似度）
- 事件聚类（关键词重叠 + 24h时间窗口）
- 重大新闻评分（0-100分，多维度加权）
- 21个细分板块分类
- 综合报告生成（TOP10 + 板块摘要 + 地理热力 + 时间线 + 源质量）

## 使用方式

### 方式一：本地分析已有数据
```bash
cd /mnt/d/GitHub/ai-news-analyzer
/usr/bin/python3 run.py
```

### 方式二：启动 API 服务
```bash
cd /mnt/d/GitHub/ai-news-analyzer
/usr/bin/python3 server.py
# 监听 0.0.0.0:8011
```

抓取模块可以 POST 数据到分析服务：
```bash
curl -X POST http://analyzer-server:8011/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "news": [...],
    "sources": ["thsnews", "aerospace", ...],
    "date": "2026-04-16"
  }'
```

### 方式三：Python 调用
```python
from services.analyzer import NewsAnalyzer

analyzer = NewsAnalyzer()
results = analyzer.analyze(news_list, sources=source_names)
```

## 部署

```bash
docker build -t ai-news-analyzer .
docker run -d -p 8011:8011 -v ./data:/app/data -v ./reports:/app/reports ai-news-analyzer
```

## 项目结构
```
ai-news-analyzer/
├── services/
│   ├── analyzer.py           # 分析入口
│   ├── deduplicator.py       # 去重 + 事件聚类
│   ├── news_scorer.py        # 评分引擎
│   ├── board_classifier.py   # 板块分类
│   ├── report_generator.py   # 报告生成
│   └── coordinates.py        # 地点坐标映射
├── data/                     # 接收的原始JSON数据
├── reports/                  # 生成的分析报告
├── server.py                 # FastAPI API 服务
├── run.py                    # 本地分析入口
├── requirements.txt
└── README.md
```
