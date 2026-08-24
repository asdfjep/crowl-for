# HS-News 爬虫模块 — 现状报告 + 改进建议

> 生成时间：2026-04-16
> 项目路径：`/mnt/d/GitHub/hs-news-service/`

---

## 1. Python 文件清单与行数统计

| 文件 | 行数 | 说明 |
|------|------|------|
| `sources/enhanced.py` | 335 | 最大文件，含 CLS / DisplayDaily / SpaceChina 三个爬虫 |
| `sources/base.py` | 205 | 基类 `BaseCrawler`、数据模型 `NewsItem`、坐标字典 |
| `app/scheduler.py` | 197 | 调度器，加载源、并发抓取、保存报告 |
| `sources/conflict_events.py` | 193 | 冲突事件监测（含伪造数据回退） |
| `sources/financial_markets.py` | 207 | 金融市场（同花顺 API + RSS） |
| `sources/polarizer.py` | 145 | 偏光片/显示行业 RSS 爬虫 |
| `sources/aerospace.py` | 141 | 航空航天 RSS 爬虫 |
| `sources/ai_news.py` | 135 | AI 新闻 RSS 爬虫 |
| `sources/playwright_base.py` | 124 | Playwright 基类 `PlaywrightCrawler` |
| `sources/aibusiness.py` | 102 | AI Business HTML 解析 |
| `sources/ofweek_pw.py` | 102 | OFweek Playwright 爬虫 |
| `sources/lgdisplay.py` | 109 | LG Display HTML 解析 |
| `sources/thsnews.py` | 90 | 同花顺 API 爬虫 |
| `sources/spacenews_pw.py` | 86 | SpaceNews Playwright 爬虫 |
| `sources/space_com.py` | 82 | Space.com RSS 爬虫 |
| `sources/boe_pw.py` | 74 | 京东方 Playwright 爬虫 |
| `sources/nasa.py` | 64 | NASA RSS 爬虫 |
| `sources/deepmind.py` | 61 | DeepMind Blog RSS |
| `sources/kr36_pw.py` | 61 | 36Kr Playwright 爬虫 |
| `sources/leiphone.py` | 61 | 雷锋网 RSS |
| `sources/qbitai.py` | 61 | 量子位 RSS |
| `sources/the_decoder.py` | 61 | The Decoder RSS |
| `sources/eu_ai.py` | 60 | EU AI Act RSS |
| `sources/synced.py` | 60 | Synced RSS |
| `sources/venturebeat.py` | 60 | VentureBeat RSS |
| `config/settings.py` | 15 | 配置文件（未实际使用） |
| `run.py` | 28 | 入口脚本 |
| `app/__init__.py` | 0 | 空文件 |
| **合计** | **2891** | **28 个 .py 文件** |

---

## 2. 爬虫实现方式分析

### 2.1 RSS 爬虫（15 个）

| 爬虫 | 源 | RSS 地址 |
|------|-----|----------|
| `AerospaceCrawler` | TechCrunch Space, HackerNews | `techcrunch.com/category/space/feed/` |
| `AINewsCrawler` | TechCrunch AI, MIT Tech Review, HackerNews | 3 个 feed |
| `DeepMindCrawler` | DeepMind Blog | `deepmind.google/discover/blog/feed/` |
| `EUAICrawler` | EU Digital Strategy | `digital-strategy.ec.europa.eu/en/rss.xml` |
| `LeiphoneCrawler` | 雷锋网 | `www.leiphone.com/feed` |
| `NASACrawler` | NASA | `www.nasa.gov/feed/` |
| `PolarizerCrawler` | OLED-Info, Ars Technica, DisplayDaily | 3 个 feed |
| `QbitaiCrawler` | 量子位 | `www.qbitai.com/feed` |
| `SpaceComCrawler` | Space.com | `www.space.com/feeds/all` |
| `SyncedCrawler` | Synced Review | `syncedreview.com/feed/` |
| `TheDecoderCrawler` | The Decoder | `the-decoder.com/feed/` |
| `VentureBeatCrawler` | VentureBeat AI | `venturebeat.com/category/ai/feed/` |
| `CLSCrawler` (enhanced) | 新浪财经 API（非 RSS，JSONP API） | `feed.mix.sina.com.cn/api/roll/...` |
| `DisplayDailyCrawler` (enhanced) | OLED-Info, Ars Technica Gadgets | 2 个 feed |
| `SpaceChinaCrawler` (enhanced) | TechCrunch Space, HackerNews | 2 个 feed |
| `ConflictEventsCrawler` | The Verge, HackerNews | 2 个 feed |
| `FinancialMarketsCrawler` | HackerNews, TechCrunch | 2 个 feed |

**共性**：全部使用 `xml.etree.ElementTree` 手动解析 RSS，每个爬虫各自实现 `_parse_date()`（格式列表完全重复）。

### 2.2 HTML 解析爬虫（2 个）

| 爬虫 | 目标 | 方法 |
|------|------|------|
| `AIBusinessCrawler` | aibusiness.com | `aiohttp` + `BeautifulSoup`（article/post/card 选择器） |
| `LGDisplayCrawler` | lgdisplay.com | `aiohttp` + `BeautifulSoup`（多 URL 回退策略） |

