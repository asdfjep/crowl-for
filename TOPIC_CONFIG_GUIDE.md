# Topic 配置与周报类型改造指南

本文说明统一周报框架里 `configs/topics/*.json` 负责什么、改写一个专题类型时要改哪些字段，以及 topic 文件外还有哪些代码会影响不同类型周报。

## 运行入口

统一框架入口：

```powershell
cd C:\Users\orang\.openclaw\workspace\.tmp_unified_news_analyzer\unified-news-analyzer
python run.py --topic ai
python run.py --topic commercial_space
python run.py --topic display_polarizer
```

`--topic xxx` 会读取：

```text
configs/topics/xxx.json
```

## Topic 文件负责什么

每个 topic JSON 是一个专题的主要配置。现有文件：

```text
configs/topics/ai.json
configs/topics/commercial_space.json
configs/topics/display_polarizer.json
```

### 顶层字段

`label`

报告里显示的中文专题名，例如 `人工智能`、`商业航天`、`偏光板与显示行业`。

`report_prefix`

输出文件名前缀，例如：

```text
ai_weekly_report_...
commercial_space_weekly_report_...
display_polarizer_weekly_report_...
```

新增专题时必须改，避免覆盖别的专题报告。

`data_dir`

该专题读取的抓取 JSON 目录。路径相对统一分析器根目录解析。

示例：

```json
"data_dir": "../../.tmp_ai_news_analyzer/ai-news-analyzer/data"
```

如果换数据源、换爬虫输出目录，先改这里。

## filter 字段

`filter` 决定哪些新闻进入这个专题。统一分析器只用正文判断主题相关性：

```text
title + summary + content
```

注意：`source`、`category`、`tags` 不再参与 topic 放行，避免 `tags: ["AI"]` 这类脏元数据把无关新闻放进来。

### keywords

基础主题关键词。适合大多数专题。

没有配置 `core_keywords` / `weak_keywords` 时，新闻正文命中 `keywords` 才能进入专题。

适合：

- AI：`AI`、`large language model`、`LLM`、`大模型`
- 商业航天：`SpaceX`、`satellite`、`launch`、`火箭`、`卫星`

### core_keywords

强相关关键词。命中后可直接认为与专题相关。

适合需要防泛词误伤的专题，例如偏光板/显示：

- `偏光片`
- `OLED`
- `display panel`
- `MicroLED`
- `背光`

### weak_keywords

弱相关关键词，不能单独放行，必须同时命中公司、业务信号或技术信号。

适合容易误伤的泛词：

- `display`
- `screen`
- `TV`
- `AR`
- `VR`

例子：`display` 单独出现不够；如果同时有 `OLED`、`panel maker`、`LG Display`、`shipment` 才更可信。

### exclude_keywords

低价值或明显跑题的排除词。

例如：

- AI 里的 `AI wallpaper`、`prompt pack`
- 商业航天里的 `telescope`、`skywatching`
- 显示行业里的 `wallpaper`、`game trailer`

### companies

专题内公司/机构名单。

公司名不是绝对放行条件。统一逻辑里，公司名通常需要配合业务信号、弱关键词或技术信号。

例子：

- `深天马 + 营收/利润/财报` 可以进入偏光板/显示专题
- `Microsoft + AI` 可以进入 AI 专题
- 单纯 `Microsoft earnings` 若正文没有 AI 相关词，不应靠公司名进入 AI

### market_noise_keywords

股市行情噪声词。

命中这类词时，如果没有公司或业务信号，直接过滤。

例如：

- `ETF`
- `A股`
- `盘前`
- `涨停`
- `跌停`

### business_signal_keywords

商业/产业事件信号。

用于判断公司新闻、融资、合同、订单、营收、产能、出货等是否值得保留。

例子：

- AI：`funding`、`enterprise`、`API`、`product`
- 商业航天：`contract`、`payload`、`launch service`
- 显示行业：`shipment`、`capacity`、`revenue`、`产能`、`出货`

### tech_signal_keywords

技术相关信号。

用于让弱词、公司、业务信号更可信，也用于板块/评分辅助。

例子：

- AI：`LLM`、`inference`、`training`、`agent`
- 商业航天：`LEO`、`rocket`、`SAR`
- 显示行业：`OLED`、`MicroLED`、`backlight`

### non_topic_noise_keywords

强排除噪声词。当前主要用于偏光板/显示，防止泛半导体、AI 基建新闻因为出现在 LED/Display 网站而进入。

例子：

- `AI infrastructure`
- `chip incentive`
- `semiconductor industry`
- `数据中心`
- `芯片激励`

### business_signal_categories

保留兼容字段。它会参与最终放行判断，但不要依赖脏 `category` 来判断主题。

当前更推荐通过正文关键词、公司、业务信号、技术信号来控制相关性。

## sources 字段

`sources` 用于数据源健康监控，不用于 topic 放行。

如果新增/删除爬虫源，记得同步这里，否则报告里的 source health 会显示缺失或统计不完整。

## scoring 字段

`scoring` 调整重要性评分。

### high_weight

命中后加分的关键词。

适合放专题核心词、重要公司、重大事件词。

### down_weight

命中后减分的关键词。

适合低价值内容、消费噪声、泛娱乐内容。

### category_base_weight

按新闻原始 `category` 给基础权重。

注意：这是评分用，不是 topic 放行用。

### score_adjustments

专题可选加分项。目前偏光板/显示使用了这类补充分。

## boards 字段

`boards` 决定周报 A1/A2/A3... 板块分类。

### definitions

每个 board 的定义：