### 2.3 Playwright 爬虫（4 个）

| 爬虫 | 目标 | 特殊处理 |
|------|------|----------|
| `OFweekCrawler` | display.ofweek.com | `wait_until='networkidle'` |
| `Kr36Crawler` | 36kr.com/newsflashes | `wait_until='networkidle'` |
| `BOECrawler` | boe.com 新闻中心 | `wait_until='networkidle'`，忽略 HTTPS 错误 |
| `SpaceNewsCrawler` | spacenews.com | `timeout=40000`，检测 Cloudflare 拦截（HTML < 5000） |

**共性**：继承 `PlaywrightCrawler`，每次 `fetch_news()` 都启动一个全新的浏览器实例（`async_playwright()` 在 `fetch_with_browser` 内），抓取完毕后关闭。

---

## 3. Scheduler 调度逻辑分析

文件：`app/scheduler.py`（197 行）

### 核心流程

```
run() / run_forever()
  └── load_sources()     → 硬编码 22 个爬虫实例到 self.sources 字典
  └── fetch_all_news()   → asyncio.gather 并发执行所有爬虫
       └── _safe_fetch() → 每个爬虫独立 try/except，45s 超时
  └── save_news()        → 生成 Markdown 报告 + 嵌入 JSON
```

### 详细分析

| 特性 | 状态 |
|------|------|
| 并发模型 | `asyncio.gather(*tasks)` — 所有源同时发起请求 |
| 超时控制 | 单个爬虫 45 秒 `asyncio.wait_for` 超时 |
| 错误隔离 | `_safe_fetch` 捕获所有异常，失败源返回 `[]` |
| 去重 | **无** — 不同源可能产出重复新闻（如多个源都抓取 HackerNews） |
| 数据持久化 | 写入 `data/report_YYYYMMDD_HHMM.md`，含 Markdown + JSON |
| 周期调度 | `run_forever(interval_minutes=60)`，简单 `while + asyncio.sleep` |
| 配置来源 | `config/settings.py` 中的 `SOURCES` **完全未被使用**，硬编码在 `load_sources()` |

### 发现的问题

1. **配置脱节**：`config/settings.py` 定义了 `SOURCES` 列表和 `DATA_DIR = "data/"`，但 `scheduler.py` 硬编码了全部爬虫，且 `DATA_DIR` 自己用 `Path(__file__).parent.parent / "data"` 重新定义。
2. **`aibusiness` 和 `lgdisplay` 已导入但未被注册**：scheduler.py 的 import 里没有引入这两个爬虫，`load_sources()` 中也没有注册它们。
3. **`spacenews_pw` 已导入但未注册**：同样未出现在 `load_sources()` 的 sources 字典中。

---

## 4. 问题检查

### 4.1 已确认的 Bug

| 严重度 | 位置 | 问题 |
|--------|------|------|
| **HIGH** | `sources/aerospace.py:102` | `_parse_rss` 中 `logger.error(f"RSS 解析失败 {source_url}: {e}")` — 变量 `source_url` **未定义**（参数名是 `source_name`），解析失败时会触发 `NameError` |
| **MEDIUM** | `sources/base.py:21-23` | `from services.severity import SeverityAssessor` — 模块不存在，`SeverityAssessor` 始终为 `None`，严重程度评估回退到 `'low'` |
| **MEDIUM** | `sources/conflict_events.py:42-44` | RSS 失败时调用 `_generate_events()` **生成伪造新闻数据**（"全球网络安全事件持续升级"等），这些数据不是真实抓取的 |
| **MEDIUM** | `sources/financial_markets.py:46-47` | 同理，数据太少时调用 `_generate_market_news()` 生成模拟市场新闻 |

### 4.2 硬编码路径 / 配置问题

| 位置 | 问题 |
|------|------|
| `sources/base.py:14` | `sys.path.insert(0, ...)` — 硬编码修改 Python 路径 |
| `run.py:10` | `sys.path.append(...)` — 同样硬编码路径 |
| `config/settings.py:15` | `DATA_DIR = "data/"` 相对路径，**实际未被任何模块使用** |
| `sources/base.py:36-62` | `LOCATION_COORDS` 硬编码约 40 个地点坐标字典，维护成本高 |
| `app/scheduler.py:41` | `DATA_DIR` 在模块级硬编码为 `Path(__file__).parent.parent / "data"` |

### 4.3 性能问题

| 问题 | 影响 | 位置 |
|------|------|------|
| **Playwright 每次启动新浏览器** | 4 个 Playwright 爬虫每次抓取都启动/关闭 Chromium（约 2-5 秒开销），串行执行时总耗时显著增加 | `playwright_base.py:50` — `async with async_playwright()` 在方法内部 |
| **重复的 RSS 源** | TechCrunch Space 被 `AerospaceCrawler` 和 `SpaceChinaCrawler` 重复抓取；HackerNews 被 4 个爬虫同时请求 | 多个文件 |
| **`_parse_date()` 完全重复** | 约 14 个文件各自复制了一份 `_parse_date()` 方法（相同 formats 列表），代码冗余 | 几乎每个 RSS 爬虫 |
| **无全局去重机制** | 跨源去重只在单个爬虫内部进行（按 title），scheduler 层没有统一去重 | `scheduler.py` |
| **固定 45s 超时对 Playwright 不够** | SpaceNews 已设 `timeout=40000`（40秒），接近 scheduler 层 45s 总超时，容易误杀 | `scheduler.py:85` + `spacenews_pw.py:23` |
| **logging.basicConfig 被调用 3 次** | `scheduler.py`、`base.py`、`enhanced.py` 都调用 `basicConfig`，只有第一个生效，其余被忽略 | 3 个文件 |

### 4.4 其他隐患

| 问题 | 位置 |
|------|------|
| `NewsItem` 的 `crawl_time = datetime.now()` 在 `__init__` 中硬编码，测试时不可控 | `sources/base.py:92` |
| `conflict_events.py` 的 URL 为伪造路径 `f"{self.base_url}/conflict/{i}"` | `sources/conflict_events.py:167` |
| `financial_markets.py` 的 URL 为伪造路径 `f"{self.base_url}/market/{i}"` | `sources/financial_markets.py:181` |
| 缺少 `requirements.txt` 或 `pyproject.toml` | 项目根目录 |
| `config/settings.py` 的 `SOURCES` 列表不完整（仅列了 9 个，实际有 22 个） | `config/settings.py` |
| `app/__init__.py` 为空文件 | — |

---

## 5. 改进建议（按优先级排序）

### 建议 1：修复 Bug — `source_url` 未定义 + 伪造数据移除 [P0 - 紧急]

**问题**：`aerospace.py:102` 引用了不存在的变量 `source_url`，会导致 `NameError`。`conflict_events.py` 和 `financial_markets.py` 在 RSS 失败时生成伪造新闻，会污染数据。

**方案**：
```python
# aerospace.py:102 — 修复
logger.error(f"RSS 解析失败 {source_name}: {e}")

# conflict_events.py / financial_markets.py — 移除 _generate_* 方法
# 改为记录 warning 并返回空列表，而不是生成假数据
```

### 建议 2：提取公共 `_parse_date()` 到基类 [P1 - 高]

**问题**：14 个文件各自复制了相同的 `_parse_date()` 方法。

**方案**：将 `_parse_date()` 上移到 `BaseCrawler`，所有子类直接使用 `self._parse_date()`。可减少约 200 行重复代码。

### 建议 3：Playwright 浏览器实例复用 [P1 - 高]

**问题**：每个 Playwright 爬虫每次 `fetch_news()` 都启动全新 Chromium，总延迟 8-20 秒。

**方案**：
- 在 `PlaywrightCrawler.__aenter__` 中启动浏览器，`__aexit__` 中关闭
- 或使用浏览器上下文池，多个 crawler 共享一个 Browser 实例
- 预期可将 4 个 Playwright 爬虫总耗时从 ~15s 降至 ~5s

### 建议 4：Scheduler 层统一去重 + 修复源注册 [P2 - 中]

**问题**：
1. 多个源重复抓取同一 RSS（HackerNews 被 4 个爬虫同时请求）
2. `aibusiness`、`lgdisplay`、`spacenews` 已存在但未注册到 scheduler
3. `config/settings.py` 与 scheduler 完全脱节

**方案**：
- `scheduler.py` 的 `fetch_all_news()` 返回后增加全局去重（按 `url` 或 `title`）
- 将 `config/settings.py` 改造为真实数据源配置（含爬虫类名、URL、分类）
- 或采用自动发现模式：`sources/` 目录下所有以 `_pw.py` 结尾和继承 `BaseCrawler` 的类自动注册

### 建议 5：添加 `requirements.txt` + 清理 logging [P2 - 中]

**问题**：
- 无依赖声明文件，环境配置困难
- 3 个模块各自调用 `logging.basicConfig`，配置混乱

**方案**：
- 创建 `requirements.txt`，至少包含：`aiohttp`, `beautifulsoup4`, `lxml`, `playwright`
- 删除 `base.py` 和 `enhanced.py` 中的 `logging.basicConfig`，只在 `scheduler.py` 或 `run.py` 中配置一次

---

## 附录：爬虫源分类统计

| 类别 | 爬虫数 | 实现方式 |
|------|--------|----------|
| **AI 资讯** | 8 | RSS 为主（TechCrunch AI, DeepMind, 雷锋网, 量子位, Synced, TheDecoder, VentureBeat, EU AI Act） |
| **航空航天** | 5 | RSS（NASA, Space.com）+ Playwright（SpaceNews）+ 多源 RSS 筛选 |
| **显示/偏光片** | 5 | RSS（OLED-Info, Ars, DisplayDaily）+ Playwright（OFweek, BOE）+ HTML（LG Display） |
| **金融/经济** | 3 | API（同花顺 ×2）+ RSS 筛选 |
| **综合/其他** | 1 | RSS 筛选（冲突事件，含伪造回退） |

**总计**：22 个已注册爬虫源，其中 RSS 15 个、HTML 解析 2 个、Playwright 4 个、API 1 个。