```json
"a4_compute": {
  "name": "A4 · 算力与芯片",
  "parent": "A4 · 算力与芯片",
  "keywords": ["算力", "GPU", "NVIDIA"]
}
```

`keywords` 命中后，新闻会被归到这个板块。

### order

报告展示顺序。

如果新增 board，必须加到 `order`，否则报告可能不按预期展示。

### fallback_mapping

当关键词分类不明显时，根据新闻 `category` 兜底映射到板块。

### default_board

完全无法分类时的默认板块。

通常是媒体评论或综合观察板块。

## Topic 文件外还有哪些负责不同周报

### run.py

位置：

```text
run.py
```

职责：

- 解析 `--topic`
- 找最新 `news_*.json`
- 调用 `NewsAnalyzer(topic=...)`

通常新增专题不用改它，只要加 `configs/topics/<topic>.json`。

### services/topic_config.py

职责：

- 按 topic 名加载 `configs/topics/<topic>.json`
- 解析 `data_dir`

新增专题一般不用改。

### services/analyzer.py

职责：

- 周期过滤
- topic 过滤
- 去重
- 聚类
- 评分
- 板块分类
- 业务关联标记
- source health
- 趋势检测
- 报告生成

最重要的是 `_filter_topic_news()`。

当前统一规则：

- topic 放行只看正文：`title + summary + content`
- `source/category/tags` 不参与 topic 放行
- `core_keywords/weak_keywords` 是增强规则，不是另一套分支语义

如果要改变所有专题的过滤语义，改这里。

如果只是改某个专题的口径，优先改 topic JSON。

### services/board_classifier.py

职责：

- 根据 topic JSON 里的 `boards` 给新闻分板块

通常只改 topic JSON 的 `boards` 即可。

除非要改变分类算法，才改这个文件。

### services/news_scorer.py

职责：

- 计算新闻/事件簇重要性分数
- 读取 topic JSON 的 `scoring`

如果只是给某专题加减分，改 topic JSON 的 `scoring`。

如果要改评分公式，改这个文件。

### services/report_generator.py

职责：

- 生成 Markdown 周报
- 生成 HTML 简报
- 生成 PDF（依赖 Selenium/Edge，缺依赖会跳过）
- 标题翻译
- 报告文件命名
- 报告结构：TOP 事件、板块排行、趋势、source health、JSON 附录等

不同专题都会经过这里。

这里有几个运行参数：

```powershell
$env:NEWS_DISABLE_MACHINE_TRANSLATION = "1"
$env:NEWS_TRANSLATION_TIMEOUT = "3"
$env:NEWS_TRANSLATION_MAX_FAILURES = "3"
```

含义：

- `NEWS_DISABLE_MACHINE_TRANSLATION=1`：完全关闭在线机器翻译
- `NEWS_TRANSLATION_TIMEOUT`：单条标题在线翻译超时秒数
- `NEWS_TRANSLATION_MAX_FAILURES`：连续失败几次后，本次运行自动熔断在线翻译

如果要改报告章节、标题格式、HTML 样式、PDF 逻辑，改这个文件。

### services/business_relevance.py

职责：

- 业务关联标记：高度关注/值得关注/宏观参考

注意：目前这是全局关键词表，不是 topic JSON 驱动。

如果不同专题需要不同业务关联规则，这是一个后续可优化点：把业务关联规则也放进 topic JSON。

### services/trend_detector.py

职责：

- 提取实体
- 保存每日 digest
- 检测趋势信号

如果趋势信号不准，改这里。

### services/deduplicator.py

职责：

- URL 去重
- 标题去重
- 相似标题去重
- 事件聚类

如果同一事件合并不好、重复太多或误合并，改这里。

## 新增一个专题要改哪些地方

最小步骤：

1. 新建 `configs/topics/<topic>.json`
2. 设置 `label`
3. 设置唯一的 `report_prefix`
4. 设置正确的 `data_dir`
5. 配置 `filter.keywords`
6. 配置 `sources`
7. 配置 `scoring`
8. 配置 `boards.definitions/order/fallback_mapping/default_board`
9. 运行：

```powershell
python run.py --topic <topic>
```

如果新专题需要更严格过滤：

- 增加 `core_keywords`
- 增加 `weak_keywords`
- 增加 `non_topic_noise_keywords`

如果新专题报告结构完全不同：

- 先尽量用 topic JSON 调 boards/scoring/filter
- 仍不够再改 `services/report_generator.py`

## 修改现有专题口径时优先改哪里

只改关键词相关性：

```text
configs/topics/<topic>.json -> filter
```

只改板块：

```text
configs/topics/<topic>.json -> boards
```

只改评分：

```text
configs/topics/<topic>.json -> scoring
```

改报告标题、章节、HTML、PDF、翻译：

```text
services/report_generator.py
```

改统一过滤算法：

```text
services/analyzer.py -> _filter_topic_news()
```

改业务关联标签：

```text
services/business_relevance.py
```

改去重/聚类：

```text
services/deduplicator.py
```

## 当前已知注意事项

1. `source/category/tags` 只用于展示、source health、统计，不用于 topic 放行。
2. 偏光板/显示这类泛词多的专题建议使用 `core_keywords + weak_keywords + non_topic_noise_keywords`。
3. AI、商业航天目前主要靠 `keywords`，如果误报仍多，也可以补 `core_keywords/weak_keywords`。
4. PDF 生成依赖 Selenium 和 Edge；缺依赖时会跳过，不影响 MD/HTML。
5. 在线翻译可能慢或超时，已有熔断参数；大批量跑报告时可设置较小超时。
6. `business_relevance.py` 仍是全局规则，不同专题混用时可能不够细，这是后续最值得抽到 topic JSON 的地方。

